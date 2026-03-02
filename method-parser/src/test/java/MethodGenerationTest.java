import lombok.extern.slf4j.Slf4j;
import org.jspecify.annotations.NonNull;
import org.junit.Before;
import org.junit.Test;
import org.junit.jupiter.api.*;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.service.MethodScannerImpl;
import rnd.method.parser.call.graph.util.TableUtil;

import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

/**
 * @author Shahidul Islam
 * @since 2026-01-12
 */
@Slf4j
public class MethodGenerationTest extends TestConfigurationBase {
    private String CACHE_DIRECTORY;
    private String REPOSITORY_DIRECTORY;

    @TestFactory
    public DynamicNode testGson() {
        return generateTestCases("gson");
    }

    private static @NonNull DynamicContainer generateTestCases(String fileNameInfix) {
        List<TestProjectConfig> configurations = TestConfigurationBase.loadConfigurations("method", fileNameInfix);

        return DynamicContainer.dynamicContainer("method-generation",
                configurations.stream().map(projectConfig -> DynamicContainer.dynamicContainer(projectConfig.name,
                        projectConfig.cases.stream().map(testCase -> DynamicTest.dynamicTest(testCase.name, () -> {

                            MethodScannerImpl methodScanner = new MethodScannerImpl();
                            List<Method> methods = methodScanner.scanMethod(TestConfigurationBase.resolvePlaceholders(projectConfig.repositoryPath), projectConfig.repositoryUrl,
                                    projectConfig.commitHash, testCase.targetPath);

                            String outputDirectory = TestConfigurationBase.resolvePlaceholders(testCase.outputDirectory);

                            TableUtil.toTable(methods, String.format(Locale.CANADA, "%s/method/%s/%s--%s.csv", outputDirectory, projectConfig.name, testCase.name, projectConfig.commitHash));

                        })))));
    }

    @Before
    public void setUp() {
        CACHE_DIRECTORY = System.getenv("METHOD_CO_EVOLUTION_CACHE_DIRECTORY");
        REPOSITORY_DIRECTORY = Path.of(CACHE_DIRECTORY, "repository").toFile().getAbsolutePath();

    }

    @Test
    public void testCheckTestAnnotation() {
        MethodScannerImpl methodScanner = new MethodScannerImpl();
        List<Method> methods = methodScanner.scanMethod(Path.of(REPOSITORY_DIRECTORY, "checkstyle").toFile().getAbsolutePath(), "https://github.com/checkstyle/checkstyle",
                "164a755af951cf0fd459d70873e1c199210d9d8b", "src");
        for (Method method : methods) {
            log.info("{}", method);
        }

    }


}
