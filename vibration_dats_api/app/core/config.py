from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DATS Vibration API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8002

    max_upload_size_mb: int = 25
    max_capture_duration_seconds: int = 180
    default_window_ms: int = 500
    min_window_ms: int = 100
    max_window_ms: int = 5000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
