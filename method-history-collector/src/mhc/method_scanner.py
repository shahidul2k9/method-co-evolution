import os.path
import os
from pathlib import Path
from git import Repo, GitCommandError
from pandas import DataFrame
import jpype
import jpype.imports
from jpype.types import *
import pandas as pd
import mhc.util as util


class Method:
    def __init__(self, file: str, method_type: str, name: str, line: int):
        self.file = file
        self.method_type = method_type
        self.name = name
        self.line = line


def scan_method(repository_df: DataFrame, repository_directory: str, data_directory: str, cache_directory):
    from com.github.javaparser import StaticJavaParser, ParserConfiguration
    from com.github.javaparser.ast.visitor import VoidVisitorAdapter
    from com.github.javaparser.ast.body import MethodDeclaration
    from java.io import File

    for _, repository in repository_df.iterrows():
        repository_name = repository['name']
        url = repository['url']
        hash = repository['hash']
        git_repository_directory = util.format_git_project_directory(repository_directory, repository_name)
        output_method_file = util.format_method_list_file(data_directory, repository_name)
        output_method_error_file = os.path.join(f"{cache_directory}/log", f"{repository_name}--method-scan-log.csv")
        if not os.path.exists(output_method_file):
            clone_and_checkout_commit(url, git_repository_directory, hash)
            java_files = collect_files(git_repository_directory, "*.java")
            print(java_files)
            methods = []
            errors = []
            for file in java_files:
                file_without_base = file[len(git_repository_directory) + 1:]
                try:
                    cu = StaticJavaParser.parse(File(file))
                    if cu is not None:
                        method_decls = cu.findAll(MethodDeclaration)
                        for mt in method_decls:
                            method_name = mt.getNameAsString()
                            line_number = mt.getName().getBegin().get().line
                            method_type = "test" if '/test/' in file_without_base.lower() or '/androidTest/'.lower() in file_without_base.lower() else "production"
                            methods.append(
                                {'file': file_without_base, 'method_type': method_type, 'method_name': method_name,
                                 'start_line': line_number})
                except Exception as e:
                    errors.append({'file': file_without_base, 'error': str(e)})
            if len(methods) > 0:
                os.makedirs(os.path.dirname(output_method_file), exist_ok=True)
                pd.DataFrame(methods).to_csv(output_method_file, index=False)
            if len(errors) > 0:
                os.makedirs(os.path.dirname(output_method_error_file), exist_ok=True)
                pd.DataFrame(errors).to_csv(output_method_error_file, index=False)


def start_java_parser(java_parser_jar_location: str):
    if not jpype.isJVMStarted():
        jpype.startJVM(classpath=[java_parser_jar_location])
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


def stop_java_parser():
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

    except GitCommandError as e:
        raise Exception(f"Git command failed: {repository_directory} {str(e)}")
    except Exception as e:
        raise Exception(f"Error: {str(e)}")
