package rnd.method.parser.call.graph.artifact;

import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.Set;

public final class ModuleInfo {
    private final Path moduleRoot;
    private String moduleName;
    private boolean testModule;
    private boolean docModule;
    private final Set<Path> mainSourceRoots = new LinkedHashSet<>();
    private final Set<Path> unitTestSourceRoots = new LinkedHashSet<>();
    private final Set<Path> integrationTestSourceRoots = new LinkedHashSet<>();
    private final Set<Path> testModuleSourceRoots = new LinkedHashSet<>();
    private final Set<Path> mainResourceRoots = new LinkedHashSet<>();
    private final Set<Path> testResourceRoots = new LinkedHashSet<>();
    private final Set<Path> generatedMainSourceRoots = new LinkedHashSet<>();
    private final Set<Path> generatedTestSourceRoots = new LinkedHashSet<>();

    public ModuleInfo(Path moduleRoot, String moduleName) {
        this.moduleRoot = moduleRoot.toAbsolutePath().normalize();
        this.moduleName = moduleName;
    }

    public Path moduleRoot() {
        return moduleRoot;
    }

    public String moduleName() {
        return moduleName;
    }

    public void setModuleName(String moduleName) {
        if (moduleName != null && !moduleName.isBlank()) {
            this.moduleName = moduleName;
        }
    }

    public boolean testModule() {
        return testModule;
    }

    public void setTestModule(boolean testModule) {
        this.testModule = testModule;
    }

    public boolean docModule() {
        return docModule;
    }

    public void setDocModule(boolean docModule) {
        this.docModule = docModule;
    }

    public Set<Path> mainSourceRoots() {
        return mainSourceRoots;
    }

    public Set<Path> unitTestSourceRoots() {
        return unitTestSourceRoots;
    }

    public Set<Path> integrationTestSourceRoots() {
        return integrationTestSourceRoots;
    }

    public Set<Path> testModuleSourceRoots() {
        return testModuleSourceRoots;
    }

    public Set<Path> mainResourceRoots() {
        return mainResourceRoots;
    }

    public Set<Path> testResourceRoots() {
        return testResourceRoots;
    }

    public Set<Path> generatedMainSourceRoots() {
        return generatedMainSourceRoots;
    }

    public Set<Path> generatedTestSourceRoots() {
        return generatedTestSourceRoots;
    }

    public void addMainSourceRoot(String root) {
        addRoot(mainSourceRoots, root);
    }

    public void addUnitTestSourceRoot(String root) {
        addRoot(unitTestSourceRoots, root);
    }

    public void addIntegrationTestSourceRoot(String root) {
        addRoot(integrationTestSourceRoots, root);
    }

    public void addTestModuleSourceRoot(String root) {
        addRoot(testModuleSourceRoots, root);
    }

    public void addMainResourceRoot(String root) {
        addRoot(mainResourceRoots, root);
    }

    public void addTestResourceRoot(String root) {
        addRoot(testResourceRoots, root);
    }

    public void addGeneratedMainSourceRoot(String root) {
        addRoot(generatedMainSourceRoots, root);
    }

    public void addGeneratedTestSourceRoot(String root) {
        addRoot(generatedTestSourceRoots, root);
    }

    private void addRoot(Set<Path> roots, String root) {
        if (root == null || root.isBlank()) {
            return;
        }
        roots.add(moduleRoot.resolve(root).normalize());
    }
}
