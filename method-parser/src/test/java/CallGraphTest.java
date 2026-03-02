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
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.DynamicContainer;
import org.junit.jupiter.api.DynamicNode;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;
import rnd.method.parser.call.graph.Main;
import rnd.method.parser.call.graph.MethodParserUtil;
import rnd.method.parser.call.graph.model.MethodCall;
import rnd.method.parser.call.graph.service.CallGraphServiceImpl;

import java.io.File;
import java.io.FileNotFoundException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Locale;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

/**
 * @author Shahidul Islam
 * @since 2025-12-23
 */
@Slf4j
public class CallGraphTest extends TestConfigurationBase {


    @Test
    public void testSymbolResolverTest() throws FileNotFoundException {
        JavaParser javaParser = new JavaParser();
        String repositoryDirectory = Paths.get(TestConfigurationBase.getEnv("METHOD_EVOLUTION_CACHE_DIRECTORY", DEFAULT_REPOSITORY_DIRECTORY), "repository/checkstyle").toString();

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
        List<Path> allJavaSourceRoots = MethodParserUtil.findAllJavaSourceRoots(Paths.get(repositoryDirectory));
        CombinedTypeSolver solver = new CombinedTypeSolver();

        for (Path path : allJavaSourceRoots) {
            solver.add(new JavaParserTypeSolver(path.toFile()));
        }
        SymbolReference<ResolvedMethodDeclaration> solve = JavaParserFacade.get(solver)
                .solve(mce);
        ResolvedMethodDeclaration resolved = solve.getCorrespondingDeclaration();


        Optional<MethodDeclaration> ast = resolved.toAst()
                .filter(MethodDeclaration.class::isInstance)
                .map(MethodDeclaration.class::cast);

        String filePath = ast
                .flatMap(m -> m.findCompilationUnit())
                .flatMap(c -> c.getStorage())
                .map(storage -> storage.getPath().toString())
                .map(file -> MethodParserUtil.stripFilePrefix(repositoryDirectory, file))
                .orElse("<external>");

        int startLine = ast
                .flatMap(NodeWithRange::getBegin)
                .map(p -> p.line)
                .orElse(-1);
        Assert.assertEquals(149, startLine);
        Assert.assertEquals("src/main/java/com/puppycrawl/tools/checkstyle/api/AuditEvent.java", filePath);
    }


    @TestFactory
    public DynamicNode testCallGraphFromConfigFilesAll() {
        return generateTestCases("all");
    }

    @TestFactory
    public DynamicNode testLightweightCallGraphFromConfigFiles() {
        return generateTestCases("white");
    }

    private static @NonNull DynamicContainer generateTestCases(String fileNameInfix) {
        List<TestProjectConfig> configurations = TestConfigurationBase.loadConfigurations("call-graph", fileNameInfix);

        return DynamicContainer.dynamicContainer("call-graph-configs",
                configurations.stream().map(projectConfig -> DynamicContainer.dynamicContainer(projectConfig.name,
                        projectConfig.cases.stream().map(testCase -> DynamicTest.dynamicTest(testCase.name, () -> {
                            CallGraphServiceImpl fanOutService = new CallGraphServiceImpl();
                            String outputDirectory = TestConfigurationBase.resolvePlaceholders(testCase.outputDirectory);

                            List<MethodCall> methodCallOut = fanOutService.findFanOut(
                                    TestConfigurationBase.resolvePlaceholders(projectConfig.repositoryUrl),
                                    TestConfigurationBase.resolvePlaceholders(projectConfig.repositoryPath),
                                    projectConfig.commitHash,
                                    List.of(testCase.targetPath),
                                    String.format(Locale.CANADA, "%s/fan-in/%s/%s--%s.csv", outputDirectory, projectConfig.name, testCase.name, projectConfig.commitHash),
                                    String.format(Locale.CANADA, "%s/fan-out/%s/%s--%s.csv", outputDirectory, projectConfig.name, testCase.name, projectConfig.commitHash)
                            );
                            methodCallOut.forEach(System.out::println);
                            Assertions.assertFalse(methodCallOut.isEmpty());
                        })))));
    }


    @Test
    public void testCommandLineCallGraph() {
        java.lang.String repositoryPath = TestConfigurationBase.getEnv("METHOD_EVOLUTION_CACHE_DIRECTORY", DEFAULT_REPOSITORY_DIRECTORY) + "/repository/checkstyle";
        String[] args = {
                "--command", "call-graph",
                "--repository-url", "https://github.com/checkstyle/checkstyle",
                "--repository-path", repositoryPath,
                "--start-commit", "164a755af951cf0fd459d70873e1c199210d9d8b",
                "--target-path", ".",
                "--output-fan-in-file", "../.cache/test/fan-in/checkstyle/checkstyle--fan-in--164a755af951cf0fd459d70873e1c199210d9d8b.csv",
                "--output-fan-out-file", "../.cache/test/fan-out/checkstyle/checkstyle--fan-out--164a755af951cf0fd459d70873e1c199210d9d8b.csv"
        };

        assertDoesNotThrow(() -> Main.main(args));
    }
}
