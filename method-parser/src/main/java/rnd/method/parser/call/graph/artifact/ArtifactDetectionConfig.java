package rnd.method.parser.call.graph.artifact;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class ArtifactDetectionConfig {
    public final RuleSet defaults = RuleSet.defaults();
    public final Map<String, ProjectRuleSet> projects = new LinkedHashMap<>();

    public RuleSet rulesForProject(String repositoryName) {
        RuleSet merged = defaults.copy();
        ProjectRuleSet project = projects.get(repositoryName);
        if (project != null) {
            merged.merge(project);
        }
        return merged;
    }

    public RuleSet rulesForModule(String repositoryName, String moduleName) {
        RuleSet merged = rulesForProject(repositoryName);
        ProjectRuleSet project = projects.get(repositoryName);
        if (project != null && moduleName != null) {
            RuleSet module = project.modules.get(moduleName);
            if (module != null) {
                merged.merge(module);
            }
        }
        return merged;
    }

    public static class ProjectRuleSet extends RuleSet {
        public final Map<String, RuleSet> modules = new LinkedHashMap<>();
    }

    public static class RuleSet {
        public final List<String> mainSourceRoots = new ArrayList<>();
        public final List<String> unitTestSourceRoots = new ArrayList<>();
        public final List<String> integrationTestSourceRoots = new ArrayList<>();
        public final List<String> mainResourceRoots = new ArrayList<>();
        public final List<String> testResourceRoots = new ArrayList<>();
        public final List<String> generatedMainSourceRoots = new ArrayList<>();
        public final List<String> generatedTestSourceRoots = new ArrayList<>();
        public final List<String> testModulePatterns = new ArrayList<>();
        public final List<String> docModulePatterns = new ArrayList<>();
        public final List<String> testMethodAnnotations = new ArrayList<>();
        public final List<String> fixtureMethodAnnotations = new ArrayList<>();
        public final List<String> legacyTestCaseSuperclasses = new ArrayList<>();
        public final List<String> legacyTestMethodNamePrefixes = new ArrayList<>();
        public final List<String> testClassContextAnnotations = new ArrayList<>();

        public static RuleSet defaults() {
            RuleSet rules = new RuleSet();
            rules.mainSourceRoots.addAll(List.of("src/main/java", "src"));
            rules.unitTestSourceRoots.addAll(List.of(
                    "src/test/java", "src/androidTest/java", "src/androidTest", "src/test",
                    "src/tests/junit", "test", "tests", "tst", "testSrc"
            ));
            rules.integrationTestSourceRoots.addAll(List.of("src/integrationTest/java", "src/it/java", "integrationTest", "it", "itest", "exttst"));
            rules.mainResourceRoots.addAll(List.of("src/main/resources", "resources"));
            rules.testResourceRoots.addAll(List.of("src/test/resources", "src/integrationTest/resources", "test-resources", "testData", "tst-rsrc"));
            rules.generatedMainSourceRoots.addAll(List.of("target/generated-sources", "build/generated/sources/main", "build/generated/sources/annotationProcessor/java/main"));
            rules.generatedTestSourceRoots.addAll(List.of("target/generated-test-sources", "testGen", "build/generated/sources/test", "build/generated/sources/annotationProcessor/java/test"));
            rules.testModulePatterns.addAll(List.of("*.test", "*.tests", "*-test", "*-tests", "test", "tests", "integrationtest", "integration-test"));
            rules.docModulePatterns.addAll(List.of("documentation", "docs"));
            rules.testMethodAnnotations.addAll(List.of(
                    "org.junit.Test",
                    "org.junit.jupiter.api.Test",
                    "org.junit.jupiter.params.ParameterizedTest",
                    "org.junit.jupiter.api.ParameterizedTest",
                    "org.junit.jupiter.api.RepeatedTest",
                    "org.junit.jupiter.api.TestFactory",
                    "org.junit.jupiter.api.TestTemplate",
                    "org.junit.experimental.theories.Theory",
                    "org.testng.annotations.Test",
                    "org.testng.annotations.Factory",
                    "net.jqwik.api.Property",
                    "net.jqwik.api.Example"
            ));
            rules.fixtureMethodAnnotations.addAll(List.of(
                    "org.junit.Before",
                    "org.junit.After",
                    "org.junit.BeforeClass",
                    "org.junit.AfterClass",
                    "org.junit.jupiter.api.BeforeEach",
                    "org.junit.jupiter.api.AfterEach",
                    "org.junit.jupiter.api.BeforeAll",
                    "org.junit.jupiter.api.AfterAll",
                    "org.testng.annotations.BeforeSuite",
                    "org.testng.annotations.AfterSuite",
                    "org.testng.annotations.BeforeTest",
                    "org.testng.annotations.AfterTest",
                    "org.testng.annotations.BeforeGroups",
                    "org.testng.annotations.AfterGroups",
                    "org.testng.annotations.BeforeClass",
                    "org.testng.annotations.AfterClass",
                    "org.testng.annotations.BeforeMethod",
                    "org.testng.annotations.AfterMethod",
                    "net.jqwik.api.lifecycle.BeforeContainer",
                    "net.jqwik.api.lifecycle.AfterContainer",
                    "net.jqwik.api.lifecycle.BeforeProperty",
                    "net.jqwik.api.lifecycle.AfterProperty",
                    "net.jqwik.api.lifecycle.BeforeExample",
                    "net.jqwik.api.lifecycle.AfterExample",
                    "net.jqwik.api.lifecycle.BeforeTry",
                    "net.jqwik.api.lifecycle.AfterTry"
            ));
            rules.legacyTestCaseSuperclasses.addAll(List.of(
                    "junit.framework.TestCase",
                    "android.test.AndroidTestCase",
                    "android.test.InstrumentationTestCase"
            ));
            rules.legacyTestMethodNamePrefixes.add("test");
            rules.testClassContextAnnotations.addAll(List.of(
                    "org.junit.jupiter.api.extension.ExtendWith",
                    "org.junit.runner.RunWith",
                    "org.mockito.junit.jupiter.MockitoSettings",
                    "org.mockito.Mock",
                    "org.mockito.Spy",
                    "org.mockito.InjectMocks",
                    "org.mockito.Captor"
            ));
            return rules;
        }

        public RuleSet copy() {
            RuleSet copy = new RuleSet();
            copy.merge(this);
            return copy;
        }

        public void merge(RuleSet other) {
            addAll(mainSourceRoots, other.mainSourceRoots);
            addAll(unitTestSourceRoots, other.unitTestSourceRoots);
            addAll(integrationTestSourceRoots, other.integrationTestSourceRoots);
            addAll(mainResourceRoots, other.mainResourceRoots);
            addAll(testResourceRoots, other.testResourceRoots);
            addAll(generatedMainSourceRoots, other.generatedMainSourceRoots);
            addAll(generatedTestSourceRoots, other.generatedTestSourceRoots);
            addAll(testModulePatterns, other.testModulePatterns);
            addAll(docModulePatterns, other.docModulePatterns);
            addAll(testMethodAnnotations, other.testMethodAnnotations);
            addAll(fixtureMethodAnnotations, other.fixtureMethodAnnotations);
            addAll(legacyTestCaseSuperclasses, other.legacyTestCaseSuperclasses);
            addAll(legacyTestMethodNamePrefixes, other.legacyTestMethodNamePrefixes);
            addAll(testClassContextAnnotations, other.testClassContextAnnotations);
        }

        private void addAll(List<String> target, List<String> source) {
            for (String value : source) {
                if (value != null && !value.isBlank() && !target.contains(value)) {
                    target.add(value);
                }
            }
        }
    }
}
