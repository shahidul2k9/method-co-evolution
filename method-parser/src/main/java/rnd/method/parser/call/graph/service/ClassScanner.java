package rnd.method.parser.call.graph.service;

import rnd.method.parser.call.graph.model.ClassMapping;

import java.util.List;

public interface ClassScanner {
    void init(String projectName, String repoRoot, String repoUrl, String commitHash, String artifactConfigPath, boolean checkoutRepository);
    List<ClassMapping> scanClass(String file);
}
