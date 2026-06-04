package rnd.method.parser.call.graph.service;

import rnd.method.parser.call.graph.model.MethodCall;

import java.util.List;

public interface CallGraphService {
    void init(
            String projectName,
            String repositoryUrl,
            String repositoryPath,
            String commitHash,
            String methodMappingFile,
            String classMappingFile,
            String artifactConfigPath,
            boolean checkoutRepository,
            long maxCacheSizeMb);

    List<MethodCall> findCallgraph(String file);
}
