"""init: 创建 sessions 和 messages 表

Revision ID: 5cada17cea80
Revises:
Create Date: 2026-07-02 21:31:59.868461

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '5cada17cea80'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 sessions 和 messages 表"""
    # 创建 sessions 表
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("user_id", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column(
            "status",
            mysql.ENUM("active", "closed", name="session_status"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # 创建 messages 表
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(50),
            sa.ForeignKey("sessions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "role",
            mysql.ENUM("user", "assistant", name="message_role"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(50), nullable=True),
        sa.Column("slots_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """删除 messages 和 sessions 表"""
    op.drop_table("messages")
    op.drop_table("sessions")
