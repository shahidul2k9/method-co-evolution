import os
import os.path
import shlex
import shutil
import time
from pathlib import Path

import javalang
import jpype
import jpype.imports
import pandas as pd
from git import GitCommandError, Repo
from pandas import DataFrame

import mhc.util as util

TEST_ANNOTATION_FQNS = {
    # JUnit 4
    "org.junit.Test",
    "org.junit.Before",
    "org.junit.After",
    "org.junit.BeforeClass",
    "org.junit.AfterClass",
    "org.junit.Ignore",

    # JUnit 5-6
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
    "org.junit.jupiter.api.RegisterExtension"


    # JUnit Theories
    "org.junit.experimental.theories.Theory",

    # TestNG
    # https://testng.org/annotations.html#_annotations

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
    "org.testng.annotations.Factory",
    # These are not related to method
    # "org.testng.annotations.DataProvider",
    # "org.testng.annotations.Listeners",
    # "org.testng.annotations.Parameters"
}
UNIT_TEST_SUPERCLASS_FQNS = {
    # JUnit 3
    "junit.framework.TestCase",

    # Android
    "android.test.AndroidTestCase",
    "android.test.InstrumentationTestCase",
}
TEST_PACKAGE_ROOT_DIRECTORY = {"test", "androidTest"}
TEST_ANNOTATION_NAMES = set(map(lambda x: x.split(".")[-1], TEST_ANNOTATION_FQNS))
METHOD_SCAN_COLUMNS = [
    "project",
    "name",
    "url",
    "artifact",
    "start_line",
    "end_line",
    "expression",
    "file",
    "pkg",
    "fqn",
    "fqs",
    "fqs_alt",
    "hash",
    "parser",
]
METHOD_CODE_COLUMNS = [
    "project",
    "name",
    "url",
    "artifact",
    "start_line",
    "end_line",
    "code",
]
SCAN_METHOD_FLUSH_INTERVAL_SECONDS = 1 * 15 * 60
SCAN_MARKER_PARSER = "__scan_marker__"
SCAN_MARKER_EXPRESSION = "__file_scanned__"


class Method:
    def __init__(self, file: str, artifact: str, name: str, line: int):
        self.file = file
        self.artifact = artifact
        self.name = name
        self.line = line


def _write_dataframe_csv(output_file: str, dataframe: pd.DataFrame, columns: list[str]) -> None:
    output_directory = os.path.dirname(output_file)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)

    temporary_output_file = f"{output_file}.tmp"
    dataframe.reindex(columns=columns).to_csv(temporary_output_file, index=False)
    os.replace(temporary_output_file, output_file)


def _append_dataframe_csv(output_file: str, rows: list[dict], columns: list[str]) -> None:
    if not rows:
        return

    output_directory = os.path.dirname(output_file)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)

    file_exists = os.path.exists(output_file) and os.path.getsize(output_file) > 0
    pd.DataFrame(rows, columns=columns).to_csv(
        output_file,
        mode="a" if file_exists else "w",
        header=not file_exists,
        index=False,
    )


def _build_scan_marker_row(
    repository_name: str,
    file_without_base: str,
    commit_hash: str,
) -> dict:
    return {
        "project": repository_name,
        "name": None,
        "url": None,
        "artifact": None,
        "start_line": None,
        "end_line": None,
        "expression": SCAN_MARKER_EXPRESSION,
        "file": file_without_base,
        "pkg": None,
        "fqn": None,
        "fqs": None,
        "fqs_alt": None,
        "hash": commit_hash,
        "parser": SCAN_MARKER_PARSER,
    }


def _load_cached_method_scan_files(method_cache_file: str) -> set[str]:
    if not os.path.exists(method_cache_file):
        return set()

    try:
        cache_df = pd.read_csv(method_cache_file, usecols=["file"])
    except (ValueError, pd.errors.EmptyDataError):
        return set()
    return set(filter(None, cache_df["file"].dropna().astype(str)))


def _flush_method_scan_buffers(
    method_cache_file: str,
    pending_method_rows: list[dict],
) -> None:
    _append_dataframe_csv(method_cache_file, pending_method_rows, METHOD_SCAN_COLUMNS)
    pending_method_rows.clear()


def _finalize_method_scan_outputs(
    method_cache_file: str,
    output_method_file: str,
) -> None:
    if os.path.exists(method_cache_file):
        try:
            cache_df = pd.read_csv(method_cache_file)
        except pd.errors.EmptyDataError:
            cache_df = pd.DataFrame(columns=METHOD_SCAN_COLUMNS)
        cache_df = cache_df.reindex(columns=METHOD_SCAN_COLUMNS)
        method_df = cache_df[cache_df["parser"] != SCAN_MARKER_PARSER].copy()
        method_df = util.convert_float_int_columns_to_nullable_int(method_df)
        _write_dataframe_csv(output_method_file, method_df, METHOD_SCAN_COLUMNS)
        os.remove(method_cache_file)
    else:
        _write_dataframe_csv(output_method_file, pd.DataFrame(columns=METHOD_SCAN_COLUMNS), METHOD_SCAN_COLUMNS)


def _extract_method_code(repository_root: str, file_path: str, start_line, end_line) -> str:
    if pd.isna(start_line) or pd.isna(end_line) or not file_path:
        return ""

    start_line_number = int(start_line)
    end_line_number = int(end_line)
    if start_line_number <= 0 or end_line_number < start_line_number:
        return ""

    absolute_file_path = os.path.join(repository_root, file_path)
    if not os.path.exists(absolute_file_path):
        return ""

    lines = _read_source_file_lines(absolute_file_path)
    if lines is None:
        return ""

    start_index = start_line_number - 1
    end_index = min(end_line_number, len(lines))
    if start_index >= len(lines):
        return ""

    return "".join(lines[start_index:end_index]).rstrip("\n")


def _read_source_file_text(source_file_path: str) -> str | None:
    try:
        with open(source_file_path, "r", encoding="utf-8") as source_file:
            return source_file.read()
    except UnicodeDecodeError:
        return None


def _read_source_file_lines(source_file_path: str) -> list[str] | None:
    source_text = _read_source_file_text(source_file_path)
    if source_text is None:
        return None

    return source_text.splitlines(keepends=True)


def generate_method_code(
    repository_df: DataFrame,
    repository_directory: str,
    data_directory: str,
) -> list[str]:
    output_files = []

    for _, repository in repository_df.iterrows():
        repository_name = repository["project"]
        repository_url = repository["url"]
        commit_hash = repository["updated_hash"]
        repository_root = util.format_git_project_directory(repository_directory, repository_name)
        input_file = util.format_method_list_file(data_directory, repository_name)
        output_file = util.format_method_code_file(data_directory, repository_name)

        clone_and_checkout_commit(repository_url, repository_root, commit_hash)

        method_df = pd.read_csv(input_file)

        missing_columns = [
            column for column in METHOD_CODE_COLUMNS if column != "code" and column not in method_df.columns
        ]
        if missing_columns:
            raise ValueError(
                f"Missing required columns in {input_file}: {', '.join(missing_columns)}"
            )

        output_df = method_df[[column for column in METHOD_CODE_COLUMNS if column != "code"]].copy()
        output_df["code"] = method_df.apply(
            lambda row: _extract_method_code(
                repository_root,
                row.get("file"),
                row.get("start_line"),
                row.get("end_line"),
            ),
            axis=1,
        )
        output_df = util.convert_float_int_columns_to_nullable_int(output_df)
        _write_dataframe_csv(output_file, output_df, METHOD_CODE_COLUMNS)
        output_files.append(output_file)

    return output_files


def _is_method_output_current(output_method_file: str, commit_hash: str) -> bool:
    if not os.path.exists(output_method_file):
        return False

    try:
        output_df = pd.read_csv(output_method_file, usecols=["hash"])
    except (ValueError, pd.errors.EmptyDataError):
        return True

    hashes = set(output_df["hash"].dropna().astype(str))
    return not hashes or hashes == {commit_hash}


def _scan_methods_in_file(
    scanner,
    repository_name: str,
    url: str,
    commit_hash: str,
    file: str,
    file_without_base: str,
) -> list[dict]:
    methods_in_file = []

    try:
        java_methods = scanner.scanMethod(file_without_base)
        for jm in java_methods:
            methods_in_file.append(
                {
                    "project": repository_name,
                    "name": jm.getName(),
                    "url": jm.getUrl(),
                    "artifact": jm.getArtifact(),
                    "start_line": jm.getStartLine(),
                    "end_line": jm.getEndLine(),
                    "expression": jm.getExpression(),
                    "file": jm.getFile(),
                    "pkg": jm.getPkg(),
                    "fqn": jm.getFqn(),
                    "fqs": jm.getFqs(),
                    "fqs_alt": jm.getFqsAlt(),
                    "hash": jm.getHash(),
                    "parser": "javaparser",
                }
            )
    except Exception:
        try:
            java_code = _read_source_file_text(file)
            if java_code is None:
                return methods_in_file
            tree = javalang.parse.parse(java_code)
            for _, node in tree.filter(javalang.tree.MethodDeclaration):
                if node.position:
                    start_line = node.position.line if node.position else None
                    methods_in_file.append(
                        {
                            "project": repository_name,
                            "name": node.name,
                            "url": util.format_to_git_url(url, commit_hash, file_without_base, start_line),
                            "artifact": "unknown",
                            "start_line": start_line,
                            "end_line": None,
                            "expression": None,
                            "pkg": None,
                            "fqn": None,
                            "fqs": None,
                            "fqs_alt": None,
                            "file": file_without_base,
                            "hash": commit_hash,
                            "parser": "javalang",
                        }
                    )
        except Exception:
            pass

    return methods_in_file


def scan_method(repository_df: DataFrame, repository_directory: str, data_directory: str, _cache_directory):
    from jpype import JClass
    MethodScannerImpl = JClass(
        "rnd.method.parser.call.graph.service.MethodScannerImpl"
    )

    for _, repository in repository_df.iterrows():
        scanner = MethodScannerImpl.getInstance()
        repository_name = repository["project"]
        url = repository['url']
        commit_hash = repository['updated_hash']
        dot_file_directory = util.format_git_project_directory(repository_directory, repository_name)
        output_method_file = util.format_method_list_file(f"{data_directory}", repository_name)
        method_cache_file = util.format_method_cache_file(f"{data_directory}", repository_name, commit_hash)
        if not os.path.exists(method_cache_file) and _is_method_output_current(output_method_file, commit_hash):
            continue

        clone_and_checkout_commit(url, dot_file_directory, commit_hash)
        scanner.init(dot_file_directory, url, commit_hash)
        java_files = sorted(collect_files(dot_file_directory, "*.java"))
        cached_files = _load_cached_method_scan_files(method_cache_file)

        last_flush_time = time.monotonic()
        pending_method_rows = []
        for file in java_files:
            file_without_base = file[len(dot_file_directory) + 1:]
            if file_without_base in cached_files:
                continue

            methods_in_file = _scan_methods_in_file(
                scanner,
                repository_name,
                url,
                commit_hash,
                file,
                file_without_base,
            )
            pending_method_rows.extend(methods_in_file)
            pending_method_rows.append(
                _build_scan_marker_row(repository_name, file_without_base, commit_hash)
            )

            if time.monotonic() - last_flush_time >= SCAN_METHOD_FLUSH_INTERVAL_SECONDS:
                _flush_method_scan_buffers(
                    method_cache_file,
                    pending_method_rows,
                )
                last_flush_time = time.monotonic()

        _flush_method_scan_buffers(
            method_cache_file,
            pending_method_rows,
        )
        _finalize_method_scan_outputs(
            method_cache_file,
            output_method_file,
        )


def start_java_jar(jars: [str], java_options: str | None = None):
    if not jpype.isJVMStarted():
        jvm_args = shlex.split(java_options) if java_options else []
        jpype.startJVM(*jvm_args, classpath=jars)
        # class MethodLister(VoidVisitorAdapter):
        #     def __init__(self):
        #         self.methods = []
        #
        #     def visit(self, mt, file):
        #         super(MethodLister, self).visit(mt, file)
        #
        #         method_name = mt.getNameAsString()
        #         line_number = mt.getName().getBegin().get().line
        #         artifact = "test" if 'test' in file.lower() or 'androidTest'.lower() in file.lower() else "production"
        #         self.methods.append(Method(file, artifact, method_name, line_number))


def stop_java_jar():
    if jpype.isJVMStarted():
        jpype.shutdownJVM()


def collect_methods(repository_directory: str, path: str):
    return None


def collect_files(repository_directory: str, file_pattern: str):
    path = Path(repository_directory)
    return list(map(os.fspath, path.rglob(file_pattern)))


def clone_and_checkout_commit(repo_url, repository_directory, commit_hash):
    """Clone a GitHub repository and checkout a specific commit hash.
       Raises an exception if cloning or checking out fails.
    """
    clone_attempts = 3
    try:
        repo = None
        last_error: GitCommandError | None = None
        for attempt in range(1, clone_attempts + 1):
            try:
                if os.path.exists(repository_directory):
                    print(f"Repository already exists at {repository_directory}. Opening local checkout...")
                    repo = Repo(repository_directory)
                    if repo.bare:
                        raise Exception(f"Error: The repository at {repository_directory} is corrupted or incomplete.")
                else:
                    print(f"Cloning repository {repo_url} into {repository_directory} (attempt {attempt}/{clone_attempts})...")
                    repo = Repo.clone_from(
                        repo_url,
                        repository_directory,
                        multi_options=["--filter=blob:none", "--no-tags"],
                    )
                break
            except GitCommandError as error:
                last_error = error
                if os.path.exists(repository_directory):
                    shutil.rmtree(repository_directory, ignore_errors=True)
                if attempt == clone_attempts:
                    raise
                time.sleep(min(5, attempt))

        if repo is None:
            raise Exception(f"Failed to clone repository after {clone_attempts} attempts: {last_error}")

        # Checkout specific commit hash
        print(f"Checking out commit {commit_hash}...")
        try:
            repo.git.fetch("origin", commit_hash, "--depth", "1")
        except GitCommandError:
            repo.remotes.origin.fetch()
        repo.git.checkout(commit_hash)

        # Verify checkout success
        current_commit = repo.head.object.hexsha
        if commit_hash not in current_commit:
            raise Exception(
                f"Failed to checkout the correct commit. Expected: {commit_hash}, Got: {current_commit}")

        print(f"Successfully checked out commit: {commit_hash}")
        return current_commit

    except GitCommandError as e:
        raise Exception(f"Git command failed: {repository_directory} {str(e)}")
    except Exception as e:
        raise Exception(f"Error: {str(e)}")


def get_all_commit_info(repo_path, branch="HEAD"):
    repo = Repo(repo_path)
    commits = []

    for c in repo.iter_commits(branch):
        commits.append({
            "hash": c.hexsha,
            "author": c.author.name,
            "email": c.author.email,
            "date": c.committed_datetime,
            "message": c.message.strip(),
            "parents": [p.hexsha for p in c.parents],
        })

    return commits
