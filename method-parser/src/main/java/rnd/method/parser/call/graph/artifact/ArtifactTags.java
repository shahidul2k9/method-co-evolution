package rnd.method.parser.call.graph.artifact;

import java.util.Arrays;
import java.util.Collection;
import java.util.EnumSet;
import java.util.Set;
import java.util.stream.Collectors;

public final class ArtifactTags {
    private static final ArtifactTag[] ORDER = {
            ArtifactTag.TEST_MODULE,
            ArtifactTag.TEST_CODE,
            ArtifactTag.TEST_UNIT,
            ArtifactTag.TEST_INTEGRATION,
            ArtifactTag.TEST_METHOD,
            ArtifactTag.TEST_FIXTURE,
            ArtifactTag.TEST_UTILITY,
            ArtifactTag.TEST_RESOURCE,
            ArtifactTag.PRODUCTION_RESOURCE,
            ArtifactTag.TEST_GENERATED,
            ArtifactTag.PRODUCTION_GENERATED,
            ArtifactTag.PRODUCTION_CODE,
    };

    private ArtifactTags() {
    }

    public static String encode(Collection<ArtifactTag> tags) {
        if (tags == null || tags.isEmpty()) {
            return "";
        }
        return Arrays.stream(ORDER)
                .filter(tags::contains)
                .map(ArtifactTag::value)
                .map(tag -> "#" + tag)
                .collect(Collectors.joining(" "));
    }

    public static boolean hasTag(String artifact, String tag) {
        if (artifact == null || artifact.isBlank() || tag == null || tag.isBlank()) {
            return false;
        }
        String normalizedTag = normalize(tag);
        return Arrays.stream(artifact.trim().split("\\s+"))
                .flatMap(token -> Arrays.stream(token.split("#")))
                .map(ArtifactTags::normalize)
                .anyMatch(normalizedTag::equals);
    }

    public static boolean hasTag(String artifact, ArtifactTag tag) {
        return tag != null && hasTag(artifact, tag.value());
    }

    public static boolean hasAny(String artifact, ArtifactTag... tags) {
        for (ArtifactTag tag : tags) {
            if (hasTag(artifact, tag)) {
                return true;
            }
        }
        return false;
    }

    public static Set<ArtifactTag> copyOf(Collection<ArtifactTag> tags) {
        if (tags == null || tags.isEmpty()) {
            return EnumSet.noneOf(ArtifactTag.class);
        }
        return EnumSet.copyOf(tags);
    }

    private static String normalize(String tag) {
        String normalized = tag == null ? "" : tag.trim();
        while (normalized.startsWith("#")) {
            normalized = normalized.substring(1);
        }
        return normalized;
    }
}
