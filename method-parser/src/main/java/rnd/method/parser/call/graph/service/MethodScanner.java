package rnd.method.parser.call.graph.service;

import rnd.method.parser.call.graph.model.Method;

import java.util.List;

/**
 * @author Nobody
 * @since 2026-01-12
 */
public interface MethodScanner {
    void init(String projectName,
              String repoRoot,
              String repoUrl,
              String commitHash,
              String artifactConfigPath,
              boolean checkoutRepository);

    List<Method> scanMethod(String file);

    void evictCache();
}
