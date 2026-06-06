package rnd.method.parser.call.graph.artifact;

import org.junit.Assert;
import org.junit.Test;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.service.ClassScannerImpl;
import rnd.method.parser.call.graph.service.MethodScannerImpl;
import rnd.method.parser.call.graph.util.JavaParserContext;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ArtifactDetectionTest {
    @Test
    public void classScannerRequiresProjectName() throws Exception {
        Path repo = Files.createTempDirectory("class-scan-project-required");
        ClassScannerImpl scanner = ClassScannerImpl.getInstance();

        Assert.assertThrows(
                IllegalArgumentException.class,
                () -> scanner.init(
                        "",
                        repo.toString(),
                        "https://github.com/apache/hadoop",
                        "abc123",
                        null,
                        false
                )
        );
    }

    @Test
    public void tagEncodingAndLookupUseHashDelimitedTags() {
        String artifact = "#test-module #test-code #test-case-method";

        Assert.assertTrue(ArtifactTags.hasTag(artifact, "test-case-method"));
        Assert.assertTrue(ArtifactTags.hasTag(artifact, "#test-case-method"));
        Assert.assertTrue(ArtifactTags.hasTag(artifact, "test-code"));
        Assert.assertFalse(ArtifactTags.hasTag(artifact, "test"));
    }

    @Test
    public void tagLookupToleratesLegacyCompactHashTags() {
        String artifact = "#test-module#test-code#test-case-method";

        Assert.assertTrue(ArtifactTags.hasTag(artifact, "test-case-method"));
        Assert.assertTrue(ArtifactTags.hasTag(artifact, "#test-case-method"));
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
        Path mainFile = Files.createDirectories(module.resolve("src/org/eclipse/jgit"))
                .resolve("Helper.java");
        Files.writeString(mainFile, "package org.eclipse.jgit; class Helper {}");
        Path resourceFile = Files.createDirectories(module.resolve("tst-rsrc"))
                .resolve("Example.java");
        Files.writeString(resourceFile, "class Example {}");

        TestArtifactDetector detector = TestArtifactDetector.load(repo, "jgit", configDir);

        ArtifactClassification unit = detector.classify(unitFile, "org.eclipse.jgit");
        Assert.assertEquals("#test-module #test-code", unit.encodedArtifact());

        ArtifactClassification main = detector.classify(mainFile, "org.eclipse.jgit");
        Assert.assertEquals("#test-module #main-code", main.encodedArtifact());

        ArtifactClassification resource = detector.classify(resourceFile, "");
        Assert.assertEquals("#test-module #test-resource", resource.encodedArtifact());
        Assert.assertTrue(resource.isResource());
    }

    @Test
    public void newDefaultTestRootsAreClassifiedAsTestCode() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-new-roots");
        Path androidFile = Files.createDirectories(repo.resolve("src/androidTest/java/demo"))
                .resolve("AndroidSmokeTest.java");
        Files.writeString(androidFile, "package demo; class AndroidSmokeTest {}");
        Path androidRootFile = Files.createDirectories(repo.resolve("src/androidTest/demo"))
                .resolve("AndroidRootTest.java");
        Files.writeString(androidRootFile, "package demo; class AndroidRootTest {}");
        Path srcTestFile = Files.createDirectories(repo.resolve("src/test/demo"))
                .resolve("LegacyLayoutTest.java");
        Files.writeString(srcTestFile, "package demo; class LegacyLayoutTest {}");
        Path antFile = Files.createDirectories(repo.resolve("src/tests/junit/demo"))
                .resolve("AntLayoutTest.java");
        Files.writeString(antFile, "package demo; class AntLayoutTest {}");

        TestArtifactDetector detector = TestArtifactDetector.load(repo, "demo", null);

        Assert.assertEquals("#test-code", detector.classify(androidFile, "demo").encodedArtifact());
        Assert.assertEquals("#test-code", detector.classify(androidRootFile, "demo").encodedArtifact());
        Assert.assertEquals("#test-code", detector.classify(srcTestFile, "demo").encodedArtifact());
        Assert.assertEquals("#test-code", detector.classify(antFile, "demo").encodedArtifact());
    }

    @Test
    public void moduleContextPatternsMatchAncestorDirectories() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-context");
        Path integrationModule = Files.createDirectories(repo.resolve("integrationtest/search"));
        Files.writeString(integrationModule.resolve("pom.xml"), "<project><artifactId>search-it</artifactId></project>");
        Path integrationMain = Files.createDirectories(integrationModule.resolve("src/main/java/demo"))
                .resolve("SearchDriver.java");
        Files.writeString(integrationMain, "package demo; class SearchDriver {}");

        Path docModule = Files.createDirectories(repo.resolve("documentation/reference"));
        Files.writeString(docModule.resolve("pom.xml"), "<project><artifactId>reference</artifactId></project>");
        Path docMain = Files.createDirectories(docModule.resolve("src/main/java/demo"))
                .resolve("Snippet.java");
        Files.writeString(docMain, "package demo; class Snippet {}");

        TestArtifactDetector detector = TestArtifactDetector.load(repo, "demo", null);

        Assert.assertEquals("#test-module #main-code", detector.classify(integrationMain, "demo").encodedArtifact());
        Assert.assertEquals("#doc-module #main-code", detector.classify(docMain, "demo").encodedArtifact());
    }

    @Test
    public void junit5AllowsPackagePrivateAnnotatedTestMethods() throws Exception {
        Map<String, ArtifactClassification> methods = classifyTestSource("""
                package demo;
                import org.junit.jupiter.api.Test;
                import org.junit.jupiter.api.BeforeEach;
                import org.junit.jupiter.params.ParameterizedTest;
                class JupiterTest {
                    @BeforeEach
                    void setUp() {}
                    @Test
                    void packagePrivateTest() {}
                    @ParameterizedTest
                    void parameterizedTest(String value) {}
                    @Test
                    private void privateTest() {}
                }
                """);

        assertHas(methods, "packagePrivateTest", "test-case-method");
        assertHas(methods, "parameterizedTest", "test-case-method");
        assertHas(methods, "privateTest", "test-helper-method");
        assertNotHas(methods, "privateTest", "test-case-method");
        assertHas(methods, "setUp", "test-fixture-method");
    }

    @Test
    public void junit4RequiresPublicVoidNoArgWhenAnnotationIsKnown() throws Exception {
        Map<String, ArtifactClassification> methods = classifyTestSource("""
                package demo;
                import org.junit.Test;
                public class JUnit4Test {
                    @Test
                    public void publicTest() {}
                    @Test
                    void packagePrivateTest() {}
                    @Test
                    public int nonVoidTest() { return 1; }
                    @Test
                    public void parameterizedTest(String value) {}
                }
                """);

        assertHas(methods, "publicTest", "test-case-method");
        assertHas(methods, "packagePrivateTest", "test-helper-method");
        assertHas(methods, "nonVoidTest", "test-helper-method");
        assertHas(methods, "parameterizedTest", "test-helper-method");
    }

    @Test
    public void unresolvedSimpleTestAnnotationFallbackIsConservative() throws Exception {
        Map<String, ArtifactClassification> methods = classifyTestSource("""
                package demo;
                class UnknownFrameworkTest {
                    @Test
                    void inferredTest() {}
                    @Test
                    private void privateInferredTest() {}
                    @Test
                    String wrongShape() { return ""; }
                }
                """);

        assertHas(methods, "inferredTest", "test-case-method");
        assertHas(methods, "privateInferredTest", "test-helper-method");
        assertHas(methods, "wrongShape", "test-helper-method");
    }

    @Test
    public void junit3RequiresLegacyInheritanceAndPublicVoidTestPrefix() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-junit3");
        Path source = Files.createDirectories(repo.resolve("src/test/java/demo"));
        Path testFile = source.resolve("LegacyTest.java");
        Files.writeString(testFile, """
                package demo;
                public class LegacyTest extends junit.framework.TestCase {
                    public void testValid() {}
                    protected void testProtectedHelper() {}
                    public int testWrongReturn() { return 0; }
                    public void helper() {}
                }
                """);

        Map<String, ArtifactClassification> methods = methodsByName(TestArtifactDetector.load(repo, "demo", null), testFile);

        assertHas(methods, "testValid", "test-case-method");
        assertHas(methods, "testProtectedHelper", "test-helper-method");
        assertHas(methods, "testWrongReturn", "test-helper-method");
        assertHas(methods, "helper", "test-helper-method");
    }

    @Test
    public void junit3IndirectInheritanceUsesConfiguredSuperclassWhenTypeSolvingWorks() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-junit3-indirect");
        Path configDir = Files.createDirectories(repo.resolve("config"));
        Files.writeString(configDir.resolve("defaults.yml"), """
                defaults:
                  legacyTestCaseSuperclasses:
                    - demo.CustomCase
                """);
        Path source = Files.createDirectories(repo.resolve("src/test/java/demo"));
        Files.writeString(source.resolve("CustomCase.java"), "package demo; public class CustomCase {}");
        Files.writeString(source.resolve("BaseCase.java"), "package demo; public class BaseCase extends CustomCase {}");
        Path testFile = source.resolve("ChildSpec.java");
        Files.writeString(testFile, """
                package demo;
                public class ChildSpec extends BaseCase {
                    public void testInheritedLegacyBase() {}
                }
                """);

        Map<String, ArtifactClassification> methods = methodsByName(TestArtifactDetector.load(repo, "demo", configDir), testFile);

        assertHas(methods, "testInheritedLegacyBase", "test-case-method");
    }

    @Test
    public void junit3HierarchyFailureFallbackIsLimitedToClassicTestClassShape() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-junit3-fallback");
        Path source = Files.createDirectories(repo.resolve("src/test/java/demo"));
        Path testFile = source.resolve("LegacyFallbackTest.java");
        Files.writeString(testFile, """
                package demo;
                public class LegacyFallbackTest extends MissingBase {
                    public void testFallback() {}
                }
                class LegacyFallbackSpec extends MissingBase {
                    public void testNotFallback() {}
                }
                """);

        Map<String, ArtifactClassification> methods = methodsByName(TestArtifactDetector.load(repo, "demo", null), testFile);

        assertHas(methods, "testFallback", "test-case-method");
        assertHas(methods, "testNotFallback", "test-helper-method");
    }

    @Test
    public void unannotatedTestPrefixedHelpersStayHelpersWithoutJUnit3Shape() throws Exception {
        Map<String, ArtifactClassification> methods = classifyTestSource("""
                package demo;
                class TokenTest {
                    public void testPublicNamingConvention() {}
                    protected void testProtectedNamingConvention() {}
                    void shouldDoThing() {}
                }
                """);

        assertHas(methods, "testPublicNamingConvention", "test-helper-method");
        assertHas(methods, "testProtectedNamingConvention", "test-helper-method");
        assertHas(methods, "shouldDoThing", "test-helper-method");
    }

    @Test
    public void jqwikTestAndLifecycleAnnotationsAreDetectedByImportFallback() throws Exception {
        Map<String, ArtifactClassification> methods = classifyTestSource("""
                package demo;
                import net.jqwik.api.Property;
                import net.jqwik.api.Example;
                import net.jqwik.api.lifecycle.BeforeProperty;
                class PropertyBasedTest {
                    @BeforeProperty
                    void beforeProperty() {}
                    @Property
                    boolean propertyHolds() { return true; }
                    @Example
                    void example() {}
                    @Property
                    String badReturnType() { return ""; }
                }
                """);

        assertHas(methods, "beforeProperty", "test-fixture-method");
        assertHas(methods, "propertyHolds", "test-case-method");
        assertHas(methods, "example", "test-case-method");
        assertHas(methods, "badReturnType", "test-helper-method");
    }

    @Test
    public void testNgTestAndFixtureAnnotationsAreDetectedByImportFallback() throws Exception {
        Map<String, ArtifactClassification> methods = classifyTestSource("""
                package demo;
                import org.testng.annotations.Test;
                import org.testng.annotations.BeforeMethod;
                class TestNgTest {
                    @BeforeMethod
                    void beforeMethod() {}
                    @Test
                    void testNgMethod() {}
                    @Test
                    private void privateTestNgMethod() {}
                }
                """);

        assertHas(methods, "beforeMethod", "test-fixture-method");
        assertHas(methods, "testNgMethod", "test-case-method");
        assertHas(methods, "privateTestNgMethod", "test-helper-method");
    }

    @Test
    public void mockitoContextAnnotationsDoNotMakeArbitraryMethodsTestCases() throws Exception {
        Map<String, ArtifactClassification> methods = classifyTestSource("""
                package demo;
                import org.junit.jupiter.api.extension.ExtendWith;
                import org.mockito.junit.jupiter.MockitoExtension;
                @ExtendWith(MockitoExtension.class)
                class MockitoContextTest {
                    void helper() {}
                }
                """);

        assertHas(methods, "helper", "test-helper-method");
        assertNotHas(methods, "helper", "test-case-method");
    }

    @Test
    public void yamlCanExtendTestAndFixtureAnnotations() throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-custom-annotations");
        Path configDir = Files.createDirectories(repo.resolve("config"));
        Files.writeString(configDir.resolve("defaults.yml"), """
                defaults:
                  testMethodAnnotations:
                    - demo.CustomTest
                  fixtureMethodAnnotations:
                    - demo.CustomBefore
                """);
        Path source = Files.createDirectories(repo.resolve("src/test/java/demo"));
        Path testFile = source.resolve("CustomAnnotationTest.java");
        Files.writeString(testFile, """
                package demo;
                @interface CustomTest {}
                @interface CustomBefore {}
                class CustomAnnotationTest {
                    @CustomBefore
                    void before() {}
                    @CustomTest
                    void customTest() {}
                }
                """);

        Map<String, ArtifactClassification> methods = methodsByName(TestArtifactDetector.load(repo, "demo", configDir), testFile);

        assertHas(methods, "before", "test-fixture-method");
        assertHas(methods, "customTest", "test-case-method");
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
        scanner.init("demo-project", repo.toString(), "https://github.com/example/demo", commit, null, true);
        List<Method> methods = scanner.scanMethod("src/test/java/demo/TokenTest.java");
        Map<String, String> artifacts = methods.stream()
                .collect(Collectors.toMap(Method::getName, Method::getArtifact));

        Assert.assertTrue(ArtifactTags.hasTag(
                artifacts.get("testDelegationTokenIdentiferSerializationRoundTrip"),
                "test-helper-method"
        ));
        Assert.assertFalse(ArtifactTags.hasTag(
                artifacts.get("testDelegationTokenIdentiferSerializationRoundTrip"),
                "test-case-method"
        ));
        Assert.assertTrue(ArtifactTags.hasTag(
                artifacts.get("testPublicNamingConvention"),
                "test-helper-method"
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
                    @Test
                    public void publicAnnotatedTest() {
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

        Map<String, ArtifactClassification> testMethods = methodsByName(detector, testFile);

        assertHas(testMethods, "testDelegationTokenIdentiferSerializationRoundTrip", "test-helper-method");
        assertHas(testMethods, "testPublicNamingConvention", "test-helper-method");
        assertHas(testMethods, "privateAnnotatedTest", "test-helper-method");
        assertHas(testMethods, "publicAnnotatedTest", "test-case-method");
        assertHas(testMethods, "setUp", "test-fixture-method");
        Assert.assertNotNull(testMethods.get("setUp").startLine());
        Assert.assertNotNull(testMethods.get("setUp").endLine());

        ArtifactClassification productionMethod = detector.classifyMethodArtifacts(mainFile, "demo").get(0);
        Assert.assertEquals("shouldRetry", productionMethod.methodName());
        Assert.assertEquals("#main-code", productionMethod.encodedArtifact());
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

        Map<String, ArtifactClassification> methods = methodsByName(TestArtifactDetector.load(repo, "demo", null), testFile);

        assertHas(methods, "ru", "test-case-method");
        assertHas(methods, "helper", "test-helper-method");
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
        Assert.assertEquals("#main-code", source.encodedArtifact());
        Assert.assertFalse(source.isResource());

        ArtifactClassification testResource = detector.classify(testResourceFile, "");
        Assert.assertEquals("#test-resource", testResource.encodedArtifact());
        Assert.assertTrue(testResource.isResource());
    }

    private static Map<String, ArtifactClassification> classifyTestSource(String source) throws Exception {
        Path repo = Files.createTempDirectory("artifact-detection-source");
        Path testSource = Files.createDirectories(repo.resolve("src/test/java/demo"));
        Path testFile = testSource.resolve("GeneratedTest.java");
        Files.writeString(testFile, source);
        return methodsByName(TestArtifactDetector.load(repo, "demo", null), testFile);
    }

    private static Map<String, ArtifactClassification> methodsByName(TestArtifactDetector detector, Path testFile) {
        return detector.classifyMethodArtifacts(testFile, "demo")
                .stream()
                .collect(Collectors.toMap(ArtifactClassification::methodName, classification -> classification, (a, b) -> a));
    }

    private static void assertHas(Map<String, ArtifactClassification> methods, String methodName, String tag) {
        Assert.assertTrue(methodName + " should have " + tag,
                ArtifactTags.hasTag(methods.get(methodName).encodedArtifact(), tag));
    }

    private static void assertNotHas(Map<String, ArtifactClassification> methods, String methodName, String tag) {
        Assert.assertFalse(methodName + " should not have " + tag,
                ArtifactTags.hasTag(methods.get(methodName).encodedArtifact(), tag));
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
