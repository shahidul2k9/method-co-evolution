package rnd.method.parser.call.graph.service;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.Range;
import com.github.javaparser.StaticJavaParser;
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
import com.github.javaparser.resolution.declarations.ResolvedConstructorDeclaration;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.javaparsermodel.JavaParserFacade;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;
import lombok.extern.slf4j.Slf4j;
import rnd.method.parser.call.graph.util.MethodParserUtil;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.model.MethodCall;
import rnd.method.parser.call.graph.util.AltConstructorDeclarationFqn;
import rnd.method.parser.call.graph.util.AltMethodDeclarationFqn;
import rnd.method.parser.call.graph.util.TableUtil;
import rnd.method.parser.call.graph.util.TestLinkerSignatureUtil;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.stream.Stream;

@Slf4j
public class CallGraphServiceImpl implements CallGraphService {


    @Override
    public List<MethodCall> findFanOut(String repositoryUrl, String repositoryLocation, String commitHash, List<String> targetPaths, String fanInOutputFile, String fanOutOutputFile, String methodMappingFile) {

        MethodParserUtil.prepareRepositoryForCommit(repositoryUrl, repositoryLocation, commitHash);

        String repositoryName = MethodParserUtil.extractRepositoryName(repositoryUrl);
        MethodMappingIndex methodMappingIndex = MethodMappingIndex.load(methodMappingFile);
        CombinedTypeSolver typeSolver = new CombinedTypeSolver();
        typeSolver.add(new ReflectionTypeSolver(true));
        Path repositoryPath = Paths.get(repositoryLocation);
        String absoluteRepositoryPath = repositoryPath.toFile().getAbsolutePath();
        List<Path> allJavaSourceRoots = MethodParserUtil.findAllJavaSourceRootsFromPackageDeclarations(repositoryPath);

        for (Path path : allJavaSourceRoots) {
            typeSolver.add(new JavaParserTypeSolver(path.toFile()));
        }
        JavaSymbolSolver symbolSolver = new JavaSymbolSolver(typeSolver);
        ParserConfiguration config = new ParserConfiguration()
                .setSymbolResolver(symbolSolver);
        StaticJavaParser.setConfiguration(config);
        JavaParser parserWithSymbolResolver = new JavaParser(config);
        List<String> files = MethodParserUtil.scanJavaFiles(repositoryLocation, targetPaths);


        List<MethodCall> methodCallOutList = files.stream()
                .flatMap(file -> {
                    try {
                        var result = parserWithSymbolResolver.parse(Paths.get(file));
                        if (result.isSuccessful()) {
                            return result.getResult().get()
                                    .findAll(MethodDeclaration.class)
                                    .stream()
                                    .flatMap(fromMd -> {
                                        if (fromMd.getSignature().getName().contains("getFirstMillisecond")) {
                                            log.info(fromMd.getSignature().getName().toString());

                                        }

                                        Set<String> lcbaMetodUrlSet = new HashSet<>();

                                        List<Method> calledMethods = new ArrayList<>();
                                         /*For handling method just before assertion
                                         e.g. mutNum.increment
                                         https://github.com/apache/commons-lang/blob/425d8085cfcaab5a78bf0632f9ae77b7e9127cf8/src/test/java/org/apache/commons/lang3/mutable/MutableIntTest.java#L146
*/
                                        Stack<Method> lcbaCandidateMethod = new Stack<>();


                                        fromMd.walk(Node.TreeTraversal.POSTORDER, node -> {


                                            if (node instanceof MethodCallExpr || node instanceof ObjectCreationExpr) {

                                                boolean isAssertionMethod = node instanceof MethodCallExpr && AssertionLineFinder.isAssertionCall(((MethodCallExpr) node).getNameAsString());

                                                if (isAssertionMethod) {
                                                    while (!lcbaCandidateMethod.isEmpty()) {
                                                        Method preceededMethod = lcbaCandidateMethod.pop();
                                                        if (preceededMethod.getInvocationLine() < node.getBegin().get().line){
                                                            lcbaMetodUrlSet.add(preceededMethod.getUrl());
                                                            lcbaCandidateMethod.clear();
                                                        }
                                                    }

                                                    ((MethodCallExpr) node).getArguments().forEach(argNode -> {

                                                        if (argNode instanceof MethodCallExpr || argNode instanceof ObjectCreationExpr) {

                                                            Method m = getMethodInfo(
                                                                    repositoryUrl,
                                                                    commitHash,
                                                                    argNode,
                                                                    typeSolver,
                                                                    absoluteRepositoryPath,
                                                                    repositoryName,
                                                                    methodMappingIndex
                                                            );
                                                            if (m != null) {
                                                                lcbaMetodUrlSet.add(m.getUrl());
                                                            }
                                                        }

                                                    });
                                                }

                                                Method methodInfo = getMethodInfo(repositoryUrl, commitHash, node, typeSolver, absoluteRepositoryPath, repositoryName, methodMappingIndex);
                                                if (methodInfo != null) {
                                                    calledMethods.add(methodInfo);
                                                    lcbaCandidateMethod.add(methodInfo);
                                                }
                                            }
                                        });

                                        calledMethods.forEach(method -> {
                                            if (lcbaMetodUrlSet.contains(method.getUrl())) {
                                                method.setLcba(1);
                                            }
                                        });

                                        String targetMethodFileSuffix = MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, new File(file).getAbsolutePath());
                                        int targetMethodStartLine = fromMd.getName().getBegin().get().line;
                                        String fromFqn = null;
                                        String fromFqs = null;
                                        String fromResolver = "javaparser";
                                        String fromFqsAlt = AltMethodDeclarationFqn.getMethodFqnSimpleParams(fromMd);
                                        try {
                                            ResolvedMethodDeclaration resolvedFromMd = fromMd.resolve();
                                            fromFqn = resolvedFromMd.getQualifiedName();
                                            fromFqs = resolvedFromMd.getQualifiedSignature();
                                        } catch (Exception e) {
                                            log.warn("Failed to parse from method FQN and FQS for {}", fromMd.getNameAsString());
                                        }
                                        if (fromFqn == null) {
                                            fromFqn = stripParameters(AltMethodDeclarationFqn.getMethodFqnQualifiedParams(fromMd));
                                            fromResolver = "heuristics";
                                        }
                                        if (fromFqs == null) {
                                            fromFqs = AltMethodDeclarationFqn.getMethodFqnQualifiedParams(fromMd);
                                            fromResolver = "heuristics";
                                        }
                                        Optional<PackageDeclaration> packageDeclaration = fromMd.findCompilationUnit().get().getPackageDeclaration();
                                        MethodCall methodCall = MethodCall.builder()
                                                .method(Method.builder()
                                                        .repositoryName(repositoryName)
                                                        .file(targetMethodFileSuffix)
                                                        .url(MethodParserUtil.toMethodUrl(repositoryUrl, commitHash, targetMethodFileSuffix, targetMethodStartLine))
                                                        .name(fromMd.getSignature().getName())
                                                        .pkg(packageDeclaration.map(NodeWithName::getNameAsString).orElse(null))
                                                        .fqn(fromFqn)
                                                        .fqs(fromFqs)
                                                        .fqsAlt(fromFqsAlt)
                                                        .testlinkerFqs(TestLinkerSignatureUtil.toSignatureKey(fromFqs))
                                                        .testlinkerFqp(TestLinkerSignatureUtil.toFullyQualifiedParamArray(fromFqs))
                                                        .resolver(fromResolver)
                                                        .startLine(targetMethodStartLine)
                                                        .endLine(fromMd.getEnd().get().line)
                                                        .hash(commitHash)
                                                        .expression("method")
                                                        .lcba(0)
                                                        .invocationLine(null)
                                                        .build())
                                                .fanMethods(calledMethods)
                                                .build();

                                        return Stream.of(methodCall);
                                    });
                        } else {
//                             log.debug("Failed to parse file {}", file);
//                             log.debug("Problems {}", result.getProblems());
                            return Stream.empty();
                        }
                    } catch (Exception e) {
                        return Stream.empty(); // skip file completely
                    }
                })
                        .

                toList();

        File fanOutFile = Paths.get(fanOutOutputFile).toFile();
        TableUtil.toTable(methodCallOutList, fanOutFile.getAbsolutePath(), true);
        File fanInFile = Paths.get(fanInOutputFile).toFile();
        List<MethodCall> methodCallInList = MethodParserUtil.fanInFromFanOut(methodCallOutList);
        TableUtil.toTable(methodCallInList, fanInFile.getAbsolutePath(), false);
        return methodCallOutList;
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

                        fqnSimple = AltMethodDeclarationFqn.getMethodFqnSimpleParams(methodAst);
                        if (resolvedDec.isPresent()) {
                            try {
                                fqn = resolvedDec.get().getQualifiedName();
                                fqs = resolvedDec.get().getQualifiedSignature();
                            } catch (Exception ignored) {
                                resolver = "heuristics";
                            }
                        }
                        if (fqn == null) {
                            fqn = stripParameters(AltMethodDeclarationFqn.getMethodFqnQualifiedParams(methodAst));
                            resolver = "heuristics";
                        }
                        if (fqs == null) {
                            fqs = AltMethodDeclarationFqn.getMethodFqnQualifiedParams(methodAst);
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
                        fqnSimple = entry.fqsAlt() != null ? entry.fqsAlt() : heuristic.fqsSimple();
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
                        fqnSimple = AltConstructorDeclarationFqn.getMethodFqnSimpleParams(constructorAst);
                        if (resolvedDec.isPresent()) {
                            try {
                                fqn = resolvedDec.get().getQualifiedName();
                                fqs = resolvedDec.get().getQualifiedSignature();
                            } catch (Exception ignored) {
                                resolver = "heuristics";
                            }
                        }
                        if (fqn == null) {
                            fqn = stripParameters(AltConstructorDeclarationFqn.getMethodFqnQualifiedParams(constructorAst));
                            resolver = "heuristics";
                        }
                        if (fqs == null) {
                            fqs = AltConstructorDeclarationFqn.getMethodFqnQualifiedParams(constructorAst);
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
                        fqnSimple = entry.fqsAlt() != null ? entry.fqsAlt() : heuristic.fqsSimple();
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
            if (filePath != null || fqn != null || fqs != null || methodName != null) {
                String fileSuffix = filePath == null ? null : MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, filePath);
                return Method.builder()
                        .repositoryName(repositoryName)
                        .name(methodName)
                        .pkg(pkg)
                        .expression(expression)
                        .fqn(fqn)
                        .fqs(fqs)
                        .fqsAlt(fqnSimple)
                        .testlinkerFqs(TestLinkerSignatureUtil.toSignatureKey(fqs))
                        .testlinkerFqp(TestLinkerSignatureUtil.toFullyQualifiedParamArray(fqs))
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
                .map(CallGraphServiceImpl::guessArgumentType)
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
        String fqs = fqn + "(" + params + ")";

        return new HeuristicMethodData(methodName, pkg, fqn, fqs, fqs);
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
                .map(CallGraphServiceImpl::guessArgumentType)
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
        String fqs = fqn + "(" + params + ")";

        return new HeuristicMethodData(typeName, pkg, fqn, fqs, fqs);
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

    private static Optional<String> findVariableType(String variableName, MethodCallExpr call, CompilationUnit cu, String pkg) {
        Optional<CallableDeclaration> callable = call.findAncestor(CallableDeclaration.class);
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

        int callLine = call.getBegin().map(position -> position.line).orElse(Integer.MAX_VALUE);
        return callable.get().findAll(VariableDeclarator.class).stream()
                .filter(variable -> variable.getNameAsString().equals(variableName))
                .filter(variable -> variable.getBegin().map(position -> position.line <= callLine).orElse(true))
                .map(variable -> qualifySourceType(variable.getType().asString(), cu, pkg))
                .filter(Objects::nonNull)
                .findFirst();
    }

    private static Optional<String> findFieldType(String fieldName, MethodCallExpr call, CompilationUnit cu, String pkg) {
        Optional<TypeDeclaration> typeDeclaration = call.findAncestor(TypeDeclaration.class);
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
        if (cleanName.contains(".")) {
            return cleanName;
        }
        if (!Character.isUpperCase(cleanName.charAt(0))) {
            return null;
        }

        if (cu != null) {
            for (ImportDeclaration imp : cu.getImports()) {
                if (!imp.isAsterisk() && !imp.isStatic()) {
                    String imported = imp.getNameAsString();
                    if (imported.endsWith("." + cleanName)) {
                        return imported;
                    }
                }
            }
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

    private static String guessArgumentType(Expression arg) {
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
                return arg.asObjectCreationExpr().getTypeAsString();
            }
            if (arg.isMethodCallExpr()) {
                return "<UNKNOWN_RETURN>";
            }
            return "<UNKNOWN>";
        }
    }

    private record HeuristicMethodData(
            String methodName,
            String pkg,
            String fqn,
            String fqs,
            String fqsSimple
    ) {
    }

    private record MethodMappingEntry(
            String repositoryName,
            String name,
            String expression,
            String pkg,
            String fqn,
            String fqs,
            String fqsAlt,
            String file,
            String url,
            Integer startLine,
            Integer endLine,
            String hash,
            String artifact
    ) {
        int paramCount() {
            String signature = fqs != null ? fqs : fqsAlt;
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
    }

    private static final class MethodMappingIndex {
        private static final MethodMappingIndex EMPTY = new MethodMappingIndex(List.of());
        private final Map<String, List<MethodMappingEntry>> byExpressionAndName;

        private MethodMappingIndex(List<MethodMappingEntry> entries) {
            Map<String, List<MethodMappingEntry>> grouped = new HashMap<>();
            for (MethodMappingEntry entry : entries) {
                grouped.computeIfAbsent(key(entry.expression(), entry.name()), ignored -> new ArrayList<>()).add(entry);
            }
            this.byExpressionAndName = grouped;
        }

        static MethodMappingIndex load(String methodMappingFile) {
            if (methodMappingFile == null || methodMappingFile.isBlank()) {
                return EMPTY;
            }

            Path path = Paths.get(methodMappingFile);
            if (!Files.exists(path)) {
                log.warn("Method mapping file does not exist: {}", methodMappingFile);
                return EMPTY;
            }

            try {
                List<MethodMappingEntry> entries = readEntries(path);
                log.info("Loaded {} method mapping entries from {}", entries.size(), methodMappingFile);
                return new MethodMappingIndex(entries);
            } catch (IOException | RuntimeException e) {
                log.warn("Failed to load method mapping file {}: {}", methodMappingFile, e.getMessage());
                return EMPTY;
            }
        }

        Optional<MethodMappingEntry> findBestMethod(HeuristicMethodData heuristic, MethodCallExpr call, String absoluteRepositoryPath) {
            List<MethodMappingEntry> candidates = byExpressionAndName.getOrDefault(key("method", heuristic.methodName()), List.of());
            if (candidates.isEmpty()) {
                return Optional.empty();
            }
            if (candidates.size() == 1) {
                return Optional.of(candidates.get(0));
            }

            int argCount = call.getArguments().size();
            String callerFile = call.findCompilationUnit()
                    .flatMap(CompilationUnit::getStorage)
                    .map(storage -> MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, storage.getPath().toString()))
                    .orElse(null);

            return candidates.stream()
                    .map(candidate -> new ScoredMethodMapping(candidate, score(candidate, heuristic, argCount, callerFile)))
                    .filter(scored -> scored.score() > 0)
                    .max(Comparator.comparingInt(ScoredMethodMapping::score))
                    .map(ScoredMethodMapping::entry);
        }

        Optional<MethodMappingEntry> findBestConstructor(HeuristicMethodData heuristic, ObjectCreationExpr call, String absoluteRepositoryPath) {
            List<MethodMappingEntry> candidates = byExpressionAndName.getOrDefault(key("constructor", heuristic.methodName()), List.of());
            if (candidates.isEmpty()) {
                return Optional.empty();
            }
            if (candidates.size() == 1) {
                return Optional.of(candidates.get(0));
            }

            int argCount = call.getArguments().size();
            String callerFile = call.findCompilationUnit()
                    .flatMap(CompilationUnit::getStorage)
                    .map(storage -> MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, storage.getPath().toString()))
                    .orElse(null);

            return candidates.stream()
                    .map(candidate -> new ScoredMethodMapping(candidate, score(candidate, heuristic, argCount, callerFile)))
                    .filter(scored -> scored.score() > 0)
                    .max(Comparator.comparingInt(ScoredMethodMapping::score))
                    .map(ScoredMethodMapping::entry);
        }

        private static int score(MethodMappingEntry candidate, HeuristicMethodData heuristic, int argCount, String callerFile) {
            int score = 0;

            if (Objects.equals(candidate.fqs(), heuristic.fqs())) {
                score += 1000;
            }
            if (Objects.equals(candidate.fqsAlt(), heuristic.fqsSimple())) {
                score += 900;
            }
            if (Objects.equals(candidate.fqn(), heuristic.fqn())) {
                score += 700;
            }
            if (candidate.fqs() != null && candidate.fqs().startsWith(heuristic.fqn() + "(")) {
                score += 500;
            }
            if (candidate.fqsAlt() != null && candidate.fqsAlt().startsWith(heuristic.fqn() + "(")) {
                score += 450;
            }
            if (candidate.paramCount() == argCount) {
                score += 100;
            }
            if (callerFile != null && Objects.equals(candidate.file(), callerFile)) {
                score += 50;
            }

            return score;
        }

        private static List<MethodMappingEntry> readEntries(Path path) throws IOException {
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
                    MethodMappingEntry firstEntry = fromColumns(firstColumns, Map.of(), false);
                    if (firstEntry != null) {
                        entries.add(firstEntry);
                    }
                }

                String line;
                while ((line = reader.readLine()) != null) {
                    if (line.isBlank()) {
                        continue;
                    }
                    MethodMappingEntry entry = fromColumns(splitDelimitedLine(line, delimiter), header, hasHeader);
                    if (entry != null) {
                        entries.add(entry);
                    }
                }
            }
            return entries;
        }

        private static MethodMappingEntry fromColumns(List<String> columns, Map<String, Integer> header, boolean hasHeader) {
            String repositoryName;
            String name;
            String expression;
            String pkg;
            String fqn;
            String fqs;
            String fqsAlt;
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
                fqsAlt = get(columns, header, "fqs_alt");
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
                fqsAlt = null;
                hash = null;
            }

            if (name == null || expression == null) {
                return null;
            }

            return new MethodMappingEntry(repositoryName, name, expression, pkg, fqn, fqs, fqsAlt, file, url, startLine, endLine, hash, artifact);
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

        private static String key(String expression, String name) {
            return (expression == null ? "" : expression) + ":" + (name == null ? "" : name);
        }
    }

    private record ScoredMethodMapping(MethodMappingEntry entry, int score) {
    }
}
