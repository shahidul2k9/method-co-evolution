package rnd.method.parser.call.graph.util;

import java.util.ArrayList;
import java.util.List;

public final class TestLinkerSignatureUtil {
    private TestLinkerSignatureUtil() {
    }

    public static String toSignatureKey(String signature) {
        ParsedSignature parsed = parse(signature);
        if (parsed == null) {
            return null;
        }

        return toSignatureKey(parsed.ownerAndName(), parsed.params());
    }

    public static String toSignatureKey(String ownerAndName, List<String> fullyQualifiedParams) {
        if (ownerAndName == null || ownerAndName.isBlank()) {
            return null;
        }

        List<String> params = fullyQualifiedParams == null ? List.of() : fullyQualifiedParams;
        List<String> simpleParams = params.stream()
                .map(TestLinkerSignatureUtil::toSimpleTypeName)
                .toList();
        return ownerAndName.trim() + "(" + String.join(", ", simpleParams) + ")";
    }

    public static String toFullyQualifiedParamArray(String signature) {
        ParsedSignature parsed = parse(signature);
        if (parsed == null) {
            return null;
        }

        return toFullyQualifiedParamArray(parsed.params());
    }

    public static String toFullyQualifiedParamArray(List<String> fullyQualifiedParams) {
        List<String> params = fullyQualifiedParams == null ? List.of() : fullyQualifiedParams;
        List<String> escaped = params.stream()
                .map(TestLinkerSignatureUtil::jsonQuote)
                .toList();
        return "[" + String.join(",", escaped) + "]";
    }

    private static ParsedSignature parse(String signature) {
        if (signature == null || signature.isBlank()) {
            return null;
        }

        int open = signature.lastIndexOf('(');
        int close = signature.lastIndexOf(')');
        if (open < 0 || close < open) {
            return null;
        }

        String ownerAndName = signature.substring(0, open).trim();
        if (ownerAndName.isBlank()) {
            return null;
        }

        String rawParams = signature.substring(open + 1, close).trim();
        if (rawParams.isBlank()) {
            return new ParsedSignature(ownerAndName, List.of());
        }

        return new ParsedSignature(ownerAndName, splitParams(rawParams));
    }

    private static List<String> splitParams(String rawParams) {
        List<String> params = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        int genericDepth = 0;

        for (int i = 0; i < rawParams.length(); i++) {
            char ch = rawParams.charAt(i);
            if (ch == '<') {
                genericDepth++;
            } else if (ch == '>' && genericDepth > 0) {
                genericDepth--;
            }

            if (ch == ',' && genericDepth == 0) {
                params.add(normalizeType(current.toString()));
                current.setLength(0);
            } else {
                current.append(ch);
            }
        }

        params.add(normalizeType(current.toString()));
        return params;
    }

    private static String normalizeType(String typeName) {
        if (typeName == null) {
            return null;
        }

        String type = typeName.trim();
        int genericStart = type.indexOf('<');
        if (genericStart >= 0) {
            type = type.substring(0, genericStart);
        }
        if (type.endsWith("...")) {
            type = type.substring(0, type.length() - 3) + "[]";
        }
        return type;
    }

    private static String toSimpleTypeName(String typeName) {
        if (typeName == null || typeName.isBlank()) {
            return typeName;
        }

        String type = normalizeType(typeName);
        while (type.endsWith("[]")) {
            String elementType = type.substring(0, type.length() - 2);
            return toSimpleTypeName(elementType) + "[]";
        }

        int lastDot = type.lastIndexOf('.');
        return lastDot >= 0 ? type.substring(lastDot + 1) : type;
    }

    private static String jsonQuote(String value) {
        if (value == null) {
            return "null";
        }

        return "\"" + value
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                + "\"";
    }

    private record ParsedSignature(String ownerAndName, List<String> params) {
    }
}
