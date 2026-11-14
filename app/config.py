from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Influencer Executive Assistant"
    database_url: str = "sqlite:///./data/app.db"
    secret_key: str = "change-me"
    fernet_key: str = ""
    access_token_minutes: int = 30
    refresh_token_days: int = 7

    llm_provider: str = "mock"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "llama3.1"

    whisper_model: str = "small"
    telegram_bot_token: str = ""
    redis_url: str = "redis://localhost:6379/0"

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    upi_vpa: str = ""

    cors_origins: str = "http://localhost:8000"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/gmail/callback"
    gmail_sync_days: int = 14
    gmail_max_per_sync: int = 25

    reply_after_days: int = 2        # brand wrote, you have not replied
    followup_after_days: int = 3     # you wrote, brand has not replied
    calendar_pull_days: int = 30
    background_jobs: bool = False    # run reminders and syncs inside the API process (no Redis needed)
    background_interval_minutes: int = 10


settings = Settings()
