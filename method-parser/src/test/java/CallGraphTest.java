import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.nodeTypes.NodeWithRange;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.resolution.model.SymbolReference;
import com.github.javaparser.symbolsolver.javaparsermodel.JavaParserFacade;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import lombok.extern.slf4j.Slf4j;
import org.eclipse.jgit.api.Git;
import org.jspecify.annotations.NonNull;
import org.junit.Assert;
import org.junit.Test;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.DynamicContainer;
import org.junit.jupiter.api.DynamicNode;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;
import rnd.method.parser.call.graph.util.MethodParserUtil;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.model.MethodCall;
import rnd.method.parser.call.graph.service.CallGraphServiceImpl;
import rnd.method.parser.call.graph.util.TableUtil;

import java.io.File;
import java.nio.file.Files;
import java.io.FileNotFoundException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;

/**
 * @author Shahidul Islam
 * @since 2025-12-23
 */
@Slf4j
public class CallGraphTest extends TestConfigurationBase {


    @Test
    public void testSymbolResolverTest() throws FileNotFoundException {
        JavaParser javaParser = new JavaParser();
        String repositoryDirectory = Paths.get(TestConfigurationBase.getEnv("ME_CACHE_DIRECTORY", DEFAULT_REPOSITORY_DIRECTORY), "repository/checkstyle").toString();
        Path target = Paths.get(repositoryDirectory, "src/main/java/com/puppycrawl/tools/checkstyle/AuditEventDefaultFormatter.java");
        org.junit.Assume.assumeTrue("checkstyle fixture repository is not available", Files.exists(target));

        ParseResult<CompilationUnit> cu = javaParser.parse(target.toFile());
        MethodDeclaration md = cu.getResult()
                .get()
                .findAll(MethodDeclaration.class)
                .stream()
                .filter(m -> m.getNameAsString().contains("getCheckShortName"))
                .findFirst()
                .get();
        MethodCallExpr mce = md.findAll(MethodCallExpr.class)
                .stream().filter(mc -> mc.getNameAsString().contains("getSourceName"))
                .findFirst()
                .get();
        List<Path> allJavaSourceRoots = MethodParserUtil.findAllJavaSourceRoots(Paths.get(repositoryDirectory));
        CombinedTypeSolver solver = new CombinedTypeSolver();

        for (Path path : allJavaSourceRoots) {
            solver.add(new JavaParserTypeSolver(path.toFile()));
        }
        SymbolReference<ResolvedMethodDeclaration> solve = JavaParserFacade.get(solver)
                .solve(mce);
        ResolvedMethodDeclaration resolved = solve.getCorrespondingDeclaration();


        Optional<MethodDeclaration> ast = resolved.toAst()
                .filter(MethodDeclaration.class::isInstance)
                .map(MethodDeclaration.class::cast);

        String filePath = ast
                .flatMap(m -> m.findCompilationUnit())
                .flatMap(c -> c.getStorage())
                .map(storage -> storage.getPath().toString())
                .map(file -> MethodParserUtil.stripFilePrefix(repositoryDirectory, file))
                .orElse("<external>");

        int startLine = ast
                .flatMap(NodeWithRange::getBegin)
                .map(p -> p.line)
                .orElse(-1);
        Assert.assertEquals(149, startLine);
        Assert.assertEquals("src/main/java/com/puppycrawl/tools/checkstyle/api/AuditEvent.java", filePath);
    }

    @org.junit.jupiter.api.Test
    void csvBoundedFallbackUsesExactClassFirst(@org.junit.jupiter.api.io.TempDir Path tempDir) throws Exception {
        FallbackFixture fixture = createFallbackFixture(tempDir, "import missing.Base; class Caller { Base target; void test(){ target.clear(); } }",
                List.of(row("Base", "missing.Base", ""), row("Child", "missing.Child", "missing.Base")),
                List.of(methodRow("clear", "method", "missing.Base.clear", "missing.Base.clear()", "src/main/java/missing/Base.java", 10),
                        methodRow("clear", "method", "missing.Child.clear", "missing.Child.clear()", "src/main/java/missing/Child.java", 20)));

        Assertions.assertEquals("missing.Base.clear", singleFallbackTarget(fixture).getFqn());
    }

    @org.junit.jupiter.api.Test
    void csvBoundedFallbackUsesClosestSubclassBeforeDeeperSubclass(@org.junit.jupiter.api.io.TempDir Path tempDir) throws Exception {
        FallbackFixture fixture = createFallbackFixture(tempDir, "import missing.Base; class Caller { Base target; void test(){ target.clear(); } }",
                List.of(row("Base", "missing.Base", ""), row("Child", "missing.Child", "missing.Base"), row("GrandChild", "missing.GrandChild", "missing.Child")),
                List.of(methodRow("clear", "method", "missing.Child.clear", "missing.Child.clear()", "src/main/java/missing/Child.java", 20),
                        methodRow("clear", "method", "missing.GrandChild.clear", "missing.GrandChild.clear()", "src/main/java/missing/GrandChild.java", 30)));

        Assertions.assertEquals("missing.Child.clear", singleFallbackTarget(fixture).getFqn());
    }

    @org.junit.jupiter.api.Test
    void csvBoundedFallbackUsesImplementorBeforeInterfaceAncestor(@org.junit.jupiter.api.io.TempDir Path tempDir) throws Exception {
        FallbackFixture fixture = createFallbackFixture(tempDir, "import missing.Service; class Caller { Service target; void test(){ target.build(); } }",
                List.of(row("Service", "missing.Service", ""), row("Impl", "missing.Impl", "missing.Service")),
                List.of(methodRow("build", "method", "missing.Impl.build", "missing.Impl.build()", "src/main/java/missing/Impl.java", 20)));

        Assertions.assertEquals("missing.Impl.build", singleFallbackTarget(fixture).getFqn());
    }

    @org.junit.jupiter.api.Test
    void csvBoundedFallbackUsesSuperclassAfterDownwardSearchFails(@org.junit.jupiter.api.io.TempDir Path tempDir) throws Exception {
        FallbackFixture fixture = createFallbackFixture(tempDir, "import missing.Child; class Caller { Child target; void test(){ target.get(); } }",
                List.of(row("Base", "missing.Base", ""), row("Child", "missing.Child", "missing.Base")),
                List.of(methodRow("get", "method", "missing.Base.get", "missing.Base.get()", "src/main/java/missing/Base.java", 10)));

        Assertions.assertEquals("missing.Base.get", singleFallbackTarget(fixture).getFqn());
    }

    @org.junit.jupiter.api.Test
    void csvBoundedFallbackUsesArityAtSameClassDistance(@org.junit.jupiter.api.io.TempDir Path tempDir) throws Exception {
        FallbackFixture fixture = createFallbackFixture(tempDir, "import missing.Service; class Caller { Service target; void test(){ target.get(1); } }",
                List.of(row("Service", "missing.Service", ""), row("ImplA", "missing.ImplA", "missing.Service"), row("ImplB", "missing.ImplB", "missing.Service")),
                List.of(methodRow("get", "method", "missing.ImplA.get", "missing.ImplA.get()", "src/main/java/missing/ImplA.java", 20),
                        methodRow("get", "method", "missing.ImplB.get", "missing.ImplB.get(int)", "src/main/java/missing/ImplB.java", 30)));

        Assertions.assertEquals("missing.ImplB.get", singleFallbackTarget(fixture).getFqn());
    }

    @org.junit.jupiter.api.Test
    void csvBoundedFallbackRejectsExternalOrUnrelatedNameOnlyMatches(@org.junit.jupiter.api.io.TempDir Path tempDir) throws Exception {
        FallbackFixture externalFixture = createFallbackFixture(tempDir.resolve("external"), "import missing.Base; class Caller { Base target; void test(){ target.toString(); } }",
                List.of(row("Caller", "demo.Caller", "")),
                List.of(methodRow("toString", "method", "java.lang.Object.toString", "java.lang.Object.toString()", "src/main/java/java/lang/Object.java", 1)));
        Assertions.assertTrue(fallbackTargets(externalFixture).isEmpty());

        FallbackFixture unrelatedFixture = createFallbackFixture(tempDir.resolve("unrelated"), "import missing.Base; class Caller { Base target; void test(){ target.clear(); } }",
                List.of(row("Base", "missing.Base", ""), row("Unrelated", "other.Unrelated", "")),
                List.of(methodRow("clear", "method", "other.Unrelated.clear", "other.Unrelated.clear()", "src/main/java/other/Unrelated.java", 20)));
        Assertions.assertTrue(fallbackTargets(unrelatedFixture).isEmpty());
    }

    @org.junit.jupiter.api.Test
    void csvBoundedFallbackNormalizesGenericsAndInnerNames(@org.junit.jupiter.api.io.TempDir Path tempDir) throws Exception {
        FallbackFixture genericFixture = createFallbackFixture(tempDir.resolve("generic"), "import missing.Box; class Caller { Box<String> box; void test(){ box.size(); } }",
                List.of(row("Box", "missing.Box", "")),
                List.of(methodRow("size", "method", "missing.Box.size", "missing.Box.size()", "src/main/java/missing/Box.java", 10)));
        Assertions.assertEquals("missing.Box.size", singleFallbackTarget(genericFixture).getFqn());

        FallbackFixture innerFixture = createFallbackFixture(tempDir.resolve("inner"), "import missing.Outer; class Caller { Outer.Inner inner; void test(){ inner.build(); } }",
                List.of(row("Outer", "missing.Outer", ""), row("Inner", "missing.Outer.Inner", "")),
                List.of(methodRow("build", "method", "missing.Outer.Inner.build", "missing.Outer.Inner.build()", "src/main/java/missing/Outer.java", 20)));
        Assertions.assertEquals("missing.Outer.Inner.build", singleFallbackTarget(innerFixture).getFqn());
    }

    @org.junit.jupiter.api.Test
    void classHierarchyCacheCanBeDisabledWithoutChangingFallback(@org.junit.jupiter.api.io.TempDir Path tempDir) throws Exception {
        FallbackFixture fixture = createFallbackFixture(tempDir, "import missing.Service; class Caller { Service target; void test(){ target.build(); } }",
                List.of(row("Service", "missing.Service", ""), row("Impl", "missing.Impl", "missing.Service")),
                List.of(methodRow("build", "method", "missing.Impl.build", "missing.Impl.build()", "src/main/java/missing/Impl.java", 20)));

        Assertions.assertEquals("missing.Impl.build", singleFallbackTarget(fixture, 0).getFqn());
    }

    @org.junit.jupiter.api.Test
    void classHierarchyCacheCanBeEnabledWithoutChangingFallback(@org.junit.jupiter.api.io.TempDir Path tempDir) throws Exception {
        FallbackFixture fixture = createFallbackFixture(tempDir, "import missing.Service; class Caller { Service target; void test(){ target.build(); target.build(); } }",
                List.of(row("Service", "missing.Service", ""), row("Impl", "missing.Impl", "missing.Service")),
                List.of(methodRow("build", "method", "missing.Impl.build", "missing.Impl.build()", "src/main/java/missing/Impl.java", 20)));

        List<Method> targets = fallbackTargets(fixture, 1);
        Assertions.assertEquals(List.of("missing.Impl.build", "missing.Impl.build"), targets.stream().map(Method::getFqn).toList());
    }


    @TestFactory
    public java.util.stream.Stream<DynamicNode> testCallGraph() throws java.io.IOException {
        String targetFile = TestConfigurationBase.getEnv("TEST_CONFIG_FILE", "");
        if (!targetFile.isBlank()) {
            return Stream.of(generateTestCases(targetFile));
        }
        if (!"true".equalsIgnoreCase(TestConfigurationBase.getEnv("RUN_CALLGRAPH_INTEGRATION", ""))) {
            return Stream.empty();
        }

        Path configDir = Paths.get("src/test/resources/call-graph");
        if (!Files.exists(configDir)) {
            return java.util.stream.Stream.empty();
        }

        List<DynamicNode> allTests;
        try (java.util.stream.Stream<Path> paths = Files.list(configDir)) {
            allTests = paths.filter(p -> p.getFileName().toString().endsWith(".json"))
                    .map(p -> {
                        String fileName = p.getFileName().toString();
                        String infix = fileName.replace(".json", "");
                        return (DynamicNode) DynamicContainer.dynamicContainer(
                                fileName,
                                java.util.stream.Stream.of(generateTestCases(infix))
                        );
                    })
                    .toList();
        }
        return allTests.stream();
    }

    private static @NonNull DynamicContainer generateTestCases(String fileNameInfix) {
        List<TestProjectConfig> configurations = TestConfigurationBase.loadConfigurations("call-graph", fileNameInfix);

        return DynamicContainer.dynamicContainer("call-graph-configs",
                configurations.stream().map(projectConfig -> DynamicContainer.dynamicContainer(projectConfig.name,
                        projectConfig.cases.stream().map(testCase -> {
                            java.util.List<DynamicNode> caseNodes = new java.util.ArrayList<>();
                            String outputDirectory = TestConfigurationBase.resolvePlaceholders(testCase.outputDirectory);
                            String fanOutFile = String.format(Locale.CANADA, "%s/callgraph/%s--%s--%s.csv", outputDirectory, projectConfig.name, testCase.name, projectConfig.commitHash);
                            String fanInFile = String.format(Locale.CANADA, "%s/fanin/%s--%s--%s.csv", outputDirectory, projectConfig.name, testCase.name, projectConfig.commitHash);
                            String methodMappingFile = TestConfigurationBase.getEnv(
                                    "METHOD_MAPPING_FILE",
                                    String.format(Locale.CANADA, "%s/data/method/%s.csv",
                                            TestConfigurationBase.getEnv("ME_CACHE_DIRECTORY", DEFAULT_REPOSITORY_DIRECTORY),
                                            projectConfig.name)
                            );
                            String classMappingFile = TestConfigurationBase.getEnv(
                                    "CLASS_MAPPING_FILE",
                                    String.format(Locale.CANADA, "%s/data/class/%s.csv",
                                            TestConfigurationBase.getEnv("ME_CACHE_DIRECTORY", DEFAULT_REPOSITORY_DIRECTORY),
                                            projectConfig.name)
                            );

                            caseNodes.add(DynamicTest.dynamicTest("Execution", () -> {
                                Path repositoryPath = Paths.get(TestConfigurationBase.resolvePlaceholders(projectConfig.repositoryPath));
                                org.junit.jupiter.api.Assumptions.assumeTrue(
                                        Files.exists(repositoryPath.resolve(".git")),
                                        "fixture repository is not available locally"
                                );
                                CallGraphServiceImpl scanner = CallGraphServiceImpl.getInstance();
                                scanner.init(
                                        TestConfigurationBase.resolvePlaceholders(projectConfig.repositoryUrl),
                                        repositoryPath.toString(),
                                        projectConfig.commitHash,
                                        methodMappingFile,
                                        classMappingFile
                                );
                                List<String> files = MethodParserUtil.scanJavaFiles(
                                        repositoryPath.toString(),
                                        List.of(testCase.targetPath)
                                );
                                String absRepoPath = repositoryPath.toFile().getAbsolutePath();
                                List<MethodCall> allResults = new ArrayList<>();
                                for (String absoluteFile : files) {
                                    String relFile = MethodParserUtil.stripFilePrefix(absRepoPath, new File(absoluteFile).getAbsolutePath());
                                    allResults.addAll(scanner.findCallgraph(relFile));
                                }
                                TableUtil.saveCallgraph(allResults, fanOutFile, fanInFile);
                                Assertions.assertFalse(allResults.isEmpty());
                            }));

                            if (testCase.asserts != null && !testCase.asserts.isEmpty()) {
                                for (int i = 0; i < testCase.asserts.size(); i++) {
                                    AssertionConfig assertionConfig = testCase.asserts.get(i);
                                    String testName = "Assertion " + (i + 1) + (assertionConfig.projection != null ? ": " + assertionConfig.projection : "");
                                    caseNodes.add(DynamicTest.dynamicTest(testName, () -> {
                                        org.junit.jupiter.api.Assumptions.assumeTrue(
                                                Files.exists(Paths.get(fanOutFile)),
                                                "callgraph output was not generated"
                                        );
                                        tech.tablesaw.api.Table table = tech.tablesaw.api.Table.read().csv(fanOutFile);
                                        tech.tablesaw.api.Table filtered = table;
                                        if (assertionConfig.projection != null) {
                                            for (java.util.Map.Entry<String, String> entry : assertionConfig.projection.entrySet()) {
                                                filtered = filtered.where(filtered.stringColumn(entry.getKey()).isEqualTo(entry.getValue()));
                                            }
                                        }

                                        if (assertionConfig.expected != null && assertionConfig.expected.size != null) {
                                            Assertions.assertEquals(assertionConfig.expected.size.intValue(), filtered.rowCount(), "Assertion failed for " + assertionConfig.projection);
                                        }
                                    }));
                                }
                            }

                            return DynamicContainer.dynamicContainer(testCase.name, caseNodes);
                        }))));
    }

    private static FallbackFixture createFallbackFixture(Path root, String callerSource, List<String> classRows, List<String> methodRows) throws Exception {
        Path repo = root.resolve("repo");
        Path caller = repo.resolve("src/test/java/demo/Caller.java");
        Files.createDirectories(caller.getParent());
        Files.writeString(caller, "package demo;\n" + callerSource + "\n");

        String commitHash;
        try (Git git = Git.init().setDirectory(repo.toFile()).call()) {
            git.add().addFilepattern(".").call();
            commitHash = git.commit().setMessage("fixture").setAuthor("Test", "test@example.com").call().getName();
        }

        Path methodCsv = root.resolve("data/method/demo.csv");
        Files.createDirectories(methodCsv.getParent());
        Files.writeString(methodCsv, String.join("\n",
                "project,name,url,artifact,start_line,end_line,expression,pkg,fqn,fqs,tctracer_fqs,testlinker_fqs,testlinker_fqp,file,abstract,parser,resolver,hash",
                String.join("\n", methodRows)) + "\n");

        Path classCsv = root.resolve("data/class/demo.csv");
        Files.createDirectories(classCsv.getParent());
        Files.writeString(classCsv, String.join("\n",
                "project,name,fqn,pkg,file,url,start_line,end_line,expression,artifact,abstract,parent_names,parent_fqns,hash",
                String.join("\n", classRows)) + "\n");

        return new FallbackFixture(repo, methodCsv, classCsv, commitHash);
    }

    private static String row(String name, String fqn, String parentFqns) {
        String parentNames = parentFqns == null || parentFqns.isBlank() ? "" : parentFqns.substring(parentFqns.lastIndexOf('.') + 1);
        return String.join(",",
                "demo",
                name,
                fqn,
                packageName(fqn),
                "src/main/java/" + fqn.replace('.', '/') + ".java",
                "https://example.test/blob/hash/src/main/java/" + fqn.replace('.', '/') + ".java#L1",
                "1",
                "50",
                "class",
                "production",
                "0",
                parentNames,
                parentFqns == null ? "" : parentFqns,
                "hash");
    }

    private static String methodRow(String name, String expression, String fqn, String fqs, String file, int startLine) {
        return String.join(",",
                "demo",
                name,
                "https://example.test/blob/hash/" + file + "#L" + startLine,
                "production",
                String.valueOf(startLine),
                String.valueOf(startLine + 5),
                expression,
                packageName(fqn),
                fqn,
                fqs,
                "",
                "",
                "",
                file,
                "0",
                "methodParser",
                "javaparser",
                "hash");
    }

    private static String packageName(String fqn) {
        int lastDot = fqn.lastIndexOf('.');
        if (lastDot < 0) {
            return "";
        }
        String owner = fqn.substring(0, lastDot);
        if (Character.isLowerCase(fqn.substring(lastDot + 1).charAt(0))) {
            int ownerDot = owner.lastIndexOf('.');
            return ownerDot < 0 ? "" : owner.substring(0, ownerDot);
        }
        return owner;
    }

    private static Method singleFallbackTarget(FallbackFixture fixture) {
        return singleFallbackTarget(fixture, 256);
    }

    private static Method singleFallbackTarget(FallbackFixture fixture, long maxCacheSizeMb) {
        List<Method> targets = fallbackTargets(fixture, maxCacheSizeMb);
        Assertions.assertEquals(1, targets.size());
        return targets.getFirst();
    }

    private static List<Method> fallbackTargets(FallbackFixture fixture) {
        return fallbackTargets(fixture, 256);
    }

    private static List<Method> fallbackTargets(FallbackFixture fixture, long maxCacheSizeMb) {
        CallGraphServiceImpl scanner = CallGraphServiceImpl.getInstance();
        scanner.configureCache(maxCacheSizeMb);
        scanner.init(
                "https://example.test/demo",
                fixture.repo().toString(),
                fixture.commitHash(),
                fixture.methodCsv().toString(),
                fixture.classCsv().toString()
        );
        return scanner.findCallgraph("src/test/java/demo/Caller.java").stream()
                .flatMap(methodCall -> methodCall.getFanMethods().stream())
                .filter(method -> "heuristics".equals(method.getResolver()))
                .sorted(Comparator.comparing(Method::getFqn, Comparator.nullsLast(String::compareTo)))
                .toList();
    }

    private record FallbackFixture(Path repo, Path methodCsv, Path classCsv, String commitHash) {
    }

}
