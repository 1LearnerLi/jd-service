"""LLM 客户端封装单元测试"""
import pytest
from unittest.mock import patch, MagicMock

from app.llm.client import get_llm, reset_llm
from langchain_openai import ChatOpenAI


class TestGetLlm:
    """get_llm 工厂函数测试"""

    def test_returns_chatopenai_instance(self):
        """验证返回 ChatOpenAI 实例"""
        reset_llm()
        with patch("app.llm.client.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock(spec=ChatOpenAI)
            llm = get_llm()
            assert isinstance(llm, MagicMock)
            mock_cls.assert_called_once()

    def test_singleton_returns_same_instance(self):
        """验证单例模式：多次调用返回同一实例"""
        reset_llm()
        with patch("app.llm.client.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock(spec=ChatOpenAI)
            llm1 = get_llm()
            llm2 = get_llm()
            assert llm1 is llm2
            # ChatOpenAI 只被构造一次
            mock_cls.assert_called_once()

    def test_default_temperature(self):
        """验证默认 temperature 为 0.1"""
        reset_llm()
        with patch("app.llm.client.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock(spec=ChatOpenAI)
            get_llm()
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["temperature"] == 0.1

    def test_custom_temperature_on_first_call(self):
        """验证首次调用可指定 temperature"""
        reset_llm()
        with patch("app.llm.client.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock(spec=ChatOpenAI)
            get_llm(temperature=0.7)
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs["temperature"] == 0.7

    def test_uses_settings_for_model_config(self):
        """验证使用 Settings 中的配置创建 LLM"""
        reset_llm()
        with patch("app.llm.client.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock(spec=ChatOpenAI)
            get_llm()
            call_kwargs = mock_cls.call_args.kwargs
            # model 来自 settings.llm_model
            assert "model" in call_kwargs
            assert "api_key" in call_kwargs
            assert "base_url" in call_kwargs


class TestResetLlm:
    """reset_llm 函数测试"""

    def test_reset_creates_new_instance(self):
        """验证 reset 后可创建新的 LLM 实例"""
        reset_llm()
        with patch("app.llm.client.ChatOpenAI") as mock_cls:
            mock_instance_1 = MagicMock(spec=ChatOpenAI)
            mock_instance_2 = MagicMock(spec=ChatOpenAI)
            mock_cls.side_effect = [mock_instance_1, mock_instance_2]
            llm1 = get_llm()
            assert mock_cls.call_count == 1
            # 重置
            reset_llm()
            llm2 = get_llm()
            assert mock_cls.call_count == 2
            assert llm1 is not llm2
