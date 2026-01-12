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
import util as util
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
    from com.github.javaparser import StaticJavaParser, ParserConfiguration
    from com.github.javaparser.symbolsolver import JavaSymbolSolver
    from com.github.javaparser.symbolsolver.resolution.typesolvers import (
        CombinedTypeSolver,
        ReflectionTypeSolver,
        JavaParserTypeSolver
    )
    from com.github.javaparser.ast.visitor import VoidVisitorAdapter
    from com.github.javaparser.ast.body import MethodDeclaration
    from java.io import File
    from com.github.javaparser.ast.body import ClassOrInterfaceDeclaration
    def has_test_annotation(method_decl, is_strict: bool) -> bool:
        for ann in method_decl.getAnnotations():
            if is_strict:
                # STRICT: fully-qualified name via symbol solver
                resolved = ann.resolve()
                if resolved.getQualifiedName() in TEST_ANNOTATION_FQNS:
                    return True
            else:
                # NON-STRICT: simple name only (no resolution)
                if ann.getNameAsString() in {
                    fqn.split(".")[-1] for fqn in TEST_ANNOTATION_NAMES
                }:
                    return True
        return False

    def get_package_name(compilation_unit):
        if compilation_unit.getPackageDeclaration().isPresent():
            return compilation_unit.getPackageDeclaration().get().getNameAsString()
        return ""

    def class_extends_test_fqn(class_decl):
        resolved_class = class_decl.resolve()

        # direct class itself
        if resolved_class.getQualifiedName() in UNIT_TEST_SUPERCLASS_FQNS:
            return True

        # all ancestors
        for ancestor in resolved_class.getAllAncestors():
            if ancestor.getQualifiedName() in UNIT_TEST_SUPERCLASS_FQNS:
                return True

        return False

    # TODO: improve logic with gradle and pom build file
    def determine_method_type(file: str, package: str, mt, is_strict_check: bool) -> str:
        bare_file_name = file.split("/")[-1]
        package_with_slash = package.replace(".", "/")

        suffix_with_package_and_file = "/" + bare_file_name if not package else "/" + package_with_slash + "/" + bare_file_name
        method_type = "production"
        if file.endswith(suffix_with_package_and_file):
            prefix = file[:-len(suffix_with_package_and_file)]
            for possible_package_root in TEST_PACKAGE_ROOT_DIRECTORY:
                if prefix.endswith("/" + possible_package_root):
                    method_type = "other"
                    break

        if has_test_annotation(mt, is_strict=is_strict_check):
            method_type = "test"
        else:
            # Superclass inheritance (FQN only)
            parent_class = mt.findAncestor(ClassOrInterfaceDeclaration)
            if parent_class.isPresent():
                if class_extends_test_fqn(parent_class.get()):
                    method_type = "test"

        return method_type

    for _, repository in repository_df.iterrows():
        repository_name = repository['name']
        url = repository['url']
        hash = repository['hash']
        dot_file_directory = util.format_git_project_directory(repository_directory, repository_name)
        output_method_file = util.format_method_list_file(f"{data_directory}", repository_name)
        output_method_error_file = os.path.join(f"{cache_directory}/log", f"{repository_name}--method-scan-log.csv")
        # if not os.path.exists(output_method_file):
        if True:
            clone_and_checkout_commit(url, dot_file_directory, hash)
            java_files = collect_files(dot_file_directory, "*.java")
            methods = []
            errors = []
            for file in java_files:
                file_without_base = file[len(dot_file_directory) + 1:]
                method_type = "todo"

                try:
                    type_solver = CombinedTypeSolver()
                    # JDK classes (java.lang, etc.)
                    type_solver.add(ReflectionTypeSolver())
                    # Project source root
                    # type_solver.add(JavaParserTypeSolver(dot_file_directory))
                    symbol_solver = JavaSymbolSolver(type_solver)
                    config = ParserConfiguration()
                    config.setLanguageLevel(ParserConfiguration.LanguageLevel.BLEEDING_EDGE)
                    config.setSymbolResolver(symbol_solver)
                    StaticJavaParser.setConfiguration(config)
                    cu = StaticJavaParser.parse(File(file))

                    package_name = str(cu.getPackageDeclaration().get().getNameAsString()) if cu.getPackageDeclaration().isPresent() else ""

                    methods_in_file = []
                    if cu is not None:
                        method_decls = cu.findAll(MethodDeclaration)
                        for mt in method_decls:
                            method_type = determine_method_type(file_without_base, package_name, mt, True)
                            start_line = mt.getName().getBegin().get().line
                            methods_in_file.append(
                                {'file': file_without_base,
                                 'method_type': method_type,
                                 'method_name': mt.getNameAsString(),
                                 'start_line': start_line,
                                 'end_line': mt.getEnd().get().line,
                                 'hash': hash,
                                 'url': util.format_to_git_url(url, hash, file_without_base, start_line),
                                 'parser': 'javaparser'})
                    methods.extend(methods_in_file)
                except Exception as e:
                    raise e
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
                                     'method_type': method_type,
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
