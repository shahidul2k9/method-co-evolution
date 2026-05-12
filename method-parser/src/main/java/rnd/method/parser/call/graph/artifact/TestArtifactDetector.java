package rnd.method.parser.call.graph.artifact;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParseProblemException;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import rnd.method.parser.call.graph.util.JavaParserContext;

import javax.xml.parsers.DocumentBuilderFactory;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

public final class TestArtifactDetector {
    private static final Set<String> TEST_ANNOTATION_FQNS = Set.of(
            "org.junit.Test",
            "org.junit.Ignore",
            "org.junit.jupiter.api.Test",
            "org.junit.jupiter.api.ParameterizedTest",
            "org.junit.jupiter.api.RepeatedTest",
            "org.junit.jupiter.api.TestFactory",
            "org.junit.jupiter.api.TestTemplate",
            "org.junit.jupiter.api.TestClassOrder",
            "org.junit.jupiter.api.TestMethodOrder",
            "org.junit.jupiter.api.TestInstance",
            "org.junit.jupiter.api.DisplayName",
            "org.junit.jupiter.api.DisplayNameGeneration",
            "org.junit.jupiter.api.ParameterizedClass",
            "org.junit.jupiter.api.ClassTemplate",
            "org.junit.jupiter.api.Nested",
            "org.junit.jupiter.api.Tag",
            "org.junit.jupiter.api.Disabled",
            "org.junit.jupiter.api.AutoClose",
            "org.junit.jupiter.api.Timeout",
            "org.junit.jupiter.api.TempDir",
            "org.junit.jupiter.api.ExtendWith",
            "org.junit.jupiter.api.RegisterExtension",
            "org.junit.experimental.theories.Theory",
            "org.testng.annotations.Test",
            "org.testng.annotations.Factory"
    );

    private static final Set<String> FIXTURE_ANNOTATION_FQNS = Set.of(
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
            "org.testng.annotations.AfterMethod"
    );

    private static final Set<String> UNIT_TEST_SUPERCLASS_FQNS = Set.of(
            "junit.framework.TestCase",
            "android.test.AndroidTestCase",
            "android.test.InstrumentationTestCase"
    );

    private final Path repoRoot;
    private final String repositoryName;
    private final ArtifactDetectionConfig config;
    private final JavaParser parser;
    private final List<ModuleInfo> modules;

    private TestArtifactDetector(Path repoRoot, String repositoryName, ArtifactDetectionConfig config, JavaParser parser) {
        this.repoRoot = repoRoot.toAbsolutePath().normalize();
        this.repositoryName = repositoryName;
        this.config = config;
        this.parser = parser == null ? JavaParserContext.create(this.repoRoot).parser() : parser;
        this.modules = discoverModules();
    }

    public static TestArtifactDetector load(Path repoRoot, String repositoryName, Path configPath) {
        return new TestArtifactDetector(
                repoRoot,
                repositoryName,
                ArtifactConfigLoader.load(configPath),
                JavaParserContext.create(repoRoot).parser()
        );
    }

    public static TestArtifactDetector load(Path repoRoot, String repositoryName, Path configPath, JavaParser parser) {
        return new TestArtifactDetector(repoRoot, repositoryName, ArtifactConfigLoader.load(configPath), parser);
    }

    public ArtifactClassification classify(Path javaFile, String packageName) {
        Path absoluteFile = javaFile.toAbsolutePath().normalize();
        ModuleInfo module = nearestModule(absoluteFile).orElseGet(() -> syntheticRootModule());
        Path packageSourceRoot = packageSourceRoot(absoluteFile, packageName).orElse(null);

        EnumSet<ArtifactTag> tags = EnumSet.noneOf(ArtifactTag.class);
        Path matchedRoot = null;
        String reason = "fallback";

        if (module.testModule()) {
            tags.add(ArtifactTag.TEST_MODULE);
        }

        RootMatch generatedTest = longestMatch(absoluteFile, module.generatedTestSourceRoots());
        RootMatch generatedMain = longestMatch(absoluteFile, module.generatedMainSourceRoots());
        RootMatch unit = longestMatch(absoluteFile, module.unitTestSourceRoots());
        RootMatch integration = longestMatch(absoluteFile, module.integrationTestSourceRoots());
        RootMatch main = longestMatch(absoluteFile, module.mainSourceRoots());

        RootMatch testResource = longestMatch(absoluteFile, module.testResourceRoots());
        RootMatch mainResource = longestMatch(absoluteFile, module.mainResourceRoots());
        if (testResource.matched() && !sourceMatchAtLeastAsSpecific(testResource, generatedTest, generatedMain, unit, integration, main)) {
            addTestContext(tags, module);
            tags.add(ArtifactTag.TEST_RESOURCE);
            return classification(tags, module, testResource.root(), "test-resource-root");
        }
        if (mainResource.matched() && !sourceMatchAtLeastAsSpecific(mainResource, generatedTest, generatedMain, unit, integration, main)) {
            if (module.testModule()) {
                addTestContext(tags, module);
                tags.add(ArtifactTag.TEST_RESOURCE);
                return classification(tags, module, mainResource.root(), "test-module-main-resource-root");
            }
            tags.add(ArtifactTag.PRODUCTION_RESOURCE);
            return classification(tags, module, mainResource.root(), "main-resource-root");
        }

        if (generatedTest.matched()) {
            addTestContext(tags, module);
            tags.add(ArtifactTag.TEST_GENERATED);
            matchedRoot = generatedTest.root();
            reason = "generated-test-source-root";
        } else if (generatedMain.matched()) {
            if (module.testModule()) {
                addTestContext(tags, module);
                tags.add(ArtifactTag.TEST_GENERATED);
            } else {
                tags.add(ArtifactTag.PRODUCTION_CODE);
                tags.add(ArtifactTag.PRODUCTION_GENERATED);
            }
            matchedRoot = generatedMain.root();
            reason = "generated-main-source-root";
        }

        if (integration.matched()) {
            addTestContext(tags, module);
            tags.add(ArtifactTag.TEST_INTEGRATION);
            matchedRoot = integration.root();
            reason = "integration-test-source-root";
        } else if (unit.matched()) {
            addTestContext(tags, module);
            tags.add(ArtifactTag.TEST_UNIT);
            matchedRoot = unit.root();
            reason = "unit-test-source-root";
        } else if (main.matched()) {
            if (module.testModule()) {
                addTestContext(tags, module);
            } else {
                tags.add(ArtifactTag.PRODUCTION_CODE);
            }
            matchedRoot = main.root();
            reason = "main-source-root";
        } else if (packageSourceRoot != null) {
            RootKind inferred = inferRootKind(module, packageSourceRoot);
            switch (inferred) {
                case INTEGRATION -> {
                    addTestContext(tags, module);
                    tags.add(ArtifactTag.TEST_INTEGRATION);
                }
                case UNIT -> {
                    addTestContext(tags, module);
                    tags.add(ArtifactTag.TEST_UNIT);
                }
                case TEST_RESOURCE -> {
                    addTestContext(tags, module);
                    tags.add(ArtifactTag.TEST_RESOURCE);
                }
                case MAIN -> {
                    if (module.testModule()) {
                        addTestContext(tags, module);
                    } else {
                        tags.add(ArtifactTag.PRODUCTION_CODE);
                    }
                }
                default -> {
                    if (module.testModule()) {
                        addTestContext(tags, module);
                    } else {
                        tags.add(ArtifactTag.PRODUCTION_CODE);
                    }
                }
            }
            matchedRoot = packageSourceRoot;
            reason = "package-derived-source-root";
        } else if (module.testModule()) {
            addTestContext(tags, module);
            matchedRoot = module.moduleRoot();
            reason = "test-module-fallback";
        } else {
            tags.add(ArtifactTag.PRODUCTION_CODE);
            matchedRoot = module.moduleRoot();
            reason = "production-fallback";
        }

        return classification(tags, module, matchedRoot, reason);
    }

    private boolean sourceMatchAtLeastAsSpecific(RootMatch resourceMatch, RootMatch... sourceMatches) {
        if (!resourceMatch.matched()) {
            return false;
        }
        int resourceDepth = resourceMatch.root().getNameCount();
        for (RootMatch sourceMatch : sourceMatches) {
            if (sourceMatch.matched() && sourceMatch.root().getNameCount() >= resourceDepth) {
                return true;
            }
        }
        return false;
    }

    public boolean shouldScanMethods(Path javaFile, String packageName) {
        return !classify(javaFile, packageName).isResource();
    }

    public boolean shouldScanCallgraph(Path javaFile, String packageName) {
        return shouldScanMethods(javaFile, packageName);
    }

    public String classifyNodeArtifact(ArtifactClassification classification, Node node) {
        Set<ArtifactTag> tags = ArtifactTags.copyOf(classification.tags());

        if (classification.isTestCode()) {
            if (node instanceof MethodDeclaration method && isTestMethod(method, classification, false)) {
                tags.add(ArtifactTag.TEST_METHOD);
            } else if (node instanceof MethodDeclaration method && isFixtureMethod(method, classification, false)) {
                tags.add(ArtifactTag.TEST_FIXTURE);
            } else if (node instanceof ConstructorDeclaration constructor) {
                Optional<MethodDeclaration> parentMethod = constructor.findAncestor(MethodDeclaration.class);
                if (parentMethod.isPresent() && isTestMethod(parentMethod.get(), classification, false)) {
                    tags.add(ArtifactTag.TEST_METHOD);
                } else if (parentMethod.isPresent() && isFixtureMethod(parentMethod.get(), classification, false)) {
                    tags.add(ArtifactTag.TEST_FIXTURE);
                } else {
                    tags.add(ArtifactTag.TEST_UTILITY);
                }
            } else {
                tags.add(ArtifactTag.TEST_UTILITY);
            }
        }

        return ArtifactTags.encode(tags);
    }

    public List<ArtifactClassification> classifyMethodArtifacts(Path javaFile, String packageName) {
        CompilationUnit cu;
        try {
            ParseResult<CompilationUnit> result = parser.parse(javaFile);
            if (result.getResult().isEmpty()) {
                return List.of();
            }
            cu = result.getResult().get();
        } catch (IOException | ParseProblemException e) {
            return List.of();
        }

        String effectivePackage = packageName == null || packageName.isBlank()
                ? cu.getPackageDeclaration().map(pd -> pd.getNameAsString()).orElse(null)
                : packageName;
        ArtifactClassification fileClassification = classify(javaFile, effectivePackage);
        if (fileClassification.isResource()) {
            return List.of();
        }

        List<ArtifactClassification> classifications = new ArrayList<>();
        for (MethodDeclaration method : cu.findAll(MethodDeclaration.class)) {
            String artifact = classifyNodeArtifact(fileClassification, method);
            classifications.add(new ArtifactClassification(
                    ArtifactTags.copyOf(parseTags(artifact)),
                    fileClassification.moduleRoot(),
                    fileClassification.sourceRoot(),
                    fileClassification.moduleName(),
                    fileClassification.reason(),
                    method.getNameAsString(),
                    method.getName().getBegin().map(p -> p.line).orElse(null),
                    method.getEnd().map(p -> p.line).orElse(null)
            ));
        }
        return classifications;
    }

    private Set<ArtifactTag> parseTags(String artifact) {
        EnumSet<ArtifactTag> tags = EnumSet.noneOf(ArtifactTag.class);
        for (ArtifactTag tag : ArtifactTag.values()) {
            if (ArtifactTags.hasTag(artifact, tag)) {
                tags.add(tag);
            }
        }
        return tags;
    }

    private boolean hasTestAnnotation(MethodDeclaration md, boolean isStrict) {
        return hasAnyAnnotation(md, TEST_ANNOTATION_FQNS, isStrict);
    }

    private boolean hasFixtureAnnotation(MethodDeclaration md, boolean isStrict) {
        return hasAnyAnnotation(md, FIXTURE_ANNOTATION_FQNS, isStrict);
    }

    private boolean hasAnyAnnotation(MethodDeclaration md, Set<String> fqns, boolean isStrict) {
        for (AnnotationExpr ann : md.getAnnotations()) {
            if (isStrict) {
                try {
                    if (fqns.contains(ann.resolve().getQualifiedName())) {
                        return true;
                    }
                } catch (Exception e) {
                    return false;
                }
            } else {
                String name = ann.getNameAsString();
                for (String fqn : fqns) {
                    if (fqn.endsWith("." + name)) {
                        return true;
                    }
                }
            }
        }
        return false;
    }

    private boolean isTestMethod(MethodDeclaration method, ArtifactClassification classification, boolean isStrict) {
        if (hasTestAnnotation(method, isStrict)) {
            return true;
        }

        String methodName = method.getNameAsString();
        Optional<ClassOrInterfaceDeclaration> parent =
                method.findAncestor(ClassOrInterfaceDeclaration.class);

        boolean classExtendsTestCase = parent.filter(this::classExtendsTest).isPresent();
        if (classExtendsTestCase
                && method.isPublic()
                && method.getType().isVoidType()
                && method.getParameters().isEmpty()
                && methodName.startsWith("test")) {
            return true;
        }

        return classification.isTestCode() && !method.isPrivate() && looksLikeTestMethodName(methodName);
    }

    private boolean isFixtureMethod(MethodDeclaration method, ArtifactClassification classification, boolean isStrict) {
        if (hasFixtureAnnotation(method, isStrict)) {
            return true;
        }
        if (!classification.isTestCode()) {
            return false;
        }
        String methodName = method.getNameAsString();
        return (methodName.equals("setUp") || methodName.equals("tearDown"))
                && method.getParameters().isEmpty()
                && method.getType().isVoidType();
    }

    private static boolean looksLikeTestMethodName(String methodName) {
        return methodName.startsWith("test")
                || methodName.startsWith("should")
                || methodName.startsWith("when")
                || methodName.startsWith("given")
                || methodName.contains("_when_")
                || methodName.contains("_then_")
                || methodName.contains("_given_");
    }

    private boolean classExtendsTest(ClassOrInterfaceDeclaration cls) {
        try {
            if (cls.isInterface()) {
                return false;
            }

            Optional<CompilationUnit> cuOpt = cls.findCompilationUnit();
            if (cuOpt.isEmpty()) {
                return false;
            }

            CompilationUnit cu = cuOpt.get();

            for (ClassOrInterfaceType extendedType : cls.getExtendedTypes()) {
                String fqn = toQualifiedName(extendedType, cu);
                if (fqn != null && UNIT_TEST_SUPERCLASS_FQNS.contains(fqn)) {
                    return true;
                }
            }

            return false;
        } catch (Exception e) {
            return false;
        }
    }

    private String toQualifiedName(ClassOrInterfaceType type, CompilationUnit cu) {
        try {
            return type.resolve().asReferenceType().getQualifiedName();
        } catch (Exception ignored) {
        }

        String simple = type.getNameAsString();

        for (ImportDeclaration imp : cu.getImports()) {
            String imported = imp.getNameAsString();

            if (!imp.isAsterisk() && imported.endsWith("." + simple)) {
                return imported;
            }
            if (imp.isAsterisk()) {
                String candidate = imported + "." + simple;
                if (UNIT_TEST_SUPERCLASS_FQNS.contains(candidate)) {
                    return candidate;
                }
            }
        }

        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse("");

        if (!packageName.isEmpty()) {
            String samePackage = packageName + "." + simple;
            if (UNIT_TEST_SUPERCLASS_FQNS.contains(samePackage)) {
                return samePackage;
            }
        }

        if (UNIT_TEST_SUPERCLASS_FQNS.contains(simple)) {
            return simple;
        }

        return simple;
    }

    private ArtifactClassification classification(
            Set<ArtifactTag> tags,
            ModuleInfo module,
            Path sourceRoot,
            String reason) {
        return new ArtifactClassification(tags, module.moduleRoot(), sourceRoot, module.moduleName(), reason);
    }

    private void addTestContext(EnumSet<ArtifactTag> tags, ModuleInfo module) {
        if (module.testModule()) {
            tags.add(ArtifactTag.TEST_MODULE);
        }
        tags.add(ArtifactTag.TEST_CODE);
    }

    private List<ModuleInfo> discoverModules() {
        Map<Path, ModuleInfo> indexed = new LinkedHashMap<>();
        indexed.put(repoRoot, new ModuleInfo(repoRoot, repoRoot.getFileName().toString()));
        try (Stream<Path> paths = Files.walk(repoRoot)) {
            paths.filter(Files::isRegularFile)
                    .filter(this::isModuleMetadata)
                    .forEach(file -> indexModuleFile(indexed, file));
        } catch (IOException ignored) {
        }

        for (ModuleInfo module : indexed.values()) {
            ArtifactDetectionConfig.RuleSet rules = config.rulesForModule(repositoryName, module.moduleName());
            addConfiguredRoots(module, rules);
            applyTestModuleFlag(module, rules);
            if (Files.exists(module.moduleRoot().resolve("pom.xml"))) {
                readMaven(module, module.moduleRoot().resolve("pom.xml"));
            }
            if (Files.exists(module.moduleRoot().resolve(".classpath"))) {
                readEclipseClasspath(module, module.moduleRoot().resolve(".classpath"));
            }
            if (Files.exists(module.moduleRoot().resolve("build.xml"))) {
                readAnt(module, module.moduleRoot().resolve("build.xml"));
            }
            readIntellijModules(module);
            readGradle(module);
        }

        return indexed.values().stream()
                .sorted(Comparator.comparingInt((ModuleInfo module) -> module.moduleRoot().getNameCount()).reversed())
                .toList();
    }

    private boolean isModuleMetadata(Path path) {
        String name = path.getFileName().toString();
        return name.equals("pom.xml")
                || name.equals("build.gradle")
                || name.equals("build.gradle.kts")
                || name.equals("build.xml")
                || name.equals(".classpath")
                || name.endsWith(".iml");
    }

    private void indexModuleFile(Map<Path, ModuleInfo> indexed, Path file) {
        Path moduleRoot = file.getParent().toAbsolutePath().normalize();
        ModuleInfo module = indexed.computeIfAbsent(moduleRoot, root -> new ModuleInfo(root, defaultModuleName(root)));
        if (file.getFileName().toString().equals("pom.xml")) {
            readMavenIdentity(module, file);
        } else if (file.getFileName().toString().endsWith(".iml")) {
            module.setModuleName(file.getFileName().toString().replaceFirst("\\.iml$", ""));
        }
    }

    private String defaultModuleName(Path root) {
        if (root.equals(repoRoot)) {
            return repoRoot.getFileName().toString();
        }
        return repoRoot.relativize(root).toString().replace('\\', '/');
    }

    private ModuleInfo syntheticRootModule() {
        ModuleInfo module = new ModuleInfo(repoRoot, repoRoot.getFileName().toString());
        addConfiguredRoots(module, config.rulesForProject(repositoryName));
        applyTestModuleFlag(module, config.rulesForProject(repositoryName));
        return module;
    }

    private Optional<ModuleInfo> nearestModule(Path absoluteFile) {
        return modules.stream()
                .filter(module -> absoluteFile.startsWith(module.moduleRoot()))
                .findFirst();
    }

    private void addConfiguredRoots(ModuleInfo module, ArtifactDetectionConfig.RuleSet rules) {
        rules.mainSourceRoots.forEach(module::addMainSourceRoot);
        rules.unitTestSourceRoots.forEach(module::addUnitTestSourceRoot);
        rules.integrationTestSourceRoots.forEach(module::addIntegrationTestSourceRoot);
        rules.mainResourceRoots.forEach(module::addMainResourceRoot);
        rules.testResourceRoots.forEach(module::addTestResourceRoot);
        rules.generatedMainSourceRoots.forEach(module::addGeneratedMainSourceRoot);
        rules.generatedTestSourceRoots.forEach(module::addGeneratedTestSourceRoot);
    }

    private void applyTestModuleFlag(ModuleInfo module, ArtifactDetectionConfig.RuleSet rules) {
        for (String pattern : rules.testModulePatterns) {
            if (globMatches(pattern, module.moduleName()) || globMatches(pattern, module.moduleRoot().getFileName().toString())) {
                module.setTestModule(true);
                return;
            }
        }
    }

    private boolean globMatches(String pattern, String value) {
        if (pattern == null || value == null) {
            return false;
        }
        StringBuilder regex = new StringBuilder();
        for (int i = 0; i < pattern.length(); i++) {
            char ch = pattern.charAt(i);
            if (ch == '*') {
                regex.append(".*");
            } else {
                regex.append(Pattern.quote(String.valueOf(ch)));
            }
        }
        return value.matches(regex.toString());
    }

    private Optional<Path> packageSourceRoot(Path absoluteFile, String packageName) {
        if (packageName == null || packageName.isBlank()) {
            return Optional.ofNullable(absoluteFile.getParent());
        }
        Path suffix = Path.of(packageName.replace('.', '/')).resolve(absoluteFile.getFileName());
        if (!absoluteFile.endsWith(suffix)) {
            return Optional.empty();
        }
        Path root = absoluteFile;
        for (int i = 0; i < suffix.getNameCount(); i++) {
            root = root.getParent();
            if (root == null) {
                return Optional.empty();
            }
        }
        return Optional.of(root);
    }

    private RootKind inferRootKind(ModuleInfo module, Path sourceRoot) {
        String rel = module.moduleRoot().relativize(sourceRoot).toString().replace('\\', '/');
        if (containsPath(module.integrationTestSourceRoots(), sourceRoot)
                || rel.equals("exttst")
                || rel.contains("integrationTest")
                || rel.equals("it")
                || rel.equals("itest")) {
            return RootKind.INTEGRATION;
        }
        if (containsPath(module.unitTestSourceRoots(), sourceRoot)
                || rel.equals("tst")
                || rel.equals("test")
                || rel.equals("tests")
                || rel.equals("testSrc")
                || rel.endsWith("/src/test/java")) {
            return RootKind.UNIT;
        }
        if (containsPath(module.testResourceRoots(), sourceRoot)
                || rel.equals("testData")
                || rel.equals("tst-rsrc")
                || rel.endsWith("/test/resources")) {
            return RootKind.TEST_RESOURCE;
        }
        if (containsPath(module.mainSourceRoots(), sourceRoot) || rel.equals("src") || rel.endsWith("/src/main/java")) {
            return RootKind.MAIN;
        }
        return RootKind.UNKNOWN;
    }

    private boolean containsPath(Set<Path> paths, Path path) {
        Path normalized = path.toAbsolutePath().normalize();
        return paths.stream().anyMatch(root -> root.toAbsolutePath().normalize().equals(normalized));
    }

    private RootMatch longestMatch(Path file, Set<Path> roots) {
        return roots.stream()
                .map(root -> root.toAbsolutePath().normalize())
                .filter(file::startsWith)
                .max(Comparator.comparingInt(Path::getNameCount))
                .map(RootMatch::new)
                .orElse(RootMatch.NONE);
    }

    private void readMavenIdentity(ModuleInfo module, Path pom) {
        Document doc = parseXml(pom);
        if (doc == null) {
            return;
        }
        String artifactId = firstText(doc, "artifactId");
        module.setModuleName(artifactId);
    }

    private void readMaven(ModuleInfo module, Path pom) {
        Document doc = parseXml(pom);
        if (doc == null) {
            return;
        }
        firstTextOptional(doc, "sourceDirectory").ifPresent(module::addMainSourceRoot);
        firstTextOptional(doc, "testSourceDirectory").ifPresent(module::addUnitTestSourceRoot);
        NodeList directories = doc.getElementsByTagName("directory");
        for (int i = 0; i < directories.getLength(); i++) {
            org.w3c.dom.Node node = directories.item(i);
            String directory = node.getTextContent().trim();
            org.w3c.dom.Node parent = node.getParentNode();
            String parentName = parent == null ? "" : parent.getNodeName();
            org.w3c.dom.Node grandParent = parent == null ? null : parent.getParentNode();
            String grandParentName = grandParent == null ? "" : grandParent.getNodeName();
            if ("testResource".equals(parentName) || "testResources".equals(grandParentName)) {
                module.addTestResourceRoot(directory);
            } else if ("resource".equals(parentName) || "resources".equals(grandParentName)) {
                module.addMainResourceRoot(directory);
            }
        }
    }

    private void readEclipseClasspath(ModuleInfo module, Path classpath) {
        Document doc = parseXml(classpath);
        if (doc == null) {
            return;
        }
        NodeList entries = doc.getElementsByTagName("classpathentry");
        for (int i = 0; i < entries.getLength(); i++) {
            if (!(entries.item(i) instanceof Element element)) {
                continue;
            }
            if (!"src".equals(element.getAttribute("kind"))) {
                continue;
            }
            String path = element.getAttribute("path");
            addNamedRoot(module, path);
        }
    }

    private void readAnt(ModuleInfo module, Path buildXml) {
        Document doc = parseXml(buildXml);
        if (doc == null) {
            return;
        }
        NodeList javacTasks = doc.getElementsByTagName("javac");
        for (int i = 0; i < javacTasks.getLength(); i++) {
            if (!(javacTasks.item(i) instanceof Element javac)) {
                continue;
            }
            addAntPathRoots(module, javac.getAttribute("srcdir"));
            addAntPathRoots(module, javac.getAttribute("sourcepath"));

            NodeList children = javac.getElementsByTagName("src");
            for (int j = 0; j < children.getLength(); j++) {
                if (children.item(j) instanceof Element child) {
                    addAntPathRoots(module, child.getAttribute("path"));
                    addAntPathRoots(module, child.getAttribute("location"));
                }
            }
        }
    }

    private void addAntPathRoots(ModuleInfo module, String pathValue) {
        if (pathValue == null || pathValue.isBlank()) {
            return;
        }
        for (String candidate : pathValue.split("[,;:]")) {
            String root = candidate.trim();
            if (!root.isBlank() && !root.contains("${")) {
                addNamedRoot(module, root);
            }
        }
    }

    private void readIntellijModules(ModuleInfo module) {
        try (Stream<Path> files = Files.list(module.moduleRoot())) {
            files.filter(path -> path.getFileName().toString().endsWith(".iml"))
                    .forEach(path -> readIml(module, path));
        } catch (IOException ignored) {
        }
    }

    private void readIml(ModuleInfo module, Path iml) {
        Document doc = parseXml(iml);
        if (doc == null) {
            return;
        }
        NodeList folders = doc.getElementsByTagName("sourceFolder");
        for (int i = 0; i < folders.getLength(); i++) {
            if (!(folders.item(i) instanceof Element element)) {
                continue;
            }
            String url = element.getAttribute("url");
            String root = url.replace("file://$MODULE_DIR$/", "").replace("file://$MODULE_DIR$", "");
            if (root.isBlank() || root.startsWith("file://")) {
                continue;
            }
            boolean generated = "true".equals(element.getAttribute("generated"));
            String type = element.getAttribute("type");
            boolean testSource = "true".equals(element.getAttribute("isTestSource"));
            if (type.contains("test-resource")) {
                module.addTestResourceRoot(root);
            } else if (type.contains("resource")) {
                module.addMainResourceRoot(root);
            } else if (generated && testSource) {
                module.addGeneratedTestSourceRoot(root);
            } else if (generated) {
                module.addGeneratedMainSourceRoot(root);
            } else if (testSource) {
                module.addUnitTestSourceRoot(root);
            } else {
                module.addMainSourceRoot(root);
            }
        }
    }

    private void readGradle(ModuleInfo module) {
        for (String name : List.of("build.gradle", "build.gradle.kts")) {
            Path gradle = module.moduleRoot().resolve(name);
            if (Files.exists(gradle)) {
                readGradleFile(module, gradle);
            }
        }
    }

    private void readGradleFile(ModuleInfo module, Path gradle) {
        String text;
        try {
            text = Files.readString(gradle, StandardCharsets.UTF_8);
        } catch (IOException e) {
            return;
        }
        extractGradleSrcDirs(text, "main", "java").forEach(module::addMainSourceRoot);
        extractGradleSrcDirs(text, "test", "java").forEach(module::addUnitTestSourceRoot);
        extractGradleSrcDirs(text, "integrationTest", "java").forEach(module::addIntegrationTestSourceRoot);
        extractGradleSrcDirs(text, "main", "resources").forEach(module::addMainResourceRoot);
        extractGradleSrcDirs(text, "test", "resources").forEach(module::addTestResourceRoot);
        extractGradleSrcDirs(text, "integrationTest", "resources").forEach(module::addTestResourceRoot);
    }

    private List<String> extractGradleSrcDirs(String text, String sourceSet, String kind) {
        List<String> roots = new ArrayList<>();
        Pattern blockPattern = Pattern.compile(sourceSet + "\\s*\\{(?<body>.*?)\\n\\s*}", Pattern.DOTALL);
        Matcher blockMatcher = blockPattern.matcher(text);
        while (blockMatcher.find()) {
            String body = blockMatcher.group("body");
            Pattern dirsPattern = Pattern.compile(kind + "\\s*\\.\\s*srcDirs?\\s*[=(]\\s*\\[?(?<dirs>[^\\]\\n)]*)", Pattern.DOTALL);
            Matcher dirsMatcher = dirsPattern.matcher(body);
            while (dirsMatcher.find()) {
                Matcher valueMatcher = Pattern.compile("[\"']([^\"']+)[\"']").matcher(dirsMatcher.group("dirs"));
                while (valueMatcher.find()) {
                    roots.add(valueMatcher.group(1));
                }
            }
        }
        return roots;
    }

    private void addNamedRoot(ModuleInfo module, String root) {
        if (root == null || root.isBlank()) {
            return;
        }
        String normalized = root.replace('\\', '/');
        if (normalized.equals("exttst") || normalized.contains("integration")) {
            module.addIntegrationTestSourceRoot(root);
        } else if (normalized.equals("tst") || normalized.equals("test") || normalized.equals("tests") || normalized.contains("testSrc")) {
            module.addUnitTestSourceRoot(root);
        } else if (normalized.equals("tst-rsrc") || normalized.contains("testData") || normalized.contains("test-resource")) {
            module.addTestResourceRoot(root);
        } else {
            module.addMainSourceRoot(root);
        }
    }

    private Document parseXml(Path file) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(false);
            factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
            return factory.newDocumentBuilder().parse(file.toFile());
        } catch (Exception e) {
            return null;
        }
    }

    private String firstText(Document doc, String tag) {
        return firstTextOptional(doc, tag).orElse(null);
    }

    private Optional<String> firstTextOptional(Document doc, String tag) {
        NodeList nodes = doc.getElementsByTagName(tag);
        if (nodes.getLength() == 0) {
            return Optional.empty();
        }
        String value = nodes.item(0).getTextContent();
        return value == null || value.isBlank() ? Optional.empty() : Optional.of(value.trim());
    }

    private enum RootKind {
        MAIN,
        UNIT,
        INTEGRATION,
        TEST_RESOURCE,
        UNKNOWN
    }

    private record RootMatch(Path root) {
        private static final RootMatch NONE = new RootMatch(null);

        boolean matched() {
            return root != null;
        }
    }
}
