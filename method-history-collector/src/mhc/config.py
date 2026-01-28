import os
from dotenv import load_dotenv

# Load env files (order: project root .env overrides cache .env)
load_dotenv(dotenv_path=os.path.join(".cache", ".env"), override=True)
load_dotenv(dotenv_path=".env", override=True)

REQUIRED_VARS = [
    "METHOD_EVOLUTION_CACHE_DIRECTORY",
    "METHOD_EVOLUTION_DATA_DIRECTORY",
    "METHOD_EVOLUTION_REPOSITORY_DIRECTORY",
    "METHOD_EVOLUTION_JAR_DIRECTORY",
    "METHOD_EVOLUTION_REPOSITORY_GROUP",
    "GITHUB_API_KEY"
]

missing = [var for var in REQUIRED_VARS if not os.environ.get(var)]

if missing:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(missing)}"
    )

CACHE_DIRECTORY = os.environ["METHOD_EVOLUTION_CACHE_DIRECTORY"]
DATA_DIRECTORY = os.environ["METHOD_EVOLUTION_DATA_DIRECTORY"]
REPOSITORY_DIRECTORY = os.environ["METHOD_EVOLUTION_REPOSITORY_DIRECTORY"]
REPOSITORY_GROUP = os.environ["METHOD_EVOLUTION_REPOSITORY_GROUP"]
JAR_DIRECTORY = os.environ["METHOD_EVOLUTION_JAR_DIRECTORY"]
GITHUB_API_KEY = os.environ["GITHUB_API_KEY"]
