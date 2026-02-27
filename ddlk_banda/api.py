from __future__ import annotations

import base64

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import Select, and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ddlk_banda.database import Base, engine, get_session
from ddlk_banda.models import (
    CallParticipant,
    CallSession,
    CallState,
    Chat,
    ChatMembership,
    ChatType,
    Device,
    ForumTopic,
    JoinState,
    MembershipRole,
    Message,
    MessageReaction,
    SyncCursor,
    User,
)
from ddlk_banda.schemas import (
    CallStart,
    ChatCreate,
    ChatOut,
    DeviceOut,
    DeviceRegister,
    MessageCreate,
    MessageOut,
    ReactionCreate,
    SignalPayload,
    TopicArchive,
    TopicCreate,
    TopicOut,
    UserCreate,
    UserOut,
)

app = FastAPI(title="ddlk-banda secure messenger")


@app.on_event("startup")
async def on_startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.post("/users", response_model=UserOut)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)) -> User:
    user = User(username=payload.username, display_name=payload.display_name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@app.post("/devices/register", response_model=DeviceOut)
async def register_device(payload: DeviceRegister, session: AsyncSession = Depends(get_session)) -> Device:
    user = await session.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    device = Device(
        user_id=payload.user_id,
        device_label=payload.device_label,
        identity_key_public=base64.b64decode(payload.identity_key_public),
        signed_prekey_public=base64.b64decode(payload.signed_prekey_public),
        signed_prekey_signature=base64.b64decode(payload.signed_prekey_signature),
        pq_kyber_public=base64.b64decode(payload.pq_kyber_public) if payload.pq_kyber_public else None,
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)
    return device


async def _create_chat(
    chat_type: ChatType,
    payload: ChatCreate,
    session: AsyncSession,
    *,
    is_forum: bool = False,
    max_members: int | None = None,
) -> Chat:
    chat = Chat(
        chat_type=chat_type,
        owner_id=payload.owner_id,
        title=payload.title,
        is_forum=is_forum,
        max_members=max_members,
    )
    session.add(chat)
    await session.flush()

    owner_role = MembershipRole.owner if chat_type in {ChatType.group, ChatType.supergroup, ChatType.channel} else MembershipRole.member
    session.add(ChatMembership(chat_id=chat.id, user_id=payload.owner_id, role=owner_role))
    for user_id in payload.members:
        role = MembershipRole.subscriber if chat_type == ChatType.channel else MembershipRole.member
        session.add(ChatMembership(chat_id=chat.id, user_id=user_id, role=role))

    await session.commit()
    await session.refresh(chat)
    return chat


@app.post("/chats/direct", response_model=ChatOut)
async def create_direct_chat(payload: ChatCreate, session: AsyncSession = Depends(get_session)) -> Chat:
    if len(payload.members) != 1:
        raise HTTPException(400, "direct chat requires exactly one counterpart")
    return await _create_chat(ChatType.direct, payload, session)


@app.post("/chats/groups", response_model=ChatOut)
async def create_group(payload: ChatCreate, session: AsyncSession = Depends(get_session)) -> Chat:
    if len(payload.members) > 199:
        raise HTTPException(400, "group supports up to 200 members including owner")
    return await _create_chat(ChatType.group, payload, session, max_members=200)


@app.post("/chats/supergroups", response_model=ChatOut)
async def create_supergroup(payload: ChatCreate, session: AsyncSession = Depends(get_session)) -> Chat:
    return await _create_chat(ChatType.supergroup, payload, session)


@app.post("/chats/channels", response_model=ChatOut)
async def create_channel(payload: ChatCreate, session: AsyncSession = Depends(get_session)) -> Chat:
    return await _create_chat(ChatType.channel, payload, session)


@app.post("/groups/{group_id}/forum/enable", response_model=ChatOut)
async def enable_forum(group_id: str, session: AsyncSession = Depends(get_session)) -> Chat:
    group = await session.get(Chat, group_id)
    if not group or group.chat_type != ChatType.supergroup:
        raise HTTPException(404, "supergroup not found")
    group.is_forum = True
    await session.commit()
    await session.refresh(group)
    return group


@app.post("/groups/{group_id}/topics", response_model=TopicOut)
async def create_topic(group_id: str, payload: TopicCreate, session: AsyncSession = Depends(get_session)) -> ForumTopic:
    group = await session.get(Chat, group_id)
    if not group or group.chat_type != ChatType.supergroup or not group.is_forum:
        raise HTTPException(400, "topics are available only for forum supergroups")

    topic = ForumTopic(group_id=group_id, title=payload.title, icon_emoji=payload.icon_emoji, created_by=payload.creator_user_id)
    session.add(topic)
    await session.commit()
    await session.refresh(topic)
    return topic


@app.patch("/topics/{topic_id}/archive", response_model=TopicOut)
async def archive_topic(topic_id: str, payload: TopicArchive, session: AsyncSession = Depends(get_session)) -> ForumTopic:
    topic = await session.get(ForumTopic, topic_id)
    if not topic or topic.is_deleted:
        raise HTTPException(404, "topic not found")
    topic.is_archived = payload.is_archived
    await session.commit()
    await session.refresh(topic)
    return topic


@app.delete("/topics/{topic_id}")
async def delete_topic(topic_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    topic = await session.get(ForumTopic, topic_id)
    if not topic:
        raise HTTPException(404, "topic not found")
    topic.is_deleted = True
    await session.commit()
    return {"ok": True}


@app.post("/messages", response_model=MessageOut)
async def send_message(payload: MessageCreate, session: AsyncSession = Depends(get_session)) -> Message:
    chat = await session.get(Chat, payload.chat_id)
    if not chat:
        raise HTTPException(404, "chat not found")

    if chat.is_forum:
        if not payload.topic_id:
            raise HTTPException(400, "topic_id is required for forum messages")
        topic = await session.get(ForumTopic, payload.topic_id)
        if not topic or topic.group_id != payload.chat_id or topic.is_archived or topic.is_deleted:
            raise HTTPException(400, "invalid topic")

    max_seq_stmt: Select[tuple[int | None]] = select(func.max(Message.server_seq)).where(
        and_(Message.chat_id == payload.chat_id, Message.topic_id == payload.topic_id)
    )
    next_seq = (await session.execute(max_seq_stmt)).scalar_one_or_none() or 0

    msg = Message(
        chat_id=payload.chat_id,
        sender_user_id=payload.sender_user_id,
        sender_device_id=payload.sender_device_id,
        client_msg_id=payload.client_msg_id,
        topic_id=payload.topic_id,
        ciphertext=base64.b64decode(payload.ciphertext),
        nonce=base64.b64decode(payload.nonce),
        aad=base64.b64decode(payload.aad) if payload.aad else None,
        message_type=payload.message_type,
        server_seq=next_seq + 1,
    )
    session.add(msg)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "duplicate client message id")
    await session.refresh(msg)

    if payload.topic_id:
        topic = await session.get(ForumTopic, payload.topic_id)
        if topic:
            topic.last_message_id = msg.id
            await session.commit()

    return msg


@app.get("/sync")
async def sync_messages(
    user_id: str,
    device_id: str,
    chat_id: str,
    from_server_seq: int = 0,
    topic_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = (
        select(Message)
        .where(Message.chat_id == chat_id, Message.server_seq > from_server_seq, Message.topic_id == topic_id)
        .order_by(Message.server_seq.asc())
        .limit(200)
    )
    rows = (await session.execute(stmt)).scalars().all()

    cursor_stmt = select(SyncCursor).where(
        SyncCursor.user_id == user_id,
        SyncCursor.device_id == device_id,
        SyncCursor.chat_id == chat_id,
        SyncCursor.topic_id == topic_id,
    )
    cursor = (await session.execute(cursor_stmt)).scalar_one_or_none()
    latest_seq = rows[-1].server_seq if rows else from_server_seq
    if not cursor:
        cursor = SyncCursor(
            user_id=user_id,
            device_id=device_id,
            chat_id=chat_id,
            topic_id=topic_id,
            last_server_seq=latest_seq,
        )
        session.add(cursor)
    else:
        cursor.last_server_seq = max(cursor.last_server_seq, latest_seq)
    await session.commit()

    return {
        "messages": [
            {
                "id": m.id,
                "chat_id": m.chat_id,
                "topic_id": m.topic_id,
                "server_seq": m.server_seq,
                "ciphertext": base64.b64encode(m.ciphertext).decode(),
                "nonce": base64.b64encode(m.nonce).decode(),
            }
            for m in rows
        ],
        "last_server_seq": latest_seq,
    }


@app.post("/messages/{message_id}/reactions")
async def add_reaction(message_id: str, payload: ReactionCreate, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    message = await session.get(Message, message_id)
    if not message:
        raise HTTPException(404, "message not found")
    reaction = MessageReaction(
        message_id=message_id,
        user_id=payload.user_id,
        emoji=payload.emoji,
        custom_emoji_id=payload.custom_emoji_id,
    )
    session.add(reaction)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
    return {"ok": True}


@app.post("/calls/start")
async def start_call(payload: CallStart, session: AsyncSession = Depends(get_session)) -> dict:
    call = CallSession(chat_id=payload.chat_id, initiator_user_id=payload.initiator_user_id, call_type=payload.call_type)
    session.add(call)
    await session.commit()
    await session.refresh(call)
    return {"call_id": call.id, "state": call.state}


@app.post("/calls/{call_id}/offer")
async def submit_offer(call_id: str, payload: SignalPayload, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    participant = CallParticipant(call_id=call_id, user_id=payload.user_id, device_id=payload.device_id, webrtc_offer=payload.sdp)
    session.add(participant)
    await session.execute(
        select(CallSession).where(CallSession.id == call_id)
    )
    call = await session.get(CallSession, call_id)
    if call:
        call.state = CallState.ringing
    await session.commit()
    return {"ok": True}


@app.post("/calls/{call_id}/answer")
async def submit_answer(call_id: str, payload: SignalPayload, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    stmt = select(CallParticipant).where(CallParticipant.call_id == call_id, CallParticipant.device_id == payload.device_id)
    participant = (await session.execute(stmt)).scalar_one_or_none()
    if not participant:
        participant = CallParticipant(call_id=call_id, user_id=payload.user_id, device_id=payload.device_id)
        session.add(participant)
    participant.webrtc_answer = payload.sdp
    participant.join_state = JoinState.joined
    call = await session.get(CallSession, call_id)
    if call:
        call.state = CallState.active
    await session.commit()
    return {"ok": True}


@app.post("/calls/{call_id}/ice")
async def submit_ice(call_id: str, payload: SignalPayload, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    stmt = select(CallParticipant).where(CallParticipant.call_id == call_id, CallParticipant.device_id == payload.device_id)
    participant = (await session.execute(stmt)).scalar_one_or_none()
    if not participant:
        raise HTTPException(404, "participant not found")
    participant.ice_candidates = [*participant.ice_candidates, payload.ice_candidate]
    await session.commit()
    return {"ok": True}


@app.post("/calls/{call_id}/end")
async def end_call(call_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    call = await session.get(CallSession, call_id)
    if not call:
        raise HTTPException(404, "call not found")
    call.state = CallState.ended
    await session.commit()
    return {"ok": True}
