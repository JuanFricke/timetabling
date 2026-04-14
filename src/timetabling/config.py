"""Application configuration loaded from environment variables / .env file."""
import os

from dotenv import load_dotenv

load_dotenv()


def get(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


DATABASE_URL: str = get("DATABASE_URL", "mysql+pymysql://app:apppass@localhost:3306/timetabling")  # type: ignore[assignment]
HARD_BLOCKS_PATH: str = get("HARD_BLOCKS_PATH", "data/input/hard_blocks.json")  # type: ignore[assignment]
SOFT_BLOCKS_PATH: str = get("SOFT_BLOCKS_PATH", "data/input/soft_blocks.json")  # type: ignore[assignment]
OUTPUT_DIR: str = get("OUTPUT_DIR", "data/output")  # type: ignore[assignment]
CP_TIME_LIMIT_SECONDS: int = int(get("CP_TIME_LIMIT_SECONDS", "60"))  # type: ignore[arg-type]
LS_MAX_ITERATIONS: int = int(get("LS_MAX_ITERATIONS", "5000"))  # type: ignore[arg-type]
