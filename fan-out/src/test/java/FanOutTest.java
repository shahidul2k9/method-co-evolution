import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.nodeTypes.NodeWithRange;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.resolution.model.SymbolReference;
import com.github.javaparser.symbolsolver.javaparsermodel.JavaParserFacade;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import lombok.extern.slf4j.Slf4j;
import org.jspecify.annotations.NonNull;
import org.junit.Assert;
import org.junit.Test;
import org.junit.jupiter.api.*;
import rnd.coevolution.fan.out.FanOutUtil;
import rnd.coevolution.fan.out.model.Fan;
import rnd.coevolution.fan.out.service.FanOutServiceImpl;

import java.io.File;
import java.io.FileNotFoundException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

/**
 * @author Shahidul Islam
 * @since 2025-12-23
 */
@Slf4j
public class FanOutTest {


    //TODO:
//    @TestFactory
//    public DynamicNode randomPathTest() {
//
//
//    }

    @Test
    public void testFanOut() throws FileNotFoundException {
        String repositoryDirectory = System.getenv().getOrDefault("REPOSITORY_DIRECTORY", "../../repository");
        Path path = Paths.get(repositoryDirectory, "checkstyle");
    }

    @Test
    public void testsymbolResolverTest() throws FileNotFoundException {
        JavaParser javaParser = new JavaParser();
        String repositoryDirectory = Paths.get(System.getenv().getOrDefault("REPOSITORY_DIRECTORY", "../../repository"), "checkstyle").toString();

        ParseResult<CompilationUnit> cu = javaParser.parse(new File(repositoryDirectory + "/src/main/java/com/puppycrawl/tools/checkstyle/AuditEventDefaultFormatter.java"));
        MethodDeclaration md = cu.getResult()
                .get()
                .findAll(MethodDeclaration.class)
                .stream()
                .filter(m -> m.getNameAsString().contains("getCheckShortName"))
                .findFirst()
                .get();
        MethodCallExpr mce = md.findAll(MethodCallExpr.class)
                .stream().filter(mc -> mc.getNameAsString().contains("getSourceName"))
                .findFirst()
                .get();
//        JavaParserTypeSolver solver = new JavaParserTypeSolver(new File(repositoryDirectory + "/Users/shahidul/dev/project/repository/checkstyle/src/main/java/com/puppycrawl/tools/checkstyle/api/AuditEvent.java"));
        List<Path> allJavaSourceRoots = FanOutUtil.findAllJavaSourceRoots(Paths.get(repositoryDirectory));
        CombinedTypeSolver solver = new CombinedTypeSolver();

        for (Path path : allJavaSourceRoots) {
            solver.add(new JavaParserTypeSolver(path.toFile()));
        }
        //JavaParserTypeSolver solver = new JavaParserTypeSolver(new File(repositoryDirectory + "/src/main/java"));
        SymbolReference<ResolvedMethodDeclaration> solve = JavaParserFacade.get(solver)
                .solve(mce);
        ResolvedMethodDeclaration resolved = solve.getCorrespondingDeclaration();


        Optional<MethodDeclaration> ast = resolved.toAst()
                .filter(MethodDeclaration.class::isInstance)
                .map(MethodDeclaration.class::cast);

        String methodName = resolved.getName();

        String filePath = ast
                .flatMap(m -> m.findCompilationUnit())
                .flatMap(c -> c.getStorage())
                .map(storage -> storage.getPath().toString())
                .map(file -> FanOutUtil.stripFilePrefix(repositoryDirectory, file))
                .orElse("<external>");

        int startLine = ast
                .flatMap(NodeWithRange::getBegin)
                .map(p -> p.line)
                .orElse(-1);
        Assert.assertEquals(149, startLine);
        Assert.assertEquals("src/main/java/com/puppycrawl/tools/checkstyle/api/AuditEvent.java", filePath);
    }


    @TestFactory
    public DynamicNode testCheckStyle() {
        return createDynamicTest("https://github.com/checkstyle/checkstyle",
                System.getenv().getOrDefault("REPOSITORY_DIRECTORY", "../../repository/checkstyle"), "164a755af951cf0fd459d70873e1c199210d9d8b", List.of(
                        "src/main/java/com/puppycrawl/tools/checkstyle/AuditEventDefaultFormatter.java"/*,
                "src/main/java/com/puppycrawl/tools/checkstyle/ModuleFactory.java",
                "src/main/java/com/puppycrawl/tools/checkstyle/Checker.java",
                "src/main/java/com/puppycrawl/tools/checkstyle/ant",
                "src/main/java/com/puppycrawl/tools/checkstyle/utils"*/
                ), "../.cache/data");

    }


    @TestFactory
    public DynamicNode testFlink() {
        return createDynamicTest("https://github.com/apache/flink", "../../repository/flink", "261e72119b69c4fc3e22d9bcdec50f6ca2fdc2e9", List.of("flink-tests/src/test/java/org/apache/flink/test/accumulators/"),
                "../.cache/data");
    }

    private static @NonNull DynamicContainer createDynamicTest(String repositoryUrl, String repositoryPath, String commitHash, List<String> targetPaths, String outputPath) {
        FanOutServiceImpl fanOutService = new FanOutServiceImpl();
        return DynamicContainer.dynamicContainer(Arrays.stream(repositoryPath.split("/")).toList().getLast(),
                targetPaths
                        .stream()
                        .map(path -> DynamicTest.dynamicTest(path, () -> {
                            List<Fan> fanOut = fanOutService.findOut(repositoryUrl, repositoryPath, commitHash, List.of(path), outputPath);
                            fanOut.forEach(System.out::println);
                            Assertions.assertFalse(fanOut.isEmpty());
                        })));
    }
}
