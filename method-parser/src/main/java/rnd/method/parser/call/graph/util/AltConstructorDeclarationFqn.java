package rnd.method.parser.call.graph.util;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.expr.ObjectCreationExpr;

import java.util.ArrayDeque;
import java.util.Comparator;
import java.util.Deque;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class AltConstructorDeclarationFqn {

    /**
     * Builds the TCTracer-style FQS for a declared constructor: fully-qualified class name,
     * simple (unqualified) parameter type names, varargs as {@code []}.
     *
     * @see AltMethodDeclarationFqn#buildSimpleParamSignature
     */
    public static String buildSimpleParamSignature(ConstructorDeclaration constructorDeclaration) {
        return buildSignature(constructorDeclaration, false);
    }

    /**
     * Builds the fully-qualified FQS for a declared constructor: fully-qualified class name,
     * fully-qualified parameter type names, varargs as {@code []}.
     *
     * @see AltMethodDeclarationFqn#buildQualifiedParamSignature
     */
    public static String buildQualifiedParamSignature(ConstructorDeclaration constructorDeclaration) {
        return buildSignature(constructorDeclaration, true);
    }

    public static String buildSignature(ConstructorDeclaration constructorDeclaration, boolean qualifiedParams) {
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

        Node node = constructorDeclaration.getParentNode().orElse(null);
        while (node != null && !(node instanceof CompilationUnit)) {
            if (node instanceof TypeDeclaration<?> td) {
                typeNames.push(td.getNameAsString());
            } else if (node instanceof ObjectCreationExpr oce && oce.getAnonymousClassBody().isPresent()) {
                typeNames.push("$" + AltMethodDeclarationFqn.anonymousClassIndex(oce));
            }
            node = node.getParentNode().orElse(null);
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
