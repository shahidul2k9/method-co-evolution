import lombok.extern.slf4j.Slf4j;
import org.jspecify.annotations.NonNull;
import org.junit.Before;
import org.junit.Test;
import org.junit.jupiter.api.*;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.service.MethodScannerImpl;
import rnd.method.parser.call.graph.util.TableUtil;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * @author Shahidul Islam
 * @since 2026-01-12
 */
@Slf4j
public class MethodGenerationTest extends TestConfigurationBase {
    private String CACHE_DIRECTORY;
    private String REPOSITORY_DIRECTORY;

    @TestFactory
    public DynamicNode testMethodParsing() {
        String targetFile = TestConfigurationBase.getEnv("TEST_CONFIG_FILE", "gson");
        return generateTestCases(targetFile);
    }

    private static @NonNull DynamicContainer generateTestCases(String fileNameInfix) {
        List<TestProjectConfig> configurations = TestConfigurationBase.loadConfigurations("method", fileNameInfix);

        return DynamicContainer.dynamicContainer("method-generation",
                configurations.stream().map(projectConfig -> DynamicContainer.dynamicContainer(projectConfig.name,
                        projectConfig.cases.stream().map(testCase -> DynamicTest.dynamicTest(testCase.name, () -> {

                            MethodScannerImpl methodScanner = MethodScannerImpl.getInstance();

                            String repoRoot = TestConfigurationBase.resolvePlaceholders(projectConfig.repositoryPath);
                            Path repoRootPath = Paths.get(repoRoot).toAbsolutePath().normalize();
                            Path targetPath = repoRootPath.resolve(testCase.targetPath).normalize();
                            methodScanner.init(
                                    repoRoot,
                                    projectConfig.repositoryUrl,
                                    projectConfig.commitHash
                            );

                            List<Method> methods;
                            if (Files.isRegularFile(targetPath) && targetPath.toString().endsWith(".java")) {
                                String relativePath = repoRootPath.relativize(targetPath).toString();

                                methods = methodScanner.scanMethod(relativePath);
                            } else {
                                try (Stream<Path> pathStream = Files.walk(targetPath)) {
                                    methods = pathStream
                                            .filter(Files::isRegularFile)
                                            .filter(path -> path.toString().endsWith(".java"))
                                            .map(path -> repoRootPath.relativize(path).toString())
                                            .flatMap(relativePath -> methodScanner.scanMethod(relativePath).stream())
                                            .collect(Collectors.toList());
                                }
                            }
                            String outputDirectory = TestConfigurationBase.resolvePlaceholders(testCase.outputDirectory);
                            TableUtil.toTable(methods, String.format(Locale.CANADA, "%s/method/%s--%s--%s.csv", outputDirectory, projectConfig.name, testCase.name, projectConfig.commitHash));

                        })))));
    }

    @Before
    public void setUp() {
        CACHE_DIRECTORY = System.getenv("METHOD_CO_EVOLUTION_CACHE_DIRECTORY");
        REPOSITORY_DIRECTORY = Path.of(CACHE_DIRECTORY, "repository").toFile().getAbsolutePath();

    }

    @Test
    public void testCheckTestAnnotation() {
        MethodScannerImpl methodScanner = MethodScannerImpl.getInstance();
        methodScanner.init(
                Path.of(REPOSITORY_DIRECTORY, "checkstyle").toFile().getAbsolutePath(),
                "https://github.com/checkstyle/checkstyle",
                "164a755af951cf0fd459d70873e1c199210d9d8b"
        );
        List<Method> methods = methodScanner.scanMethod("src");

    }


}
