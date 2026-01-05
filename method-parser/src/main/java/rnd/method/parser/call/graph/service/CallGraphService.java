package rnd.method.parser.call.graph.service;

import rnd.method.parser.call.graph.model.MethodCall;

import java.util.List;

public interface CallGraphService {
    List<MethodCall> findFanOut(String repositoryUrl, String repositoryPath, String commitHash, List<String> targetPaths, String outputFile);
}
