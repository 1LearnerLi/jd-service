"""平台核心模块测试"""
import pytest
from app.core.exceptions import (
    AppException,
    NotFoundException,
    ValidationException,
    BusinessException,
)
from app.core.response import APIResponse, success_response, error_response


class TestExceptions:
    """异常类测试"""

    def test_app_exception_default(self):
        """AppException 默认参数"""
        exc = AppException("错误")
        assert exc.message == "错误"
        assert exc.status_code == 500
        assert str(exc) == "错误"

    def test_app_exception_custom_status(self):
        """AppException 自定义状态码"""
        exc = AppException("自定义", status_code=418)
        assert exc.status_code == 418

    def test_not_found_exception(self):
        """NotFoundException 默认行为"""
        exc = NotFoundException()
        assert exc.status_code == 404
        assert exc.message == "资源不存在"

    def test_not_found_exception_custom_msg(self):
        """NotFoundException 自定义消息"""
        exc = NotFoundException("用户不存在")
        assert exc.status_code == 404
        assert exc.message == "用户不存在"

    def test_validation_exception(self):
        """ValidationException 默认行为"""
        exc = ValidationException()
        assert exc.status_code == 422
        assert exc.message == "参数校验失败"

    def test_business_exception(self):
        """BusinessException 默认行为"""
        exc = BusinessException()
        assert exc.status_code == 400
        assert exc.message == "业务处理失败"

    def test_exception_inheritance(self):
        """异常继承关系"""
        assert issubclass(NotFoundException, AppException)
        assert issubclass(ValidationException, AppException)
        assert issubclass(BusinessException, AppException)


class TestAPIResponse:
    """统一响应模型测试"""

    def test_api_response_default(self):
        """APIResponse 默认值"""
        resp = APIResponse()
        assert resp.success is True
        assert resp.data is None
        assert resp.error is None
        assert resp.meta is None

    def test_api_response_with_data(self):
        """APIResponse 携带数据"""
        resp = APIResponse(success=True, data={"id": 1})
        assert resp.data == {"id": 1}

    def test_success_response_no_data(self):
        """success_response 无数据"""
        result = success_response()
        assert result["success"] is True
        assert result["data"] is None
        assert result["error"] is None
        assert result["meta"] is None

    def test_success_response_with_data(self):
        """success_response 携带数据"""
        result = success_response(data={"key": "value"})
        assert result["success"] is True
        assert result["data"] == {"key": "value"}

    def test_success_response_with_meta(self):
        """success_response 携带元数据"""
        result = success_response(data=[], meta={"total": 0, "page": 1})
        assert result["meta"] == {"total": 0, "page": 1}

    def test_error_response(self):
        """error_response 基本行为"""
        result = error_response("出错了")
        assert result["success"] is False
        assert result["data"] is None
        assert result["error"] == "出错了"

    def test_error_response_empty_msg(self):
        """error_response 空消息"""
        result = error_response("")
        assert result["success"] is False
        assert result["error"] == ""


class TestSettings:
    """配置加载测试"""

    def test_settings_loads_from_env(self):
        """Settings 从 .env 加载"""
        from app.config import settings

        # 基本类型检查
        assert isinstance(settings.openai_api_key, str)
        assert isinstance(settings.openai_base_url, str)
        assert isinstance(settings.llm_model, str)
        assert isinstance(settings.platform_database_url, str)
        assert isinstance(settings.app_host, str)
        assert isinstance(settings.app_port, int)
        assert isinstance(settings.log_level, str)

    def test_settings_has_required_fields(self):
        """Settings 包含所有必要字段"""
        from app.config import Settings

        fields = Settings.model_fields
        assert "openai_api_key" in fields
        assert "openai_base_url" in fields
        assert "llm_model" in fields
        assert "platform_database_url" in fields
        assert "app_host" in fields
        assert "app_port" in fields
        assert "log_level" in fields
