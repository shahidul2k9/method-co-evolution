import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class TestConfigurationBase {
    protected static final Pattern PLACEHOLDER_PATTERN = Pattern.compile("\\$\\{([^}]+)}");
    protected static final Path OPTIONAL_ENV_FILE = Paths.get("..", ".cache", ".env");
    protected static final String DEFAULT_REPOSITORY_DIRECTORY = "../.cache";
    protected static final Map<String, String> RESOLVED_ENV = TestConfigurationBase.loadEnvironmentVariables();


    static String resolvePlaceholders(String value) {
        Matcher matcher = PLACEHOLDER_PATTERN.matcher(value);
        StringBuilder resolved = new StringBuilder();

        while (matcher.find()) {
            String key = matcher.group(1);
            String replacement = getEnv(key, "METHOD_EVOLUTION_CACHE_DIRECTORY".equals(key) ? DEFAULT_REPOSITORY_DIRECTORY : "");
            matcher.appendReplacement(resolved, Matcher.quoteReplacement(replacement));
        }
        matcher.appendTail(resolved);
        return resolved.toString();
    }

    static List<TestProjectConfig> loadConfigurations(String resourceGroup, String fileNameInfix) {
        ObjectMapper objectMapper = new ObjectMapper();
        List<TestProjectConfig> configurations = new ArrayList<>();

        try (var jsonFiles = java.nio.file.Files.list(Paths.get("src/test/resources/" + resourceGroup))) {
            List<Path> configFiles = jsonFiles
                    .filter(path -> path.getFileName().toString().endsWith(".json") && (path.getFileName().toString().contains(fileNameInfix) || fileNameInfix.equalsIgnoreCase("all")))
                    .sorted()
                    .toList();

            for (Path configFile : configFiles) {
                try (InputStream inputStream = java.nio.file.Files.newInputStream(configFile)) {
                    Map<String, List<TestProjectConfig>> wrapper = objectMapper.readValue(inputStream,
                            new TypeReference<>() {
                            });
                    configurations.addAll(wrapper.getOrDefault("groups", List.of()));
                }
            }
        } catch (IOException exception) {
            throw new RuntimeException("Unable to read test run configuration", exception);
        }

        return configurations;
    }

    static String getEnv(String key, String defaultValue) {
        return RESOLVED_ENV.getOrDefault(key, defaultValue);
    }

    static Map<String, String> loadEnvironmentVariables() {
        Map<String, String> values = new HashMap<>(System.getenv());
        if (!Files.exists(OPTIONAL_ENV_FILE)) {
            return values;
        }

        try {
            for (String rawLine : Files.readAllLines(OPTIONAL_ENV_FILE)) {
                String line = rawLine.trim();
                if (line.isEmpty() || line.startsWith("#")) {
                    continue;
                }

                int splitIndex = line.indexOf('=');
                if (splitIndex <= 0) {
                    continue;
                }

                String key = line.substring(0, splitIndex).trim();
                if (key.isEmpty()) {
                    continue;
                }

                String parsedValue = stripWrappingQuotes(line.substring(splitIndex + 1).trim());
                values.putIfAbsent(key, parsedValue);
            }
        } catch (IOException exception) {
            throw new RuntimeException("Unable to read optional env file: " + OPTIONAL_ENV_FILE, exception);
        }

        return values;
    }

    private static String stripWrappingQuotes(String value) {
        if (value.length() >= 2 && ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'")))) {
            return value.substring(1, value.length() - 1);
        }
        return value;
    }




    public static class TestProjectConfig {
        public String name;
        public String repositoryUrl;
        public String repositoryPath;
        public String commitHash;
        public List<TestRunConfig> cases;
    }

    public static class TestRunConfig {
        public String name;
        public String targetPath;
        public String outputDirectory;
        public String fanOutFile;
    }
}
