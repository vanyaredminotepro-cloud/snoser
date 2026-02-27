from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.sqlite import BLOB
from sqlalchemy.orm import Mapped, mapped_column

from ddlk_banda.database import Base


class UserStatus(str, enum.Enum):
    active = "active"
    blocked = "blocked"
    deleted = "deleted"


class ChatType(str, enum.Enum):
    direct = "direct"
    group = "group"
    supergroup = "supergroup"
    channel = "channel"


class MembershipRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    member = "member"
    subscriber = "subscriber"


class MessageType(str, enum.Enum):
    text = "text"
    media = "media"
    system = "system"
    service = "service"


class DeliveryState(str, enum.Enum):
    pending = "pending"
    delivered = "delivered"
    acked = "acked"


class CallType(str, enum.Enum):
    voice = "voice"
    video = "video"


class CallState(str, enum.Enum):
    created = "created"
    ringing = "ringing"
    active = "active"
    ended = "ended"


class JoinState(str, enum.Enum):
    invited = "invited"
    joined = "joined"
    left = "left"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.active, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    device_label: Mapped[str] = mapped_column(String(100))
    identity_key_public: Mapped[bytes] = mapped_column(BLOB)
    signed_prekey_public: Mapped[bytes] = mapped_column(BLOB)
    signed_prekey_signature: Mapped[bytes] = mapped_column(BLOB)
    pq_kyber_public: Mapped[bytes | None] = mapped_column(BLOB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_type: Mapped[ChatType] = mapped_column(Enum(ChatType), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_forum: Mapped[bool] = mapped_column(Boolean, default=False)
    linked_discussion_chat_id: Mapped[str | None] = mapped_column(ForeignKey("chats.id"), nullable=True)
    max_members: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMembership(Base):
    __tablename__ = "chat_memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[MembershipRole] = mapped_column(Enum(MembershipRole), default=MembershipRole.member)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ForumTopic(Base):
    __tablename__ = "forum_topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    icon_emoji: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_msg_chat_topic_seq", "chat_id", "topic_id", "server_seq"),
        UniqueConstraint("sender_device_id", "client_msg_id", name="uq_device_client_msg"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    sender_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    sender_device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    topic_id: Mapped[str | None] = mapped_column(ForeignKey("forum_topics.id"), nullable=True)
    client_msg_id: Mapped[str] = mapped_column(String(64))
    ciphertext: Mapped[bytes] = mapped_column(BLOB)
    nonce: Mapped[bytes] = mapped_column(BLOB)
    aad: Mapped[bytes | None] = mapped_column(BLOB, nullable=True)
    message_type: Mapped[MessageType] = mapped_column(Enum(MessageType), default=MessageType.text)
    server_seq: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageReaction(Base):
    __tablename__ = "message_reactions"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "emoji", "custom_emoji_id", name="uq_reaction"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    emoji: Mapped[str] = mapped_column(String(32))
    custom_emoji_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CallSession(Base):
    __tablename__ = "call_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    initiator_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    call_type: Mapped[CallType] = mapped_column(Enum(CallType))
    state: Mapped[CallState] = mapped_column(Enum(CallState), default=CallState.created)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CallParticipant(Base):
    __tablename__ = "call_participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id: Mapped[str] = mapped_column(ForeignKey("call_sessions.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    webrtc_offer: Mapped[str | None] = mapped_column(String, nullable=True)
    webrtc_answer: Mapped[str | None] = mapped_column(String, nullable=True)
    ice_candidates: Mapped[list] = mapped_column(JSON, default=list)
    join_state: Mapped[JoinState] = mapped_column(Enum(JoinState), default=JoinState.invited)


class SyncCursor(Base):
    __tablename__ = "sync_cursors"
    __table_args__ = (UniqueConstraint("user_id", "device_id", "chat_id", "topic_id", name="uq_cursor"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    topic_id: Mapped[str | None] = mapped_column(ForeignKey("forum_topics.id"), nullable=True)
    last_server_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    last_acked_client_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
