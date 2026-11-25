"""平台级配置，从 .env 读取"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""

    # LLM
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"

    # 平台数据库
    platform_database_url: str = "mysql+asyncmy://root:123321@localhost:3307/ecs_platform"

    # 应用
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
