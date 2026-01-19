import os.path
import os
import traceback
from pathlib import Path
from git import Repo, GitCommandError
from pandas import DataFrame
import jpype
import jpype.imports
from jpype.types import *
import pandas as pd
import mhc.util as util
import javalang
import datetime
import traceback

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


class Method:
    def __init__(self, file: str, method_type: str, name: str, line: int):
        self.file = file
        self.method_type = method_type
        self.name = name
        self.line = line


def scan_method(repository_df: DataFrame, repository_directory: str, data_directory: str, cache_directory):
    from jpype import JClass
    MethodScannerImpl = JClass(
        "rnd.method.parser.call.graph.service.MethodScannerImpl"
    )

    scanner = MethodScannerImpl()
    for _, repository in repository_df.iterrows():
        repository_name = repository['name']
        url = repository['url']
        hash = repository['hash']
        dot_file_directory = util.format_git_project_directory(repository_directory, repository_name)
        output_method_file = util.format_method_list_file(f"{data_directory}", repository_name)
        output_method_error_file = os.path.join(f"{cache_directory}/log", f"{repository_name}--method-scan-log.csv")
        if not os.path.exists(output_method_file):
        # if True:
            clone_and_checkout_commit(url, dot_file_directory, hash)
            java_files = collect_files(dot_file_directory, "*.java")
            methods = []
            errors = []
            for file in java_files:
                file_without_base = file[len(dot_file_directory) + 1:]
                try:
                    methods_in_file = []
                    java_methods = scanner.scanMethod(
                        dot_file_directory,
                        url,
                        hash,
                        file_without_base
                    )
                    for jm in java_methods:
                        methods_in_file.append({
                            "file": jm.getFile(),
                            "method_type": jm.getMethodType(),
                            "method_name": jm.getName(),
                            "start_line": jm.getStartLine(),
                            "end_line": jm.getEndLine(),
                            "hash": jm.getHash(),
                            "url": jm.getUrl(),
                            "parser": "javaparser"
                        })
                    methods.extend(methods_in_file)
                except Exception as e:
                    error_msg = str(e)
                    if not error_msg:
                        error_msg = f"{type(e).__module__}.{type(e).__name__}"
                    errors.append(
                        {'file': file_without_base, 'parser': 'javaparser', 'created_at': datetime.datetime.now(),
                         'msg': error_msg})
                    try:
                        methods_in_file = []
                        with open(file, 'r', encoding='utf-8') as f:
                            java_code = f.read()
                        tree = javalang.parse.parse(java_code)
                        for _, node in tree.filter(javalang.tree.MethodDeclaration):
                            if node.position:
                                start_line = node.position.line if node.position else None
                                methods_in_file.append(
                                    {'file': file_without_base,
                                     'method_type': "unknown",
                                     'method_name': node.name,
                                     'start_line': start_line,
                                     'end_line': -1, # Heuristically find end line
                                     'hash': hash,
                                     'url': util.format_to_git_url(url, hash, file_without_base, start_line),
                                     'parser': 'javalang'})
                        methods.extend(methods_in_file)
                    except Exception as e:
                        error_msg = str(e)
                        if not error_msg:
                            error_msg = f"{type(e).__module__}.{type(e).__name__}"
                        errors.append(
                            {'file': file_without_base, 'parser': 'javalang', 'created_at': datetime.datetime.now(),
                             'msg': error_msg})

            os.makedirs(os.path.dirname(output_method_file), exist_ok=True)
            pd.DataFrame(methods).to_csv(output_method_file, index=False)
            if len(errors) > 0:
                os.makedirs(os.path.dirname(output_method_error_file), exist_ok=True)
                pd.DataFrame(errors).to_csv(output_method_error_file, index=False)
            else:
                if os.path.isfile(output_method_error_file):
                    os.remove(output_method_error_file)


def start_java_jar(jars: [str]):
    if not jpype.isJVMStarted():
        jpype.startJVM(classpath=jars)
        # class MethodLister(VoidVisitorAdapter):
        #     def __init__(self):
        #         self.methods = []
        #
        #     def visit(self, mt, file):
        #         super(MethodLister, self).visit(mt, file)
        #
        #         method_name = mt.getNameAsString()
        #         line_number = mt.getName().getBegin().get().line
        #         method_type = "test" if 'test' in file.lower() or 'androidTest'.lower() in file.lower() else "production"
        #         self.methods.append(Method(file, method_type, method_name, line_number))


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
    try:
        if os.path.exists(repository_directory):
            print(f"Repository already exists at {repository_directory}. Pulling latest changes...")
            repo = Repo(repository_directory)

            # Ensure the repository is valid
            if repo.bare:
                raise Exception(
                    f"Error: The repository at {repository_directory} is corrupted or incomplete.")

            # repo.remotes.origin.pull()
        else:
            print(f"Cloning repository {repo_url} into {repository_directory}...")
            repo = Repo.clone_from(repo_url, repository_directory)

        # Checkout specific commit hash
        print(f"Checking out commit {commit_hash}...")
        # repo.remotes.origin.fetch()
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
