package rnd.method.parser.call.graph.service;

import com.github.javaparser.JavaParser;
import com.github.javaparser.Range;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.PackageDeclaration;
import com.github.javaparser.ast.body.CallableDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.ast.expr.SimpleName;
import com.github.javaparser.ast.nodeTypes.NodeWithParameters;
import com.github.javaparser.ast.nodeTypes.NodeWithName;
import com.github.javaparser.ast.nodeTypes.NodeWithRange;
import com.github.javaparser.ast.nodeTypes.NodeWithSimpleName;
import com.github.javaparser.ast.visitor.VoidVisitorAdapter;
import com.github.javaparser.resolution.declarations.ResolvedConstructorDeclaration;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.symbolsolver.javaparsermodel.JavaParserFacade;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import lombok.extern.slf4j.Slf4j;
import rnd.method.parser.call.graph.artifact.ArtifactClassification;
import rnd.method.parser.call.graph.artifact.TestArtifactDetector;
import rnd.method.parser.call.graph.util.JavaParserContext;
import rnd.method.parser.call.graph.util.MethodParserUtil;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.model.MethodCall;
import rnd.method.parser.call.graph.util.AltConstructorDeclarationFqn;
import rnd.method.parser.call.graph.util.AltMethodDeclarationFqn;

import rnd.method.parser.call.graph.util.TestLinkerSignatureUtil;

import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.stream.Stream;

@Slf4j
public class CallGraphServiceImpl implements CallGraphService {

    private String repositoryUrl;
    private String repositoryLocation;
    private String repositoryName;
    private String commitHash;
    private CombinedTypeSolver typeSolver;
    private JavaParser parserWithSymbolResolver;
    private MethodMappingIndex methodMappingIndex;
    private ClassMappingIndex classMappingIndex;
    private String absoluteRepositoryPath;
    private TestArtifactDetector artifactDetector;
    private long maxCacheSizeMb = 256;

    public static CallGraphServiceImpl getInstance() {
        return new CallGraphServiceImpl();
    }

    public void logCacheStats() {
        if (classMappingIndex == null) {
            return;
        }
        log.info("Callgraph class hierarchy cache stats: {}", classMappingIndex.cacheStats());
    }

    @Override
    public synchronized void init(
            String projectName,
            String repositoryUrl,
            String repositoryPath,
            String commitHash,
            String methodMappingFile,
            String classMappingFile,
            String artifactConfigPath,
            boolean checkoutRepository,
            long maxCacheSizeMb) {
        if (parserWithSymbolResolver != null) {
            throw new IllegalStateException("CallGraphServiceImpl.init must be called exactly once");
        }
        if (checkoutRepository) {
            MethodParserUtil.prepareRepositoryForCommit(repositoryUrl, repositoryPath, commitHash);
        }
        String canonicalProjectName = requireProjectName(projectName);
        this.maxCacheSizeMb = Math.max(0, maxCacheSizeMb);
        this.repositoryUrl = repositoryUrl;
        this.repositoryLocation = repositoryPath;
        this.commitHash = commitHash;
        this.repositoryName = canonicalProjectName;
        this.classMappingIndex = ClassMappingIndex.load(classMappingFile, this.maxCacheSizeMb);
        this.methodMappingIndex = MethodMappingIndex.load(methodMappingFile, classMappingIndex);
        Path repoPath = Paths.get(repositoryPath);
        this.absoluteRepositoryPath = repoPath.toFile().getAbsolutePath();
        JavaParserContext parserContext = JavaParserContext.create(repoPath, commitHash, true);
        this.typeSolver = parserContext.typeSolver();
        this.parserWithSymbolResolver = parserContext.parser();
        this.artifactDetector = TestArtifactDetector.load(
                repoPath,
                this.repositoryName,
                artifactConfigPath == null || artifactConfigPath.isBlank() ? null : Paths.get(artifactConfigPath),
                parserContext.parser()
        );
    }

    private static String requireProjectName(String projectName) {
        if (projectName == null || projectName.isBlank()) {
            throw new IllegalArgumentException("Project name is required");
        }
        return projectName.trim();
    }

    @Override
    public List<MethodCall> findCallgraph(String file) {
        ensureInitialized();
        String absoluteFilePath = Paths.get(repositoryLocation, file).toFile().getAbsolutePath();
        try {
            var result = parserWithSymbolResolver.parse(Paths.get(absoluteFilePath));
            if (!result.isSuccessful()) {
                return List.of();
            }
            CompilationUnit cu = result.getResult().get();
            String packageName = cu.getPackageDeclaration()
                    .map(pd -> pd.getNameAsString())
                    .orElse(null);
            ArtifactClassification classification = artifactDetector.classify(Paths.get(absoluteFilePath), packageName, cu);
            if (classification.isResource()) {
                return List.of();
            }
            FileCallGraphContext context = new FileCallGraphContext(file);
            new CallGraphVisitor().visit(cu, context);
            return context.results();
        } catch (Exception e) {
            return List.of();
        }
    }

    private void ensureInitialized() {
        if (parserWithSymbolResolver == null) {
            throw new IllegalStateException("CallGraphServiceImpl.init must be called before findCallgraph");
        }
    }

    private MethodCall buildCallgraphForMethod(MethodCallTraversalState state, String fileRelative) {
        MethodDeclaration fromMd = state.fromMd();
        if (fromMd.getSignature().getName().contains("getFirstMillisecond")) {
            log.info(fromMd.getSignature().getName().toString());
        }

        state.calledMethods().forEach(method -> {
            if (state.lcbaMethodUrlSet().contains(method.getUrl())) {
                method.setLcba(1);
            }
        });

        int targetMethodStartLine = fromMd.getName().getBegin().get().line;
        String fromFqn = null;
        String fromFqs = null;
        String fromResolver = "javaparser";
        String fromTcTracerFqs = AltMethodDeclarationFqn.buildSimpleParamSignature(fromMd);
        try {
            ResolvedMethodDeclaration resolvedFromMd = fromMd.resolve();
            fromFqn = resolvedFromMd.getQualifiedName();
            fromFqs = resolvedFromMd.getQualifiedSignature();
        } catch (Exception e) {
            log.warn("Failed to parse from method FQN and FQS for {}", fromMd.getNameAsString());
        }
        // Fix anonymous class naming: resolver uses UUIDs or silently drops $N
        if (AltMethodDeclarationFqn.isInAnonymousClass(fromTcTracerFqs)) {
            String astQualified = AltMethodDeclarationFqn.buildQualifiedParamSignature(fromMd);
            fromFqn = stripParameters(astQualified);
            fromFqs = astQualified;
        } else {
            if (fromFqn != null && fromFqn.contains("Anonymous-")) {
                fromFqn = stripParameters(AltMethodDeclarationFqn.buildQualifiedParamSignature(fromMd));
            }
            if (fromFqs != null && fromFqs.contains("Anonymous-")) {
                fromFqs = AltMethodDeclarationFqn.buildQualifiedParamSignature(fromMd);
            }
        }
        if (fromFqn == null) {
            fromFqn = stripParameters(AltMethodDeclarationFqn.buildQualifiedParamSignature(fromMd));
            fromResolver = "heuristics";
        }
        if (fromFqs == null) {
            fromFqs = AltMethodDeclarationFqn.buildQualifiedParamSignature(fromMd);
            fromResolver = "heuristics";
        }
        Optional<PackageDeclaration> packageDeclaration = fromMd.findCompilationUnit().get().getPackageDeclaration();
        MethodCall methodCall = MethodCall.builder()
                .method(Method.builder()
                        .repositoryName(repositoryName)
                        .file(fileRelative)
                        .url(MethodParserUtil.toMethodUrl(repositoryUrl, commitHash, fileRelative, targetMethodStartLine))
                        .name(fromMd.getSignature().getName())
                        .pkg(packageDeclaration.map(NodeWithName::getNameAsString).orElse(null))
                        .fqn(fromFqn)
                        .fqs(fromFqs)
                        .tcTracerFqs(fromTcTracerFqs)
                        .testlinkerFqs(fromTcTracerFqs)
                        .testlinkerFqp(TestLinkerSignatureUtil.toParamTypeJson(fromFqs))
                        .resolver(fromResolver)
                        .startLine(targetMethodStartLine)
                        .endLine(fromMd.getEnd().get().line)
                        .hash(commitHash)
                        .expression("method")
                        .lcba(0)
                        .invocationLine(null)
                        .build())
                .fanMethods(state.calledMethods())
                .build();
        return methodCall;
    }

    private void collectCallNode(MethodCallTraversalState state, Node node) {
        boolean isAssertionMethod = node instanceof MethodCallExpr && AssertionLineFinder.isAssertionCall(((MethodCallExpr) node).getNameAsString());
        if (isAssertionMethod) {
            while (!state.lcbaCandidateMethod().isEmpty()) {
                Method precededMethod = state.lcbaCandidateMethod().pop();
                if (precededMethod.getInvocationLine() < node.getBegin().get().line) {
                    state.lcbaMethodUrlSet().add(precededMethod.getUrl());
                    state.lcbaCandidateMethod().clear();
                }
            }
            ((MethodCallExpr) node).getArguments().forEach(argNode -> {
                if (argNode instanceof MethodCallExpr || argNode instanceof ObjectCreationExpr) {
                    Method m = getMethodInfo(repositoryUrl, commitHash, argNode, typeSolver, absoluteRepositoryPath, repositoryName, methodMappingIndex);
                    if (m != null) {
                        state.lcbaMethodUrlSet().add(m.getUrl());
                    }
                }
            });
        }
        Method methodInfo = getMethodInfo(repositoryUrl, commitHash, node, typeSolver, absoluteRepositoryPath, repositoryName, methodMappingIndex);
        if (methodInfo != null) {
            state.calledMethods().add(methodInfo);
            state.lcbaCandidateMethod().add(methodInfo);
        }
    }

    private final class CallGraphVisitor extends VoidVisitorAdapter<FileCallGraphContext> {
        @Override
        public void visit(MethodDeclaration methodDeclaration, FileCallGraphContext context) {
            MethodCallTraversalState state = new MethodCallTraversalState(methodDeclaration);
            context.methodStack().push(state);
            super.visit(methodDeclaration, context);
            context.methodStack().pop();
            context.results().add(buildCallgraphForMethod(state, context.fileRelative()));
        }

        @Override
        public void visit(MethodCallExpr methodCallExpr, FileCallGraphContext context) {
            super.visit(methodCallExpr, context);
            context.currentMethod().ifPresent(state -> collectCallNode(state, methodCallExpr));
        }

        @Override
        public void visit(ObjectCreationExpr objectCreationExpr, FileCallGraphContext context) {
            super.visit(objectCreationExpr, context);
            context.currentMethod().ifPresent(state -> collectCallNode(state, objectCreationExpr));
        }
    }

    private record FileCallGraphContext(
            String fileRelative,
            Deque<MethodCallTraversalState> methodStack,
            List<MethodCall> results
    ) {
        FileCallGraphContext(String fileRelative) {
            this(fileRelative, new ArrayDeque<>(), new ArrayList<>());
        }

        Optional<MethodCallTraversalState> currentMethod() {
            return Optional.ofNullable(methodStack.peek());
        }
    }

    private record MethodCallTraversalState(
            MethodDeclaration fromMd,
            Set<String> lcbaMethodUrlSet,
            List<Method> calledMethods,
            Stack<Method> lcbaCandidateMethod
    ) {
        MethodCallTraversalState(MethodDeclaration fromMd) {
            this(fromMd, new HashSet<>(), new ArrayList<>(), new Stack<>());
        }
    }

    private static Method getMethodInfo(String repositoryUrl, String commitHash, Node callNode, CombinedTypeSolver typeSolver, String absoluteRepositoryPath, String repositoryName, MethodMappingIndex methodMappingIndex) {
        try {
            String methodName = null;
            String filePath = null;
            Integer invocationStartLine = null;
            Integer startLine = null;
            Integer endLine = null;
            String pkg = null;
            String fqs = null;
            String fqn = null;
            String fqnSimple = null;
            String expression = null;
            String resolvedUrl = null;
            String resolver = "javaparser";
            String testlinkerFqs = null;
            String testlinkerFqp = null;

            if (callNode instanceof MethodCallExpr) {
                MethodCallExpr methodCallExpr = (MethodCallExpr) callNode;
                invocationStartLine = callNode.getBegin()
                        .map(p -> p.line)
                        .orElse(null);

                Optional<ResolvedMethodDeclaration> resolvedDec;
                try {
                    resolvedDec = JavaParserFacade.get(typeSolver)
                            .solve(methodCallExpr, false)
                            .getDeclaration();
                } catch (Exception e) {
                    resolvedDec = Optional.empty();
                }
                Optional<MethodDeclaration> ast =
                        resolvedDec
                                .flatMap(ResolvedMethodDeclaration::toAst)
                                .filter(MethodDeclaration.class::isInstance)
                                .map(MethodDeclaration.class::cast);
                if (ast.isEmpty()) {
                    ast = findLocalMethodDeclaration(methodCallExpr);
                }

                expression = "method";

                if (ast.isPresent()) {
                    MethodDeclaration methodAst = ast.get();
                    methodName = methodAst.getSignature().getName();

                    filePath = methodAst
                            .findCompilationUnit()
                            .flatMap(CompilationUnit::getStorage)
                            .map(storage -> storage.getPath().toString())
                            .orElse(null);
                    if (filePath != null) {
                        startLine = methodAst
                                .getName()
                                .getBegin()
                                .map(p -> p.line)
                                .orElse(null);

                        endLine = methodAst
                                .getEnd()
                                .map(p -> p.line)
                                .orElse(null);

                        pkg = methodAst
                                .findCompilationUnit()
                                .flatMap(cu -> cu.getPackageDeclaration()
                                        .map(NodeWithName::getNameAsString))
                                .orElse(null);   // empty if default

                        fqnSimple = AltMethodDeclarationFqn.buildSimpleParamSignature(methodAst);
                        if (resolvedDec.isPresent()) {
                            try {
                                fqn = resolvedDec.get().getQualifiedName();
                                fqs = resolvedDec.get().getQualifiedSignature();
                            } catch (Exception ignored) {
                                resolver = "heuristics";
                            }
                        }
                        if (fqn == null) {
                            fqn = stripParameters(AltMethodDeclarationFqn.buildQualifiedParamSignature(methodAst));
                            resolver = "heuristics";
                        }
                        if (fqs == null) {
                            fqs = AltMethodDeclarationFqn.buildQualifiedParamSignature(methodAst);
                            resolver = "heuristics";
                        }
                    }
                } else {
                    resolver = "heuristics";
                    HeuristicMethodData heuristic = buildHeuristicMethodData(methodCallExpr);
                    Optional<MethodMappingEntry> mapped = methodMappingIndex.findBestMethod(heuristic, methodCallExpr, absoluteRepositoryPath);
                    if (mapped.isPresent()) {
                        MethodMappingEntry entry = mapped.get();
                        methodName = entry.name();
                        pkg = entry.pkg() != null ? entry.pkg() : heuristic.pkg();
                        expression = entry.expression() != null ? entry.expression() : expression;
                        fqn = entry.fqn() != null ? entry.fqn() : heuristic.fqn();
                        fqs = entry.fqs() != null ? entry.fqs() : heuristic.fqs();
                        fqnSimple = TestLinkerSignatureUtil.fromDeclaredFqs(entry.fqs() != null ? entry.fqs() : heuristic.fqs());
                        filePath = entry.file();
                        startLine = entry.startLine();
                        endLine = entry.endLine();
                        resolvedUrl = entry.url();
                    }
               /*     else {
                        methodName = heuristic.methodName();
                        pkg = heuristic.pkg();
                        fqn = heuristic.fqn();
                        fqs = heuristic.fqs();
                        fqnSimple = heuristic.fqsSimple();
                    }*/
                }


            } else if (callNode instanceof ObjectCreationExpr) {
                ObjectCreationExpr objectCreationExpr = (ObjectCreationExpr) callNode;
                invocationStartLine = callNode.getBegin()
                        .map(p -> p.line)
                        .orElse(null);
                Optional<ResolvedConstructorDeclaration> resolvedDec;
                try {
                    resolvedDec = JavaParserFacade.get(typeSolver)
                            .solve(objectCreationExpr)
                            .getDeclaration();
                } catch (Exception e) {
                    resolvedDec = Optional.empty();
                }
                Optional<ConstructorDeclaration> ast =
                        resolvedDec
                                .flatMap(ResolvedConstructorDeclaration::toAst)
                                .filter(ConstructorDeclaration.class::isInstance)
                                .map(ConstructorDeclaration.class::cast);

                expression = "constructor";
                if (ast.isPresent()) {
                    ConstructorDeclaration constructorAst = ast.get();
                    methodName = constructorAst.getSignature().getName();

                    filePath = constructorAst
                            .findCompilationUnit()
                            .flatMap(CompilationUnit::getStorage)
                            .map(storage -> storage.getPath().toString())
                            .orElse(null);
                    if (filePath != null) {

                        startLine = constructorAst
                                .getName()
                                .getBegin()
                                .map(p -> p.line)
                                .orElse(null);

                        endLine = constructorAst
                                .getEnd()
                                .map(p -> p.line)
                                .orElse(null);

                        pkg = constructorAst
                                .findCompilationUnit()
                                .flatMap(cu -> cu.getPackageDeclaration()
                                        .map(NodeWithName::getNameAsString))
                                .orElse(null);   // empty if default
                        fqnSimple = AltConstructorDeclarationFqn.buildSimpleParamSignature(constructorAst);
                        if (resolvedDec.isPresent()) {
                            try {
                                fqn = resolvedDec.get().getQualifiedName();
                                fqs = resolvedDec.get().getQualifiedSignature();
                            } catch (Exception ignored) {
                                resolver = "heuristics";
                            }
                        }
                        if (fqn == null) {
                            fqn = stripParameters(AltConstructorDeclarationFqn.buildQualifiedParamSignature(constructorAst));
                            resolver = "heuristics";
                        }
                        if (fqs == null) {
                            fqs = AltConstructorDeclarationFqn.buildQualifiedParamSignature(constructorAst);
                            resolver = "heuristics";
                        }
                    }
                } else {
                    resolver = "heuristics";
                    HeuristicMethodData heuristic = buildHeuristicConstructorData(objectCreationExpr);
                    Optional<MethodMappingEntry> mapped = methodMappingIndex.findBestConstructor(heuristic, objectCreationExpr, absoluteRepositoryPath);
                    if (mapped.isPresent()) {
                        MethodMappingEntry entry = mapped.get();
                        methodName = entry.name();
                        pkg = entry.pkg() != null ? entry.pkg() : heuristic.pkg();
                        expression = entry.expression() != null ? entry.expression() : expression;
                        fqn = entry.fqn() != null ? entry.fqn() : heuristic.fqn();
                        fqs = entry.fqs() != null ? entry.fqs() : heuristic.fqs();
                        fqnSimple = TestLinkerSignatureUtil.fromDeclaredFqs(entry.fqs() != null ? entry.fqs() : heuristic.fqs());
                        filePath = entry.file();
                        startLine = entry.startLine();
                        endLine = entry.endLine();
                        resolvedUrl = entry.url();
                    }
              /*      else {
                        methodName = heuristic.methodName();
                        pkg = heuristic.pkg();
                        fqn = heuristic.fqn();
                        fqs = heuristic.fqs();
                        fqnSimple = heuristic.fqsSimple();
                    }*/
                }
            }
            List<String> invocationParamTypes = getInvocationArgumentTypes(callNode);
            String testlinkerOwnerAndName = fqn != null ? fqn : stripParameters(fqs);
            if (testlinkerOwnerAndName != null && "javaparser".equals(resolver)) {
                // Symbol resolver succeeded: use actual call-site argument types.
                // This is the key TestLinker distinction — params reflect what was *passed*, not declared.
                testlinkerFqs = TestLinkerSignatureUtil.fromInvocationArgs(testlinkerOwnerAndName, invocationParamTypes);
                testlinkerFqp = TestLinkerSignatureUtil.toParamTypeJson(invocationParamTypes);
            } else {
                // Heuristics fallback: the matched method may have different arity/types than the actual
                // call site, so invocation arg types are unreliable. Use declared types instead.
                testlinkerFqs = fqnSimple != null ? fqnSimple : TestLinkerSignatureUtil.fromDeclaredFqs(fqs);
                testlinkerFqp = TestLinkerSignatureUtil.toParamTypeJson(fqs);
            }

            if (filePath != null || fqn != null || fqs != null || methodName != null) {
                String fileSuffix = filePath == null ? null : MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, filePath);
                return Method.builder()
                        .repositoryName(repositoryName)
                        .name(methodName)
                        .pkg(pkg)
                        .expression(expression)
                        .fqn(fqn)
                        .fqs(fqs)
                        .tcTracerFqs(fqnSimple)
                        .testlinkerFqs(testlinkerFqs)
                        .testlinkerFqp(testlinkerFqp)
                        .resolver(resolver)
                        .url(resolvedUrl != null ? resolvedUrl : (fileSuffix == null ? null : MethodParserUtil.toMethodUrl(repositoryUrl, commitHash, fileSuffix, startLine)))
                        .file(fileSuffix)
                        .startLine(startLine)
                        .endLine(endLine)
                        .hash(commitHash)
                        .lcba(0)
                        .invocationLine(invocationStartLine)
                        .build();
            }

        } catch (Exception e) {
            String name = callNode instanceof MethodCallExpr ? ((MethodCallExpr) callNode).getNameAsString() : "";
            name = callNode instanceof ObjectCreationExpr ? ((ObjectCreationExpr) callNode).getTypeAsString() : "";

//            log.error("Method resolve error {} {}", name, e.getMessage());
        }
        return null;
    }

    private static Optional<MethodDeclaration> findLocalMethodDeclaration(MethodCallExpr call) {
        int argCount = call.getArguments().size();
        return call.findCompilationUnit().stream()
                .flatMap(cu -> cu.findAll(MethodDeclaration.class).stream())
                .filter(method -> method.getNameAsString().equals(call.getNameAsString()))
                .filter(method -> method.getParameters().size() == argCount)
                .findFirst();
    }

    private static String stripParameters(String signature) {
        if (signature == null) {
            return null;
        }
        int open = signature.lastIndexOf('(');
        return open >= 0 ? signature.substring(0, open) : signature;
    }

    private static HeuristicMethodData buildHeuristicMethodData(MethodCallExpr call) {
        String methodName = call.getNameAsString();
        Optional<CompilationUnit> cu = call.findCompilationUnit();
        String pkg = cu
                .flatMap(CompilationUnit::getPackageDeclaration)
                .map(NodeWithName::getNameAsString)
                .orElse(null);

        String declaringType = guessDeclaringType(call, cu.orElse(null), pkg);
        String fqn = declaringType == null || declaringType.isBlank()
                ? methodName
                : declaringType + "." + methodName;
        String params = call.getArguments().stream()
                .map(arg -> guessArgumentType(arg, call, cu.orElse(null), pkg))
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
        String fqs = fqn + "(" + params + ")";

        return new HeuristicMethodData(methodName, pkg, declaringType, fqn, fqs);
    }

    private static HeuristicMethodData buildHeuristicConstructorData(ObjectCreationExpr call) {
        Optional<CompilationUnit> cu = call.findCompilationUnit();
        String pkg = cu
                .flatMap(CompilationUnit::getPackageDeclaration)
                .map(NodeWithName::getNameAsString)
                .orElse(null);

        String typeName = call.getType().getNameAsString();
        String declaringType = qualifySourceType(call.getTypeAsString(), cu.orElse(null), pkg);
        String fqn = declaringType == null || declaringType.isBlank()
                ? typeName + "." + typeName
                : declaringType + "." + typeName;
        String params = call.getArguments().stream()
                .map(arg -> guessArgumentType(arg, call, cu.orElse(null), pkg))
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
        String fqs = fqn + "(" + params + ")";

        return new HeuristicMethodData(typeName, pkg, declaringType, fqn, fqs);
    }

    private static String guessDeclaringType(MethodCallExpr call, CompilationUnit cu, String pkg) {
        Optional<Expression> scope = call.getScope();
        if (scope.isPresent()) {
            Expression scopeExpr = scope.get();
            String scopeType = guessScopeType(scopeExpr, call, cu, pkg);
            if (scopeType != null) {
                return scopeType;
            }
            String scopeText = scopeExpr.toString();
            String resolvedScope = qualifyTypeLikeName(scopeText, cu, pkg);
            if (resolvedScope != null) {
                return resolvedScope;
            }
            return "<UNKNOWN:" + scopeText + ">";
        }

        String staticImportOwner = findStaticImportOwner(call.getNameAsString(), cu);
        if (staticImportOwner != null) {
            return staticImportOwner;
        }

        return call.findAncestor(TypeDeclaration.class)
                .map(type -> qualifyTypeLikeName(type.getNameAsString(), cu, pkg))
                .orElse(pkg);
    }

    private static String guessScopeType(Expression scope, MethodCallExpr call, CompilationUnit cu, String pkg) {
        if (scope.isThisExpr()) {
            return call.findAncestor(TypeDeclaration.class)
                    .map(type -> qualifyTypeLikeName(type.getNameAsString(), cu, pkg))
                    .orElse(null);
        }

        if (scope.isFieldAccessExpr()) {
            String fieldName = scope.asFieldAccessExpr().getNameAsString();
            Expression fieldScope = scope.asFieldAccessExpr().getScope();
            if (fieldScope.isThisExpr()) {
                return findFieldType(fieldName, call, cu, pkg).orElse(null);
            }
        }

        if (scope.isNameExpr()) {
            String name = scope.asNameExpr().getNameAsString();
            Optional<String> localOrParameterType = findVariableType(name, call, cu, pkg);
            if (localOrParameterType.isPresent()) {
                return localOrParameterType.get();
            }
            return findFieldType(name, call, cu, pkg).orElse(null);
        }

        try {
            return scope.calculateResolvedType().describe();
        } catch (Exception ignored) {
            return null;
        }
    }

    private static Optional<String> findVariableType(String variableName, Node context, CompilationUnit cu, String pkg) {
        Optional<CallableDeclaration> callable = context.findAncestor(CallableDeclaration.class);
        if (callable.isEmpty()) {
            return Optional.empty();
        }

        if (callable.get() instanceof NodeWithParameters<?> withParameters) {
            Optional<String> parameterType = withParameters.getParameters().stream()
                    .filter(parameter -> parameter.getNameAsString().equals(variableName))
                    .map(parameter -> qualifySourceType(parameter.getType().asString(), cu, pkg))
                    .filter(Objects::nonNull)
                    .findFirst();
            if (parameterType.isPresent()) {
                return parameterType;
            }
        }

        int callLine = context.getBegin().map(position -> position.line).orElse(Integer.MAX_VALUE);
        return callable.get().findAll(VariableDeclarator.class).stream()
                .filter(variable -> variable.getNameAsString().equals(variableName))
                .filter(variable -> variable.getBegin().map(position -> position.line <= callLine).orElse(true))
                .map(variable -> qualifySourceType(variable.getType().asString(), cu, pkg))
                .filter(Objects::nonNull)
                .findFirst();
    }

    private static Optional<String> findFieldType(String fieldName, Node context, CompilationUnit cu, String pkg) {
        Optional<TypeDeclaration> typeDeclaration = context.findAncestor(TypeDeclaration.class);
        if (typeDeclaration.isEmpty()) {
            return Optional.empty();
        }

        return typeDeclaration.get().findAll(FieldDeclaration.class).stream()
                .flatMap(field -> field.getVariables().stream())
                .filter(variable -> variable.getNameAsString().equals(fieldName))
                .map(variable -> qualifySourceType(variable.getType().asString(), cu, pkg))
                .filter(Objects::nonNull)
                .findFirst();
    }

    private static String qualifySourceType(String sourceType, CompilationUnit cu, String pkg) {
        if (sourceType == null || sourceType.isBlank()) {
            return null;
        }

        String type = sourceType.trim();
        while (type.endsWith("[]")) {
            type = type.substring(0, type.length() - 2);
        }
        if (type.endsWith("...")) {
            type = type.substring(0, type.length() - 3);
        }
        int genericStart = type.indexOf('<');
        if (genericStart >= 0) {
            type = type.substring(0, genericStart);
        }

        return qualifyTypeLikeName(type, cu, pkg);
    }

    private static String qualifyTypeLikeName(String name, CompilationUnit cu, String pkg) {
        if (name == null || name.isBlank()) {
            return null;
        }

        String cleanName = name.replace(".class", "").trim();
        if (cleanName.contains("(") || cleanName.contains(")") || cleanName.contains(" ")) {
            return null;
        }
        if (!Character.isUpperCase(cleanName.charAt(0))) {
            return null;
        }

        if (cu != null) {
            for (ImportDeclaration imp : cu.getImports()) {
                if (!imp.isAsterisk() && !imp.isStatic()) {
                    String imported = imp.getNameAsString();
                    if (cleanName.contains(".")) {
                        String firstPart = cleanName.substring(0, cleanName.indexOf('.'));
                        if (imported.endsWith("." + firstPart)) {
                            return imported + cleanName.substring(cleanName.indexOf('.'));
                        }
                    }
                    if (imported.endsWith("." + cleanName)) {
                        return imported;
                    }
                }
            }
        }

        if (cleanName.contains(".")) {
            return cleanName;
        }

        return pkg == null || pkg.isBlank() ? cleanName : pkg + "." + cleanName;
    }

    private static String findStaticImportOwner(String methodName, CompilationUnit cu) {
        if (cu == null) {
            return null;
        }

        for (ImportDeclaration imp : cu.getImports()) {
            if (!imp.isStatic() || imp.isAsterisk()) {
                continue;
            }

            String imported = imp.getNameAsString();
            if (imported.endsWith("." + methodName)) {
                return imported.substring(0, imported.length() - methodName.length() - 1);
            }
        }

        return null;
    }

    private static List<String> getInvocationArgumentTypes(Node callNode) {
        Optional<CompilationUnit> cu = callNode.findCompilationUnit();
        String pkg = cu
                .flatMap(CompilationUnit::getPackageDeclaration)
                .map(NodeWithName::getNameAsString)
                .orElse(null);

        if (callNode instanceof MethodCallExpr methodCallExpr) {
            return methodCallExpr.getArguments().stream()
                    .map(arg -> guessArgumentType(arg, callNode, cu.orElse(null), pkg))
                    .toList();
        }
        if (callNode instanceof ObjectCreationExpr objectCreationExpr) {
            return objectCreationExpr.getArguments().stream()
                    .map(arg -> guessArgumentType(arg, callNode, cu.orElse(null), pkg))
                    .toList();
        }
        return List.of();
    }

    private static String guessArgumentType(Expression arg, Node context, CompilationUnit cu, String pkg) {
        try {
            return arg.calculateResolvedType().describe();
        } catch (Exception ignored) {
            if (arg.isStringLiteralExpr()) {
                return "java.lang.String";
            }
            if (arg.isIntegerLiteralExpr()) {
                return "int";
            }
            if (arg.isLongLiteralExpr()) {
                return "long";
            }
            if (arg.isDoubleLiteralExpr()) {
                return "double";
            }
            if (arg.isCharLiteralExpr()) {
                return "char";
            }
            if (arg.isBooleanLiteralExpr()) {
                return "boolean";
            }
            if (arg.isNullLiteralExpr()) {
                return "null";
            }
            if (arg.isObjectCreationExpr()) {
                String typeName = arg.asObjectCreationExpr().getTypeAsString();
                String qualified = qualifySourceType(typeName, cu, pkg);
                return qualified != null ? qualified : typeName;
            }
            if (arg.isNameExpr()) {
                String name = arg.asNameExpr().getNameAsString();
                Optional<String> localOrParameterType = findVariableType(name, context, cu, pkg);
                if (localOrParameterType.isPresent()) {
                    return localOrParameterType.get();
                }
                Optional<String> fieldType = findFieldType(name, context, cu, pkg);
                if (fieldType.isPresent()) {
                    return fieldType.get();
                }
            }
            if (arg.isFieldAccessExpr()) {
                String fieldName = arg.asFieldAccessExpr().getNameAsString();
                Optional<String> fieldType = findFieldType(fieldName, context, cu, pkg);
                if (fieldType.isPresent()) {
                    return fieldType.get();
                }
            }
            if (arg.isMethodCallExpr()) {
                return "<UNKNOWN_RETURN>";
            }
            return "<UNKNOWN>";
        }
    }

    private static String ownerFromMethod(String fqn, String fqs) {
        String ownerAndName = fqn != null ? fqn : stripParameters(fqs);
        if (ownerAndName == null || ownerAndName.isBlank()) {
            return null;
        }
        String normalized = eraseGenerics(ownerAndName);
        int dot = normalized.lastIndexOf('.');
        return dot > 0 ? normalized.substring(0, dot) : null;
    }

    private static int parameterCount(String signature) {
        if (signature == null) {
            return -1;
        }
        int open = signature.lastIndexOf('(');
        int close = signature.lastIndexOf(')');
        if (open < 0 || close < open) {
            return -1;
        }
        String params = signature.substring(open + 1, close).trim();
        if (params.isBlank()) {
            return 0;
        }
        return params.split("\\s*,\\s*").length;
    }

    private static String normalizeSignature(String signature) {
        if (signature == null) {
            return null;
        }
        return eraseGenerics(signature).replace("...", "[]").replace('$', '.');
    }

    private static String normalizeClassName(String name) {
        if (name == null || name.isBlank()) {
            return null;
        }
        String normalized = eraseGenerics(name)
                .replace(".class", "")
                .replace('$', '.')
                .trim();
        while (normalized.endsWith("[]")) {
            normalized = normalized.substring(0, normalized.length() - 2);
        }
        if (normalized.endsWith("...")) {
            normalized = normalized.substring(0, normalized.length() - 3);
        }
        if (normalized.contains("(") || normalized.contains(")") || normalized.contains(" ") || normalized.startsWith("<UNKNOWN:")) {
            return null;
        }
        return normalized.isBlank() ? null : normalized;
    }

    private static String eraseGenerics(String value) {
        if (value == null || value.indexOf('<') < 0) {
            return value;
        }
        StringBuilder result = new StringBuilder();
        int depth = 0;
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            if (ch == '<') {
                depth++;
            } else if (ch == '>') {
                if (depth > 0) {
                    depth--;
                }
            } else if (depth == 0) {
                result.append(ch);
            }
        }
        return result.toString();
    }

    private record HeuristicMethodData(
            String methodName,
            String pkg,
            String declaringType,
            String fqn,
            String fqs
    ) {
    }

    private record MethodMappingEntry(
            String repositoryName,
            String name,
            String expression,
            String pkg,
            String fqn,
            String fqs,
            String file,
            String url,
            Integer startLine,
            Integer endLine,
            String hash,
            String artifact,
            String ownerFqn,
            int index
    ) {
        int paramCount() {
            return parameterCount(fqs);
        }
    }

    private record ClassMappingEntry(
            String name,
            String fqn,
            String parentFqns,
            String file,
            Integer startLine,
            Integer endLine,
            String expression,
            int index
    ) {
    }

    private static final class ClassMappingIndex {
        private static final ClassMappingIndex EMPTY = new ClassMappingIndex(List.of(), 0);
        private final Map<String, ClassMappingEntry> byFqn;
        private final Map<String, String> aliases;
        private final Map<String, List<String>> parentsByChild;
        private final Map<String, List<String>> childrenByParent;
        private Cache<String, List<String>> searchOrderCache;
        private Cache<String, List<List<String>>> searchLevelsCache;

        private ClassMappingIndex(List<ClassMappingEntry> entries, long maxCacheSizeMb) {
            Map<String, ClassMappingEntry> fqnMap = new LinkedHashMap<>();
            Map<String, String> aliasMap = new HashMap<>();
            for (ClassMappingEntry entry : entries) {
                String normalized = normalizeClassName(entry.fqn());
                if (normalized == null) {
                    continue;
                }
                fqnMap.putIfAbsent(normalized, entry);
                addAlias(aliasMap, entry.fqn(), normalized);
                addAlias(aliasMap, normalized, normalized);
                addAlias(aliasMap, normalized.replace('$', '.'), normalized);
            }
            this.byFqn = fqnMap;
            this.aliases = aliasMap;

            Map<String, List<String>> parentMap = new LinkedHashMap<>();
            Map<String, List<String>> childMap = new LinkedHashMap<>();
            for (ClassMappingEntry entry : entries) {
                String child = normalize(entry.fqn());
                if (child == null || !fqnMap.containsKey(child)) {
                    continue;
                }
                for (String parentText : splitParentFqns(entry.parentFqns())) {
                    String parent = normalize(parentText);
                    if (parent == null || !fqnMap.containsKey(parent)) {
                        continue;
                    }
                    parentMap.computeIfAbsent(child, ignored -> new ArrayList<>()).add(parent);
                    childMap.computeIfAbsent(parent, ignored -> new ArrayList<>()).add(child);
                }
            }
            this.parentsByChild = parentMap;
            this.childrenByParent = childMap;
            configureCache(maxCacheSizeMb);
        }

        static ClassMappingIndex load(String classMappingFile) {
            return load(classMappingFile, 256);
        }

        static ClassMappingIndex load(String classMappingFile, long maxCacheSizeMb) {
            if (classMappingFile == null || classMappingFile.isBlank()) {
                throw new IllegalArgumentException("Class mapping file location not specified");
            }
            Path path = Paths.get(classMappingFile);
            if (!Files.exists(path)) {
                throw new IllegalArgumentException("Class mapping file does not exist: " + classMappingFile);
            }
            try {
                List<ClassMappingEntry> entries = readEntries(path);
                log.info("Loaded {} class mapping entries from {}", entries.size(), classMappingFile);
                return new ClassMappingIndex(entries, maxCacheSizeMb);
            } catch (IOException | RuntimeException e) {
                throw new IllegalArgumentException("Failed to load class mapping file " + classMappingFile + ": " + e.getMessage(), e);
            }
        }

        void configureCache(long maxCacheSizeMb) {
            if (maxCacheSizeMb <= 0) {
                this.searchOrderCache = null;
                this.searchLevelsCache = null;
                return;
            }
            long maxWeight = Math.max(1, maxCacheSizeMb) * 1024L * 1024L;
            long perCacheWeight = Math.max(1, maxWeight / 2);
            this.searchOrderCache = Caffeine.newBuilder()
                    .maximumWeight(perCacheWeight)
                    .weigher((String ignored, List<String> value) -> weighStringList(value))
                    .recordStats()
                    .build();
            this.searchLevelsCache = Caffeine.newBuilder()
                    .maximumWeight(perCacheWeight)
                    .weigher((String ignored, List<List<String>> value) -> weighNestedStringList(value))
                    .recordStats()
                    .build();
        }

        boolean contains(String fqn) {
            String normalized = normalize(fqn);
            return normalized != null && byFqn.containsKey(normalized);
        }

        String normalize(String name) {
            String normalized = normalizeClassName(name);
            if (normalized == null) {
                return null;
            }
            String alias = aliases.get(normalized);
            if (alias != null) {
                return alias;
            }
            alias = aliases.get(normalized.replace('$', '.'));
            if (alias != null) {
                return alias;
            }
            return byFqn.containsKey(normalized) ? normalized : null;
        }

        List<String> searchOrder(String ownerFqn) {
            String start = normalize(ownerFqn);
            if (start == null || !byFqn.containsKey(start)) {
                return List.of();
            }
            if (searchOrderCache != null) {
                return searchOrderCache.get(start, this::computeSearchOrder);
            }
            return computeSearchOrder(start);
        }

        private List<String> computeSearchOrder(String start) {
            LinkedHashSet<String> ordered = new LinkedHashSet<>();
            ordered.add(start);
            ordered.addAll(breadthFirst(start, childrenByParent));
            ordered.addAll(breadthFirst(start, parentsByChild));
            return List.copyOf(ordered);
        }

        List<List<String>> searchLevels(String ownerFqn) {
            String start = normalize(ownerFqn);
            if (start == null || !byFqn.containsKey(start)) {
                return List.of();
            }
            if (searchLevelsCache != null) {
                return searchLevelsCache.get(start, this::computeSearchLevels);
            }
            return computeSearchLevels(start);
        }

        private List<List<String>> computeSearchLevels(String start) {
            List<List<String>> levels = new ArrayList<>();
            levels.add(List.of(start));
            levels.addAll(breadthFirstLevels(start, childrenByParent));
            levels.addAll(breadthFirstLevels(start, parentsByChild));
            return levels.stream().map(List::copyOf).toList();
        }

        String cacheStats() {
            if (searchOrderCache == null && searchLevelsCache == null) {
                return "disabled";
            }
            String orderStats = searchOrderCache == null ? "disabled" : searchOrderCache.stats().toString();
            String levelsStats = searchLevelsCache == null ? "disabled" : searchLevelsCache.stats().toString();
            return "searchOrder=" + orderStats + ", searchLevels=" + levelsStats;
        }

        private static int weighStringList(List<String> value) {
            return Math.max(1, value.stream().filter(Objects::nonNull).mapToInt(text -> 40 + text.length() * 2).sum());
        }

        private static int weighNestedStringList(List<List<String>> value) {
            int total = 40;
            for (List<String> level : value) {
                total += 40 + weighStringList(level);
            }
            return Math.max(1, total);
        }

        private static List<String> breadthFirst(String start, Map<String, List<String>> adjacency) {
            List<String> result = new ArrayList<>();
            Set<String> seen = new HashSet<>();
            Deque<String> queue = new ArrayDeque<>();
            seen.add(start);
            queue.add(start);
            while (!queue.isEmpty()) {
                String current = queue.removeFirst();
                for (String next : adjacency.getOrDefault(current, List.of())) {
                    if (seen.add(next)) {
                        result.add(next);
                        queue.addLast(next);
                    }
                }
            }
            return result;
        }

        private static List<List<String>> breadthFirstLevels(String start, Map<String, List<String>> adjacency) {
            List<List<String>> levels = new ArrayList<>();
            Set<String> seen = new HashSet<>();
            List<String> currentLevel = List.of(start);
            seen.add(start);
            while (!currentLevel.isEmpty()) {
                List<String> nextLevel = new ArrayList<>();
                for (String current : currentLevel) {
                    for (String next : adjacency.getOrDefault(current, List.of())) {
                        if (seen.add(next)) {
                            nextLevel.add(next);
                        }
                    }
                }
                if (!nextLevel.isEmpty()) {
                    levels.add(nextLevel);
                }
                currentLevel = nextLevel;
            }
            return levels;
        }

        private static void addAlias(Map<String, String> aliases, String alias, String canonical) {
            String normalizedAlias = normalizeClassName(alias);
            if (normalizedAlias != null) {
                aliases.putIfAbsent(normalizedAlias, canonical);
            }
        }

        private static List<String> splitParentFqns(String parentFqns) {
            if (parentFqns == null || parentFqns.isBlank()) {
                return List.of();
            }
            return Arrays.stream(parentFqns.split("\\|"))
                    .map(String::trim)
                    .filter(text -> !text.isBlank())
                    .toList();
        }

        private static List<ClassMappingEntry> readEntries(Path path) throws IOException {
            List<ClassMappingEntry> entries = new ArrayList<>();
            try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String firstLine = reader.readLine();
                if (firstLine == null) {
                    return entries;
                }
                char delimiter = firstLine.indexOf('\t') >= 0 ? '\t' : ',';
                List<String> firstColumns = splitDelimitedLine(firstLine, delimiter);
                Map<String, Integer> header = toHeader(firstColumns);
                boolean hasHeader = header.containsKey("fqn") || header.containsKey("parent_fqns");
                if (!hasHeader) {
                    ClassMappingEntry firstEntry = fromColumns(firstColumns, Map.of(), false, entries.size());
                    if (firstEntry != null) {
                        entries.add(firstEntry);
                    }
                }
                String line;
                while ((line = reader.readLine()) != null) {
                    if (line.isBlank()) {
                        continue;
                    }
                    ClassMappingEntry entry = fromColumns(splitDelimitedLine(line, delimiter), header, hasHeader, entries.size());
                    if (entry != null) {
                        entries.add(entry);
                    }
                }
            }
            return entries;
        }

        private static ClassMappingEntry fromColumns(List<String> columns, Map<String, Integer> header, boolean hasHeader, int index) {
            String name;
            String fqn;
            String parentFqns;
            String file;
            Integer startLine;
            Integer endLine;
            String expression;
            if (hasHeader) {
                name = get(columns, header, "name");
                fqn = get(columns, header, "fqn");
                parentFqns = get(columns, header, "parent_fqns");
                file = get(columns, header, "file");
                startLine = parseInteger(get(columns, header, "start_line"));
                endLine = parseInteger(get(columns, header, "end_line"));
                expression = get(columns, header, "expression");
            } else {
                if (columns.size() < 13) {
                    return null;
                }
                name = clean(columns.get(1));
                fqn = clean(columns.get(2));
                file = clean(columns.get(4));
                startLine = parseInteger(clean(columns.get(6)));
                endLine = parseInteger(clean(columns.get(7)));
                expression = clean(columns.get(8));
                parentFqns = clean(columns.get(12));
            }
            return fqn == null ? null : new ClassMappingEntry(name, fqn, parentFqns, file, startLine, endLine, expression, index);
        }

        private static Map<String, Integer> toHeader(List<String> columns) {
            Map<String, Integer> header = new HashMap<>();
            for (int i = 0; i < columns.size(); i++) {
                String column = clean(columns.get(i));
                if (column != null) {
                    header.put(column.toLowerCase(Locale.ROOT), i);
                }
            }
            return header;
        }

        private static List<String> splitDelimitedLine(String line, char delimiter) {
            List<String> columns = new ArrayList<>();
            StringBuilder current = new StringBuilder();
            boolean quoted = false;
            for (int i = 0; i < line.length(); i++) {
                char ch = line.charAt(i);
                if (ch == '"') {
                    if (quoted && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                        current.append('"');
                        i++;
                    } else {
                        quoted = !quoted;
                    }
                } else if (ch == delimiter && !quoted) {
                    columns.add(clean(current.toString()));
                    current.setLength(0);
                } else {
                    current.append(ch);
                }
            }
            columns.add(clean(current.toString()));
            return columns;
        }

        private static String get(List<String> columns, Map<String, Integer> header, String name) {
            Integer index = header.get(name);
            if (index == null || index >= columns.size()) {
                return null;
            }
            return clean(columns.get(index));
        }

        private static String clean(String value) {
            if (value == null) {
                return null;
            }
            String cleaned = value.trim();
            return cleaned.isEmpty() ? null : cleaned;
        }

        private static Integer parseInteger(String value) {
            try {
                return value == null ? null : Integer.parseInt(value);
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
    }

    private static final class MethodMappingIndex {
        private static final MethodMappingIndex EMPTY = new MethodMappingIndex(List.of(), ClassMappingIndex.EMPTY);
        private final ClassMappingIndex classIndex;
        private final Map<String, List<MethodMappingEntry>> byOwnerExpressionAndName;

        private MethodMappingIndex(List<MethodMappingEntry> entries, ClassMappingIndex classIndex) {
            this.classIndex = classIndex;
            Map<String, List<MethodMappingEntry>> grouped = new HashMap<>();
            for (MethodMappingEntry entry : entries) {
                grouped.computeIfAbsent(key(entry.ownerFqn(), entry.expression(), entry.name()), ignored -> new ArrayList<>()).add(entry);
            }
            this.byOwnerExpressionAndName = grouped;
        }

        static MethodMappingIndex load(String methodMappingFile, ClassMappingIndex classIndex) {
            if (methodMappingFile == null || methodMappingFile.isBlank()) {
                throw new IllegalArgumentException("Method mapping file location not specified");
            }

            Path path = Paths.get(methodMappingFile);
            if (!Files.exists(path)) {
                throw new IllegalArgumentException("Method mapping file does not exist: " + methodMappingFile);
            }

            try {
                List<MethodMappingEntry> entries = readEntries(path, classIndex);
                log.info("Loaded {} CSV-bounded method mapping entries from {}", entries.size(), methodMappingFile);
                return new MethodMappingIndex(entries, classIndex);
            } catch (IOException | RuntimeException e) {
                throw new IllegalArgumentException("Failed to load method mapping file " + methodMappingFile + ": " + e.getMessage(), e);
            }
        }

        Optional<MethodMappingEntry> findBestMethod(HeuristicMethodData heuristic, MethodCallExpr call, String absoluteRepositoryPath) {
            int argCount = call.getArguments().size();
            String callerFile = call.findCompilationUnit()
                    .flatMap(CompilationUnit::getStorage)
                    .map(storage -> MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, storage.getPath().toString()))
                    .orElse(null);
            return findBest(heuristic, "method", argCount, callerFile);
        }

        Optional<MethodMappingEntry> findBestConstructor(HeuristicMethodData heuristic, ObjectCreationExpr call, String absoluteRepositoryPath) {
            int argCount = call.getArguments().size();
            String callerFile = call.findCompilationUnit()
                    .flatMap(CompilationUnit::getStorage)
                    .map(storage -> MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, storage.getPath().toString()))
                    .orElse(null);
            return findBest(heuristic, "constructor", argCount, callerFile);
        }

        private Optional<MethodMappingEntry> findBest(HeuristicMethodData heuristic, String expression, int argCount, String callerFile) {
            List<List<String>> ownerLevels = classIndex.searchLevels(heuristic.declaringType());
            if (ownerLevels.isEmpty()) {
                return Optional.empty();
            }

            for (List<String> ownerLevel : ownerLevels) {
                List<MethodMappingEntry> candidates = ownerLevel.stream()
                        .flatMap(owner -> byOwnerExpressionAndName.getOrDefault(key(owner, expression, heuristic.methodName()), List.of()).stream())
                        .toList();
                Optional<ScoredMethodMapping> best = candidates.stream()
                        .map(candidate -> new ScoredMethodMapping(candidate, score(candidate, heuristic, argCount, callerFile)))
                        .filter(scored -> scored.score() >= 0)
                        .max(Comparator
                                .comparingInt(ScoredMethodMapping::score)
                                .thenComparing(scored -> -scored.entry().index()));
                if (best.isPresent()) {
                    return best.map(ScoredMethodMapping::entry);
                }
            }
            return Optional.empty();
        }

        private static int score(MethodMappingEntry candidate, HeuristicMethodData heuristic, int argCount, String callerFile) {
            int score = 0;

            if (candidate.paramCount() >= 0 && candidate.paramCount() != argCount) {
                return -1;
            }
            if (Objects.equals(candidate.fqn(), heuristic.fqn())) {
                score += 300;
            }
            if (Objects.equals(normalizeSignature(candidate.fqs()), normalizeSignature(heuristic.fqs()))) {
                score += 200;
            }
            if (candidate.fqs() != null && stripParameters(candidate.fqs()).equals(heuristic.fqn())) {
                score += 100;
            }
            if (candidate.paramCount() == argCount) {
                score += 50;
            }
            if (callerFile != null && Objects.equals(candidate.file(), callerFile)) {
                score += 25;
            }

            return score;
        }

        private static List<MethodMappingEntry> readEntries(Path path, ClassMappingIndex classIndex) throws IOException {
            List<MethodMappingEntry> entries = new ArrayList<>();
            try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
                String firstLine = reader.readLine();
                if (firstLine == null) {
                    return entries;
                }

                char delimiter = firstLine.indexOf('\t') >= 0 ? '\t' : ',';
                List<String> firstColumns = splitDelimitedLine(firstLine, delimiter);
                Map<String, Integer> header = toHeader(firstColumns);
                boolean hasHeader = header.containsKey("name") || header.containsKey("expression");

                if (!hasHeader) {
                    MethodMappingEntry firstEntry = fromColumns(firstColumns, Map.of(), false, classIndex, entries.size());
                    if (firstEntry != null) {
                        entries.add(firstEntry);
                    }
                }

                String line;
                while ((line = reader.readLine()) != null) {
                    if (line.isBlank()) {
                        continue;
                    }
                    MethodMappingEntry entry = fromColumns(splitDelimitedLine(line, delimiter), header, hasHeader, classIndex, entries.size());
                    if (entry != null) {
                        entries.add(entry);
                    }
                }
            }
            return entries;
        }

        private static MethodMappingEntry fromColumns(List<String> columns, Map<String, Integer> header, boolean hasHeader, ClassMappingIndex classIndex, int index) {
            String repositoryName;
            String name;
            String expression;
            String pkg;
            String fqn;
            String fqs;
            String file;
            String url;
            Integer startLine;
            Integer endLine;
            String hash;
            String artifact;

            if (hasHeader) {
                repositoryName = get(columns, header, "project");
                name = get(columns, header, "name");
                expression = get(columns, header, "expression");
                pkg = get(columns, header, "pkg");
                fqn = get(columns, header, "fqn");
                fqs = get(columns, header, "fqs");
                file = get(columns, header, "file");
                url = get(columns, header, "url");
                startLine = parseInteger(get(columns, header, "start_line"));
                endLine = parseInteger(get(columns, header, "end_line"));
                hash = get(columns, header, "hash");
                artifact = get(columns, header, "artifact");
            } else {
                if (columns.size() < 8) {
                    return null;
                }
                repositoryName = clean(columns.get(0));
                expression = clean(columns.get(1));
                name = clean(columns.get(2));
                file = clean(columns.get(3));
                url = clean(columns.get(4));
                artifact = clean(columns.get(5));
                startLine = parseInteger(clean(columns.get(6)));
                endLine = parseInteger(clean(columns.get(7)));
                pkg = null;
                fqn = null;
                fqs = null;
                hash = null;
            }

            if (name == null || expression == null) {
                return null;
            }

            String ownerFqn = classIndex.normalize("constructor".equals(expression) ? fqn : ownerFromMethod(fqn, fqs));
            if (ownerFqn == null) {
                ownerFqn = classIndex.normalize(ownerFromMethod(fqn, fqs));
            }
            if (ownerFqn == null || !classIndex.contains(ownerFqn)) {
                return null;
            }

            return new MethodMappingEntry(repositoryName, name, expression, pkg, fqn, fqs, file, url, startLine, endLine, hash, artifact, ownerFqn, index);
        }

        private static Map<String, Integer> toHeader(List<String> columns) {
            Map<String, Integer> header = new HashMap<>();
            for (int i = 0; i < columns.size(); i++) {
                String column = clean(columns.get(i));
                if (column != null) {
                    header.put(column.toLowerCase(Locale.ROOT), i);
                }
            }
            return header;
        }

        private static List<String> splitDelimitedLine(String line, char delimiter) {
            List<String> columns = new ArrayList<>();
            StringBuilder current = new StringBuilder();
            boolean quoted = false;

            for (int i = 0; i < line.length(); i++) {
                char ch = line.charAt(i);
                if (ch == '"') {
                    if (quoted && i + 1 < line.length() && line.charAt(i + 1) == '"') {
                        current.append('"');
                        i++;
                    } else {
                        quoted = !quoted;
                    }
                } else if (ch == delimiter && !quoted) {
                    columns.add(clean(current.toString()));
                    current.setLength(0);
                } else {
                    current.append(ch);
                }
            }

            columns.add(clean(current.toString()));
            return columns;
        }

        private static String get(List<String> columns, Map<String, Integer> header, String name) {
            Integer index = header.get(name);
            if (index == null || index >= columns.size()) {
                return null;
            }
            return clean(columns.get(index));
        }

        private static String clean(String value) {
            if (value == null) {
                return null;
            }
            String cleaned = value.trim();
            return cleaned.isEmpty() ? null : cleaned;
        }

        private static Integer parseInteger(String value) {
            try {
                return value == null ? null : Integer.parseInt(value);
            } catch (NumberFormatException ignored) {
                return null;
            }
        }

        private static String key(String owner, String expression, String name) {
            return (owner == null ? "" : owner) + ":" + (expression == null ? "" : expression) + ":" + (name == null ? "" : name);
        }
    }

    private record ScoredMethodMapping(MethodMappingEntry entry, int score) {
    }
}
