from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_INTEGRATION_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_INTEGRATION_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: Optional[str] = None
    SPEEDVIBE_BASE_URL: str = "https://speedvibeinfotech-hub.com.ng"
    CHROMA_PERSIST_DIR: str = str(_INTEGRATION_ROOT / "chroma_data_speedvibe")
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    @property
    def chroma_path(self) -> Path:
        return Path(self.CHROMA_PERSIST_DIR).resolve()


settings = Settings()
