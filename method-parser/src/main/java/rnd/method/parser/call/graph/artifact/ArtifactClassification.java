package rnd.method.parser.call.graph.artifact;

import java.nio.file.Path;
import java.util.Collection;
import java.util.EnumSet;
import java.util.Set;

public final class ArtifactClassification {
    private final EnumSet<ArtifactTag> tags;
    private final Path moduleRoot;
    private final Path sourceRoot;
    private final String moduleName;
    private final String reason;
    private final String methodName;
    private final Integer startLine;
    private final Integer endLine;

    public ArtifactClassification(
            Collection<ArtifactTag> tags,
            Path moduleRoot,
            Path sourceRoot,
            String moduleName,
            String reason) {
        this(tags, moduleRoot, sourceRoot, moduleName, reason, null, null, null);
    }

    public ArtifactClassification(
            Collection<ArtifactTag> tags,
            Path moduleRoot,
            Path sourceRoot,
            String moduleName,
            String reason,
            String methodName,
            Integer startLine,
            Integer endLine) {
        this.tags = tags == null || tags.isEmpty()
                ? EnumSet.noneOf(ArtifactTag.class)
                : EnumSet.copyOf(tags);
        this.moduleRoot = moduleRoot;
        this.sourceRoot = sourceRoot;
        this.moduleName = moduleName;
        this.reason = reason;
        this.methodName = methodName;
        this.startLine = startLine;
        this.endLine = endLine;
    }

    public Set<ArtifactTag> tags() {
        return EnumSet.copyOf(tags);
    }

    public Path moduleRoot() {
        return moduleRoot;
    }

    public Path sourceRoot() {
        return sourceRoot;
    }

    public String moduleName() {
        return moduleName;
    }

    public String reason() {
        return reason;
    }

    public String methodName() {
        return methodName;
    }

    public Integer startLine() {
        return startLine;
    }

    public Integer endLine() {
        return endLine;
    }

    public String encodedArtifact() {
        return ArtifactTags.encode(tags);
    }

    public boolean hasTag(ArtifactTag tag) {
        return tags.contains(tag);
    }

    public boolean hasAny(ArtifactTag... candidates) {
        for (ArtifactTag candidate : candidates) {
            if (tags.contains(candidate)) {
                return true;
            }
        }
        return false;
    }

    public boolean isTestCode() {
        return tags.contains(ArtifactTag.TEST_CODE);
    }

    public boolean isResource() {
        return tags.contains(ArtifactTag.TEST_RESOURCE)
                || tags.contains(ArtifactTag.PRODUCTION_RESOURCE);
    }
}
