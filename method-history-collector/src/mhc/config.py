import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=True)

REQUIRED_VARS = [
    "ME_PROJECT_DIRECTORY",
    "ME_WORKSPACE_DIRECTORY",
    "ME_EXPERIMENT_NAME",
    "GITHUB_API_KEY"
]

missing = [var for var in REQUIRED_VARS if not os.environ.get(var)]

if missing:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(missing)}"
    )

PROJECT_DIRECTORY = os.environ["ME_PROJECT_DIRECTORY"]
WORKSPACE_DIRECTORY = os.environ["ME_WORKSPACE_DIRECTORY"]
GITHUB_API_KEY = os.environ["GITHUB_API_KEY"]
HF_TOKEN = os.environ.get("HF_TOKEN")
ME_EXPERIMENT_NAME = os.environ.get("ME_EXPERIMENT_NAME")
ME_TOOLS = os.environ.get("ME_TOOLS", "historyFinder")
ME_STRATEGIES = os.environ.get("ME_STRATEGIES", "omc,omc--nc--ncc")
ME_ARTIFACTS = os.environ.get("ME_ARTIFACTS", "main-code,test-code")
ME_REVISION_TYPES = os.environ.get("ME_REVISION_TYPES", "ch_diff,ch_all")
ME_PROJECT_INDEX = os.environ.get("ME_PROJECT_INDEX", ":")
ME_PROJECTS = os.environ.get("ME_PROJECTS", ":")
ME_REPLACE = os.environ.get("ME_REPLACE")


def resolve_experiment_name(experiment: str | None = None) -> str:
    resolved = (experiment or os.environ.get("ME_EXPERIMENT_NAME") or ME_EXPERIMENT_NAME or "").strip()
    if not resolved:
        raise ValueError("Experiment name is required. Pass --experiment-name or set ME_EXPERIMENT_NAME.")
    return resolved


def resolve_experiment_directory(
    workspace_directory: str | os.PathLike[str] | None = None,
    experiment: str | None = None,
) -> Path:
    workspace_root = Path(workspace_directory or WORKSPACE_DIRECTORY)
    return workspace_root / "experiment" / resolve_experiment_name(experiment)


def resolve_experiment_output_directory(
    workspace_directory: str | os.PathLike[str] | None = None,
    experiment: str | None = None,
) -> Path:
    return resolve_experiment_directory(workspace_directory, experiment)


def resolve_history_directory(
    workspace_directory: str | os.PathLike[str] | None = None,
    experiment: str | None = None,
    explicit: str | os.PathLike[str] | None = None,
) -> Path:
    return Path(explicit) if explicit is not None else resolve_experiment_directory(workspace_directory, experiment) / "history"


def resolve_repository_directory(
    workspace_directory: str | os.PathLike[str] | None = None,
    experiment: str | None = None,
    explicit: str | os.PathLike[str] | None = None,
) -> Path:
    return Path(explicit) if explicit is not None else resolve_experiment_directory(workspace_directory, experiment) / "repository"


def resolve_jar_directory(
    workspace_directory: str | os.PathLike[str] | None = None,
    explicit: str | os.PathLike[str] | None = None,
) -> Path:
    return Path(explicit) if explicit is not None else Path(workspace_directory or WORKSPACE_DIRECTORY) / "jar"


def resolve_artifact_config_path(
    workspace_directory: str | os.PathLike[str] | None = None,
    explicit: str | os.PathLike[str] | None = None,
) -> Path:
    return Path(explicit) if explicit is not None else Path(workspace_directory or WORKSPACE_DIRECTORY) / "config" / "artifact-detection"


EXPERIMENT_NAME = resolve_experiment_name(ME_EXPERIMENT_NAME)
EXPERIMENT_DIRECTORY = str(resolve_experiment_directory(WORKSPACE_DIRECTORY, EXPERIMENT_NAME))
HISTORY_DIRECTORY = os.environ.get("ME_HISTORY_DIRECTORY", str(resolve_history_directory(WORKSPACE_DIRECTORY, ME_EXPERIMENT_NAME)))
REPOSITORY_DIRECTORY = os.environ.get(
    "ME_REPOSITORY_DIRECTORY",
    str(resolve_repository_directory(WORKSPACE_DIRECTORY, ME_EXPERIMENT_NAME)),
)
JAR_DIRECTORY = os.environ.get("ME_JAR_DIRECTORY", str(resolve_jar_directory(WORKSPACE_DIRECTORY)))
