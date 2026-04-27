from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Audio Scalogram API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8001

    max_upload_size_mb: int = 25
    max_audio_duration_seconds: int = 20
    default_sample_rate: int = 22050
    default_wavelet: str = "morl"
    default_width_min: int = 1
    default_width_max: int = 128
    default_colormap: str = "magma"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
