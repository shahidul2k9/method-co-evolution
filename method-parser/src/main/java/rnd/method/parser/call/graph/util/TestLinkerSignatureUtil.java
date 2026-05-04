package rnd.method.parser.call.graph.util;

import java.util.ArrayList;
import java.util.List;

public final class TestLinkerSignatureUtil {
    private TestLinkerSignatureUtil() {
    }

    /**
     * Converts a fully-qualified method signature (as produced by JavaParser's
     * {@code ResolvedMethodDeclaration.getQualifiedSignature()}) into the TestLinker
     * signature key format: {@code OwnerClass.methodName(SimpleType1, SimpleType2)}.
     *
     * <p>Parameter types are simplified to unqualified names; varargs ({@code ...})
     * are normalised to array notation ({@code []}). Generic bounds are stripped.
     *
     * <p>Use this overload when you have the declared FQS of a method (e.g. when
     * building the {@code testlinker_fqs} column for a method index or for the
     * <em>calling</em> side ({@code from_testlinker_fqs}) of a call-graph edge).
     */
    public static String fromDeclaredFqs(String fqs) {
        ParsedSignature parsed = parse(fqs);
        if (parsed == null) {
            return null;
        }

        return fromInvocationArgs(parsed.ownerAndName(), parsed.params());
    }

    /**
     * Builds a TestLinker signature key from an owner+name string and a list of
     * <em>actual argument types</em> collected at a call site.
     *
     * <p>This is the key distinction from {@link #fromDeclaredFqs}: here the
     * parameter list comes from the runtime argument expressions at the call site,
     * not from the method declaration. This means individual entries can be:
     * <ul>
     *   <li>{@code null} — when a null literal is passed</li>
     *   <li>{@code <UNKNOWN>} — when the argument type cannot be resolved</li>
     *   <li>A resolved runtime argument type that differs from the declared param type</li>
     * </ul>
     *
     * <p>Use this overload when building {@code to_testlinker_fqs} for a call-graph
     * fan-out edge, where {@code fullyQualifiedParams} is derived from
     * {@link CallGraphServiceImpl#getInvocationArgumentTypes}.
     */
    public static String fromInvocationArgs(String ownerAndName, List<String> fullyQualifiedParams) {
        if (ownerAndName == null || ownerAndName.isBlank()) {
            return null;
        }

        List<String> params = fullyQualifiedParams == null ? List.of() : fullyQualifiedParams;
        List<String> simpleParams = params.stream()
                .map(TestLinkerSignatureUtil::toSimpleTypeName)
                .toList();
        return ownerAndName.trim() + "(" + String.join(", ", simpleParams) + ")";
    }

    /**
     * Returns a JSON array of fully-qualified parameter types parsed from a
     * declared FQS string. Varargs are normalised to {@code []}.
     *
     * <p>Example: {@code "IOUtils.closeQuietly(java.io.Closeable...)"}
     * → {@code ["java.io.Closeable[]"]}
     */
    public static String toParamTypeJson(String fqs) {
        ParsedSignature parsed = parse(fqs);
        if (parsed == null) {
            return null;
        }

        return toParamTypeJson(parsed.params());
    }

    /**
     * Returns a JSON array of fully-qualified parameter types from an already-split
     * list. Null entries are serialised as JSON {@code null}.
     */
    public static String toParamTypeJson(List<String> fullyQualifiedParams) {
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
        // Detect varargs before stripping generics: "Collection<? extends T>..." ends with "..."
        // but indexOf('<') would truncate the string before the "..." is reached.
        boolean varArgs = type.endsWith("...");
        int genericStart = type.indexOf('<');
        if (genericStart >= 0) {
            type = type.substring(0, genericStart);
        }
        if (type.endsWith("...")) {
            type = type.substring(0, type.length() - 3);
            varArgs = true;
        }
        if (varArgs) {
            type = type + "[]";
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
