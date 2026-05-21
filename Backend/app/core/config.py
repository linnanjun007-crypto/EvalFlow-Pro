from functools import lru_cache
from pydantic import BaseModel, Field


class Settings(BaseModel):
    project_name: str = Field(default="EvalFlow Pro Backend")
    version: str = Field(default="0.1.0")
    api_v1_prefix: str = Field(default="/api/v1")
    database_url: str = Field(default="postgresql+psycopg://postgres:123456@localhost:5432/postgres")
    redis_url: str = Field(default="redis://localhost:6379/0")
    upload_dir: str = Field(default="data/uploads")
    output_dir: str = Field(default="data/outputs")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
