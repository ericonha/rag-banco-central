from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    embedding_model: str = ""
    embedding_dim: int = 0


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

    anthropic_workspace_id: str = ""
