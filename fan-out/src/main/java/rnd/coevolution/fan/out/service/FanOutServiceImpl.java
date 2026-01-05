package rnd.coevolution.fan.out.service;

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
import org.apache.commons.io.FileUtils;
import rnd.coevolution.fan.out.FanOutUtil;
import rnd.coevolution.fan.out.model.Fan;
import rnd.coevolution.fan.out.model.Method;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

@Slf4j
public class FanOutServiceImpl implements FanOutService {

    public FanOutServiceImpl() {

//        StaticJavaParser.setConfiguration(config);
//        StaticJavaParser.getConfiguration().setSymbolResolver(new JavaSymbolSolver(typeSolver));
    }

    @Override
    public List<Fan> findOut(String repositoryUrl, String repositoryLocation, String commitHash, List<String> targetPaths, String outputPath) {

        String repositoryName = Arrays.stream(repositoryUrl.split("/")).toList().getLast();
        CombinedTypeSolver typeSolver = new CombinedTypeSolver();
        typeSolver.add(new ReflectionTypeSolver(false));
        Path repositoryPath = Paths.get(repositoryLocation);
        String absoluteRepositoryPath = repositoryPath.toFile().getAbsolutePath();
        List<Path> allJavaSourceRoots = FanOutUtil.findAllJavaSourceRoots(repositoryPath);

        for (Path path : allJavaSourceRoots) {
            typeSolver.add(new JavaParserTypeSolver(path.toFile()));
        }
        JavaSymbolSolver symbolSolver = new JavaSymbolSolver(typeSolver);
        ParserConfiguration config = new ParserConfiguration()
                .setSymbolResolver(symbolSolver);
        JavaParser javaParser = new JavaParser(config);
        List<String> files = FanOutUtil.scanJavaFiles(repositoryLocation, targetPaths);


        List<Fan> fanList = files.stream()
                .flatMap(file -> {
                    try {
                        var result = javaParser.parse(FileUtils.readFileToString(new File(file), StandardCharsets.UTF_8));
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
                                                                        .orElse("<external>");

                                                                int startLine = ast
                                                                        .flatMap(NodeWithRange::getBegin)
                                                                        .map(p -> p.line)
                                                                        .orElse(-1);

                                                                int endLine = ast
                                                                        .flatMap(NodeWithRange::getEnd)
                                                                        .map(p -> p.line)
                                                                        .orElse(-1);

                                                                String fileSuffix = FanOutUtil.stripFilePrefix(absoluteRepositoryPath, filePath);
                                                                return Stream.of(
                                                                        Method.builder()
                                                                                .name(methodName)
                                                                                .url(FanOutUtil.toMethodUrl(repositoryUrl,commitHash , fileSuffix, startLine))
                                                                                .file(fileSuffix)
                                                                                .startLine(startLine)
                                                                                .endLine(endLine)
                                                                                .hash(commitHash)
                                                                                .build()
                                                                );

                                                            } catch (Exception e) {
                                                                log.error("Method resolve error {}", call.getNameAsString(), e);
                                                                return Stream.empty(); // unresolved or external
                                                            }
                                                        })
                                                        .toList();

                                        String targetMethodFileSuffix = FanOutUtil.stripFilePrefix(absoluteRepositoryPath, new File(file).getAbsolutePath());
                                        int targetMethodStartLine = method.getName().getBegin().get().line;
                                        Fan fan = Fan.builder()
                                                .method(Method.builder()
                                                        .file(targetMethodFileSuffix)
                                                        .url(FanOutUtil.toMethodUrl(repositoryUrl, commitHash, targetMethodFileSuffix, targetMethodStartLine))
                                                        .name(method.getSignature().getName())
                                                        .startLine(targetMethodStartLine)
                                                        .endLine(method.getName().getEnd().get().line)
                                                        .hash(commitHash)
                                                        .build())
                                                .fanMethods(calledMethods)
                                                .build();

                                        return Stream.of(fan);
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

        File fanOutFile = Paths.get(outputPath, "fan-out", repositoryName, repositoryName + "-" + commitHash + ".csv").toFile();
        FanOutUtil.toTable(fanList, fanOutFile.getAbsolutePath());
        File fanInFile = Paths.get(outputPath, "fan-in", repositoryName, repositoryName + "-" + commitHash + ".csv").toFile();
        List<Fan> fanInList = FanOutUtil.fanInFromFanOut(fanList);
        FanOutUtil.toTable(fanInList, fanInFile.getAbsolutePath());
        return fanList;
    }
}
