import org.junit.Assert;
import org.junit.Test;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.service.MethodScannerImpl;
import rnd.method.parser.call.graph.artifact.ArtifactClassification;
import rnd.method.parser.call.graph.artifact.ArtifactTags;
import rnd.method.parser.call.graph.artifact.TestArtifactDetector;
import rnd.method.parser.call.graph.util.JavaParserContext;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ArtifactDetectionTest {
    @Test
    public void tagEncodingAndLookupUseHashDelimitedTags() {
        String artifact = "#test-module #test-code #test-unit #test-method";

        Assert.assertTrue(ArtifactTags.hasTag(artifact, "test-method"));
        Assert.assertTrue(ArtifactTags.hasTag(artifact, "#test-method"));
        Assert.assertTrue(ArtifactTags.hasTag(artifact, "test-code"));
        Assert.assertFalse(ArtifactTags.hasTag(artifact, "test"));
    }

    @Test
    public void tagLookupToleratesLegacyCompactHashTags() {
        String artifact = "#test-module#test-code#test-unit#test-method";

        Assert.assertTrue(ArtifactTags.hasTag(artifact, "test-method"));
        Assert.assertTrue(ArtifactTags.hasTag(artifact, "#test-method"));
        Assert.assertFalse(ArtifactTags.hasTag(artifact, "test"));
    }

    @Test
    public void jgitStyleTestModuleRootsAreClassified() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-jgit");
        Path configDir = Files.createDirectories(repo.resolve("config"));
        Files.writeString(configDir.resolve("jgit.yml"), """
                projects:
                  jgit:
                    testModulePatterns:
                      - "*.test"
                    modules:
                      org.eclipse.jgit.test:
                        mainSourceRoots:
                          - src
                        unitTestSourceRoots:
                          - tst
                        integrationTestSourceRoots:
                          - exttst
                        testResourceRoots:
                          - tst-rsrc
                """);

        Path module = Files.createDirectories(repo.resolve("org.eclipse.jgit.test"));
        Files.writeString(module.resolve("pom.xml"), """
                <project>
                  <artifactId>org.eclipse.jgit.test</artifactId>
                </project>
                """);
        Path unitFile = Files.createDirectories(module.resolve("tst/org/eclipse/jgit"))
                .resolve("ExampleTest.java");
        Files.writeString(unitFile, "package org.eclipse.jgit; class ExampleTest {}");
        Path resourceFile = Files.createDirectories(module.resolve("tst-rsrc"))
                .resolve("Example.java");
        Files.writeString(resourceFile, "class Example {}");

        TestArtifactDetector detector = TestArtifactDetector.load(repo, "jgit", configDir);

        ArtifactClassification unit = detector.classify(unitFile, "org.eclipse.jgit");
        Assert.assertEquals("#test-module #test-code #test-unit", unit.encodedArtifact());

        ArtifactClassification resource = detector.classify(resourceFile, "");
        Assert.assertEquals("#test-module #test-code #test-resource", resource.encodedArtifact());
        Assert.assertTrue(resource.isResource());
    }

    @Test
    public void privateNamingHelperInTestRootIsTestUtility() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-private-helper");
        runGit(repo, "init");
        runGit(repo, "config", "user.email", "test@example.com");
        runGit(repo, "config", "user.name", "Test User");
        Path sourceRoot = Files.createDirectories(repo.resolve("src/test/java/demo"));
        Files.writeString(sourceRoot.resolve("TokenTest.java"), """
                package demo;
                class TokenTest {
                    private boolean testDelegationTokenIdentiferSerializationRoundTrip() {
                        return true;
                    }
                    public void testPublicNamingConvention() {
                    }
                }
                """);
        runGit(repo, "add", ".");
        runGit(repo, "commit", "-m", "fixture");
        String commit = new String(new ProcessBuilder("git", "rev-parse", "HEAD")
                .directory(repo.toFile())
                .start()
                .getInputStream()
                .readAllBytes()).trim();

        MethodScannerImpl scanner = MethodScannerImpl.getInstance();
        scanner.init(repo.toString(), "https://github.com/example/demo", commit);
        List<Method> methods = scanner.scanMethod("src/test/java/demo/TokenTest.java");
        Map<String, String> artifacts = methods.stream()
                .collect(Collectors.toMap(Method::getName, Method::getArtifact));

        Assert.assertTrue(ArtifactTags.hasTag(
                artifacts.get("testDelegationTokenIdentiferSerializationRoundTrip"),
                "test-utility"
        ));
        Assert.assertFalse(ArtifactTags.hasTag(
                artifacts.get("testDelegationTokenIdentiferSerializationRoundTrip"),
                "test-method"
        ));
        Assert.assertTrue(ArtifactTags.hasTag(
                artifacts.get("testPublicNamingConvention"),
                "test-method"
        ));
    }

    @Test
    public void classifyMethodArtifactsUsesJavaParserMethodRoles() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-method-roles");
        Path testSource = Files.createDirectories(repo.resolve("src/test/java/demo"));
        Path testFile = testSource.resolve("TokenTest.java");
        Files.writeString(testFile, """
                package demo;
                import org.junit.Before;
                import org.junit.Test;
                class TokenTest {
                    private boolean testDelegationTokenIdentiferSerializationRoundTrip() {
                        return true;
                    }
                    public void testPublicNamingConvention() {
                    }
                    @Test
                    private void privateAnnotatedTest() {
                    }
                    @Before
                    public void setUp() {
                    }
                }
                """);

        Path mainSource = Files.createDirectories(repo.resolve("src/main/java/demo"));
        Path mainFile = mainSource.resolve("RetryPolicy.java");
        Files.writeString(mainFile, """
                package demo;
                class RetryPolicy {
                    boolean shouldRetry() {
                        return true;
                    }
                }
                """);

        TestArtifactDetector detector = TestArtifactDetector.load(repo, "demo", null);

        Map<String, ArtifactClassification> testMethods = detector.classifyMethodArtifacts(testFile, "demo")
                .stream()
                .collect(Collectors.toMap(ArtifactClassification::methodName, classification -> classification));

        Assert.assertTrue(ArtifactTags.hasTag(
                testMethods.get("testDelegationTokenIdentiferSerializationRoundTrip").encodedArtifact(),
                "test-utility"
        ));
        Assert.assertFalse(ArtifactTags.hasTag(
                testMethods.get("testDelegationTokenIdentiferSerializationRoundTrip").encodedArtifact(),
                "test-method"
        ));
        Assert.assertTrue(ArtifactTags.hasTag(
                testMethods.get("testPublicNamingConvention").encodedArtifact(),
                "test-method"
        ));
        Assert.assertTrue(ArtifactTags.hasTag(
                testMethods.get("privateAnnotatedTest").encodedArtifact(),
                "test-method"
        ));
        Assert.assertTrue(ArtifactTags.hasTag(
                testMethods.get("setUp").encodedArtifact(),
                "test-fixture"
        ));
        Assert.assertNotNull(testMethods.get("setUp").startLine());
        Assert.assertNotNull(testMethods.get("setUp").endLine());

        ArtifactClassification productionMethod = detector.classifyMethodArtifacts(mainFile, "demo").get(0);
        Assert.assertEquals("shouldRetry", productionMethod.methodName());
        Assert.assertEquals("#production-code", productionMethod.encodedArtifact());
    }

    @Test
    public void sharedParserContextProvidesParserAndTypeSolver() throws Exception {
        Path repo = Files.createTempDirectory("artifact-parser-context");
        Path source = Files.createDirectories(repo.resolve("src/main/java/demo"));
        Files.writeString(source.resolve("Example.java"), "package demo; class Example {}");

        JavaParserContext context = JavaParserContext.create(repo);

        Assert.assertNotNull(context.parser());
        Assert.assertNotNull(context.typeSolver());
        Assert.assertNotNull(context.configuration());
    }

    @Test
    public void classifyMethodArtifactsUsesPartialAstWhenParseHasRecoverableProblems() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-partial-ast");
        Path testSource = Files.createDirectories(repo.resolve("src/test/java/demo"));
        Path testFile = testSource.resolve("PerformanceTest.java");
        Files.writeString(testFile, """
                package demo;
                import org.junit.Test;
                class PerformanceTest {
                    @Test
                    public void ru() throws Exception {
                        helper();
                    }

                    private void helper() {
                        try {
                            throw new Exception();
                        } catch (Exception _) {
                        }
                    }
                }
                """);

        TestArtifactDetector detector = TestArtifactDetector.load(repo, "demo", null);
        Map<String, ArtifactClassification> methods = detector.classifyMethodArtifacts(testFile, "demo")
                .stream()
                .collect(Collectors.toMap(ArtifactClassification::methodName, classification -> classification));

        Assert.assertTrue(ArtifactTags.hasTag(methods.get("ru").encodedArtifact(), "test-method"));
        Assert.assertTrue(ArtifactTags.hasTag(methods.get("helper").encodedArtifact(), "test-utility"));
    }

    @Test
    public void javaSourceWinsWhenMavenResourceRootOverlapsSourceRoot() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-overlap-resource");
        Files.writeString(repo.resolve("pom.xml"), """
                <project>
                  <artifactId>jfreechart</artifactId>
                  <build>
                    <sourceDirectory>source</sourceDirectory>
                    <testSourceDirectory>tests</testSourceDirectory>
                    <resources>
                      <resource>
                        <directory>source</directory>
                      </resource>
                    </resources>
                  </build>
                </project>
                """);
        Path sourceFile = Files.createDirectories(repo.resolve("source/org/jfree/chart"))
                .resolve("ChartFactory.java");
        Files.writeString(sourceFile, "package org.jfree.chart; class ChartFactory {}");
        Path testResourceFile = Files.createDirectories(repo.resolve("src/test/resources/demo"))
                .resolve("Fixture.java");
        Files.writeString(testResourceFile, "class Fixture {}");

        TestArtifactDetector detector = TestArtifactDetector.load(repo, "jfreechart", null);

        ArtifactClassification source = detector.classify(sourceFile, "org.jfree.chart");
        Assert.assertEquals("#production-code", source.encodedArtifact());
        Assert.assertFalse(source.isResource());

        ArtifactClassification testResource = detector.classify(testResourceFile, "");
        Assert.assertEquals("#test-code #test-resource", testResource.encodedArtifact());
        Assert.assertTrue(testResource.isResource());
    }

    private static void runGit(Path repo, String... args) throws Exception {
        String[] command = new String[args.length + 1];
        command[0] = "git";
        System.arraycopy(args, 0, command, 1, args.length);
        Process process = new ProcessBuilder(command)
                .directory(repo.toFile())
                .redirectErrorStream(true)
                .start();
        if (process.waitFor() != 0) {
            throw new IllegalStateException(new String(process.getInputStream().readAllBytes()));
        }
    }
}
