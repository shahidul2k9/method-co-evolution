package rnd.method.parser.call.graph;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.resolution.UnsolvedSymbolException;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.api.errors.InvalidRemoteException;
import org.eclipse.jgit.api.errors.GitAPIException;
import org.eclipse.jgit.lib.ObjectId;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.model.MethodCall;

import java.io.BufferedReader;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

@Slf4j
public class MethodParserUtil {
    private static final int MAX_PACKAGE_SCAN_LINES = 120;
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
        return findAllJavaSourceRootsFromPackageDeclarations(repoRoot);
    }

    public static List<Path> findAllJavaSourceRootsFromPackageDeclarations(Path repoRoot) {
        List<Path> javaFiles;
        try (Stream<Path> stream = Files.walk(repoRoot)) {
            javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(MethodParserUtil::isJavaFile)
                    .filter(path -> !containsExcludedDirectory(path))
                    .sorted()
                    .toList();
        } catch (IOException ignored) {
            return List.of();
        }

        Set<Path> sourceRoots = new LinkedHashSet<>();
        Map<Path, Path> packageDirectoryRoots = new HashMap<>();

        for (Path javaFile : javaFiles) {
            Path packageDirectory = javaFile.getParent();
            Path cachedRoot = packageDirectoryRoots.get(packageDirectory);
            if (cachedRoot != null) {
                sourceRoots.add(cachedRoot);
                continue;
            }

            Optional<String> packageName = extractPackageName(javaFile);
            Path sourceRoot = inferSourceRootFromPackage(javaFile, packageName);
            sourceRoots.add(sourceRoot);
            packageDirectoryRoots.put(packageDirectory, sourceRoot);
        }

        return deduplicateRoots(new ArrayList<>(sourceRoots));
    }

    private static boolean isJavaFile(Path path) {
        return path.toString().endsWith(".java");
    }

    private static boolean containsExcludedDirectory(Path path) {
        for (Path element : path) {
            if (EXCLUDED_DIRS.contains(element.toString())) {
                return true;
            }
        }
        return false;
    }

    private static Optional<String> extractPackageName(Path javaFile) {
        Optional<String> packageFromParser = extractPackageNameWithJavaParser(javaFile);
        if (packageFromParser.isPresent()) {
            return packageFromParser;
        }
        return extractPackageNameFromFileHeader(javaFile);
    }

    private static Optional<String> extractPackageNameWithJavaParser(Path javaFile) {
        try {
            ParseResult<CompilationUnit> result = new JavaParser().parse(javaFile);
            if (!result.isSuccessful() || result.getResult().isEmpty()) {
                return Optional.empty();
            }

            return result.getResult()
                    .flatMap(CompilationUnit::getPackageDeclaration)
                    .map(packageDeclaration -> packageDeclaration.getName().asString())
                    .filter(packageName -> !packageName.isBlank());
        } catch (Exception ignored) {
            return Optional.empty();
        }
    }

    private static Optional<String> extractPackageNameFromFileHeader(Path javaFile) {
        try (BufferedReader reader = Files.newBufferedReader(javaFile, StandardCharsets.UTF_8)) {
            String line;
            int linesRead = 0;
            while ((line = reader.readLine()) != null && linesRead++ < MAX_PACKAGE_SCAN_LINES) {
                String trimmed = line.trim();
                if (trimmed.isEmpty() || trimmed.startsWith("//") || trimmed.startsWith("/*") || trimmed.startsWith("*")) {
                    continue;
                }
                if (trimmed.startsWith("package ") && trimmed.endsWith(";")) {
                    String packageName = trimmed.substring("package ".length(), trimmed.length() - 1).trim();
                    if (!packageName.isBlank()) {
                        return Optional.of(packageName);
                    }
                }
                if (trimmed.startsWith("import ") || trimmed.startsWith("class ") || trimmed.startsWith("interface ") || trimmed.startsWith("enum ") || trimmed.startsWith("record ") || trimmed.startsWith("@")) {
                    break;
                }
            }
        } catch (IOException ignored) {
            return Optional.empty();
        }
        return Optional.empty();
    }

    private static Path inferSourceRootFromPackage(Path javaFile, Optional<String> packageName) {
        Path packageDirectory = javaFile.getParent();
        if (packageName.isEmpty()) {
            return packageDirectory;
        }

        String[] packageParts = packageName.get().split("\\.");
        Path sourceRoot = packageDirectory;
        for (int i = packageParts.length - 1; i >= 0; i--) {
            if (sourceRoot == null || !sourceRoot.getFileName().toString().equals(packageParts[i])) {
                return packageDirectory;
            }
            sourceRoot = sourceRoot.getParent();
        }

        return sourceRoot != null ? sourceRoot : packageDirectory;
    }

    public static void prepareRepositoryForCommit(String repositoryUrl, String repositoryPath, String commitHash) {
        if (commitHash == null || commitHash.isBlank()) {
            throw new IllegalArgumentException("Commit hash is required");
        }

        Path path = Paths.get(repositoryPath);
        Path gitDirectory = path.resolve(".git");

        if (Files.exists(path) && !Files.isDirectory(path)) {
            throw new IllegalStateException("Repository path exists and is not a directory: " + repositoryPath);
        }

        try (Git git = Files.exists(gitDirectory) && Files.isDirectory(gitDirectory)
                ? Git.open(path.toFile())
                : cloneRepository(repositoryUrl, path, repositoryPath)) {

            ObjectId resolvedCommit = git.getRepository().resolve(commitHash);
            if (resolvedCommit == null) {
                throw new IllegalArgumentException("Unable to resolve commit hash: " + commitHash);
            }

            git.checkout()
                    .setName(resolvedCommit.getName())
                    .setForced(true)
                    .call();

            ObjectId headCommit = git.getRepository().resolve("HEAD");
            if (headCommit == null || !headCommit.getName().equals(resolvedCommit.getName())) {
                throw new IllegalStateException("Repository checkout failed for commit: " + commitHash);
            }
        } catch (IOException | GitAPIException exception) {
            throw new IllegalStateException("Failed to prepare repository at " + repositoryPath + " for commit " + commitHash, exception);
        }
    }

    private static Git cloneRepository(String repositoryUrl, Path path, String repositoryPath) {
        try {
            if (Files.exists(path) && Files.isDirectory(path)) {
                try (Stream<Path> children = Files.list(path)) {
                    if (children.findAny().isPresent()) {
                        throw new IllegalStateException("Repository path is not a Git repository: " + repositoryPath);
                    }
                }
            }

            Path parent = path.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }

            return Git.cloneRepository()
                    .setURI(repositoryUrl)
                    .setDirectory(path.toFile())
                    .call();
        } catch (InvalidRemoteException exception) {
            throw new IllegalStateException("Invalid repository URL: " + repositoryUrl, exception);
        } catch (GitAPIException | IOException exception) {
            throw new IllegalStateException("Failed to clone repository " + repositoryUrl + " to " + repositoryPath, exception);
        }
    }

    private static List<Path> deduplicateRoots(List<Path> roots) {
        Set<String> takenSourceDirectory = new HashSet<>();
        List<Path> result = new ArrayList<>();
        for (Path root : roots) {
            String directory = root.toAbsolutePath().toString();
            if (!takenSourceDirectory.contains(directory)) {
                result.add(root);
                takenSourceDirectory.add(directory);
            }
        }
        return result;
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


    public static String extractRepositoryName(String repoUrl) {
        if (repoUrl == null || repoUrl.isBlank()) {
            return null;
        }

        try {
            String path = URI.create(repoUrl).getPath();   // e.g. /google/gson or /apache/commons-lang.git
            if (path == null || path.isBlank()) {
                return null;
            }

            String[] parts = path.replaceAll("/+$", "").split("/");
            String repoName = parts[parts.length - 1];

            if (repoName.endsWith(".git")) {
                repoName = repoName.substring(0, repoName.length() - 4);
            }

            return repoName;
        } catch (Exception e) {
            return null;
        }
    }

    public static String getMethodFqnSimpleParams(MethodDeclaration methodDeclaration) {
        String classFqn = getDeclaringTypeFqnSafe(methodDeclaration);
        String methodName = methodDeclaration.getNameAsString();

        String params = IntStream.range(0, methodDeclaration.getParameters().size())
                .mapToObj(i -> getSimpleParamTypeSafe(methodDeclaration, i))
                .collect(Collectors.joining(", "));

        return classFqn + "." + methodName + "(" + params + ")";
    }

    private static String getDeclaringTypeFqnSafe(MethodDeclaration methodDeclaration) {
        // Prefer AST-based FQN because it is much more robust than full symbol resolution
        String astFqn = getAstDeclaringTypeFqn(methodDeclaration);
        if (astFqn != null && !astFqn.isBlank()) {
            return astFqn;
        }

        // Fallback to symbol solver if AST path somehow fails
        try {
            return methodDeclaration.resolve().declaringType().getQualifiedName();
        } catch (Exception e) {
            return "<UNKNOWN_CLASS>";
        }
    }

    private static String getAstDeclaringTypeFqn(MethodDeclaration methodDeclaration) {
        Optional<CompilationUnit> cuOpt = methodDeclaration.findCompilationUnit();
        String packageName = cuOpt
                .flatMap(CompilationUnit::getPackageDeclaration)
                .map(pd -> pd.getNameAsString())
                .orElse("");

        Deque<String> typeNames = new ArrayDeque<>();

        TypeDeclaration<?> current = methodDeclaration.findAncestor(TypeDeclaration.class).orElse(null);
        while (current != null) {
            typeNames.push(current.getNameAsString());
            current = current.findAncestor(TypeDeclaration.class).orElse(null);
        }

        String typePath = String.join(".", typeNames);

        if (!packageName.isEmpty() && !typePath.isEmpty()) {
            return packageName + "." + typePath;
        }
        if (!typePath.isEmpty()) {
            return typePath;
        }
        return null;
    }

    private static String getSimpleParamTypeSafe(MethodDeclaration methodDeclaration, int paramIndex) {
        // First try resolved type
        try {
            String resolvedType = methodDeclaration.resolve().getParam(paramIndex).describeType();
            return toSimpleTypeName(resolvedType);
        } catch (UnsolvedSymbolException e) {
            // fallback to source text, e.g. "Address", "List<Address>", "Foo[]"
            return toSimpleTypeName(methodDeclaration.getParameter(paramIndex).getType().asString());
        } catch (Exception e) {
            return toSimpleTypeName(methodDeclaration.getParameter(paramIndex).getType().asString());
        }
    }

    private static String toSimpleTypeName(String typeName) {
        if (typeName == null || typeName.isBlank()) {
            return typeName;
        }

        typeName = typeName.trim();

        // varargs
        if (typeName.endsWith("...")) {
            String elementType = typeName.substring(0, typeName.length() - 3);
            return toSimpleTypeName(elementType) + "...";
        }

        // arrays
        if (typeName.endsWith("[]")) {
            String elementType = typeName.substring(0, typeName.length() - 2);
            return toSimpleTypeName(elementType) + "[]";
        }

        // remove generics: List<com.foo.Address> -> List
        int genericStart = typeName.indexOf('<');
        if (genericStart >= 0) {
            typeName = typeName.substring(0, genericStart);
        }

        // remove package: java.util.List -> List
        int lastDot = typeName.lastIndexOf('.');
        return lastDot >= 0 ? typeName.substring(lastDot + 1) : typeName;
    }
}
