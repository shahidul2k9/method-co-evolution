package rnd.method.parser.call.graph.util;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.expr.ObjectCreationExpr;

import java.util.ArrayDeque;
import java.util.Comparator;
import java.util.Deque;
import java.util.List;
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

        Node node = methodDeclaration.getParentNode().orElse(null);
        while (node != null && !(node instanceof CompilationUnit)) {
            if (node instanceof TypeDeclaration<?> td) {
                typeNames.push(td.getNameAsString());
            } else if (node instanceof ObjectCreationExpr oce && oce.getAnonymousClassBody().isPresent()) {
                typeNames.push("$" + anonymousClassIndex(oce));
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

    static int anonymousClassIndex(ObjectCreationExpr target) {
        TypeDeclaration<?> enclosing = target.findAncestor(TypeDeclaration.class).orElse(null);
        if (enclosing == null) {
            return 1;
        }
        List<ObjectCreationExpr> anonymousClasses = enclosing.findAll(ObjectCreationExpr.class,
                oce -> oce.getAnonymousClassBody().isPresent());
        anonymousClasses.sort(Comparator
                .comparingInt((ObjectCreationExpr oce) -> oce.getBegin().map(p -> p.line).orElse(0))
                .thenComparingInt(oce -> oce.getBegin().map(p -> p.column).orElse(0)));
        int idx = anonymousClasses.indexOf(target);
        return idx >= 0 ? idx + 1 : 1;
    }

}
