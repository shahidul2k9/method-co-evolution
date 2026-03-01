package rnd.method.parser.call.graph.service;

import com.github.javaparser.ParseProblemException;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.AnnotationExpr;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;
import rnd.method.parser.call.graph.MethodParserUtil;
import rnd.method.parser.call.graph.model.Method;

import java.io.File;
import java.io.FileNotFoundException;
import java.nio.file.Path;
import java.util.*;

/**
 * @author Shahidul Islam
 * @since 2026-01-12
 */
public class MethodScannerImpl implements MethodScanner {
    private static final Set<String> TEST_ANNOTATION_FQNS = Set.of(
//            # JUnit 4
            "org.junit.Test",
            "org.junit.Before",
            "org.junit.After",
            "org.junit.BeforeClass",
            "org.junit.AfterClass",
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
            "org.junit.jupiter.api.BeforeEach",
            "org.junit.jupiter.api.AfterEach",
            "org.junit.jupiter.api.BeforeAll",
            "org.junit.jupiter.api.AfterAll",
            "org.junit.jupiter.api.ParameterizedClass",
            "org.junit.jupiter.api.BeforeParameterizedClassInvocation",
            "org.junit.jupiter.api.AfterParameterizedClassInvocation",
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
            "org.testng.annotations.BeforeSuite",
            "org.testng.annotations.AfterSuite",
            "org.testng.annotations.BeforeTest",
            "org.testng.annotations.AfterTest",
            "org.testng.annotations.BeforeGroups",
            "org.testng.annotations.AfterGroups",
            "org.testng.annotations.BeforeClass",
            "org.testng.annotations.AfterClass",
            "org.testng.annotations.BeforeMethod",
            "org.testng.annotations.AfterMethod",
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
        String repositoryName = MethodParserUtil.extractRepositoryName(repoUrl);
        File javaFile = Path.of(repoRoot, file).toFile();
        CombinedTypeSolver typeResolver = new CombinedTypeSolver();
        typeResolver.add(new ReflectionTypeSolver());
        typeResolver.add(new JavaParserTypeSolver(new File(repoRoot)));

        JavaSymbolSolver symbolSolver = new JavaSymbolSolver(typeResolver);

        ParserConfiguration config = new ParserConfiguration()
                .setSymbolResolver(symbolSolver)
                .setLanguageLevel(ParserConfiguration.LanguageLevel.BLEEDING_EDGE);

        StaticJavaParser.setConfiguration(config);

        CompilationUnit cu;
        try {
            cu = StaticJavaParser.parse(javaFile);
        } catch (ParseProblemException | FileNotFoundException e) {
            return Collections.emptyList();
        }

        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse("");

        List<Method> result = new ArrayList<>();

        for (MethodDeclaration md : cu.findAll(MethodDeclaration.class)) {
            String methodType = determineMethodType(javaFile, packageName, md);

            int start = md.getName().getBegin().map(p -> p.line).orElse(-1);
            int end = md.getEnd().map(p -> p.line).orElse(-1);
            String methodUrl = MethodParserUtil.toMethodUrl(repoUrl, commitHash, file, start);
            ;

            result.add(Method.builder()
                    .repositoryName(repositoryName)
                    .name(md.getNameAsString())
                    .pkg(cu.findCompilationUnit().get().getPackageDeclaration().get().getNameAsString())
                    .fqn(MethodParserUtil.getMethodFqnSimpleParams(md))
                    .file(file)
                    .startLine(start)
                    .endLine(end)
                    .hash(commitHash)
                    .url(methodUrl)
                    .methodType(methodType)
                    .lastAssertionLine(AssertionLineFinder.findLastAssertionLine(md, typeResolver ).orElse(-1))
                    .invocationLine(-1)
                    .build()
            );
        }
        return result;
    }

    private String determineMethodType(
            File file,
            String pkg,
            MethodDeclaration md) {

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


        if (hasTestAnnotation(md, false)) {
            methodType = "test";
        } else {
            Optional<ClassOrInterfaceDeclaration> parent =
                    md.findAncestor(ClassOrInterfaceDeclaration.class);

            if (parent.isPresent() && classExtendsTest(parent.get())) {
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

    private boolean classExtendsTest(ClassOrInterfaceDeclaration cls) {
        try {
            var resolved = cls.resolve();

            if (UNIT_TEST_SUPERCLASS_FQNS.contains(
                    resolved.getQualifiedName())) {
                return true;
            }

            return resolved.getAllAncestors().stream()
                    .anyMatch(a ->
                            UNIT_TEST_SUPERCLASS_FQNS.contains(
                                    a.getQualifiedName()));
        } catch (Exception e) {
            return false;
        }
    }
}
