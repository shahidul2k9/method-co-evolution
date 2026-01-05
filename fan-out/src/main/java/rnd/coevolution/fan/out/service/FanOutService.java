package rnd.coevolution.fan.out.service;

import rnd.coevolution.fan.out.model.Fan;

import java.util.List;

public interface FanOutService {
    List<Fan> findOut(String repositoryUrl, String repositoryPath, String commitHash, List<String> targetPaths, String outputFile);
}
