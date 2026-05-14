package rnd.method.parser.call.graph.artifact;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public final class ArtifactConfigLoader {
    private ArtifactConfigLoader() {
    }

    public static ArtifactDetectionConfig load(Path configPath) {
        ArtifactDetectionConfig config = new ArtifactDetectionConfig();
        if (configPath == null || !Files.exists(configPath)) {
            return config;
        }
        try {
            if (Files.isDirectory(configPath)) {
                try (Stream<Path> files = Files.list(configPath)) {
                    for (Path file : files
                            .filter(ArtifactConfigLoader::isYaml)
                            .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                            .toList()) {
                        parseFile(file, config);
                    }
                }
            } else if (isYaml(configPath)) {
                parseFile(configPath, config);
            }
            return config;
        } catch (IOException e) {
            throw new IllegalArgumentException("Unable to load artifact config from " + configPath, e);
        }
    }

    private static boolean isYaml(Path path) {
        String name = path.getFileName().toString().toLowerCase();
        return name.endsWith(".yml") || name.endsWith(".yaml");
    }

    private static void parseFile(Path file, ArtifactDetectionConfig config) throws IOException {
        List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
        String section = null;
        String project = null;
        String module = null;
        String pendingListKey = null;

        for (String raw : lines) {
            String noComment = stripComment(raw);
            if (noComment.isBlank()) {
                continue;
            }
            int indent = countIndent(noComment);
            String line = noComment.trim();
            if (line.endsWith(":") && !line.startsWith("-")) {
                String key = line.substring(0, line.length() - 1).trim();
                pendingListKey = null;
                if (indent == 0) {
                    section = key;
                    project = null;
                    module = null;
                } else if ("projects".equals(section) && indent == 2) {
                    project = key;
                    module = null;
                    config.projects.computeIfAbsent(project, ignored -> new ArtifactDetectionConfig.ProjectRuleSet());
                } else if ("projects".equals(section) && "modules".equals(key)) {
                    module = null;
                } else if ("projects".equals(section) && indent == 6 && project != null) {
                    module = key;
                    config.projects
                            .computeIfAbsent(project, ignored -> new ArtifactDetectionConfig.ProjectRuleSet())
                            .modules
                            .computeIfAbsent(module, ignored -> new ArtifactDetectionConfig.RuleSet());
                } else {
                    pendingListKey = key;
                }
                if (isRuleKey(key)) {
                    pendingListKey = key;
                }
            } else if (line.startsWith("- ") && pendingListKey != null) {
                String value = stripQuotes(line.substring(2).trim());
                String listKey = pendingListKey;
                ruleSet(config, section, project, module).ifPresent(rules -> addRuleValue(rules, listKey, value));
            }
        }
    }

    private static java.util.Optional<ArtifactDetectionConfig.RuleSet> ruleSet(
            ArtifactDetectionConfig config,
            String section,
            String project,
            String module) {
        if ("defaults".equals(section)) {
            return java.util.Optional.of(config.defaults);
        }
        if (!"projects".equals(section) || project == null) {
            return java.util.Optional.empty();
        }
        ArtifactDetectionConfig.ProjectRuleSet projectRules =
                config.projects.computeIfAbsent(project, ignored -> new ArtifactDetectionConfig.ProjectRuleSet());
        if (module != null) {
            return java.util.Optional.of(projectRules.modules.computeIfAbsent(module, ignored -> new ArtifactDetectionConfig.RuleSet()));
        }
        return java.util.Optional.of(projectRules);
    }

    private static boolean isRuleKey(String key) {
        return switch (key) {
            case "mainSourceRoots", "unitTestSourceRoots", "integrationTestSourceRoots",
                    "mainResourceRoots", "testResourceRoots", "generatedMainSourceRoots",
                    "generatedTestSourceRoots", "testModulePatterns", "docModulePatterns",
                    "documentationModulePatterns" -> true;
            default -> false;
        };
    }

    private static void addRuleValue(ArtifactDetectionConfig.RuleSet rules, String key, String value) {
        switch (key) {
            case "mainSourceRoots" -> add(rules.mainSourceRoots, value);
            case "unitTestSourceRoots" -> add(rules.unitTestSourceRoots, value);
            case "integrationTestSourceRoots" -> add(rules.integrationTestSourceRoots, value);
            case "mainResourceRoots" -> add(rules.mainResourceRoots, value);
            case "testResourceRoots" -> add(rules.testResourceRoots, value);
            case "generatedMainSourceRoots" -> add(rules.generatedMainSourceRoots, value);
            case "generatedTestSourceRoots" -> add(rules.generatedTestSourceRoots, value);
            case "testModulePatterns" -> add(rules.testModulePatterns, value);
            case "docModulePatterns", "documentationModulePatterns" -> add(rules.docModulePatterns, value);
            default -> {
            }
        }
    }

    private static void add(List<String> values, String value) {
        if (value != null && !value.isBlank() && !values.contains(value)) {
            values.add(value);
        }
    }

    private static String stripComment(String line) {
        int index = line.indexOf('#');
        return index >= 0 ? line.substring(0, index) : line;
    }

    private static int countIndent(String line) {
        int count = 0;
        while (count < line.length() && line.charAt(count) == ' ') {
            count++;
        }
        return count;
    }

    private static String stripQuotes(String value) {
        if (value.length() >= 2
                && ((value.startsWith("\"") && value.endsWith("\""))
                || (value.startsWith("'") && value.endsWith("'")))) {
            return value.substring(1, value.length() - 1);
        }
        return value;
    }
}
