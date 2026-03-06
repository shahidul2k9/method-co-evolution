import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import rnd.method.parser.call.graph.util.MethodParserUtil;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class MethodParserUtilTest {

    @TempDir
    Path tempDir;

    @Test
    void shouldInferSourceRootFromPackageDeclaration() throws IOException {
        Path sourceFile = tempDir.resolve("module/src/main/java/com/example/service/App.java");
        Files.createDirectories(sourceFile.getParent());
        Files.writeString(sourceFile, "package com.example.service;\npublic class App {}\n");

        List<Path> roots = MethodParserUtil.findAllJavaSourceRootsFromPackageDeclarations(tempDir);

        assertEquals(1, roots.size());
        assertEquals(tempDir.resolve("module/src/main/java"), roots.getFirst());
    }

    @Test
    void shouldTreatDirectoryAsRootWhenPackageDeclarationMissing() throws IOException {
        Path sourceFile = tempDir.resolve("src/custom/NoPackage.java");
        Files.createDirectories(sourceFile.getParent());
        Files.writeString(sourceFile, "public class NoPackage {}\n");

        List<Path> roots = MethodParserUtil.findAllJavaSourceRootsFromPackageDeclarations(tempDir);

        assertEquals(1, roots.size());
        assertEquals(sourceFile.getParent(), roots.getFirst());
    }

    @Test
    void shouldFallbackToPackageDirectoryWhenPackagePathDoesNotMatch() throws IOException {
        Path sourceFile = tempDir.resolve("src/main/java/wrong/path/Mismatch.java");
        Files.createDirectories(sourceFile.getParent());
        Files.writeString(sourceFile, "package com.example.mismatch;\npublic class Mismatch {}\n");

        List<Path> roots = MethodParserUtil.findAllJavaSourceRootsFromPackageDeclarations(tempDir);

        assertEquals(1, roots.size());
        assertEquals(sourceFile.getParent(), roots.getFirst());
    }


    @Test
    void shouldFallbackToHeaderParsingWhenJavaParserFails() throws IOException {
        Path sourceFile = tempDir.resolve("module/src/main/java/com/example/broken/Broken.java");
        Files.createDirectories(sourceFile.getParent());
        Files.writeString(sourceFile, "package com.example.broken;\npublic class Broken {\n");

        List<Path> roots = MethodParserUtil.findAllJavaSourceRootsFromPackageDeclarations(tempDir);

        assertEquals(1, roots.size());
        assertEquals(tempDir.resolve("module/src/main/java"), roots.getFirst());
    }

    @Test
    void shouldIgnoreExcludedDirectories() throws IOException {
        Path sourceFile = tempDir.resolve("build/generated/com/example/Generated.java");
        Files.createDirectories(sourceFile.getParent());
        Files.writeString(sourceFile, "package com.example;\npublic class Generated {}\n");

        List<Path> roots = MethodParserUtil.findAllJavaSourceRootsFromPackageDeclarations(tempDir);

        assertTrue(roots.isEmpty());
    }
}
