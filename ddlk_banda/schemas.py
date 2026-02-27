from __future__ import annotations

from pydantic import BaseModel, Field

from ddlk_banda.models import CallType, ChatType, MessageType


class UserCreate(BaseModel):
    username: str
    display_name: str


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str


class DeviceRegister(BaseModel):
    user_id: str
    device_label: str
    identity_key_public: str
    signed_prekey_public: str
    signed_prekey_signature: str
    pq_kyber_public: str | None = None


class DeviceOut(BaseModel):
    id: str
    user_id: str
    device_label: str


class ChatCreate(BaseModel):
    owner_id: str
    title: str | None = None
    members: list[str] = Field(default_factory=list)


class ChatOut(BaseModel):
    id: str
    chat_type: ChatType
    title: str | None = None
    is_forum: bool = False


class TopicCreate(BaseModel):
    creator_user_id: str
    title: str
    icon_emoji: str | None = None


class TopicOut(BaseModel):
    id: str
    group_id: str
    title: str
    icon_emoji: str | None = None
    is_archived: bool


class TopicArchive(BaseModel):
    is_archived: bool


class MessageCreate(BaseModel):
    chat_id: str
    sender_user_id: str
    sender_device_id: str
    client_msg_id: str
    ciphertext: str
    nonce: str
    aad: str | None = None
    message_type: MessageType = MessageType.text
    topic_id: str | None = None


class MessageOut(BaseModel):
    id: str
    chat_id: str
    topic_id: str | None = None
    server_seq: int


class ReactionCreate(BaseModel):
    user_id: str
    emoji: str
    custom_emoji_id: str | None = None


class CallStart(BaseModel):
    chat_id: str
    initiator_user_id: str
    call_type: CallType


class SignalPayload(BaseModel):
    user_id: str
    device_id: str
    sdp: str | None = None
    ice_candidate: str | None = None
