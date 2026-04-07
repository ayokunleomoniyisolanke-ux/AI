from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OPENAI_API_KEY: str = ""
    SPEEDVIBE_BASE_URL: str = "https://speedvibeinfotech-hub.com.ng"
    CHROMA_PERSIST_DIR: str = "./chroma_data_speedvibe"
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    @property
    def chroma_path(self) -> Path:
        return Path(self.CHROMA_PERSIST_DIR).resolve()


settings = Settings()
