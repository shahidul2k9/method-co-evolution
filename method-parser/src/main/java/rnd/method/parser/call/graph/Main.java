package rnd.method.parser.call.graph;

import org.apache.commons.cli.*;
import rnd.method.parser.call.graph.model.MethodCall;
import rnd.method.parser.call.graph.service.CallGraphServiceImpl;

import java.util.List;
import java.util.Set;

public class Main {
    public static void main(String[] args) {
        CommandLineParser commandLineParser = new DefaultParser();
        CommandLine commandLine = null;
        try {
            commandLine = commandLineParser.parse(createOptions(), args);
        } catch (ParseException e) {
            throw new RuntimeException(e);
        }
        String command = commandLine.getOptionValue("command");
        String repositoryUrl = commandLine.getOptionValue("repository-url");
        String repositoryPath = commandLine.getOptionValue("repository-path");
        String commitHash = commandLine.getOptionValue("start-commit");
        String targetPath = commandLine.getOptionValue("target-path");
        String outputPath = commandLine.getOptionValue("output-path");
        Set<String> allowed = Set.of("call-graph");
        if (allowed.contains(command)) {
            if ("call-graph".equalsIgnoreCase(command)) {
                generateCallGraph(repositoryUrl, repositoryPath, commitHash, List.of(targetPath), outputPath);
            }
        } else {
            throw new IllegalArgumentException("Invalid command: " + command + ". Allowed: " + allowed);
        }
    }

    private static Options createOptions() {
        Options options = new Options();

        options.addOption(Option.builder()
                        .longOpt("command")
                        .hasArg(true)
                        .desc("Command name")
                        .required(true)
                        .build())
                .addOption(Option.builder()
                        .longOpt("call-graph")
                        .hasArg(true)
                        .desc("Call Graph")
                        .required(false)
                        .build())
                .addOption(Option.builder()
                        .longOpt("repository-path")
                        .hasArg(true)
                        .desc("Full path on the local system of source project")
                        .required(false)
                        .build())
                .addOption(Option.builder()
                        .longOpt("repository-url")
                        .hasArg(true)
                        .desc("HTTP repository URL")
                        .required(true)
                        .build())
                .addOption(Option.builder()
                        .longOpt("start-commit")
                        .hasArg(true)
                        .desc(" Start commit hash, default is HEAD")
                        .required(true)
                        .build())
                .addOption(Option.builder()
                        .longOpt("target-path")
                        .hasArg(true)
                        .desc(" Relative path or file within the repository for which call graph need to be genrated")
                        .required(true)
                        .build())
                .addOption(Option.builder()
                        .longOpt("output-path")
                        .hasArg(true)
                        .desc(" Path to write output")
                        .required(true)
                        .build());
        return options;
    }

    public static void generateCallGraph(String repositoryUrl, String repositoryPath, String commitHash, List<String> targetPaths, String outputPath) {
        CallGraphServiceImpl fanOutService = new CallGraphServiceImpl();
        List<MethodCall> methodCallOut = fanOutService.findFanOut(repositoryUrl, repositoryPath, commitHash, targetPaths, outputPath);
    }
}
