package rnd.method.parser.call.graph.util;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.body.Parameter;

import java.util.Optional;
import java.util.Set;

final class ParamTypeNameUtil {
    private static final Set<String> JAVA_LANG_TYPES = Set.of(
            "Boolean", "Byte", "Character", "Class", "Double", "Enum", "Float",
            "Integer", "Long", "Math", "Number", "Object", "Short", "String",
            "StringBuilder", "StringBuffer", "System", "Throwable", "Void"
    );

    private ParamTypeNameUtil() {
    }

    static String getParamTypeSafe(Parameter parameter, boolean qualified) {
        try {
            String resolvedType = parameter.getType().resolve().describe();
            String typeName = qualified ? normalizeQualifiedTypeName(resolvedType) : toSimpleTypeName(resolvedType);
            // Always append [] for varargs regardless of whether the element type is already an array
            // (e.g. boolean[]... → boolean[][]; the resolver returns the element type boolean[])
            if (parameter.isVarArgs() && !typeName.endsWith("...")) {
                typeName = typeName + "[]";
            }
            return typeName;
        } catch (Exception ignored) {
            String sourceType = parameter.getType().asString();
            return qualified
                    ? qualifySourceTypeName(sourceType, parameter.findCompilationUnit())
                    : toSimpleTypeName(sourceType);
        }
    }

    private static String qualifySourceTypeName(String typeName, Optional<CompilationUnit> cuOpt) {
        if (typeName == null || typeName.isBlank()) {
            return typeName;
        }

        typeName = typeName.trim();

        if (typeName.endsWith("...")) {
            return qualifySourceTypeName(typeName.substring(0, typeName.length() - 3), cuOpt) + "[]";
        }
        if (typeName.endsWith("[]")) {
            return qualifySourceTypeName(typeName.substring(0, typeName.length() - 2), cuOpt) + "[]";
        }

        int genericStart = typeName.indexOf('<');
        if (genericStart >= 0) {
            typeName = typeName.substring(0, genericStart);
        }

        return normalizeQualifiedTypeName(qualifyRawTypeName(typeName, cuOpt));
    }

    private static String qualifyRawTypeName(String typeName, Optional<CompilationUnit> cuOpt) {
        if (typeName.contains(".") || isPrimitiveOrVoid(typeName)) {
            return typeName;
        }
        if (typeName.startsWith("?")) {
            return typeName;
        }
        if (JAVA_LANG_TYPES.contains(typeName)) {
            return "java.lang." + typeName;
        }

        if (cuOpt.isPresent()) {
            CompilationUnit cu = cuOpt.get();
            for (ImportDeclaration imp : cu.getImports()) {
                if (!imp.isAsterisk() && !imp.isStatic()) {
                    String imported = imp.getNameAsString();
                    if (imported.endsWith("." + typeName)) {
                        return imported;
                    }
                }
            }
            String packageName = cu.getPackageDeclaration()
                    .map(pd -> pd.getNameAsString())
                    .orElse("");
            if (!packageName.isBlank() && Character.isUpperCase(typeName.charAt(0))) {
                return packageName + "." + typeName;
            }
        }

        return typeName;
    }

    private static String normalizeQualifiedTypeName(String typeName) {
        if (typeName == null || typeName.isBlank()) {
            return typeName;
        }

        typeName = typeName.trim();
        int genericStart = typeName.indexOf('<');
        if (genericStart >= 0) {
            typeName = typeName.substring(0, genericStart);
        }
        return typeName;
    }

    private static String toSimpleTypeName(String typeName) {
        if (typeName == null || typeName.isBlank()) {
            return typeName;
        }

        typeName = normalizeQualifiedTypeName(typeName);

        if (typeName.endsWith("...")) {
            return toSimpleTypeName(typeName.substring(0, typeName.length() - 3)) + "[]";
        }
        if (typeName.endsWith("[]")) {
            return toSimpleTypeName(typeName.substring(0, typeName.length() - 2)) + "[]";
        }

        int lastDot = typeName.lastIndexOf('.');
        return lastDot >= 0 ? typeName.substring(lastDot + 1) : typeName;
    }

    private static boolean isPrimitiveOrVoid(String typeName) {
        return "byte".equals(typeName)
                || "short".equals(typeName)
                || "int".equals(typeName)
                || "long".equals(typeName)
                || "float".equals(typeName)
                || "double".equals(typeName)
                || "boolean".equals(typeName)
                || "char".equals(typeName)
                || "void".equals(typeName);
    }
}
