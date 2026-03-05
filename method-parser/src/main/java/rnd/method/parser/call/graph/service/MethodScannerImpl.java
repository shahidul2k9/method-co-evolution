package rnd.method.parser.call.graph.service;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseProblemException;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import com.github.javaparser.resolution.TypeSolver;
import com.github.javaparser.resolution.declarations.ResolvedConstructorDeclaration;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;
import lombok.extern.slf4j.Slf4j;
import rnd.method.parser.call.graph.MethodParserUtil;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.util.AltConstructorDeclarationFqn;
import rnd.method.parser.call.graph.util.AltMethodDeclarationFqn;

import java.io.File;
import java.io.FileNotFoundException;
import java.nio.file.Path;
import java.util.*;

/**
 * @author Shahidul Islam
 * @since 2026-01-12
 */
@Slf4j
public class MethodScannerImpl implements MethodScanner {
    private static final Set<String> TEST_ANNOTATION_FQNS = Set.of(
//            # JUnit 4
            "org.junit.Test",
//            "org.junit.Before",
//            "org.junit.After",
//            "org.junit.BeforeClass",
//            "org.junit.AfterClass",
            "org.junit.Ignore",

//            # JUnit 5-6
            "org.junit.jupiter.api.Test",
            "org.junit.jupiter.api.ParameterizedTest",
            "org.junit.jupiter.api.RepeatedTest",
            "org.junit.jupiter.api.TestFactory",
            "org.junit.jupiter.api.TestTemplate",
            "org.junit.jupiter.api.TestClassOrder",
            "org.junit.jupiter.api.TestMethodOrder",
            "org.junit.jupiter.api.TestInstance",
            "org.junit.jupiter.api.DisplayName",
            "org.junit.jupiter.api.DisplayNameGeneration",
//            "org.junit.jupiter.api.BeforeEach",
//            "org.junit.jupiter.api.AfterEach",
//            "org.junit.jupiter.api.BeforeAll",
//            "org.junit.jupiter.api.AfterAll",
            "org.junit.jupiter.api.ParameterizedClass",
//            "org.junit.jupiter.api.BeforeParameterizedClassInvocation",
//            "org.junit.jupiter.api.AfterParameterizedClassInvocation",
            "org.junit.jupiter.api.ClassTemplate",
            "org.junit.jupiter.api.Nested",
            "org.junit.jupiter.api.Tag",
            "org.junit.jupiter.api.Disabled",
            "org.junit.jupiter.api.AutoClose",
            "org.junit.jupiter.api.Timeout",
            "org.junit.jupiter.api.TempDir",
            "org.junit.jupiter.api.ExtendWith",
            "org.junit.jupiter.api.RegisterExtension",


//            # JUnit Theories
            "org.junit.experimental.theories.Theory",

//            # TestNG
//            # https://testng.org/annotations.html#_annotations

            "org.testng.annotations.Test",
//            "org.testng.annotations.BeforeSuite",
//            "org.testng.annotations.AfterSuite",
//            "org.testng.annotations.BeforeTest",
//            "org.testng.annotations.AfterTest",
//            "org.testng.annotations.BeforeGroups",
//            "org.testng.annotations.AfterGroups",
//            "org.testng.annotations.BeforeClass",
//            "org.testng.annotations.AfterClass",
//            "org.testng.annotations.BeforeMethod",
//            "org.testng.annotations.AfterMethod",
            "org.testng.annotations.Factory"
//            # These are not related to method
//    # "org.testng.annotations.DataProvider",
//            # "org.testng.annotations.Listeners",
//            # "org.testng.annotations.Parameters"
    );

    private static final Set<String> UNIT_TEST_SUPERCLASS_FQNS = Set.of(
//            # JUnit 3
            "junit.framework.TestCase",

//            # Android
            "android.test.AndroidTestCase",
            "android.test.InstrumentationTestCase"
    );

    private static final Set<String> TEST_PACKAGE_ROOT_DIRECTORY = Set.of("test/java", "androidTest/java");

    @Override
    public List<Method> scanMethod(String repoRoot, String repoUrl, String commitHash, String file) {
        MethodParserUtil.prepareRepositoryForCommit(repoUrl, repoRoot, commitHash);

        String repositoryName = MethodParserUtil.extractRepositoryName(repoUrl);
        File javaFile = Path.of(repoRoot, file).toFile();
        CombinedTypeSolver typeResolver = new CombinedTypeSolver();
        typeResolver.add(new ReflectionTypeSolver());
        typeResolver.add(new JavaParserTypeSolver(new File(repoRoot)));

        JavaSymbolSolver symbolSolver = new JavaSymbolSolver(typeResolver);

        ParserConfiguration config = new ParserConfiguration()
                .setSymbolResolver(symbolSolver)
                .setLanguageLevel(ParserConfiguration.LanguageLevel.BLEEDING_EDGE);

        JavaParser parserWithSymbolResolver = new JavaParser(config);
        StaticJavaParser.setConfiguration(config);

        CompilationUnit cu;
        try {
            cu = parserWithSymbolResolver.parse(javaFile).getResult().get();
        } catch (ParseProblemException | FileNotFoundException e) {
            log.error("Failed to parse file {}", javaFile);
            return Collections.emptyList();
        }

        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse(null);

        List<Method> result = new ArrayList<>();

        cu.walk(node -> {
            if (node instanceof MethodDeclaration md) {
                String methodType = determineMethodType(javaFile, packageName, md, typeResolver);

                String fqn = null;
                String fqs = null;
                try {
                    ResolvedMethodDeclaration resolvedDec = md.resolve();
                    fqn = resolvedDec.getQualifiedName();
                    fqs = resolvedDec.getQualifiedSignature();
                } catch (Exception ignored) {
                    log.error("Failed to resolve method {}", md.getNameAsString());
                }
                
                int start = md.getName().getBegin().map(p -> p.line).orElse(-1);
                Integer end = md.getEnd().map(p -> p.line).orElse(null);
                String methodUrl = MethodParserUtil.toMethodUrl(repoUrl, commitHash, file, start);
                
                result.add(Method.builder()
                        .repositoryName(repositoryName)
                        .name(md.getNameAsString())
                        .expression("method")
                        .pkg(cu.findCompilationUnit().flatMap(CompilationUnit::getPackageDeclaration).map(pd -> pd.getNameAsString()).orElse(null))
                        .fqn(fqn)
                        .fqs(fqs)
                        .fqsAlt(AltMethodDeclarationFqn.getMethodFqnSimpleParams(md))
                        .file(file)
                        .startLine(start)
                        .endLine(end)
                        .hash(commitHash)
                        .url(methodUrl)
                        .artifact(methodType)
                        .lcba(0)
                        .invocationLine(null)
                        .build()
                );
            } else if (node instanceof ConstructorDeclaration cd) {
                String methodType = determineMethodType(javaFile, packageName, cd, typeResolver);

                String fqn = null;
                String fqs = null;

                try {
                    ResolvedConstructorDeclaration resolvedDec = cd.resolve();
                    fqn = resolvedDec.getQualifiedName();
                    fqs = resolvedDec.getQualifiedSignature();
                } catch (Exception ignored) {
                }

                int start = cd.getName().getBegin().map(p -> p.line).orElse(-1);
                Integer end = cd.getEnd().map(p -> p.line).orElse(null);
                String methodUrl = MethodParserUtil.toMethodUrl(repoUrl, commitHash, file, start);

                result.add(Method.builder()
                        .repositoryName(repositoryName)
                        .name(cd.getNameAsString())
                        .expression("constructor")
                        .pkg(cu.findCompilationUnit().flatMap(CompilationUnit::getPackageDeclaration).map(pd -> pd.getNameAsString()).orElse(null))
                        .fqn(fqn)
                        .fqs(fqs)
                        .fqsAlt(AltConstructorDeclarationFqn.getMethodFqnSimpleParams(cd))
                        .file(file)
                        .startLine(start)
                        .endLine(end)
                        .hash(commitHash)
                        .url(methodUrl)
                        .artifact(methodType)
                        .lcba(0)
                        .invocationLine(null)
                        .build()
                );
            }
        });
        return result;
    }

    private String determineMethodType(
            File file,
            String pkg,
            com.github.javaparser.ast.Node node, TypeSolver typeResolver) {

        String filePath = file.getPath().replace(File.separatorChar, '/');
        String bareFileName = file.getName();

        String packageWithSlash = pkg == null || pkg.isEmpty()
                ? ""
                : pkg.replace('.', '/');

        String suffixWithPackageAndFile =
                packageWithSlash.isEmpty()
                        ? "/" + bareFileName
                        : "/" + packageWithSlash + "/" + bareFileName;

        String methodType = "production";

        if (filePath.endsWith(suffixWithPackageAndFile)) {
            String prefix = filePath.substring(
                    0,
                    filePath.length() - suffixWithPackageAndFile.length()
            );

            for (String possiblePackageRoot : TEST_PACKAGE_ROOT_DIRECTORY) {
                if (prefix.endsWith("/" + possiblePackageRoot)) {
                    methodType = "test_util";
                    break;
                }
            }
        }


        if (node instanceof MethodDeclaration && isTestMethod((MethodDeclaration) node, false)) {
            methodType = "test";
        } else if (node instanceof ConstructorDeclaration) {
            Optional<MethodDeclaration> parentMethod = node.findAncestor(MethodDeclaration.class);
            if (parentMethod.isPresent() && isTestMethod(parentMethod.get(), false)) {
                methodType = "test";
            }
        }


        return methodType;
    }

    private boolean hasTestAnnotation(MethodDeclaration md, boolean isStrict) {
        for (AnnotationExpr ann : md.getAnnotations()) {
            if (isStrict) {
                try {
                    if (TEST_ANNOTATION_FQNS.contains(
                            ann.resolve().getQualifiedName())) {
                        return true;
                    }
                } catch (Exception e) {
                    return false;
                }
            } else {
                String name = ann.getNameAsString();
                for (String fqn : TEST_ANNOTATION_FQNS) {
                    if (fqn.endsWith("." + name)) {
                        return true;
                    }
                }
            }
        }
        return false;
    }

    private boolean isTestMethod(MethodDeclaration method, boolean isStrict) {
        if (hasTestAnnotation(method, false)) {
            return true;
        }

        String methodName = method.getNameAsString();
        Optional<ClassOrInterfaceDeclaration> parent =
                method.findAncestor(ClassOrInterfaceDeclaration.class);


        boolean classExtendsTestCase = parent.filter(this::classExtendsTest).isPresent();
        // JUnit 3 style
        if (classExtendsTestCase
                && method.isPublic()
                && method.getType().isVoidType()
                && method.getParameters().isEmpty()
                && methodName.startsWith("test")) {
            return true;
        }

        // fallback naming-based heuristic
        return looksLikeTestMethodName(methodName);
    }


    private static boolean looksLikeTestMethodName(String methodName) {
        return methodName.startsWith("test")
                || methodName.startsWith("should")
                || methodName.startsWith("when")
                || methodName.startsWith("given")
                || methodName.contains("_when_")
                || methodName.contains("_then_")
                || methodName.contains("_given_");
    }

    private boolean classExtendsTest(ClassOrInterfaceDeclaration cls) {
        try {
            if (cls.isInterface()) {
                return false;
            }

            Optional<CompilationUnit> cuOpt = cls.findCompilationUnit();
            if (cuOpt.isEmpty()) {
                return false;
            }

            CompilationUnit cu = cuOpt.get();

            for (ClassOrInterfaceType extendedType : cls.getExtendedTypes()) {
                String fqn = toQualifiedName(extendedType, cu);
                if (fqn != null && UNIT_TEST_SUPERCLASS_FQNS.contains(fqn)) {
                    return true;
                }
            }

            return false;
        } catch (Exception e) {
            return false;
        }
    }

    private String toQualifiedName(ClassOrInterfaceType type, CompilationUnit cu) {
        String name = type.getNameWithScope();

        // already fully qualified in source
        if (name.contains(".")) {
            return name;
        }

        // exact import match
        for (ImportDeclaration imp : cu.getImports()) {
            if (imp.isAsterisk()) {
                continue;
            }

            String imported = imp.getNameAsString();
            if (imported.endsWith("." + name)) {
                return imported;
            }
        }

        // optional heuristic for common junit wildcard imports
        for (ImportDeclaration imp : cu.getImports()) {
            if (!imp.isAsterisk()) {
                continue;
            }

            String pkg = imp.getNameAsString();
            String candidate = pkg + "." + name;
            if (UNIT_TEST_SUPERCLASS_FQNS.contains(candidate)) {
                return candidate;
            }
        }

        // same package fallback
        if (cu.getPackageDeclaration().isPresent()) {
            return cu.getPackageDeclaration().get().getNameAsString() + "." + name;
        }

        return name;
    }

}
