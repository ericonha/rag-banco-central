from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    embedding_model: str = ""
    embedding_dim: int = 0
    # USD per million tokens; 0 = unknown (cost is then not recorded)
    llm_price_input_per_mtok: float = 0.0
    llm_price_output_per_mtok: float = 0.0
    # how many previous messages (user+assistant) are sent to the LLM as context
    history_max_messages: int = 6


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
