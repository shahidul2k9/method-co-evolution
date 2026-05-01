package rnd.method.parser.call.graph.util;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class AltMethodDeclarationFqn {
    public static String getMethodFqnSimpleParams(MethodDeclaration methodDeclaration) {
        return getMethodFqnParams(methodDeclaration, false);
    }

    public static String getMethodFqnQualifiedParams(MethodDeclaration methodDeclaration) {
        return getMethodFqnParams(methodDeclaration, true);
    }

    public static String getMethodFqnParams(MethodDeclaration methodDeclaration, boolean qualifiedParams) {
        String classFqn = getDeclaringTypeFqnSafe(methodDeclaration);
        String methodName = methodDeclaration.getNameAsString();

        String params = IntStream.range(0, methodDeclaration.getParameters().size())
                .mapToObj(i -> ParamTypeNameUtil.getParamTypeSafe(methodDeclaration.getParameter(i), qualifiedParams))
                .collect(Collectors.joining(", "));

        return classFqn + "." + methodName + "(" + params + ")";
    }

    private static String getDeclaringTypeFqnSafe(MethodDeclaration methodDeclaration) {
        // Prefer AST-based FQN because it is much more robust than full symbol resolution
        String astFqn = getAstDeclaringTypeFqn(methodDeclaration);
        if (astFqn != null && !astFqn.isBlank()) {
            return astFqn;
        }

        // Fallback to symbol solver if AST path somehow fails
        try {
            return methodDeclaration.resolve().declaringType().getQualifiedName();
        } catch (Exception e) {
            return "<UNKNOWN_CLASS>";
        }
    }

    private static String getAstDeclaringTypeFqn(MethodDeclaration methodDeclaration) {
        Optional<CompilationUnit> cuOpt = methodDeclaration.findCompilationUnit();
        String packageName = cuOpt
                .flatMap(CompilationUnit::getPackageDeclaration)
                .map(pd -> pd.getNameAsString())
                .orElse("");

        Deque<String> typeNames = new ArrayDeque<>();

        TypeDeclaration<?> current = methodDeclaration.findAncestor(TypeDeclaration.class).orElse(null);
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
