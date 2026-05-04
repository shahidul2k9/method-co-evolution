import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=True)

REQUIRED_VARS = [
    "ME_PROJECT_DIRECTORY",
    "ME_CACHE_DIRECTORY",
    "ME_DATA_DIRECTORY",
    "ME_REPOSITORY_DIRECTORY",
    "ME_JAR_DIRECTORY",
    "GITHUB_API_KEY"
]

missing = [var for var in REQUIRED_VARS if not os.environ.get(var)]

if missing:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(missing)}"
    )

PROJECT_DIRECTORY = os.environ["ME_PROJECT_DIRECTORY"]
CACHE_DIRECTORY = os.environ["ME_CACHE_DIRECTORY"]
DATA_DIRECTORY = os.environ["ME_DATA_DIRECTORY"]
HISTORY_DIRECTORY = os.environ.get("ME_HISTORY_DIRECTORY", str(Path(CACHE_DIRECTORY) / "history"))
REPOSITORY_DIRECTORY = os.environ["ME_REPOSITORY_DIRECTORY"]
JAR_DIRECTORY = os.environ["ME_JAR_DIRECTORY"]
GITHUB_API_KEY = os.environ["GITHUB_API_KEY"]
HF_TOKEN = os.environ.get("HF_TOKEN")
