package rnd.method.parser.call.graph.model;

import lombok.Builder;
import lombok.Data;

/**
 * @author Shahidul Islam
 * @since 2025-12-23
 */
@Data
@Builder
public class Method {
    String repositoryName;
    String name;
    String pkg;
    String fqn;
    String file;
    String url;
    Integer startLine;
    Integer endLine;
    Integer invocationLine;
    String methodType;
    String hash;
    Integer lcba;

    @Override
    public String toString() {
        return "Method{" +
                "repositoryName='" + repositoryName + '\'' +
                ", name='" + name + '\'' +
                ", pkg='" + pkg + '\'' +
                ", fqn='" + fqn + '\'' +
                ", file='" + file + '\'' +
                ", url='" + url + '\'' +
                ", startLine=" + startLine +
                ", endLine=" + endLine +
                ", invocationLine=" + invocationLine +
                ", methodType='" + methodType + '\'' +
                ", hash='" + hash + '\'' +
                ", lastAssertionLine=" + lcba +
                '}';
    }
}
