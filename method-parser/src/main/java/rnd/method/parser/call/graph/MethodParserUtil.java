package rnd.method.parser.call.graph;

import lombok.extern.slf4j.Slf4j;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.model.MethodCall;
import tech.tablesaw.api.IntColumn;
import tech.tablesaw.api.StringColumn;
import tech.tablesaw.api.Table;
import tech.tablesaw.columns.Column;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.stream.Collectors;
import java.util.stream.Stream;

@Slf4j
public class MethodParserUtil {
    private static final List<String> JAVA_SOURCE_ROOT_SUFFIXES = List.of(
            // Standard Java
            "/src/main/java",
            "/src/test/java",
            "/src/integrationTest/java",
            "/src/java",
            "/java",

            // Android (Gradle / Studio)
            "/app/src/main/java",
            "/app/src/test/java",
            "/app/src/androidTest/java",
            "/src/androidTest/java",

            // Android (AOSP)
            "/frameworks/base/core/java",
            "/frameworks/base/java",
            "/frameworks/*/java",          // handled via traversal
            "/packages/apps",              // handled via traversal

            // Product / Legacy
            "/source/java",
            "/sources/java",
            "/code/java",
            "/modules/src",
            "/core/java"
    );
    private static final Set<String> EXCLUDED_DIRS = Set.of(
            ".git", ".gradle", ".idea", ".settings",
            "target", "build", "out",
            "node_modules", "dist",
            "generated", "gen", "external", "third_party"
    );


    public static List<String> scanJavaFiles(String repositoryPath, List<String> targetPaths) {
        List<String> files = new ArrayList<>();
        Path repoRoot = Paths.get(repositoryPath);

        for (String target : targetPaths) {
            Path path = repoRoot.resolve(target).normalize();
            if (Files.exists(path)) {
                try {
                    if (Files.isRegularFile(path) && path.toString().endsWith(".java")) {
                        files.add(path.toString());
                    } else if (Files.isDirectory(path)) {
                        Files.walk(path)
                                .filter(Files::isRegularFile)
                                .filter(p -> p.toString().endsWith(".java"))
                                .forEach(p -> files.add(p.toString()));
                    }
                } catch (IOException e) {
                    log.error("Failed to scan path {}", path, e);
                }
            }
        }
        Collections.sort(files);
        return files;
    }

    public static List<Path> findAllJavaSourceRoots(Path repoRoot) {
        List<Path> roots = new ArrayList<>();

        try {
            Files.walk(repoRoot)
                    .filter(Files::isDirectory)
                    .filter(MethodParserUtil::isCandidateSourceRoot)
                    .filter(MethodParserUtil::containsJavaFiles)
                    .forEach(roots::add);

        } catch (IOException ignored) {
        }

        return deduplicateRoots(roots);
    }

    private static boolean isCandidateSourceRoot(Path dir) {
        String path = dir.toString().replace("\\", "/");

        // Exclude build / generated / third-party dirs
        for (String excluded : EXCLUDED_DIRS) {
            if (path.contains("/" + excluded + "/")) {
                return false;
            }
        }

        // Direct suffix match
        for (String suffix : JAVA_SOURCE_ROOT_SUFFIXES) {
            if (!suffix.contains("*") && path.endsWith(suffix)) {
                return true;
            }
        }

        // Handle wildcard-style Android / product layouts
        return matchesWildcardSourceRoot(path);
    }

    private static boolean containsJavaFiles(Path dir) {
        try {
            return Files.walk(dir)
                    .anyMatch(p -> Files.isRegularFile(p) && p.toString().endsWith(".java"));
        } catch (IOException e) {
            return false;
        }
    }

    private static List<Path> deduplicateRoots(List<Path> roots) {
        roots.sort(Comparator.comparingInt(p -> p.getNameCount()));

        List<Path> result = new ArrayList<>();

        for (Path root : roots) {
            if (result.stream().noneMatch(r -> root.startsWith(r))) {
                result.add(root);
            }
        }
        return result;
    }


    private static boolean matchesWildcardSourceRoot(String path) {

        // frameworks/<anything>/java
        if (path.contains("/frameworks/") && path.endsWith("/java")) {
            return true;
        }

        // packages/apps/<app>/src
        if (path.contains("/packages/apps/") && path.endsWith("/src")) {
            return true;
        }

        // src/<anything>/java  (Gradle variants)
        if (path.contains("/src/") && path.endsWith("/java")) {
            return true;
        }

        return false;
    }


    public static String toMethodUrl(String repositoryUrl, String commitHash, String file, Integer lineNumber) {
        return repositoryUrl + "/blob/" + commitHash + "/" + file + (lineNumber != null ? "#L" + lineNumber : "");
    }

    public static String stripFilePrefix(String prefix, String text) {
        if (text.startsWith(prefix)) {
            String fileSuffix = text.substring(prefix.length());
            if (fileSuffix.startsWith("/")) {
                return fileSuffix.substring(1);
            } else {
                return fileSuffix;
            }
        } else {
            return text;
        }
    }

    public static void toTable(List<MethodCall> methodCalls, String outputPath, boolean isFanIn) {
        String focalMethodPrefix = isFanIn ? "caller_" : "callee_";
        String otherMethodPrefix = isFanIn ? "callee_" : "caller_";
        StringColumn focalMethodNameColumn = StringColumn.create(focalMethodPrefix + "name");
        IntColumn focalMethodStartLineColumn = IntColumn.create(focalMethodPrefix + "start");
        IntColumn focalMethodEndLineColumn = IntColumn.create(focalMethodPrefix + "end");
        StringColumn focalMethodFileColumn = StringColumn.create(focalMethodPrefix + "file");
        StringColumn focalMethodUrlColumn = StringColumn.create(focalMethodPrefix + "url");

        StringColumn otherMethodNameColumn = StringColumn.create(otherMethodPrefix + "name");
        IntColumn otherMethodStartLineColumn = IntColumn.create(otherMethodPrefix + "start");
        IntColumn otherMethodEndLineColumn = IntColumn.create(otherMethodPrefix + "end");
        StringColumn otherMethodFileColumn = StringColumn.create(otherMethodPrefix + "file");
        StringColumn otherMethodUrlColumn = StringColumn.create(otherMethodPrefix + "url");
        List<Column<?>> focalMethodColumns = Arrays.asList(focalMethodNameColumn, focalMethodStartLineColumn, focalMethodEndLineColumn, focalMethodFileColumn, focalMethodUrlColumn);
        List<Column<?>> otherMethodColumns = List.of(otherMethodNameColumn, otherMethodStartLineColumn, otherMethodEndLineColumn, otherMethodFileColumn, otherMethodUrlColumn);
        Table table = Table.create(isFanIn ? Stream.concat(focalMethodColumns.stream(), otherMethodColumns.stream()).toList() : Stream.concat(otherMethodColumns.stream(), focalMethodColumns.stream()).toList());
        for (MethodCall methodCall : methodCalls) {
            Method focalMethod = methodCall.getMethod();
            for (Method otherMethod : methodCall.getFanMethods()) {
                focalMethodNameColumn.append(focalMethod.getName());
                focalMethodStartLineColumn.append(focalMethod.getStartLine());
                focalMethodEndLineColumn.append(focalMethod.getEndLine());
                focalMethodFileColumn.append(focalMethod.getFile());
                focalMethodUrlColumn.append(focalMethod.getUrl());

                otherMethodNameColumn.append(otherMethod.getName());
                otherMethodStartLineColumn.append(otherMethod.getStartLine());
                otherMethodEndLineColumn.append(otherMethod.getEndLine());
                otherMethodFileColumn.append(otherMethod.getFile());
                otherMethodUrlColumn.append(otherMethod.getUrl());

            }

        }
        boolean mkdirs = new File(outputPath).getParentFile().mkdirs();
        table.write().csv(outputPath);
    }

    public static List<MethodCall> fanInFromFanOut(List<MethodCall> methodCallOutList) {
        Map<String, List<Method>> fanIn = new HashMap<>();
        Map<String, Method> methodMap = new HashMap<>();
        for (MethodCall methodCall : methodCallOutList) {
            Method caller = methodCall.getMethod();
            for (Method callee : methodCall.getFanMethods()) {
                fanIn.putIfAbsent(callee.getUrl(), new ArrayList<>());
                methodMap.putIfAbsent(callee.getUrl(), callee);
                fanIn.get(callee.getUrl()).add(caller);
            }
        }
        return fanIn.entrySet().stream().map(entry -> MethodCall.builder()
                        .method(methodMap.get(entry.getKey()))
                        .fanMethods(entry.getValue())
                        .build())
                .collect(Collectors.toCollection(ArrayList::new));
    }

}
