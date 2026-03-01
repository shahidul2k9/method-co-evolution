import lombok.extern.slf4j.Slf4j;
import org.junit.Before;
import org.junit.Test;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.service.MethodScannerImpl;

import java.lang.reflect.Array;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;

/**
 * @author Shahidul Islam
 * @since 2026-01-12
 */
@Slf4j
public class MethodGenerationTest {
    private  String CACHE_DIRECTORY;
    private  String REPOSITORY_DIRECTORY;

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
