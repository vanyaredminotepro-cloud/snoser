# ddlk-banda: архитектура БД и структура ядра (FastAPI + SQLAlchemy)

## 1) Цели и принцип приватности (Zero-Knowledge)

- Сервер **не хранит открытый текст сообщений** и не имеет ключей расшифровки.
- Для личных чатов: E2EE (Signal/Double Ratchet-подход).
- Для супергрупп/каналов: групповой ключ `group_epoch_key`, который:
  - ротируется при изменении состава участников,
  - распространяется как индивидуальные зашифрованные envelope-сообщения для каждого участника,
  - передается через подписанное сервером приглашение (сервер подтверждает метаданные, но не знает ключ).
- Сервер хранит только:
  - зашифрованные payload,
  - публичные ключи, prekeys, подписи,
  - метаданные доставки/синхронизации.

---

## 2) Предлагаемые пакеты Python (нейминг ddlk-banda)

```text
ddlk_banda/
  api/
    routers/
      auth.py
      chats.py
      messages.py
      topics.py
      calls.py
  db/
    base.py
    models/
      user.py
      device.py
      chat.py
      membership.py
      message.py
      reaction.py
      forum_topic.py
      key_material.py
      call_session.py
      sync_state.py
  schemas/
    chat.py
    message.py
    topic.py
    call.py
  services/
    chat_service.py
    message_service.py
    e2ee_service.py
    group_key_service.py
    sync_service.py
    call_service.py
  security/
    identity.py
    ratchet_session.py
    key_envelope.py
```

---

## 3) Типы чатов

`chat_type` (enum):
- `direct` — личный чат 1:1
- `group` — группа до 200
- `supergroup` — масштабируемая группа
- `channel` — one-to-many

Дополнительные флаги:
- `is_forum` (только для supergroup)
- `linked_discussion_chat_id` (channel -> supergroup для комментариев)

---

## 4) Схема БД (SQLAlchemy-first)

## 4.1 users
- `id` (UUID, PK)
- `username` (varchar, unique)
- `display_name` (varchar)
- `created_at` (timestamp)
- `status` (enum: active/blocked/deleted)

## 4.2 devices
- `id` (UUID, PK)
- `user_id` (FK -> users.id)
- `device_label` (varchar)
- `identity_key_public` (bytes/base64)
- `signed_prekey_public` (bytes/base64)
- `signed_prekey_signature` (bytes/base64)
- `pq_kyber_public` (bytes/base64, nullable)
- `last_seen_at` (timestamp)
- `created_at` (timestamp)

## 4.3 chats
- `id` (UUID, PK)
- `chat_type` (enum)
- `title` (varchar, nullable)
- `owner_id` (FK -> users.id, nullable)
- `is_forum` (bool, default false)
- `linked_discussion_chat_id` (FK -> chats.id, nullable)
- `max_members` (int, nullable; для group = 200)
- `created_at` (timestamp)

## 4.4 chat_memberships
- `id` (UUID, PK)
- `chat_id` (FK -> chats.id)
- `user_id` (FK -> users.id)
- `role` (enum: owner/admin/member/subscriber)
- `permissions` (jsonb)
- `joined_at` (timestamp)
- `left_at` (timestamp, nullable)
- `mute_until` (timestamp, nullable)

## 4.5 messages
- `id` (UUID, PK)
- `chat_id` (FK -> chats.id)
- `sender_user_id` (FK -> users.id)
- `sender_device_id` (FK -> devices.id)
- `topic_id` (FK -> forum_topics.id, nullable)
- `client_msg_id` (varchar, unique per sender_device_id)
- `ciphertext` (bytea/text)
- `ciphertext_version` (smallint)
- `nonce` (bytea)
- `aad` (bytea, nullable)
- `message_type` (enum: text/media/system/service)
- `reply_to_message_id` (FK -> messages.id, nullable)
- `server_seq` (bigint) — монотонный seq внутри chat/topic
- `created_at` (timestamp)
- `edited_at` (timestamp, nullable)
- `deleted_at` (timestamp, nullable)

Индексы:
- `(chat_id, topic_id, server_seq)`
- `(chat_id, created_at)`
- `(sender_device_id, client_msg_id)` unique

## 4.6 message_reactions
- `id` (UUID, PK)
- `message_id` (FK -> messages.id)
- `user_id` (FK -> users.id)
- `emoji` (varchar)
- `custom_emoji_id` (FK -> custom_emojis.id, nullable)
- `created_at` (timestamp)

Unique: `(message_id, user_id, emoji, custom_emoji_id)`

## 4.7 custom_emojis
- `id` (UUID, PK)
- `owner_user_id` (FK -> users.id, nullable)
- `pack_name` (varchar)
- `file_ref` (varchar / object storage key)
- `created_at` (timestamp)

## 4.8 forum_topics
- `id` (UUID, PK)
- `group_id` (FK -> chats.id)
- `title` (varchar)
- `icon_emoji` (varchar, nullable)
- `last_message_id` (FK -> messages.id, nullable)
- `is_archived` (bool, default false)
- `is_deleted` (bool, default false)
- `created_by` (FK -> users.id)
- `created_at` (timestamp)
- `updated_at` (timestamp)

## 4.9 group_key_epochs
- `id` (UUID, PK)
- `chat_id` (FK -> chats.id)
- `epoch_no` (int)
- `key_fingerprint` (varchar)
- `rotated_at` (timestamp)
- `rotated_by` (FK -> users.id)

## 4.10 group_key_envelopes
- `id` (UUID, PK)
- `epoch_id` (FK -> group_key_epochs.id)
- `recipient_user_id` (FK -> users.id)
- `recipient_device_id` (FK -> devices.id, nullable)
- `encrypted_group_key` (bytea/text)
- `delivery_state` (enum: pending/delivered/acked)
- `created_at` (timestamp)

## 4.11 server_signed_invites
- `id` (UUID, PK)
- `chat_id` (FK -> chats.id)
- `inviter_user_id` (FK -> users.id)
- `invitee_hint` (varchar/uuid)
- `invite_payload` (jsonb)
- `server_signature` (bytea)
- `expires_at` (timestamp)
- `used_at` (timestamp, nullable)

## 4.12 call_sessions
- `id` (UUID, PK)
- `chat_id` (FK -> chats.id)
- `initiator_user_id` (FK -> users.id)
- `call_type` (enum: voice/video)
- `state` (enum: created/ringing/active/ended)
- `sfu_mode` (bool, default false)
- `started_at` (timestamp)
- `ended_at` (timestamp, nullable)

## 4.13 call_participants
- `id` (UUID, PK)
- `call_id` (FK -> call_sessions.id)
- `user_id` (FK -> users.id)
- `device_id` (FK -> devices.id)
- `webrtc_offer` (text, nullable)
- `webrtc_answer` (text, nullable)
- `ice_candidates` (jsonb)
- `join_state` (enum: invited/joined/left)
- `joined_at` (timestamp, nullable)
- `left_at` (timestamp, nullable)

## 4.14 sync_cursors
- `id` (UUID, PK)
- `user_id` (FK -> users.id)
- `device_id` (FK -> devices.id)
- `chat_id` (FK -> chats.id)
- `topic_id` (FK -> forum_topics.id, nullable)
- `last_server_seq` (bigint)
- `last_acked_client_seq` (bigint)
- `updated_at` (timestamp)

---

## 5) Базовые SQLAlchemy модели (каркас)

```python
# ddlk_banda/db/models/chat.py
class Chat(Base):
    __tablename__ = "chats"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    chat_type = mapped_column(Enum(ChatType), nullable=False)
    title = mapped_column(String(255))
    owner_id = mapped_column(ForeignKey("users.id"))
    is_forum = mapped_column(Boolean, default=False, nullable=False)
    linked_discussion_chat_id = mapped_column(ForeignKey("chats.id"), nullable=True)
    max_members = mapped_column(Integer, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
```

```python
# ddlk_banda/db/models/message.py
class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_msg_chat_topic_seq", "chat_id", "topic_id", "server_seq"),
        UniqueConstraint("sender_device_id", "client_msg_id", name="uq_device_client_msg"),
    )

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    chat_id = mapped_column(ForeignKey("chats.id"), nullable=False)
    sender_user_id = mapped_column(ForeignKey("users.id"), nullable=False)
    sender_device_id = mapped_column(ForeignKey("devices.id"), nullable=False)
    topic_id = mapped_column(ForeignKey("forum_topics.id"), nullable=True)
    client_msg_id = mapped_column(String(64), nullable=False)
    ciphertext = mapped_column(LargeBinary, nullable=False)
    nonce = mapped_column(LargeBinary, nullable=False)
    aad = mapped_column(LargeBinary, nullable=True)
    server_seq = mapped_column(BigInteger, nullable=False)
```

---

## 6) Логика синхронизации ("идеальная связь")

Ключевая идея:
- Клиент отправляет сообщение сразу в UI со статусом `pending`.
- Сообщение уходит с `client_msg_id` + `client_seq`.
- Сервер присваивает `server_seq` и возвращает ack.
- При reconnection клиент запрашивает diff: `GET /sync?chat_id=...&from_server_seq=N`.

State-machine сообщения:
- `pending_local`
- `sent_to_server`
- `server_acked`
- `delivered_to_peer` (по device receipt)
- `read` (опционально, если политика чата разрешает)

Антидублирование:
- idempotency через unique `(sender_device_id, client_msg_id)`.

Оффлайн очередь:
- в локальном хранилище клиента сообщения сортируются по `client_seq`.
- при восстановлении связи отправка батчами, сервер упорядочивает по времени приема и выдает `server_seq`.

---

## 7) Звонки (WebRTC, сервер как координатор)

- Сервер хранит только signaling:
  - SDP offer/answer,
  - ICE candidates,
  - состояние сессии.
- Медиапоток идет P2P/SFU с DTLS-SRTP.
- TURN/STUN предоставляются сервером инфраструктуры, но контент медиапотока не расшифровывается backend-API.

Минимальные API:
- `POST /calls/start`
- `POST /calls/{id}/offer`
- `POST /calls/{id}/answer`
- `POST /calls/{id}/ice`
- `POST /calls/{id}/end`

---

## 8) Форумы и темы (Telegram 2.0 стиль)

- `is_forum = true` у supergroup.
- Сообщение в тему = обычное E2EE сообщение + обязательный `topic_id`.
- Выборка ленты:
  - общая лента форума по темам (агрегировано),
  - внутренняя лента темы фильтруется строго по `(chat_id, topic_id)`.
- Сообщения разных тем не смешиваются за счет индекса `(chat_id, topic_id, server_seq)`.

Пример тела API для сообщения в тему:

```json
{
  "chat_id": "<uuid>",
  "topic_id": "<uuid>",
  "client_msg_id": "dev42-000123",
  "ciphertext": "base64...",
  "nonce": "base64...",
  "message_type": "text"
}
```

---

## 9) Что отправить на Этап 2

После утверждения этой схемы можно переходить к реализации `ddlk_banda/security/`:
- X25519 identity + signed prekeys,
- optional Kyber KEM,
- Double Ratchet session state,
- reset/re-init сессии,
- групповые key envelopes для каждой эпохи.

## 10) Что отправить на Этап 3

- SQLAlchemy + Pydantic для `forum_topics` (create/delete/archive),
- `POST /groups/{group_id}/topics`,
- валидация `topic_id` при отправке сообщений в forum supergroup.
