package rnd.method.parser.call.graph.service;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.PackageDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.ast.expr.SimpleName;
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
import rnd.method.parser.call.graph.MethodParserUtil;
import rnd.method.parser.call.graph.model.MethodCall;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.util.AltConstructorDeclarationFqn;
import rnd.method.parser.call.graph.util.AltMethodDeclarationFqn;
import rnd.method.parser.call.graph.util.TableUtil;

import java.io.File;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

@Slf4j
public class CallGraphServiceImpl implements CallGraphService {


    @Override
    public List<MethodCall> findFanOut(String repositoryUrl, String repositoryLocation, String commitHash, List<String> targetPaths, String fanInOutputFile, String fanOutOutputFile) {

        MethodParserUtil.prepareRepositoryForCommit(repositoryUrl, repositoryLocation, commitHash);

        String repositoryName = MethodParserUtil.extractRepositoryName(repositoryUrl);
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
//                                        testEmptyString
                                        if (fromMd.getSignature().getName().contains("testNulls")) {
                                            log.info(fromMd.getSignature().getName().toString());

                                        }

                                        List<Method> calledMethods = new ArrayList<>();

                                        fromMd.walk(com.github.javaparser.ast.Node.TreeTraversal.POSTORDER, node -> {

                                            if (node instanceof MethodCallExpr || node instanceof ObjectCreationExpr) {

                                                Method methodInfo = getMethodInfo(repositoryUrl, commitHash, node, typeSolver, absoluteRepositoryPath, repositoryName);
                                                if (methodInfo != null) {
                                                    calledMethods.add(methodInfo);
                                                }
                                                boolean isAssertionMethod = node instanceof MethodCallExpr && AssertionLineFinder.isAssertionCall(((MethodCallExpr) node).getNameAsString());
                                                if (!calledMethods.isEmpty()
                                                        && isAssertionMethod) {
                                                    calledMethods.getLast()
                                                            .setLcba(1);
                                                }
                                            }
                                        });

                                        String targetMethodFileSuffix = MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, new File(file).getAbsolutePath());
                                        int targetMethodStartLine = fromMd.getName().getBegin().get().line;
                                        String fromFqn = null;
                                        String fromFqs = null;
                                        try{
                                            ResolvedMethodDeclaration resolvedFromMd = fromMd.resolve();

                                            fromFqn  = resolvedFromMd.getQualifiedName();
                                            fromFqs  = resolvedFromMd.getQualifiedName();
                                        }catch(Exception e){
                                            log.warn("Failed to parse from method FQN and FQS for {}", fromMd.getNameAsString());
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
                                                        .fqsAlt(AltMethodDeclarationFqn.getMethodFqnSimpleParams(fromMd))
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
                .toList();

        File fanOutFile = Paths.get(fanOutOutputFile).toFile();
        TableUtil.toTable(methodCallOutList, fanOutFile.getAbsolutePath(), true);
        File fanInFile = Paths.get(fanInOutputFile).toFile();
        List<MethodCall> methodCallInList = MethodParserUtil.fanInFromFanOut(methodCallOutList);
        TableUtil.toTable(methodCallInList, fanInFile.getAbsolutePath(), false);
        return methodCallOutList;
    }

    private static Method getMethodInfo(String repositoryUrl, String commitHash, Node callNode, CombinedTypeSolver typeSolver, String absoluteRepositoryPath, String repositoryName) {
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


            if (callNode instanceof MethodCallExpr) {
                Optional<ResolvedMethodDeclaration> resolvedDec = JavaParserFacade.get(typeSolver)
                        .solve((MethodCallExpr) callNode)
                        .getDeclaration();
                Optional<MethodDeclaration> ast =
                        resolvedDec
                                .flatMap(ResolvedMethodDeclaration::toAst)
                                .filter(MethodDeclaration.class::isInstance)
                                .map(MethodDeclaration.class::cast);

                expression = "method";
                methodName = ast.get().getSignature().getName();

                filePath = ast
                        .flatMap(Node::findCompilationUnit)
                        .flatMap(CompilationUnit::getStorage)
                        .map(storage -> storage.getPath().toString())
                        .orElse(null);
                invocationStartLine = callNode.getBegin()
                        .map(p -> p.line)
                        .orElse(null);
                if (filePath != null) {
                    startLine = ast
                            .map(NodeWithSimpleName::getName)
                            .flatMap(SimpleName::getBegin)
                            .map(p -> p.line)
                            .orElse(null);

                    endLine = ast
                            .flatMap(NodeWithRange::getEnd)
                            .map(p -> p.line)
                            .orElse(null);

                    pkg = ast
                            .flatMap(Node::findCompilationUnit)
                            .flatMap(cu -> cu.getPackageDeclaration()
                                    .map(NodeWithName::getNameAsString))
                            .orElse(null);   // empty if default

                    fqs = resolvedDec.get().getQualifiedSignature();
                    fqn = resolvedDec.get().getQualifiedName();
                    fqnSimple = AltMethodDeclarationFqn.getMethodFqnSimpleParams(ast.get());
                }


            } else if (callNode instanceof ObjectCreationExpr) {
                Optional<ResolvedConstructorDeclaration> resolvedDec = JavaParserFacade.get(typeSolver)
                        .solve((ObjectCreationExpr) callNode)
                        .getDeclaration();
                Optional<ConstructorDeclaration> ast =
                        resolvedDec
                                .flatMap(ResolvedConstructorDeclaration::toAst)
                                .filter(ConstructorDeclaration.class::isInstance)
                                .map(ConstructorDeclaration.class::cast);

                expression = "constructor";
                methodName = ast.get().getSignature().getName();

                filePath = ast
                        .flatMap(Node::findCompilationUnit)
                        .flatMap(CompilationUnit::getStorage)
                        .map(storage -> storage.getPath().toString())
                        .orElse(null);
                invocationStartLine = callNode.getBegin()
                        .map(p -> p.line)
                        .orElse(null);
                if (filePath != null) {

                    startLine = ast
                            .map(NodeWithSimpleName::getName)
                            .flatMap(SimpleName::getBegin)
                            .map(p -> p.line)
                            .orElse(null);

                    endLine = ast
                            .flatMap(NodeWithRange::getEnd)
                            .map(p -> p.line)
                            .orElse(null);

                    pkg = ast
                            .flatMap(Node::findCompilationUnit)
                            .flatMap(cu -> cu.getPackageDeclaration()
                                    .map(NodeWithName::getNameAsString))
                            .orElse(null);   // empty if default
                    fqs = resolvedDec.get().getQualifiedSignature();
                    fqn = resolvedDec.get().getQualifiedName();
                    fqnSimple = AltConstructorDeclarationFqn.getMethodFqnSimpleParams(ast.get());
                }
            }
            if (filePath != null) {
                String fileSuffix = MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, filePath);
                return Method.builder()
                        .repositoryName(repositoryName)
                        .name(methodName)
                        .pkg(pkg)
                        .expression(expression)
                        .fqn(fqn)
                        .fqs(fqs)
                        .fqsAlt(fqnSimple)
                        .url(MethodParserUtil.toMethodUrl(repositoryUrl, commitHash, fileSuffix, startLine))
                        .file(fileSuffix)
                        .startLine(startLine)
                        .endLine(endLine)
                        .hash(commitHash)
                        .lcba(0)
                        .invocationLine(invocationStartLine)
                        .build();
            }

        } catch (Exception e) {
//                                                    log.error("Method resolve error {}", callNode.getNameAsString());
        }
        return null;
    }
}
