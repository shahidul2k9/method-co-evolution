import os
def format_git_project_directory(repository_directory:str, repository_name: str) -> str:
    return os.path.join(f"{repository_directory}", repository_name)

def format_method_list_file(data_directory:str, repository_name: str) -> str:
    return os.path.join(f"{data_directory}", f"{repository_name}--method.csv")

def format_method_history_file(data_directory:str, tool_name:str, file:str, method_name:str, start_line:int) -> str:
    file_without_extension = file[:-len('.java')] if file.lower().endswith(".java") else file
    file.replace(".java", "")
    return os.path.join(f"{data_directory}/{tool_name}/{file_without_extension}--{method_name}--{start_line}.json")
