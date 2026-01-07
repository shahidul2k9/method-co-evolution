package rnd.method.parser.call.graph.service;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.nodeTypes.NodeWithRange;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.resolution.model.SymbolReference;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.javaparsermodel.JavaParserFacade;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;
import lombok.extern.slf4j.Slf4j;
import rnd.method.parser.call.graph.MethodParserUtil;
import rnd.method.parser.call.graph.model.MethodCall;
import rnd.method.parser.call.graph.model.Method;

import java.io.File;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

@Slf4j
public class CallGraphServiceImpl implements CallGraphService {


    @Override
    public List<MethodCall> findFanOut(String repositoryUrl, String repositoryLocation, String commitHash, List<String> targetPaths, String fanInOutputFile, String fanOutOutputFile) {

        String repositoryName = Arrays.stream(repositoryUrl.split("/")).toList().getLast();
        CombinedTypeSolver typeSolver = new CombinedTypeSolver();
        typeSolver.add(new ReflectionTypeSolver(false));
        Path repositoryPath = Paths.get(repositoryLocation);
        String absoluteRepositoryPath = repositoryPath.toFile().getAbsolutePath();
        List<Path> allJavaSourceRoots = MethodParserUtil.findAllJavaSourceRoots(repositoryPath);

        for (Path path : allJavaSourceRoots) {
            typeSolver.add(new JavaParserTypeSolver(path.toFile()));
        }
        JavaSymbolSolver symbolSolver = new JavaSymbolSolver(typeSolver);
        ParserConfiguration config = new ParserConfiguration()
                .setSymbolResolver(symbolSolver);
        JavaParser javaParser = new JavaParser(config);
        List<String> files = MethodParserUtil.scanJavaFiles(repositoryLocation, targetPaths);


        List<MethodCall> methodCallOutList = files.stream()
                .flatMap(file -> {
                    try {
                        var result = javaParser.parse(Paths.get(file));
                        if (result.isSuccessful()) {
                            return result.getResult().get()
                                    .findAll(MethodDeclaration.class)
                                    .stream()
                                    .flatMap(method -> {

                                        List<Method> calledMethods =
                                                method.findAll(MethodCallExpr.class).stream()
                                                        .flatMap(call -> {
                                                            try {
                                                                SymbolReference<ResolvedMethodDeclaration> solution = JavaParserFacade.get(typeSolver)
                                                                        .solve(call);

                                                                ResolvedMethodDeclaration resolved = call.resolve();

                                                                Optional<MethodDeclaration> ast = resolved.toAst()
                                                                        .filter(MethodDeclaration.class::isInstance)
                                                                        .map(MethodDeclaration.class::cast);

                                                                String methodName = resolved.getName();

                                                                String filePath = ast
                                                                        .flatMap(md -> md.findCompilationUnit())
                                                                        .flatMap(cu -> cu.getStorage())
                                                                        .map(storage -> storage.getPath().toString())
                                                                        .orElse(null);

                                                                if (filePath != null) {

                                                                    int startLine = ast
                                                                            .flatMap(NodeWithRange::getBegin)
                                                                            .map(p -> p.line)
                                                                            .orElse(-1);

                                                                    int endLine = ast
                                                                            .flatMap(NodeWithRange::getEnd)
                                                                            .map(p -> p.line)
                                                                            .orElse(-1);

                                                                    String fileSuffix = MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, filePath);
                                                                    return Stream.of(
                                                                            Method.builder()
                                                                                    .name(methodName)
                                                                                    .url(MethodParserUtil.toMethodUrl(repositoryUrl, commitHash, fileSuffix, startLine))
                                                                                    .file(fileSuffix)
                                                                                    .startLine(startLine)
                                                                                    .endLine(endLine)
                                                                                    .hash(commitHash)
                                                                                    .build()
                                                                    );
                                                                } else {
                                                                    return Stream.empty();
                                                                }

                                                            } catch (Exception e) {
                                                                log.error("Method resolve error {}", call.getNameAsString(), e);
                                                                return Stream.empty(); // unresolved or external
                                                            }
                                                        })
                                                        .toList();

                                        String targetMethodFileSuffix = MethodParserUtil.stripFilePrefix(absoluteRepositoryPath, new File(file).getAbsolutePath());
                                        int targetMethodStartLine = method.getName().getBegin().get().line;
                                        MethodCall methodCall = MethodCall.builder()
                                                .method(Method.builder()
                                                        .file(targetMethodFileSuffix)
                                                        .url(MethodParserUtil.toMethodUrl(repositoryUrl, commitHash, targetMethodFileSuffix, targetMethodStartLine))
                                                        .name(method.getSignature().getName())
                                                        .startLine(targetMethodStartLine)
                                                        .endLine(method.getEnd().get().line)
                                                        .hash(commitHash)
                                                        .build())
                                                .fanMethods(calledMethods)
                                                .build();

                                        return Stream.of(methodCall);
                                    });
                        } else {
                            log.error("Failed to parse file {}", file);
                            log.error("Problems {}", result.getProblems());
                            return Stream.empty();
                        }
                    } catch (Exception e) {
                        return Stream.empty(); // skip file completely
                    }
                })
                .toList();

        File fanOutFile = Paths.get(fanOutOutputFile).toFile();
        MethodParserUtil.toTable(methodCallOutList, fanOutFile.getAbsolutePath(), true);
        File fanInFile = Paths.get(fanInOutputFile).toFile();
        List<MethodCall> methodCallInList = MethodParserUtil.fanInFromFanOut(methodCallOutList);
        MethodParserUtil.toTable(methodCallInList, fanInFile.getAbsolutePath(), false);
        return methodCallOutList;
    }
}
