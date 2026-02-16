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
    String hash;
    String name;
    String fqn;
    String file;
    String url;
    Integer startLine;
    Integer endLine;
    String methodType;
    String pkg;
    Integer lastAssertionLine;

    @Override
    public String toString() {
        final StringBuffer sb = new StringBuffer("{");
        sb.append("file='").append(file).append('\'');
        sb.append(", name='").append(name).append('\'');
        sb.append(", type='").append(methodType).append('\'');
        sb.append(", startLine=").append(startLine);
        sb.append(", endLine=").append(endLine);
        sb.append('}');
        return sb.toString();
    }
}
