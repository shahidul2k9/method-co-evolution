package rnd.method.parser.call.graph.util;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;

import java.nio.file.Path;
import java.util.List;

public final class JavaParserContext {
    private final JavaParser parser;
    private final CombinedTypeSolver typeSolver;
    private final ParserConfiguration configuration;

    private JavaParserContext(JavaParser parser, CombinedTypeSolver typeSolver, ParserConfiguration configuration) {
        this.parser = parser;
        this.typeSolver = typeSolver;
        this.configuration = configuration;
    }

    public static JavaParserContext create(Path repoRoot) {
        return create(repoRoot, false);
    }

    public static JavaParserContext create(Path repoRoot, boolean reflectionTypeSolverJreOnly) {
        CombinedTypeSolver typeSolver = new CombinedTypeSolver();
        typeSolver.add(new ReflectionTypeSolver(reflectionTypeSolverJreOnly));

        List<Path> javaSourceRoots = MethodParserUtil.findAllJavaSourceRoots(repoRoot);
        if (javaSourceRoots.isEmpty()) {
            typeSolver.add(new JavaParserTypeSolver(repoRoot.toFile()));
        } else {
            for (Path javaSourceRoot : javaSourceRoots) {
                typeSolver.add(new JavaParserTypeSolver(javaSourceRoot.toFile()));
            }
        }

        ParserConfiguration configuration = new ParserConfiguration()
                .setSymbolResolver(new JavaSymbolSolver(typeSolver))
                .setLanguageLevel(ParserConfiguration.LanguageLevel.BLEEDING_EDGE);

        StaticJavaParser.setConfiguration(configuration);
        return new JavaParserContext(new JavaParser(configuration), typeSolver, configuration);
    }

    public JavaParser parser() {
        return parser;
    }

    public CombinedTypeSolver typeSolver() {
        return typeSolver;
    }

    public ParserConfiguration configuration() {
        return configuration;
    }
}
