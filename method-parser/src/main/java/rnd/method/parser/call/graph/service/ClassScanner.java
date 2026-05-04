package rnd.method.parser.call.graph.service;

import rnd.method.parser.call.graph.model.ClassMapping;

import java.util.List;

public interface ClassScanner {
    void init(String repoRoot, String repoUrl, String commitHash);
    List<ClassMapping> scanClass(String file);
}
