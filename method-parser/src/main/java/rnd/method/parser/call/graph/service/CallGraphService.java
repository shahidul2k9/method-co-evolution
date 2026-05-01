package rnd.method.parser.call.graph.service;

import rnd.method.parser.call.graph.model.MethodCall;

import java.util.List;

public interface CallGraphService {
    default List<MethodCall> findFanOut(String repositoryUrl, String repositoryPath, String commitHash, List<String> targetPaths, String outputFanInFile, String outputFanOutFile) {
        return findFanOut(repositoryUrl, repositoryPath, commitHash, targetPaths, outputFanInFile, outputFanOutFile, null);
    }

    List<MethodCall> findFanOut(String repositoryUrl, String repositoryPath, String commitHash, List<String> targetPaths, String outputFanInFile, String outputFanOutFile, String methodMappingFile);
}
