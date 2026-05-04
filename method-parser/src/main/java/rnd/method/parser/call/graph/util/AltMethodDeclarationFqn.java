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

    /**
     * Builds the TCTracer-style FQS for a declared method: fully-qualified class name,
     * simple (unqualified) parameter type names, varargs as {@code []}.
     *
     * <p>Example: {@code org.apache.IOUtils.closeQuietly(Closeable[])}
     *
     * <p>This is used for the {@code tctracer_fqs} column and for the
     * {@code from_testlinker_fqs} column (calling method side), where both always
     * reflect the declared parameter types rather than actual call-site argument types.
     */
    public static String buildSimpleParamSignature(MethodDeclaration methodDeclaration) {
        return buildSignature(methodDeclaration, false);
    }

    /**
     * Builds the fully-qualified FQS for a declared method: fully-qualified class name,
     * fully-qualified parameter type names, varargs as {@code []}.
     *
     * <p>Example: {@code org.apache.IOUtils.closeQuietly(java.io.Closeable[])}
     *
     * <p>This is used as a fallback for the {@code fqs} column when the symbol solver
     * cannot resolve the method declaration.
     */
    public static String buildQualifiedParamSignature(MethodDeclaration methodDeclaration) {
        return buildSignature(methodDeclaration, true);
    }

    public static String buildSignature(MethodDeclaration methodDeclaration, boolean qualifiedParams) {
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

    /**
     * Returns {@code true} when {@code tcTracerFqs} (a signature built by
     * {@link #buildSimpleParamSignature}) contains a {@code .$N} segment, which indicates
     * that the method is declared inside an anonymous class.
     *
     * <p>The symbol resolver consistently mis-reports the class path of such methods —
     * either by substituting a random UUID ({@code Anonymous-XXXX}) or by silently
     * dropping the {@code $N} level. Use this check to decide whether to override
     * {@code fqn}/{@code fqs} with the AST-based qualified signature from
     * {@link #buildQualifiedParamSignature}.
     *
     * <p>Example: {@code "hudson.cli.CLI.$2.send(byte[])"} → {@code true}
     */
    public static boolean isInAnonymousClass(String tcTracerFqs) {
        if (tcTracerFqs == null) return false;
        int idx = tcTracerFqs.indexOf(".$");
        while (idx >= 0) {
            int j = idx + 2;
            if (j < tcTracerFqs.length() && Character.isDigit(tcTracerFqs.charAt(j))) {
                return true;
            }
            idx = tcTracerFqs.indexOf(".$", idx + 1);
        }
        return false;
    }

    public static int anonymousClassIndex(ObjectCreationExpr target) {
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
