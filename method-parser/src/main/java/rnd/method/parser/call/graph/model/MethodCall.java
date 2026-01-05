package rnd.method.parser.call.graph.model;

import lombok.Builder;
import lombok.Data;

import java.util.List;
@Data
@Builder
public class MethodCall {
    Method method;
    List<Method> fanMethods;

    @Override
    public String toString() {
        return "{" +
                "methodUri='" + method + '\'' +
                ", calledMethodUris=" + fanMethods +
                '}';
    }
}
