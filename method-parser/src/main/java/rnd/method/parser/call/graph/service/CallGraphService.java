package rnd.method.parser.call.graph.service;

import rnd.method.parser.call.graph.model.MethodCall;

import java.util.List;

public interface CallGraphService {
    void init(String repositoryUrl, String repositoryPath, String commitHash, String methodMappingFile);

    List<MethodCall> findCallgraph(String file);
}
