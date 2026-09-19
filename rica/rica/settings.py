from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    litellm_base_url: str = "http://litellm:4000/v1"
    litellm_master_key: str = ""
    rica_internal_key: str = ""
    knowledge_dir: Path = Path("/knowledge")
    tz: str = "Asia/Dhaka"
    # Used until _rica/profile.md sets preferred_name
    owner_name: str = ""
    ladders_file: Path = PACKAGE_DIR / "config" / "ladders.yaml"
    warmup_local: bool = True
    planner_history_messages: int = 6

    # Retrieval (M3+)
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "rica_chunks"
    data_dir: Path = Path("/data")
    fastembed_cache: Path = Path("/cache/fastembed")

    # Knowledge sync (rica-ingest)
    knowledge_repo: str = ""
    knowledge_branch: str = "main"
    sync_interval_s: int = 120
    deploy_key: Path = Path("/run/secrets/deploy_key")
    known_hosts: Path = Path("/run/secrets/known_hosts")
