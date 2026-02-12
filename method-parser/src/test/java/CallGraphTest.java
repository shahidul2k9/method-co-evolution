import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
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
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

/**
 * @author Shahidul Islam
 * @since 2025-12-23
 */
@Slf4j
public class CallGraphTest {

    private static final Pattern PLACEHOLDER_PATTERN = Pattern.compile("\\$\\{([^}]+)}");

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
        return generateTestCases("lightweight");
    }
    private static @NonNull DynamicContainer generateTestCases(String fileNameInfix) {
        List<CallGraphConfig> configurations = loadConfigurations(fileNameInfix);

        return DynamicContainer.dynamicContainer("call-graph-configs",
                configurations.stream().map(config -> DynamicContainer.dynamicContainer(config.name,
                        config.cases.stream().map(testCase -> DynamicTest.dynamicTest(testCase.name, () -> {
                            CallGraphServiceImpl fanOutService = new CallGraphServiceImpl();
                            List<MethodCall> methodCallOut = fanOutService.findFanOut(
                                    resolvePlaceholders(config.repositoryUrl),
                                    resolvePlaceholders(config.repositoryPath),
                                    config.commitHash,
                                    testCase.targetPaths,
                                    resolvePlaceholders(testCase.fanInFile),
                                    resolvePlaceholders(testCase.fanOutFile)
                            );
                            methodCallOut.forEach(System.out::println);
                            Assertions.assertFalse(methodCallOut.isEmpty());
                        })))));
    }

    private static String resolvePlaceholders(String value) {
        Matcher matcher = PLACEHOLDER_PATTERN.matcher(value);
        StringBuilder resolved = new StringBuilder();

        while (matcher.find()) {
            String key = matcher.group(1);
            String replacement = System.getenv(key);
            if (replacement == null && "REPOSITORY_DIRECTORY".equals(key)) {
                replacement = "../../repository";
            }
            if (replacement == null) {
                replacement = "";
            }
            matcher.appendReplacement(resolved, Matcher.quoteReplacement(replacement));
        }
        matcher.appendTail(resolved);
        return resolved.toString();
    }

    private static List<CallGraphConfig> loadConfigurations(String fileNameInfix) {
        ObjectMapper objectMapper = new ObjectMapper();
        List<CallGraphConfig> configurations = new ArrayList<>();

        try (var jsonFiles = java.nio.file.Files.list(Paths.get("src/test/resources/call-graph"))) {
            List<Path> configFiles = jsonFiles
                    .filter(path -> path.getFileName().toString().endsWith(".json") && (path.getFileName().toString().contains(fileNameInfix) || fileNameInfix.equalsIgnoreCase("all")))
                    .sorted()
                    .toList();

            for (Path configFile : configFiles) {
                try (InputStream inputStream = java.nio.file.Files.newInputStream(configFile)) {
                    Map<String, List<CallGraphConfig>> wrapper = objectMapper.readValue(inputStream,
                            new TypeReference<>() {
                            });
                    configurations.addAll(wrapper.getOrDefault("groups", List.of()));
                }
            }
        } catch (IOException exception) {
            throw new RuntimeException("Unable to read call graph test configurations", exception);
        }

        return configurations;
    }

    @Test
    public void testCommandLineCallGraph() {
        java.lang.String repositoryPath = System.getenv().getOrDefault("REPOSITORY_DIRECTORY", "../../repository") + "/checkstyle";
        String[] args = {
                "--command", "call-graph",
                "--repository-url", "https://github.com/checkstyle/checkstyle",
                "--repository-path", repositoryPath,
                "--start-commit", "164a755af951cf0fd459d70873e1c199210d9d8b",
                "--target-path", ".",
                "--output-fan-in-file", "../.cache/data/fan-in/checkstyle/checkstyle--fan-in--164a755af951cf0fd459d70873e1c199210d9d8b.csv",
                "--output-fan-out-file", "../.cache/data/fan-out/checkstyle/checkstyle--fan-out--164a755af951cf0fd459d70873e1c199210d9d8b.csv"
        };

        assertDoesNotThrow(() -> Main.main(args));
    }

    private static class CallGraphConfig {
        public String name;
        public String repositoryUrl;
        public String repositoryPath;
        public String commitHash;
        public List<CallGraphCase> cases;
    }

    private static class CallGraphCase {
        public String name;
        public List<String> targetPaths;
        public String fanInFile;
        public String fanOutFile;
    }
}
