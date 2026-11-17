import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    starting_equity: float = 5000
    exchange_api_key: str = os.getenv("EXCHANGE_API_KEY", "")


settings = Settings()
