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
    # Cross-encoder used by pgml.rank to rerank retrieval candidates; empty = reranking off
    rerank_model: str = ""
    rerank_candidates: int = 20
    # Pipeline health: warn when the last scrape is older than this
    pipeline_stale_hours: int = 36
    # Optional Slack/Discord-compatible webhook called when a pipeline stage fails
    pipeline_alert_webhook_url: str = ""
    # CORS: comma-separated list of allowed browser origins ("*" allows any)
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Rate limiting per client IP and minute (0 disables). Chat endpoints call the LLM, so they get less.
    rate_limit_per_minute: int = 120
    rate_limit_chat_per_minute: int = 15
    # Output limit of one answer (the answer says so when it is cut off)
    llm_max_tokens: int = 2048
    # With an exact document-number match, send up to this many of that document's chunks (in order)
    pinned_chunks: int = 12
    # Read the client IP from X-Forwarded-For (only enable behind a reverse proxy you control)
    rate_limit_trust_proxy: bool = False


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
