from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://parkly:parkly@localhost:5432/parkly"
    jwt_secret: str = "local-development-only-change-me"
    access_token_minutes: int = 60
    app_env: str = "development"
    web_origin: str = "http://localhost:3000"
    event_api_key: str = "local-event-key"
    event_source_keys: str = ""
    payment_mode: str = "SIMULATED_TEST"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
