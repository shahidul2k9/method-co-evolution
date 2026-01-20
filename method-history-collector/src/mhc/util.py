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



def format_to_git_url(repository_url: str, hash: str, file: str, start_line_no: int) -> str:
    return f"{repository_url}/blob/{hash}/{file}#L{start_line_no}"

def convert_method_file_to_method_url(repository_url: str, hash: str, method_file: str) -> str:
    file_parts = method_file.rsplit("/", maxsplit=1)
    file_path_prefix = f"{file_parts[0]}/" if len(file_parts) > 1 else ""
    bare_method_file_name = file_parts[-1]
    file_name, method_name, start_line_no = bare_method_file_name.replace(".json", "").split("--")
    return f"{repository_url}/blob/{hash}/{file_path_prefix}{file_name}.java#L{start_line_no}"


def remove_prefix_if_exists(s: set[str], prefix) -> set[str]:
    return set(map(lambda f: f[len(prefix):] if f.startswith(prefix) else f, s))
