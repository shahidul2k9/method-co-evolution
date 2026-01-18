import os


def format_git_project_directory(repository_directory: str, repository_name: str) -> str:
    return os.path.join(f"{repository_directory}", repository_name)


def format_method_list_file(data_directory: str, repository_name: str) -> str:
    return os.path.join(f"{data_directory}/method", f"{repository_name}--method.csv")


def format_repository_history_index_file(cache_dir: str) -> str:
    return os.path.join(f"{cache_dir}", f"repository-history-index.csv")


def format_method_history_path(cache_directory: str, tool_name: str, repository_name) -> str:
    return os.path.join(f"{cache_directory}/history/{tool_name}/{repository_name}")


def format_method_history_file_suffix(file: str, method_name: str, start_line: int) -> str:
    file_without_extension = file[:-len('.java')] if file.lower().endswith(".java") else file
    file.replace(".java", "")
    return os.path.join(f"{file_without_extension}--{method_name}--{start_line}.json")



def format_to_git_url(repository_url: str, hash: str, file: str, line_no: int) -> str:
    return f"{repository_url}/blob/{hash}/{file}#L{line_no}"


def remove_prefix_if_exists(s: set[str], prefix) -> set[str]:
    return set(map(lambda f: f[len(prefix):] if f.startswith(prefix) else f, s))
