# app/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    API_KEY: str
    PROFILE_DIR: str = "./data/profiles"
    RULES_DIR: str = "./data/rules"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()