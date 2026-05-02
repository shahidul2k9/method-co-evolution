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
    String expression;
    String pkg;
    String fqn;
    String fqs;
    String fqsAlt;
    String testlinkerFqs;
    String testlinkerFqp;
    String resolver;
    String file;
    String url;
    String callerUrl;
    String callDepth;
    Integer startLine;
    Integer endLine;
    Integer invocationLine;
    String artifact;
    String hash;
    Integer lcba;
    Integer abstractMethod;

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
                ", methodType='" + artifact + '\'' +
                ", hash='" + hash + '\'' +
                ", lastAssertionLine=" + lcba +
                '}';
    }
}
