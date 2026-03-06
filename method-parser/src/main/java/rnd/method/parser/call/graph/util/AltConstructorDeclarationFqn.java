package rnd.method.parser.call.graph.util;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.resolution.UnsolvedSymbolException;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class AltConstructorDeclarationFqn {

    public static String getMethodFqnSimpleParams(ConstructorDeclaration constructorDeclaration) {
        String classFqn = getDeclaringTypeFqnSafe(constructorDeclaration);
        String methodName = constructorDeclaration.getNameAsString();

        String params = IntStream.range(0, constructorDeclaration.getParameters().size())
                .mapToObj(i -> getSimpleParamTypeSafe(constructorDeclaration, i))
                .collect(Collectors.joining(", "));

        return classFqn + "." + methodName + "(" + params + ")";
    }

    private static String getDeclaringTypeFqnSafe(ConstructorDeclaration constructorDeclaration) {
        // Prefer AST-based FQN because it is much more robust than full symbol resolution
        String astFqn = getAstDeclaringTypeFqn(constructorDeclaration);
        if (astFqn != null && !astFqn.isBlank()) {
            return astFqn;
        }

        // Fallback to symbol solver if AST path somehow fails
        try {
            return constructorDeclaration.resolve().declaringType().getQualifiedName();
        } catch (Exception e) {
            return "<UNKNOWN_CLASS>";
        }
    }

    private static String getAstDeclaringTypeFqn(ConstructorDeclaration constructorDeclaration) {
        Optional<CompilationUnit> cuOpt = constructorDeclaration.findCompilationUnit();
        String packageName = cuOpt
                .flatMap(CompilationUnit::getPackageDeclaration)
                .map(pd -> pd.getNameAsString())
                .orElse("");

        Deque<String> typeNames = new ArrayDeque<>();

        TypeDeclaration<?> current = constructorDeclaration.findAncestor(TypeDeclaration.class).orElse(null);
        while (current != null) {
            typeNames.push(current.getNameAsString());
            current = current.findAncestor(TypeDeclaration.class).orElse(null);
        }

        String typePath = String.join(".", typeNames);

        if (!packageName.isEmpty() && !typePath.isEmpty()) {
            return packageName + "." + typePath;
        }
        if (!typePath.isEmpty()) {
            return typePath;
        }
        return null;
    }

    private static String getSimpleParamTypeSafe(ConstructorDeclaration methodDeclaration, int paramIndex) {
        // First try resolved type
        try {
            String resolvedType = methodDeclaration.resolve().getParam(paramIndex).describeType();
            return toSimpleTypeName(resolvedType);
        } catch (UnsolvedSymbolException e) {
            // fallback to source text, e.g. "Address", "List<Address>", "Foo[]"
            return toSimpleTypeName(methodDeclaration.getParameter(paramIndex).getType().asString());
        } catch (Exception e) {
            return toSimpleTypeName(methodDeclaration.getParameter(paramIndex).getType().asString());
        }
    }

    private static String toSimpleTypeName(String typeName) {
        if (typeName == null || typeName.isBlank()) {
            return typeName;
        }

        typeName = typeName.trim();

        // varargs
        if (typeName.endsWith("...")) {
            String elementType = typeName.substring(0, typeName.length() - 3);
//            return toSimpleTypeName(elementType) + "...";
            return toSimpleTypeName(elementType) + "[]";
        }

        // arrays
        if (typeName.endsWith("[]")) {
            String elementType = typeName.substring(0, typeName.length() - 2);
            return toSimpleTypeName(elementType) + "[]";
        }

        // remove generics: List<com.foo.Address> -> List
        int genericStart = typeName.indexOf('<');
        if (genericStart >= 0) {
            typeName = typeName.substring(0, genericStart);
        }

        // remove package: java.util.List -> List
        int lastDot = typeName.lastIndexOf('.');
        return lastDot >= 0 ? typeName.substring(lastDot + 1) : typeName;
    }
}
