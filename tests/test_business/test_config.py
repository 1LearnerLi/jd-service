"""电商业务线配置测试"""
from app.business.ecommerce.config import EcommerceSettings


class TestEcommerceSettings:
    """EcommerceSettings 配置测试"""

    def test_default_database_url(self):
        """验证默认数据库 URL 存在"""
        settings = EcommerceSettings()
        assert "mysql" in settings.eco_database_url
        assert "ecs" in settings.eco_database_url

    def test_config_is_distinct_from_platform(self):
        """验证业务线配置与平台配置使用不同数据库"""
        from app.config import settings as platform_settings

        eco_settings = EcommerceSettings()
        assert eco_settings.eco_database_url != platform_settings.platform_database_url
        # 业务配置不应该感知平台数据库
        assert not hasattr(eco_settings, "platform_database_url")

    def test_env_file_config(self):
        """验证从 .env 读取配置"""
        settings = EcommerceSettings()
        # 应该有 model_config 从 .env 读取
        assert hasattr(settings, "model_config")
        assert "env_file" in settings.model_config
