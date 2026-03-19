import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=True)

REQUIRED_VARS = [
    "ME_CACHE_DIRECTORY",
    "ME_DATA_DIRECTORY",
    "ME_REPOSITORY_DIRECTORY",
    "ME_JAR_DIRECTORY",
    "ME_REPOSITORY_GROUP",
    "GITHUB_API_KEY"
]

missing = [var for var in REQUIRED_VARS if not os.environ.get(var)]

if missing:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(missing)}"
    )

CACHE_DIRECTORY = os.environ["ME_CACHE_DIRECTORY"]
DATA_DIRECTORY = os.environ["ME_DATA_DIRECTORY"]
REPOSITORY_DIRECTORY = os.environ["ME_REPOSITORY_DIRECTORY"]
REPOSITORY_GROUP = os.environ["ME_REPOSITORY_GROUP"]
JAR_DIRECTORY = os.environ["ME_JAR_DIRECTORY"]
GITHUB_API_KEY = os.environ["GITHUB_API_KEY"]
HF_TOKEN = os.environ.get("HF_TOKEN")
