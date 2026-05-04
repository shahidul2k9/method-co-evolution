package rnd.method.parser.call.graph.service;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseProblemException;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.ImportDeclaration;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.AnnotationDeclaration;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.EnumDeclaration;
import com.github.javaparser.ast.body.RecordDeclaration;
import com.github.javaparser.ast.body.TypeDeclaration;
import com.github.javaparser.ast.expr.ObjectCreationExpr;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;
import lombok.extern.slf4j.Slf4j;
import rnd.method.parser.call.graph.model.ClassMapping;
import rnd.method.parser.call.graph.util.AltMethodDeclarationFqn;
import rnd.method.parser.call.graph.util.MethodParserUtil;

import java.io.File;
import java.io.FileNotFoundException;
import java.nio.file.Path;
import java.util.*;
import java.util.stream.Collectors;

@Slf4j
public class ClassScannerImpl implements ClassScanner {

    private static final Set<String> TEST_PACKAGE_ROOT_DIRECTORY = Set.of("test/java", "androidTest/java");

    private String repoRoot;
    private String repoUrl;
    private String commitHash;
    private String repositoryName;
    private JavaParser parserWithSymbolResolver;

    private ClassScannerImpl() {
    }

    public static ClassScannerImpl getInstance() {
        return new ClassScannerImpl();
    }

    @Override
    public synchronized void init(String repoRoot, String repoUrl, String commitHash) {
        if (parserWithSymbolResolver != null) {
            throw new IllegalStateException("ClassScannerImpl.init must be called exactly once");
        }

        MethodParserUtil.prepareRepositoryForCommit(repoUrl, repoRoot, commitHash);

        CombinedTypeSolver typeSolver = new CombinedTypeSolver();
        typeSolver.add(new ReflectionTypeSolver());
        List<Path> javaSourceRoots = MethodParserUtil.findAllJavaSourceRoots(Path.of(repoRoot));
        if (javaSourceRoots.isEmpty()) {
            typeSolver.add(new JavaParserTypeSolver(new File(repoRoot)));
        } else {
            for (Path root : javaSourceRoots) {
                typeSolver.add(new JavaParserTypeSolver(root.toFile()));
            }
        }

        JavaSymbolSolver symbolSolver = new JavaSymbolSolver(typeSolver);
        ParserConfiguration config = new ParserConfiguration()
                .setSymbolResolver(symbolSolver)
                .setLanguageLevel(ParserConfiguration.LanguageLevel.BLEEDING_EDGE);

        StaticJavaParser.setConfiguration(config);
        this.repoRoot = repoRoot;
        this.repoUrl = repoUrl;
        this.commitHash = commitHash;
        this.repositoryName = MethodParserUtil.extractRepositoryName(repoUrl);
        this.parserWithSymbolResolver = new JavaParser(config);
    }

    @Override
    public List<ClassMapping> scanClass(String file) {
        if (parserWithSymbolResolver == null) {
            throw new IllegalStateException("ClassScannerImpl.init must be called before scanClass");
        }

        File javaFile = Path.of(repoRoot, file).toFile();

        CompilationUnit cu;
        try {
            cu = parserWithSymbolResolver.parse(javaFile).getResult().get();
        } catch (ParseProblemException | FileNotFoundException e) {
            return Collections.emptyList();
        }

        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse("");

        String artifact = determineArtifact(javaFile, packageName);

        List<ClassMapping> result = new ArrayList<>();

        cu.walk(node -> {
            if (node instanceof TypeDeclaration<?> td) {
                result.add(buildFromTypeDeclaration(td, cu, packageName, file, artifact));
            } else if (node instanceof ObjectCreationExpr oce && oce.getAnonymousClassBody().isPresent()) {
                result.add(buildFromAnonymousClass(oce, cu, packageName, file, artifact));
            }
        });

        return result;
    }

    private ClassMapping buildFromTypeDeclaration(
            TypeDeclaration<?> td,
            CompilationUnit cu,
            String packageName,
            String file,
            String artifact) {

        String name = td.getNameAsString();
        String fqn = buildFqn(td, packageName);
        String expression = expressionOf(td);
        int abstractClass = isAbstractOrInterface(td) ? 1 : 0;

        int startLine = td.getName().getBegin().map(p -> p.line).orElse(-1);
        Integer endLine = td.getEnd().map(p -> p.line).orElse(null);
        String url = MethodParserUtil.toMethodUrl(repoUrl, commitHash, file, startLine);

        List<ClassOrInterfaceType> parentTypes = collectParentTypes(td);
        String parentNames;
        String parentFqns;
        if (parentTypes.isEmpty() && td instanceof ClassOrInterfaceDeclaration cid && !cid.isInterface()) {
            parentNames = "Object";
            parentFqns = "java.lang.Object";
        } else {
            parentNames = joinNames(parentTypes.stream()
                    .map(t -> t.getNameAsString())
                    .collect(Collectors.toList()));
            parentFqns = joinNames(parentTypes.stream()
                    .map(t -> resolveTypeFqn(t, cu))
                    .collect(Collectors.toList()));
        }

        return ClassMapping.builder()
                .repositoryName(repositoryName)
                .name(name)
                .fqn(fqn)
                .pkg(packageName.isEmpty() ? null : packageName)
                .file(file)
                .url(url)
                .startLine(startLine)
                .endLine(endLine)
                .expression(expression)
                .artifact(artifact)
                .abstractClass(abstractClass)
                .parentNames(parentNames.isEmpty() ? null : parentNames)
                .parentFqns(parentFqns.isEmpty() ? null : parentFqns)
                .hash(commitHash)
                .build();
    }

    private ClassMapping buildFromAnonymousClass(
            ObjectCreationExpr oce,
            CompilationUnit cu,
            String packageName,
            String file,
            String artifact) {

        int idx = AltMethodDeclarationFqn.anonymousClassIndex(oce);
        String name = "$" + idx;
        String fqn = buildAnonymousFqn(oce, packageName);

        int startLine = oce.getBegin().map(p -> p.line).orElse(-1);
        Integer endLine = oce.getEnd().map(p -> p.line).orElse(null);
        String url = MethodParserUtil.toMethodUrl(repoUrl, commitHash, file, startLine);

        String parentName = oce.getType().getNameAsString();
        String parentFqn = resolveTypeFqn(oce.getType(), cu);

        return ClassMapping.builder()
                .repositoryName(repositoryName)
                .name(name)
                .fqn(fqn)
                .pkg(packageName.isEmpty() ? null : packageName)
                .file(file)
                .url(url)
                .startLine(startLine)
                .endLine(endLine)
                .expression("anonymous")
                .artifact(artifact)
                .abstractClass(0)
                .parentNames(parentName)
                .parentFqns(parentFqn)
                .hash(commitHash)
                .build();
    }

    private String buildFqn(TypeDeclaration<?> typeDecl, String packageName) {
        Deque<String> names = new ArrayDeque<>();
        Node node = typeDecl;
        while (node != null && !(node instanceof CompilationUnit)) {
            if (node instanceof TypeDeclaration<?> td) {
                names.push(td.getNameAsString());
            } else if (node instanceof ObjectCreationExpr oce && oce.getAnonymousClassBody().isPresent()) {
                names.push("$" + AltMethodDeclarationFqn.anonymousClassIndex(oce));
            }
            node = node.getParentNode().orElse(null);
        }
        String typePath = String.join(".", names);
        return packageName.isEmpty() ? typePath : packageName + "." + typePath;
    }

    private String buildAnonymousFqn(ObjectCreationExpr oce, String packageName) {
        Deque<String> names = new ArrayDeque<>();
        Node node = oce;
        while (node != null && !(node instanceof CompilationUnit)) {
            if (node instanceof TypeDeclaration<?> td) {
                names.push(td.getNameAsString());
            } else if (node instanceof ObjectCreationExpr anon && anon.getAnonymousClassBody().isPresent()) {
                names.push("$" + AltMethodDeclarationFqn.anonymousClassIndex(anon));
            }
            node = node.getParentNode().orElse(null);
        }
        String typePath = String.join(".", names);
        return packageName.isEmpty() ? typePath : packageName + "." + typePath;
    }

    private List<ClassOrInterfaceType> collectParentTypes(TypeDeclaration<?> td) {
        List<ClassOrInterfaceType> parents = new ArrayList<>();
        if (td instanceof ClassOrInterfaceDeclaration cid) {
            parents.addAll(cid.getExtendedTypes());
            parents.addAll(cid.getImplementedTypes());
        } else if (td instanceof EnumDeclaration ed) {
            parents.addAll(ed.getImplementedTypes());
        } else if (td instanceof RecordDeclaration rd) {
            parents.addAll(rd.getImplementedTypes());
        }
        return parents;
    }

    private String resolveTypeFqn(ClassOrInterfaceType type, CompilationUnit cu) {
        try {
            return type.resolve().asReferenceType().getQualifiedName();
        } catch (Exception e) {
            return resolveFromImports(type.getNameAsString(), cu);
        }
    }

    private String resolveFromImports(String simpleName, CompilationUnit cu) {
        for (ImportDeclaration imp : cu.getImports()) {
            if (!imp.isAsterisk() && imp.getNameAsString().endsWith("." + simpleName)) {
                return imp.getNameAsString();
            }
        }
        String pkg = cu.getPackageDeclaration().map(pd -> pd.getNameAsString()).orElse("");
        return pkg.isEmpty() ? simpleName : pkg + "." + simpleName;
    }

    private String expressionOf(TypeDeclaration<?> td) {
        if (td instanceof ClassOrInterfaceDeclaration cid) {
            return cid.isInterface() ? "interface" : "class";
        }
        if (td instanceof EnumDeclaration) return "enum";
        if (td instanceof AnnotationDeclaration) return "annotation";
        if (td instanceof RecordDeclaration) return "record";
        return "class";
    }

    private boolean isAbstractOrInterface(TypeDeclaration<?> td) {
        if (td instanceof ClassOrInterfaceDeclaration cid) {
            return cid.isAbstract() || cid.isInterface();
        }
        if (td instanceof AnnotationDeclaration) return true;
        return false;
    }

    private String joinNames(List<String> names) {
        return names.stream()
                .filter(s -> s != null && !s.isBlank())
                .collect(Collectors.joining("|"));
    }

    private String determineArtifact(File file, String pkg) {
        String filePath = file.getPath().replace(File.separatorChar, '/');
        String bareFileName = file.getName();
        String packageWithSlash = pkg == null || pkg.isEmpty() ? "" : pkg.replace('.', '/');
        String suffix = packageWithSlash.isEmpty()
                ? "/" + bareFileName
                : "/" + packageWithSlash + "/" + bareFileName;

        if (filePath.endsWith(suffix)) {
            String prefix = filePath.substring(0, filePath.length() - suffix.length());
            for (String testRoot : TEST_PACKAGE_ROOT_DIRECTORY) {
                if (prefix.endsWith("/" + testRoot)) {
                    return "test";
                }
            }
        }
        return "production";
    }
}
