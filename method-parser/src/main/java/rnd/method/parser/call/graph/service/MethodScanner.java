package rnd.method.parser.call.graph.service;

import rnd.method.parser.call.graph.model.Method;

import java.util.List;

/**
 * @author Shahidul Islam
 * @since 2026-01-12
 */
public interface MethodScanner {
    List<Method> scanMethod(String repoRoot,
                            String repoUrl,
                            String commitHash,
                            String file);
}
