package rnd.method.parser.call.graph.artifact;

public enum ArtifactTag {
    TEST_MODULE("test-module"),
    TEST_CODE("test-code"),
    TEST_METHOD("test-method"),
    TEST_UTILITY("test-utility"),
    TEST_FIXTURE("test-fixture"),
    TEST_UNIT("test-unit"),
    TEST_INTEGRATION("test-integration"),
    TEST_RESOURCE("test-resource"),
    PRODUCTION_RESOURCE("production-resource"),
    TEST_GENERATED("test-generated"),
    PRODUCTION_GENERATED("production-generated"),
    PRODUCTION_CODE("production-code");

    private final String value;

    ArtifactTag(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
