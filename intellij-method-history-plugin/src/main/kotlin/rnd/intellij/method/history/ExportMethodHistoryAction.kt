package rnd.intellij.method.history

import com.intellij.ide.highlighter.JavaFileType
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.ui.TextBrowseFolderListener
import com.intellij.openapi.util.NlsContexts
import com.intellij.openapi.vcs.AbstractVcs
import com.intellij.openapi.vcs.ProjectLevelVcsManager
import com.intellij.openapi.vcs.VcsException
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.vcs.history.VcsFileRevision
import com.intellij.openapi.vcs.history.VcsHistoryProvider
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiFileFactory
import com.intellij.psi.PsiManager
import com.intellij.psi.PsiMethod
import com.intellij.psi.PsiJavaFile
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.util.ui.FormBuilder
import com.intellij.vcsUtil.VcsUtil
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import javax.swing.JComponent
import javax.swing.JPanel

class ExportMethodHistoryAction : AnAction(), DumbAware {
    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT

    override fun update(event: AnActionEvent) {
        event.presentation.isEnabledAndVisible = event.project != null
    }

    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project ?: return
        val dialog = ExportDialog(project)
        if (!dialog.showAndGet()) {
            return
        }

        val settings = dialog.settings()
        if (settings == null) {
            Messages.showErrorDialog(project, "All paths are required.", "Export Method History Batch")
            return
        }

        MethodHistoryExporter(project, settings).run()
    }
}

private class ExportDialog(private val project: Project) : DialogWrapper(project) {
    private val repoRootField = TextFieldWithBrowseButton()
    private val oracleDirField = TextFieldWithBrowseButton()
    private val outputDirField = TextFieldWithBrowseButton()

    init {
        title = "Export Method History Batch"
        repoRootField.text = project.basePath.orEmpty()
        configureBrowseButton("Repository Root", repoRootField)
        configureBrowseButton("Oracle JSON Directory", oracleDirField)
        configureBrowseButton("Output Directory", outputDirField)
        init()
    }

    override fun createCenterPanel(): JComponent {
        return FormBuilder.createFormBuilder()
            .addLabeledComponent("Repository Root", repoRootField, 1, false)
            .addLabeledComponent("Oracle JSON Directory", oracleDirField, 1, false)
            .addLabeledComponent("Output Directory", outputDirField, 1, false)
            .addComponentFillVertically(JPanel(), 0)
            .panel
    }

    fun settings(): ExportSettings? {
        val repoRoot = repoRootField.text.trim()
        val oracleDir = oracleDirField.text.trim()
        val outputDir = outputDirField.text.trim()
        if (repoRoot.isEmpty() || oracleDir.isEmpty() || outputDir.isEmpty()) {
            return null
        }

        return ExportSettings(Path.of(repoRoot), Path.of(oracleDir), Path.of(outputDir))
    }

    private fun configureBrowseButton(
        @NlsContexts.Button title: String,
        targetField: TextFieldWithBrowseButton,
    ) {
        val descriptor = FileChooserDescriptorFactory.createSingleFolderDescriptor()
        targetField.toolTipText = title
        targetField.addBrowseFolderListener(TextBrowseFolderListener(descriptor, project))
    }
}

data class ExportSettings(
    val repoRoot: Path,
    val oracleDir: Path,
    val outputDir: Path,
)

data class OracleMethod(
    val repositoryName: String,
    val file: String,
    val element: String,
    val startLine: Int,
    val endLine: Int,
    val sourceName: String,
)

data class MethodSelector(
    val methodName: String,
    val parameterCount: Int?,
    val containingClassName: String?,
)

data class MethodSnapshot(
    val text: String,
    val startLine: Int,
    val endLine: Int,
)

data class MethodRevisionRecord(
    val revision: String,
    val text: String,
)

private class MethodHistoryExporter(
    private val project: Project,
    private val settings: ExportSettings,
) {
    fun run() {
        object : Task.Backgroundable(project, "Exporting Method History", true) {
            override fun run(indicator: ProgressIndicator) {
                val methods = loadOracleMethods(settings.oracleDir)
                if (methods.isEmpty()) {
                    notify("No oracle JSON files were found in ${settings.oracleDir}.")
                    return
                }

                Files.createDirectories(settings.outputDir)

                var successCount = 0
                val failures = mutableListOf<String>()

                methods.forEachIndexed { index, method ->
                    indicator.text = "Exporting ${method.sourceName}"
                    indicator.fraction = (index + 1).toDouble() / methods.size.toDouble()

                    try {
                        exportMethod(method)
                        successCount += 1
                    } catch (ex: Exception) {
                        failures += "${method.sourceName}: ${ex.message}"
                    }
                }

                val summary = buildString {
                    append("Exported $successCount/${methods.size} method histories to ${settings.outputDir}.")
                    if (failures.isNotEmpty()) {
                        append("\n\nFailures:\n")
                        append(failures.joinToString("\n"))
                    }
                }
                notify(summary)
            }
        }.queue()
    }

    private fun exportMethod(method: OracleMethod) {
        val startedAtNanos = System.nanoTime()
        val virtualFile = resolveVirtualFile(settings.repoRoot, method.file)
            ?: error("File not found under repository root: ${method.file}")
        val filePath = VcsUtil.getFilePath(virtualFile)
        val vcs = resolveVcs(virtualFile) ?: error("No VCS is configured for ${method.file}")
        val historyProvider = vcs.vcsHistoryProvider ?: error("No VCS history provider for ${vcs.displayName}")
        val selector = buildSelector(virtualFile, method)

        val historySession = createHistorySession(historyProvider, filePath)
            ?: error("No file history session returned for ${method.file}")

        val revisions = historySession.revisionList
        if (revisions.isEmpty()) {
            error("No file revisions found for ${method.file}")
        }

        val records = mutableListOf<MethodRevisionRecord>()
        var previousMethodText: String? = null

        for (revision in revisions.asReversed()) {
            val content = loadRevisionContent(revision) ?: continue
            val snapshot = parseMethodSnapshot(project, method.file, content, selector) ?: continue
            if (snapshot.text == previousMethodText) {
                continue
            }

            records += MethodRevisionRecord(
                revision = revision.revisionNumber.asString(),
                text = snapshot.text,
            )
            previousMethodText = snapshot.text
        }

        val outputFile = settings.outputDir.resolve(method.sourceName)
        Files.writeString(
            outputFile,
            buildOutputJson(records, elapsedMillis(startedAtNanos)),
            StandardCharsets.UTF_8,
            StandardOpenOption.CREATE,
            StandardOpenOption.TRUNCATE_EXISTING,
        )
    }

    private fun resolveVcs(virtualFile: VirtualFile): AbstractVcs? {
        return ProjectLevelVcsManager.getInstance(project).getVcsFor(virtualFile)
    }

    private fun buildSelector(
        virtualFile: com.intellij.openapi.vfs.VirtualFile,
        method: OracleMethod,
    ): MethodSelector {
        val psiFile = ApplicationManager.getApplication().runReadAction<PsiFile?> {
            PsiManager.getInstance(project).findFile(virtualFile)
        } ?: return MethodSelector(method.element, null, null)

        val document = FileDocumentManager.getInstance().getDocument(virtualFile)
            ?: return MethodSelector(method.element, null, null)

        val lineIndex = (method.startLine - 1).coerceAtLeast(0)
        val offset = if (lineIndex < document.lineCount) document.getLineStartOffset(lineIndex) else 0

        val matchedMethod = ApplicationManager.getApplication().runReadAction<PsiMethod?> {
            val elementAtOffset = psiFile.findElementAt(offset)
            val byOffset = PsiTreeUtil.getParentOfType(elementAtOffset, PsiMethod::class.java)
            if (byOffset != null && byOffset.name == method.element) {
                return@runReadAction byOffset
            }

            PsiTreeUtil.findChildrenOfType(psiFile, PsiMethod::class.java).firstOrNull { candidate ->
                candidate.name == method.element && rangeLooksSimilar(document, candidate, method)
            }
        }

        return if (matchedMethod != null) {
            MethodSelector(
                methodName = matchedMethod.name,
                parameterCount = matchedMethod.parameterList.parametersCount,
                containingClassName = matchedMethod.containingClass?.name,
            )
        } else {
            MethodSelector(method.element, null, null)
        }
    }

    private fun rangeLooksSimilar(
        document: com.intellij.openapi.editor.Document,
        method: PsiMethod,
        oracleMethod: OracleMethod,
    ): Boolean {
        val startLine = document.getLineNumber(method.textRange.startOffset) + 1
        val endLine = document.getLineNumber(method.textRange.endOffset.coerceAtMost(document.textLength)) + 1
        return method.name == oracleMethod.element &&
            startLine <= oracleMethod.startLine &&
            endLine >= oracleMethod.endLine
    }

    private fun createHistorySession(
        historyProvider: VcsHistoryProvider,
        filePath: com.intellij.openapi.vcs.FilePath,
    ) = historyProvider.createSessionFor(filePath)

    private fun loadRevisionContent(revision: VcsFileRevision): String? {
        val bytes = try {
            revision.loadContent()
        } catch (_: VcsException) {
            return null
        } ?: return null
        val charset = revision.defaultCharset ?: StandardCharsets.UTF_8
        return bytes.toString(charset)
    }

    private fun notify(message: String) {
        ApplicationManager.getApplication().invokeLater {
            Messages.showInfoMessage(project, message, "Export Method History Batch")
        }
    }
}

private fun resolveVirtualFile(repoRoot: Path, relativePath: String): VirtualFile? {
    val absolutePath = repoRoot.resolve(relativePath).normalize().toString()
    return LocalFileSystem.getInstance().refreshAndFindFileByPath(absolutePath)
}

private fun loadOracleMethods(oracleDir: Path): List<OracleMethod> {
    if (!Files.isDirectory(oracleDir)) {
        return emptyList()
    }

    return Files.list(oracleDir).use { stream ->
        stream
            .filter { Files.isRegularFile(it) && it.fileName.toString().endsWith(".json") }
            .sorted()
            .map(::parseOracleMethod)
            .toList()
    }
}

private fun parseOracleMethod(path: Path): OracleMethod {
    val json = Files.readString(path, StandardCharsets.UTF_8)
    val values = parseFlatJsonObject(json)

    return OracleMethod(
        repositoryName = values["repositoryName"] ?: "",
        file = values["file"] ?: error("Missing file in $path"),
        element = values["element"] ?: error("Missing element in $path"),
        startLine = (values["startLine"] ?: error("Missing startLine in $path")).toInt(),
        endLine = (values["endLine"] ?: error("Missing endLine in $path")).toInt(),
        sourceName = path.fileName.toString(),
    )
}

private fun parseMethodSnapshot(
    project: Project,
    filePath: String,
    content: String,
    selector: MethodSelector,
): MethodSnapshot? {
    return ApplicationManager.getApplication().runReadAction<MethodSnapshot?> {
        val psiFile = PsiFileFactory.getInstance(project)
            .createFileFromText(Path.of(filePath).fileName.toString(), JavaFileType.INSTANCE, content) as? PsiJavaFile
            ?: return@runReadAction null

        val method = findMethodInPsiFile(psiFile, selector) ?: return@runReadAction null
        MethodSnapshot(
            text = method.text,
            startLine = lineNumberOf(content, method.textRange.startOffset),
            endLine = lineNumberOf(content, method.textRange.endOffset),
        )
    }
}

private fun findMethodInPsiFile(psiFile: PsiJavaFile, selector: MethodSelector): PsiMethod? {
    val candidates = PsiTreeUtil.findChildrenOfType(psiFile, PsiMethod::class.java).filter { method ->
        method.name == selector.methodName
    }
    if (candidates.isEmpty()) {
        return null
    }

    selector.containingClassName?.let { className ->
        candidates.firstOrNull { it.containingClass?.name == className && methodMatchesSelector(it, selector) }?.let { return it }
    }

    candidates.firstOrNull { methodMatchesSelector(it, selector) }?.let { return it }
    return candidates.first()
}

private fun methodMatchesSelector(method: PsiMethod, selector: MethodSelector): Boolean {
    val parameterCountMatches = selector.parameterCount == null || method.parameterList.parametersCount == selector.parameterCount
    val classMatches = selector.containingClassName == null || method.containingClass?.name == selector.containingClassName
    return parameterCountMatches && classMatches
}

private fun lineNumberOf(content: String, offset: Int): Int {
    val boundedOffset = offset.coerceIn(0, content.length)
    return content.take(boundedOffset).count { it == '\n' } + 1
}

private fun parseFlatJsonObject(json: String): Map<String, String> {
    val result = linkedMapOf<String, String>()
    val regex = Regex("\"([^\"]+)\"\\s*:\\s*(\"((?:\\\\.|[^\"])*)\"|-?\\d+|true|false|null)")
    for (match in regex.findAll(json)) {
        val key = match.groupValues[1]
        val rawValue = match.groupValues[2]
        val value = when {
            rawValue.startsWith("\"") -> rawValue.removePrefix("\"").removeSuffix("\"")
                .replace("\\\"", "\"")
                .replace("\\\\", "\\")
            rawValue == "null" -> ""
            else -> rawValue
        }
        result[key] = value
    }
    return result
}

private fun buildOutputJson(
    records: List<MethodRevisionRecord>,
    runtimeMillis: Long,
): String {
    val revisionsJson = records.joinToString(",\n") { record ->
        """
        |          {
        |            "changeTags": [],
        |            "commitHash": ${jsonString(record.revision)}
        |          }
        """.trimMargin()
    }

    return """
    |{
    |  "traceMap": {
    |    "intelliJ": {
    |      "runtime": $runtimeMillis,
    |      "commits": [
    |$revisionsJson
    |      ]
    |    }
    |  }
    |}
    """.trimMargin()
}

private fun jsonString(value: String): String {
    return buildString {
        append('"')
        value.forEach { ch ->
            when (ch) {
                '\\' -> append("\\\\")
                '"' -> append("\\\"")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> append(ch)
            }
        }
        append('"')
    }
}

private fun elapsedMillis(startedAtNanos: Long): Long {
    return (System.nanoTime() - startedAtNanos) / 1_000_000
}
