package rnd.method.parser.call.graph.model;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class ClassMapping {
    String repositoryName;
    String name;
    String fqn;
    String pkg;
    String file;
    String url;
    Integer startLine;
    Integer endLine;
    String expression;
    String artifact;
    Integer abstractClass;
    String parentNames;
    String parentFqns;
    String hash;
}
