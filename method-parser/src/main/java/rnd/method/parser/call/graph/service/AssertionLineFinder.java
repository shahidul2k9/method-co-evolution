package rnd.method.parser.call.graph.service;

import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.stmt.AssertStmt;
import com.github.javaparser.ast.stmt.Statement;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.resolution.model.SymbolReference;
import com.github.javaparser.symbolsolver.javaparsermodel.JavaParserFacade;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import lombok.extern.slf4j.Slf4j;

import java.util.HashSet;
import java.util.Optional;
import java.util.Set;

@Slf4j
public final class AssertionLineFinder {

    private static final Set<String> ASSERTION_OWNER_FQNS = Set.of(
            // JUnit 3/4
            "junit.framework.Assert",
            "org.junit.Assert",

            // JUnit 5+
            "org.junit.jupiter.api.Assertions",
            "org.junit.jupiter.api.Assumptions",

            // TestNG
            "org.testng.Assert",
            "org.testng.AssertJUnit",

            // Hamcrest
            "org.hamcrest.MatcherAssert",

            // Google Truth
            "com.google.common.truth.Truth",
            "com.google.common.truth.Truth8",
            "com.google.common.truth.TruthJUnit",

            // AssertJ
            "org.assertj.core.api.Assertions",
            "org.assertj.core.api.AssertionsForClassTypes",
            "org.assertj.core.api.AssertionsForInterfaceTypes",
            "org.assertj.core.api.BDDAssertions",
            "org.assertj.core.api.WithAssertions"
    );

    private static final Set<String> EXACT_ASSERTION_METHOD_NAMES = Set.of(
            "assertThat",
            "assertEquals",
            "assertNotEquals",
            "assertSame",
            "assertNotSame",
            "assertTrue",
            "assertFalse",
            "assertNull",
            "assertNotNull",
            "assertArrayEquals",
            "assertIterableEquals",
            "assertLinesMatch",
            "assertInstanceOf",
            "assertThrows",
            "assertThrowsExactly",
            "assertDoesNotThrow",
            "assertTimeout",
            "assertTimeoutPreemptively",
            "assertAll",
            "fail",
            "assumeTrue",
            "assumeFalse",
            "assumeThat",
            "assumingThat",
            "then",
            "assertThatThrownBy",
            "assertThatCode",
            "assertThatExceptionOfType",
            "assertWithMessage",
            "assertAbout",
            "assertSoftly",
            "failBecauseExceptionWasNotThrown"
    );

    private AssertionLineFinder() {
    }

    /**
     * Returns the last line number in the file occupied by an assertion statement/call
     * inside the given method.
     * <p>
     * This uses the enclosing statement's end line when possible, so multi-line assertions
     * such as assertThat(...).isEqualTo(...) return the last line of the whole statement.
     */
    public static Optional<Integer> findLastAssertionLine(MethodDeclaration method, CombinedTypeSolver typeSolver) {
        if (method == null || method.getBody().isEmpty()) {
            return Optional.empty();
        }

        int maxLine = -1;

        // Java built-in assert statement
        for (AssertStmt assertStmt : method.findAll(AssertStmt.class)) {
            int line = assertStmt.getRange()
                    .map(range -> range.end.line)
                    .orElse(-1);
            maxLine = Math.max(maxLine, line);
        }

        // Assertion library method calls
        Set<Statement> matchedStatements = new HashSet<>();

        for (MethodCallExpr call : method.findAll(MethodCallExpr.class)) {
            if (!isAssertionCall(call, typeSolver, false)) {
                continue;
            }

            Optional<Statement> enclosingStatement = findEnclosingStatement(call);
            if (enclosingStatement.isPresent()) {
                matchedStatements.add(enclosingStatement.get());
            } else {
                int line = call.getRange()
                        .map(range -> range.end.line)
                        .orElse(-1);
                maxLine = Math.max(maxLine, line);
            }
        }

        for (Statement stmt : matchedStatements) {
            int line = stmt.getRange()
                    .map(range -> range.end.line)
                    .orElse(-1);
            maxLine = Math.max(maxLine, line);
        }

        return maxLine >= 0 ? Optional.of(maxLine) : Optional.empty();
    }

    private static Optional<Statement> findEnclosingStatement(Node node) {
        Node current = node;
        while (current != null) {
            if (current instanceof Statement statement) {
                return Optional.of(statement);
            }
            current = current.getParentNode().orElse(null);
        }
        return Optional.empty();
    }

    public static boolean isAssertionCall(MethodCallExpr call, CombinedTypeSolver typeResolver, boolean useSymbolResolver) {
        if (useSymbolResolver) {
            try {
                SymbolReference<ResolvedMethodDeclaration> ref =
                        JavaParserFacade.get(typeResolver).solve(call);
                if (ref.isSolved()) {
                    ResolvedMethodDeclaration resolved = ref.getCorrespondingDeclaration();
                    String owner = resolved.declaringType().getQualifiedName();
                    String methodName = resolved.getName();
                    return (ASSERTION_OWNER_FQNS.contains(owner) || isKnownAssertionPackage(owner))
                            && isStrongAssertionName(methodName);
                } else return isStrongAssertionName(call.getNameAsString());
            } catch (RuntimeException e) {
                return isStrongAssertionName(call.getNameAsString());
            }
        } else {
            return isStrongAssertionName(call.getNameAsString());
        }

    }

    private static boolean isKnownAssertionPackage(String owner) {
        return owner.startsWith("org.junit.")
                || owner.startsWith("junit.framework.")
                || owner.startsWith("org.testng.")
                || owner.startsWith("org.hamcrest.")
                || owner.startsWith("org.assertj.core.api.")
                || owner.startsWith("com.google.common.truth.");
    }

    private static boolean isStrongAssertionName(String methodName) {
        return methodName.startsWith("assert")
                || methodName.startsWith("assume")
                || EXACT_ASSERTION_METHOD_NAMES.contains(methodName);
    }
}