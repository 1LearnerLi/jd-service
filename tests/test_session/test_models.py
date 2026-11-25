"""会话层模型测试"""
import pytest
from app.session.models import Session, Message


class TestSessionModel:
    """Session ORM 模型测试"""

    def test_session_model_fields(self):
        """验证 Session 模型包含所有必要字段"""
        assert hasattr(Session, "id")
        assert hasattr(Session, "user_id")
        assert hasattr(Session, "title")
        assert hasattr(Session, "status")
        assert hasattr(Session, "created_at")
        assert hasattr(Session, "updated_at")

    def test_session_tablename(self):
        """验证 Session 表名"""
        assert Session.__tablename__ == "sessions"

    def test_session_id_type(self):
        """验证 Session.id 为 String(50)"""
        col = Session.__table__.columns["id"]
        assert str(col.type) == "VARCHAR(50)"

    def test_session_user_id_index(self):
        """验证 user_id 有索引"""
        col = Session.__table__.columns["user_id"]
        assert col.index is True

    def test_session_default_status(self):
        """验证 Session.status 默认值为 active"""
        col = Session.__table__.columns["status"]
        assert col.default.arg == "active"

    def test_session_messages_relationship(self):
        """验证 Session 和 Message 的关联关系"""
        assert hasattr(Session, "messages")


class TestMessageModel:
    """Message ORM 模型测试"""

    def test_message_model_fields(self):
        """验证 Message 模型包含所有必要字段"""
        assert hasattr(Message, "id")
        assert hasattr(Message, "session_id")
        assert hasattr(Message, "role")
        assert hasattr(Message, "content")
        assert hasattr(Message, "intent")
        assert hasattr(Message, "slots_json")
        assert hasattr(Message, "created_at")

    def test_message_tablename(self):
        """验证 Message 表名"""
        assert Message.__tablename__ == "messages"

    def test_message_session_id_foreign_key(self):
        """验证 session_id 有外键"""
        col = Message.__table__.columns["session_id"]
        assert col.foreign_keys

    def test_message_session_id_index(self):
        """验证 session_id 有索引"""
        col = Message.__table__.columns["session_id"]
        assert col.index is True

    def test_message_session_relationship(self):
        """验证 Message 和 Session 的关联关系"""
        assert hasattr(Message, "session")
