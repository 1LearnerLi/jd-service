"""电商业务线数据库配置

业务线数据库连接信息属于业务线自己的管理范围，
不属于平台配置（app/config.py）。
"""
from pydantic_settings import BaseSettings


class EcommerceSettings(BaseSettings):
    """电商业务数据库配置"""

    eco_database_url: str = "mysql+asyncmy://root:123321@localhost:3307/ecs"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


ecommerce_settings = EcommerceSettings()
