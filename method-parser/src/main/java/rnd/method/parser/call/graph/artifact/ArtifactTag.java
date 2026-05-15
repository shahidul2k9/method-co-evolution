package rnd.method.parser.call.graph.artifact;

public enum ArtifactTag {
    TEST_MODULE("test-module"),
    DOC_MODULE("doc-module"),
    TEST_CODE("test-code"),
    MAIN_CODE("main-code"),
    TEST_CASE_METHOD("test-case-method"),
    TEST_HELPER_METHOD("test-helper-method"),
    TEST_FIXTURE_METHOD("test-fixture-method"),
    TEST_RESOURCE("test-resource"),
    MAIN_RESOURCE("main-resource"),
    TEST_CODE_GENERATED("test-code-generated"),
    MAIN_CODE_GENERATED("main-code-generated");

    private final String value;

    ArtifactTag(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
