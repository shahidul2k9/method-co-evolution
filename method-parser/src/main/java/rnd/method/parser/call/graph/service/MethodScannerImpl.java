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
    private static final boolean ENABLE_METHOD_SCAN_SYMBOL_RESOLUTION =
            Boolean.parseBoolean(System.getProperty("mhc.methodScan.resolve", "true"));
    private static final double SLOW_SCAN_SECONDS = 60.0;
    private static final double SLOW_RESOLVE_SECONDS = 5.0;

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
    public synchronized void init(
            String projectName,
            String repoRoot,
            String repoUrl,
            String commitHash,
            String artifactConfigPath,
            boolean checkoutRepository) {
        if (parserWithSymbolResolver != null) {
            throw new IllegalStateException("MethodScannerImpl.init must be called exactly once");
        }

        if (checkoutRepository) {
            MethodParserUtil.prepareRepositoryForCommit(repoUrl, repoRoot, commitHash);
        }

        String canonicalProjectName = requireProjectName(projectName);
        Path repoRootPath = Path.of(repoRoot);
        long contextStartedAt = System.nanoTime();
        JavaParserContext parserContext = ENABLE_METHOD_SCAN_SYMBOL_RESOLUTION
                ? JavaParserContext.create(repoRootPath, commitHash)
                : JavaParserContext.createParserOnly(repoRootPath);
        log.info(
                "MethodScannerImpl init parser-context repoRoot={} commit={} symbol_resolution_enabled={} elapsed_seconds={}",
                repoRoot,
                commitHash,
                ENABLE_METHOD_SCAN_SYMBOL_RESOLUTION,
                secondsSince(contextStartedAt)
        );
        this.repoRoot = repoRoot;
        this.repoUrl = repoUrl;
        this.commitHash = commitHash;
        this.repositoryName = canonicalProjectName;
        this.parserWithSymbolResolver = parserContext.parser();

        long artifactStartedAt = System.nanoTime();
        this.artifactDetector = TestArtifactDetector.load(
                repoRootPath,
                this.repositoryName,
                artifactConfigPath == null || artifactConfigPath.isBlank() ? null : Path.of(artifactConfigPath),
                parserContext.parser()
        );
        log.info(
                "MethodScannerImpl init artifact-detector repoRoot={} repository={} elapsed_seconds={}",
                repoRoot,
                this.repositoryName,
                secondsSince(artifactStartedAt)
        );
    }

    private static String requireProjectName(String projectName) {
        if (projectName == null || projectName.isBlank()) {
            throw new IllegalArgumentException("Project name is required");
        }
        return projectName.trim();
    }

    @Override
    public List<Method> scanMethod(String file) {
        ensureInitialized();

        long scanStartedAt = System.nanoTime();
        File javaFile = Path.of(repoRoot, file).toFile();

        CompilationUnit cu;
        try {
            long parseStartedAt = System.nanoTime();
            cu = parserWithSymbolResolver.parse(javaFile).getResult().get();
            log.debug(
                    "method-scan java-parse finish file={} elapsed_seconds={}",
                    file,
                    secondsSince(parseStartedAt)
            );
        } catch (ParseProblemException | FileNotFoundException e) {
            log.warn(
                    "method-scan java-parse failed file={} elapsed_seconds={} error={}",
                    file,
                    secondsSince(scanStartedAt),
                    e.toString()
            );
            return Collections.emptyList();
        }

        String packageName = cu.getPackageDeclaration()
                .map(pd -> pd.getNameAsString())
                .orElse(null);

        long classifyStartedAt = System.nanoTime();
        ArtifactClassification fileClassification = artifactDetector.classify(javaFile.toPath(), packageName, cu);
        log.debug(
                "method-scan artifact-classification finish file={} artifact={} elapsed_seconds={}",
                file,
                fileClassification.encodedArtifact(),
                secondsSince(classifyStartedAt)
        );
        if (fileClassification.isResource()) {
            log.info(
                    "method-scan file skipped resource file={} elapsed_seconds={}",
                    file,
                    secondsSince(scanStartedAt)
            );
            return Collections.emptyList();
        }

        int methodCount = cu.findAll(MethodDeclaration.class).size();
        int constructorCount = cu.findAll(ConstructorDeclaration.class).size();
        log.info(
                "method-scan file walk start file={} methods={} constructors={} symbol_resolution_enabled={}",
                file,
                methodCount,
                constructorCount,
                ENABLE_METHOD_SCAN_SYMBOL_RESOLUTION
        );

        List<Method> result = new ArrayList<>();

        cu.walk(node -> {
            if (node instanceof MethodDeclaration md) {
                String methodType = artifactDetector.classifyNodeArtifact(fileClassification, md);

                String tcTracerFqs = AltMethodDeclarationFqn.buildSimpleParamSignature(md);
                ResolvedSignature signature = methodSignature(md, tcTracerFqs, file);

                int start = md.getName().getBegin().map(p -> p.line).orElse(-1);
                Integer end = md.getEnd().map(p -> p.line).orElse(null);
                String methodUrl = MethodParserUtil.toMethodUrl(repoUrl, commitHash, file, start);

                result.add(Method.builder()
                        .repositoryName(repositoryName)
                        .name(md.getNameAsString())
                        .expression("method")
                        .pkg(cu.findCompilationUnit().flatMap(CompilationUnit::getPackageDeclaration).map(pd -> pd.getNameAsString()).orElse(null))
                        .fqn(signature.fqn())
                        .fqs(signature.fqs())
                        .tcTracerFqs(tcTracerFqs)
                        .testlinkerFqs(tcTracerFqs)
                        .testlinkerFqp(TestLinkerSignatureUtil.toParamTypeJson(signature.fqs()))
                        .resolver(signature.resolver())
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

                String tcTracerFqs = AltConstructorDeclarationFqn.buildSimpleParamSignature(cd);
                ResolvedSignature signature = constructorSignature(cd, tcTracerFqs, file);

                int start = cd.getName().getBegin().map(p -> p.line).orElse(-1);
                Integer end = cd.getEnd().map(p -> p.line).orElse(null);
                String methodUrl = MethodParserUtil.toMethodUrl(repoUrl, commitHash, file, start);

                result.add(Method.builder()
                        .repositoryName(repositoryName)
                        .name(cd.getNameAsString())
                        .expression("constructor")
                        .pkg(cu.findCompilationUnit().flatMap(CompilationUnit::getPackageDeclaration).map(pd -> pd.getNameAsString()).orElse(null))
                        .fqn(signature.fqn())
                        .fqs(signature.fqs())
                        .tcTracerFqs(tcTracerFqs)
                        .testlinkerFqs(tcTracerFqs)
                        .testlinkerFqp(TestLinkerSignatureUtil.toParamTypeJson(signature.fqs()))
                        .resolver(signature.resolver())
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
        double elapsed = secondsSince(scanStartedAt);
        if (elapsed >= SLOW_SCAN_SECONDS) {
            log.warn(
                    "method-scan file finish slow file={} rows={} methods={} constructors={} elapsed_seconds={}",
                    file,
                    result.size(),
                    methodCount,
                    constructorCount,
                    elapsed
            );
        } else {
            log.info(
                    "method-scan file finish file={} rows={} methods={} constructors={} elapsed_seconds={}",
                    file,
                    result.size(),
                    methodCount,
                    constructorCount,
                    elapsed
            );
        }
        return result;
    }

    @Override
    public void evictCache() {
        long startedAt = System.nanoTime();
        try {
            Class<?> facadeClass = Class.forName("com.github.javaparser.symbolsolver.javaparsermodel.JavaParserFacade");
            facadeClass.getMethod("clearInstances").invoke(null);
            log.debug("MethodScannerImpl evictCache finish elapsed_seconds={}", secondsSince(startedAt));
        } catch (Throwable ignored) {
            log.debug("MethodScannerImpl evictCache skipped elapsed_seconds={}", secondsSince(startedAt));
        }
    }

    private static ResolvedSignature methodSignature(MethodDeclaration method, String tcTracerFqs, String file) {
        String astQualified = AltMethodDeclarationFqn.buildQualifiedParamSignature(method);
        String fqn = stripParameters(astQualified);
        String fqs = astQualified;
        String resolver = "heuristics";

        if (!ENABLE_METHOD_SCAN_SYMBOL_RESOLUTION) {
            return new ResolvedSignature(fqn, fqs, resolver);
        }

        long resolveStartedAt = System.nanoTime();
        try {
            ResolvedMethodDeclaration resolvedDec = method.resolve();
            fqn = resolvedDec.getQualifiedName();
            fqs = resolvedDec.getQualifiedSignature();
            resolver = "javaparser";
        } catch (Exception ignored) {
            fqn = stripParameters(astQualified);
            fqs = astQualified;
            resolver = "heuristics";
        } finally {
            logResolveDuration("method", file, method.getNameAsString(), resolveStartedAt);
        }

        // Fix anonymous class naming: resolver uses UUIDs (Anonymous-XXXX) or silently
        // drops the $N level. The AST-based signature is authoritative in both cases.
        if (AltMethodDeclarationFqn.isInAnonymousClass(tcTracerFqs)) {
            fqn = stripParameters(astQualified);
            fqs = astQualified;
            resolver = "heuristics";
        } else {
            if (fqn != null && fqn.contains("Anonymous-")) {
                fqn = stripParameters(astQualified);
                resolver = "heuristics";
            }
            if (fqs != null && fqs.contains("Anonymous-")) {
                fqs = astQualified;
                resolver = "heuristics";
            }
        }

        return new ResolvedSignature(fqn, fqs, resolver);
    }

    private static ResolvedSignature constructorSignature(ConstructorDeclaration constructor, String tcTracerFqs, String file) {
        String astQualified = AltConstructorDeclarationFqn.buildQualifiedParamSignature(constructor);
        String fqn = stripParameters(astQualified);
        String fqs = astQualified;
        String resolver = "heuristics";

        if (!ENABLE_METHOD_SCAN_SYMBOL_RESOLUTION) {
            return new ResolvedSignature(fqn, fqs, resolver);
        }

        long resolveStartedAt = System.nanoTime();
        try {
            ResolvedConstructorDeclaration resolvedDec = constructor.resolve();
            fqn = resolvedDec.getQualifiedName();
            fqs = resolvedDec.getQualifiedSignature();
            resolver = "javaparser";
        } catch (Exception ignored) {
            fqn = stripParameters(astQualified);
            fqs = astQualified;
            resolver = "heuristics";
        } finally {
            logResolveDuration("constructor", file, constructor.getNameAsString(), resolveStartedAt);
        }

        // Fix anonymous class naming (same logic as for method declarations above).
        if (AltMethodDeclarationFqn.isInAnonymousClass(tcTracerFqs)) {
            fqn = stripParameters(astQualified);
            fqs = astQualified;
            resolver = "heuristics";
        } else {
            if (fqn != null && fqn.contains("Anonymous-")) {
                fqn = stripParameters(astQualified);
                resolver = "heuristics";
            }
            if (fqs != null && fqs.contains("Anonymous-")) {
                fqs = astQualified;
                resolver = "heuristics";
            }
        }

        return new ResolvedSignature(fqn, fqs, resolver);
    }

    private static void logResolveDuration(String kind, String file, String name, long startedAt) {
        double elapsed = secondsSince(startedAt);
        if (elapsed >= SLOW_RESOLVE_SECONDS) {
            log.warn(
                    "method-scan slow-resolve kind={} file={} name={} elapsed_seconds={}",
                    kind,
                    file,
                    name,
                    elapsed
            );
        } else {
            log.debug(
                    "method-scan resolve finish kind={} file={} name={} elapsed_seconds={}",
                    kind,
                    file,
                    name,
                    elapsed
            );
        }
    }

    private void ensureInitialized() {
        if (parserWithSymbolResolver == null) {
            throw new IllegalStateException("MethodScannerImpl.init must be called before scanMethod");
        }
    }

    private record ResolvedSignature(String fqn, String fqs, String resolver) {
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

    private static double secondsSince(long startedAt) {
        return (System.nanoTime() - startedAt) / 1_000_000_000.0;
    }

}
