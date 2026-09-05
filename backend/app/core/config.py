from functools import lru_cache
from pathlib import Path
import os
from dotenv import load_dotenv

from pydantic import BaseModel

# Resolve from the repository root so `uvicorn` works from backend/ or root.
load_dotenv(Path(__file__).resolve().parents[3] / ".env")


class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL") or "sqlite:///./recon_audit.db"
    data_dir: Path = Path(os.getenv("RECON_DATA_DIR") or str(Path(__file__).resolve().parents[3] / "infra" / "seed_data")).resolve()
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    agent_step_budget: int = int(os.getenv("AGENT_STEP_BUDGET") or "4")
    agent_max_concurrency: int = int(os.getenv("AGENT_MAX_CONCURRENCY") or "4")


@lru_cache
def get_settings() -> Settings:
    return Settings()
