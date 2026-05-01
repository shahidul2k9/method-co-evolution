package rnd.method.parser.call.graph.util;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class AltConstructorDeclarationFqn {
    public static String getMethodFqnSimpleParams(ConstructorDeclaration constructorDeclaration) {
        return getMethodFqnParams(constructorDeclaration, false);
    }

    public static String getMethodFqnQualifiedParams(ConstructorDeclaration constructorDeclaration) {
        return getMethodFqnParams(constructorDeclaration, true);
    }

    public static String getMethodFqnParams(ConstructorDeclaration constructorDeclaration, boolean qualifiedParams) {
        String classFqn = getDeclaringTypeFqnSafe(constructorDeclaration);
        String methodName = constructorDeclaration.getNameAsString();

        String params = IntStream.range(0, constructorDeclaration.getParameters().size())
                .mapToObj(i -> ParamTypeNameUtil.getParamTypeSafe(constructorDeclaration.getParameter(i), qualifiedParams))
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

}
