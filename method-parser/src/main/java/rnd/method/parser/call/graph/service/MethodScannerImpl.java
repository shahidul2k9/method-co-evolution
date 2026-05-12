package rnd.method.parser.call.graph.service;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseProblemException;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.ConstructorDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.resolution.declarations.ResolvedConstructorDeclaration;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import lombok.extern.slf4j.Slf4j;
import rnd.method.parser.call.graph.artifact.ArtifactClassification;
import rnd.method.parser.call.graph.artifact.TestArtifactDetector;
import rnd.method.parser.call.graph.util.JavaParserContext;
import rnd.method.parser.call.graph.util.MethodParserUtil;
import rnd.method.parser.call.graph.model.Method;
import rnd.method.parser.call.graph.util.AltConstructorDeclarationFqn;
import rnd.method.parser.call.graph.util.AltMethodDeclarationFqn;
import rnd.method.parser.call.graph.util.TestLinkerSignatureUtil;

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
    private String repoRoot;
    private String repoUrl;
    private String commitHash;
    private String repositoryName;
    private JavaParser parserWithSymbolResolver;
    private TestArtifactDetector artifactDetector;

    private MethodScannerImpl() {
    }

    public static MethodScannerImpl getInstance() {
        return new MethodScannerImpl();
    }

    @Override
    public synchronized void init(String repoRoot, String repoUrl, String commitHash) {
        init(repoRoot, repoUrl, commitHash, null);
    }

    public synchronized void init(String repoRoot, String repoUrl, String commitHash, String artifactConfigPath) {
        if (parserWithSymbolResolver != null) {
            throw new IllegalStateException("MethodScannerImpl.init must be called exactly once");
        }

        MethodParserUtil.prepareRepositoryForCommit(repoUrl, repoRoot, commitHash);

        JavaParserContext parserContext = JavaParserContext.create(Path.of(repoRoot));
        this.repoRoot = repoRoot;
        this.repoUrl = repoUrl;
        this.commitHash = commitHash;
        this.repositoryName = MethodParserUtil.extractRepositoryName(repoUrl);
        this.parserWithSymbolResolver = parserContext.parser();
        this.artifactDetector = TestArtifactDetector.load(
                Path.of(repoRoot),
                this.repositoryName,
                artifactConfigPath == null || artifactConfigPath.isBlank() ? null : Path.of(artifactConfigPath),
                parserContext.parser()
        );
    }

    @Override
    public List<Method> scanMethod(String file) {
        ensureInitialized();

        File javaFile = Path.of(repoRoot, file).toFile();

        CompilationUnit cu;
        try {
            cu = parserWithSymbolResolver.parse(javaFile).getResult().get();
        } catch (ParseProblemException | FileNotFoundException e) {
//            log.error("Failed to parse file {}", javaFile);
            return Collections.emptyList();
        }

        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse(null);

        ArtifactClassification fileClassification = artifactDetector.classify(javaFile.toPath(), packageName);
        if (fileClassification.isResource()) {
            return Collections.emptyList();
        }

        List<Method> result = new ArrayList<>();

        cu.walk(node -> {
            if (node instanceof MethodDeclaration md) {
                String methodType = artifactDetector.classifyNodeArtifact(fileClassification, md);

                String fqn = null;
                String fqs = null;
                String resolver = "javaparser";
                try {
                    ResolvedMethodDeclaration resolvedDec = md.resolve();
                    fqn = resolvedDec.getQualifiedName();
                    fqs = resolvedDec.getQualifiedSignature();
                } catch (Exception ignored) {
//                    log.error("Failed to resolve method {}", md.getNameAsString());
                }
                String tcTracerFqs = AltMethodDeclarationFqn.buildSimpleParamSignature(md);
                // Fix anonymous class naming: resolver uses UUIDs (Anonymous-XXXX) or silently
                // drops the $N level. tcTracerFqs (AST-based) is authoritative in both cases.
                if (AltMethodDeclarationFqn.isInAnonymousClass(tcTracerFqs)) {
                    String astQualified = AltMethodDeclarationFqn.buildQualifiedParamSignature(md);
                    fqn = stripParameters(astQualified);
                    fqs = astQualified;
                } else {
                    if (fqn != null && fqn.contains("Anonymous-")) {
                        fqn = stripParameters(AltMethodDeclarationFqn.buildQualifiedParamSignature(md));
                    }
                    if (fqs != null && fqs.contains("Anonymous-")) {
                        fqs = AltMethodDeclarationFqn.buildQualifiedParamSignature(md);
                    }
                }
                if (fqn == null) {
                    fqn = stripParameters(AltMethodDeclarationFqn.buildQualifiedParamSignature(md));
                    resolver = "heuristics";
                }
                if (fqs == null) {
                    fqs = AltMethodDeclarationFqn.buildQualifiedParamSignature(md);
                    resolver = "heuristics";
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
                        .tcTracerFqs(tcTracerFqs)
                        .testlinkerFqs(tcTracerFqs)
                        .testlinkerFqp(TestLinkerSignatureUtil.toParamTypeJson(fqs))
                        .resolver(resolver)
                        .file(file)
                        .startLine(start)
                        .endLine(end)
                        .hash(commitHash)
                        .url(methodUrl)
                        .artifact(methodType)
                        .abstractMethod(isAbstractMethod(md) ? 1 : 0)
                        .lcba(0)
                        .invocationLine(null)
                        .build()
                );
            } else if (node instanceof ConstructorDeclaration cd) {
                String methodType = artifactDetector.classifyNodeArtifact(fileClassification, cd);

                String fqn = null;
                String fqs = null;
                String resolver = "javaparser";

                try {
                    ResolvedConstructorDeclaration resolvedDec = cd.resolve();
                    fqn = resolvedDec.getQualifiedName();
                    fqs = resolvedDec.getQualifiedSignature();
                } catch (Exception ignored) {
                }
                String tcTracerFqs = AltConstructorDeclarationFqn.buildSimpleParamSignature(cd);
                // Fix anonymous class naming (same logic as for method declarations above)
                if (AltMethodDeclarationFqn.isInAnonymousClass(tcTracerFqs)) {
                    String astQualified = AltConstructorDeclarationFqn.buildQualifiedParamSignature(cd);
                    fqn = stripParameters(astQualified);
                    fqs = astQualified;
                } else {
                    if (fqn != null && fqn.contains("Anonymous-")) {
                        fqn = stripParameters(AltConstructorDeclarationFqn.buildQualifiedParamSignature(cd));
                    }
                    if (fqs != null && fqs.contains("Anonymous-")) {
                        fqs = AltConstructorDeclarationFqn.buildQualifiedParamSignature(cd);
                    }
                }
                if (fqn == null) {
                    fqn = stripParameters(AltConstructorDeclarationFqn.buildQualifiedParamSignature(cd));
                    resolver = "heuristics";
                }
                if (fqs == null) {
                    fqs = AltConstructorDeclarationFqn.buildQualifiedParamSignature(cd);
                    resolver = "heuristics";
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
                        .tcTracerFqs(tcTracerFqs)
                        .testlinkerFqs(tcTracerFqs)
                        .testlinkerFqp(TestLinkerSignatureUtil.toParamTypeJson(fqs))
                        .resolver(resolver)
                        .file(file)
                        .startLine(start)
                        .endLine(end)
                        .hash(commitHash)
                        .url(methodUrl)
                        .artifact(methodType)
                        .abstractMethod(0)
                        .lcba(0)
                        .invocationLine(null)
                        .build()
                );
            }
        });
        return result;
    }

    private void ensureInitialized() {
        if (parserWithSymbolResolver == null) {
            throw new IllegalStateException("MethodScannerImpl.init must be called before scanMethod");
        }
    }

    private static String stripParameters(String signature) {
        if (signature == null) {
            return null;
        }
        int open = signature.lastIndexOf('(');
        return open >= 0 ? signature.substring(0, open) : signature;
    }

    private static boolean isAbstractMethod(MethodDeclaration method) {
        if (method.isAbstract()) {
            return true;
        }
        return method.findAncestor(ClassOrInterfaceDeclaration.class)
                .map(ClassOrInterfaceDeclaration::isInterface)
                .orElse(false)
                && method.getBody().isEmpty();
    }

}
