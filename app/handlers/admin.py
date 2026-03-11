import json
import logging
import re
import uuid
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup

from app.config import config
from app.core.models import IncomingPost
from app.core.services import NewsService
from app.utils.text_tools import content_hash

logger = logging.getLogger(__name__)
router = Router(name="admin")


class WriteNewsState(StatesGroup):
    waiting_text = State()


class ScheduleState(StatesGroup):
    waiting_payload = State()


class MapState(StatesGroup):
    waiting_media = State()


class RegistrationState(StatesGroup):
    waiting_form = State()


class AdminState(StatesGroup):
    waiting_registration_reject_reason = State()


def _extract_media(message: Message) -> tuple[str | None, str | None]:
    if message.photo:
        return message.photo[-1].file_id, "photo"
    if message.video:
        return message.video.file_id, "video"
    if message.animation:
        return message.animation.file_id, "animation"
    if message.document:
        return message.document.file_id, "document"
    return None, None


def _extract_hashtags(text: str) -> set[str]:
    return {f"#{m.upper()}" for m in re.findall(r"#([A-Za-zА-Яа-я0-9_]+)", text)}


def _detect_claimed_country(text: str) -> str:
    tags = _extract_hashtags(text)
    for country, country_tags in config.country_hashtags.items():
        upper_tags = {tag.upper() for tag in country_tags}
        if tags & upper_tags:
            return country
    return "MANUAL"




def _normalize_hashtags_to_english(text: str) -> str:
    out = text
    for country, tags in config.country_hashtags.items():
        if not tags:
            continue
        eng = tags[0]
        out = re.sub(rf"(?i)#{re.escape(country)}\b", eng, out)
        for alias in config.country_aliases.get(country, []):
            out = re.sub(rf"(?i)#{re.escape(alias)}\b", eng, out)
    return out
def _is_author_allowed_for_country(country: str, user_id: int) -> bool:
    allowed_ids = config.manual_country_authors.get(country)
    if not allowed_ids:
        return True
    return user_id in allowed_ids or user_id == config.admin_id


REG_TYPE_LABELS = {
    "person": "Известный человек",
    "group": "Группировка",
    "country": "Страна",
}

REGISTRATION_TEMPLATES = {
    "country": """Шаблон анкеты для страны:\n\n1. Название вашей страны\n2. Количество солдат в стране (от 10 до 20)\n3. Количество граждан (от 25 до 40)\n4. Территория для регистрации\n5. Флаг вашей страны\n6. Гимн страны (необязательно)\n7. Позывной/имя руководителя страны\n8. Местоположение столицы\n9. Бюджет страны (50-100 тыс. вирт рублей)\n10. Цвет страны на карте (нельзя: серый/белый/чёрный)\n\nОтправьте заполненную анкету одним сообщением.""",
    "group": """Шаблон анкеты для группировки:\n\n1. Префикс группировки (ЧВК, ДШРГ и т.д.)\n2. Название и полное звучание\n3. Зависимая/независимая\n4. Задачи группировки\n5. Численность (20-40)\n6. Позывной командира\n7. Страна базирования (если зависима)\n8. Бюджет (20-35 тыс. вирт-рублей)\n\nОтправьте заполненную анкету одним сообщением.""",
    "person": """Шаблон анкеты для известного человека:\n\n1. Ненастоящее имя/позывной\n2. Страна деятельности\n3. С чем связана деятельность\n4. Работа\n5. Деньги (10-15 тыс. вирт рублей)\n\nОтправьте заполненную анкету одним сообщением.""",
}


def _registration_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Зарегистрироваться как известный человек", callback_data="reg:person")],
            [InlineKeyboardButton(text="Зарегистрироваться как группировка", callback_data="reg:group")],
            [InlineKeyboardButton(text="Зарегистрироваться как страна", callback_data="reg:country")],
        ]
    )


def _registration_review_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Принять анкету", callback_data=f"regmod:approve:{token}"),
                InlineKeyboardButton(text="Отклонить анкету", callback_data=f"regmod:reject:{token}"),
            ]
        ]
    )


def _admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Статус", callback_data="admin:status")],
            [InlineKeyboardButton(text="Пауза", callback_data="admin:pause"), InlineKeyboardButton(text="Резюме", callback_data="admin:resume")],
            [InlineKeyboardButton(text="Написать новость", callback_data="admin:write_news")],
            [InlineKeyboardButton(text="Анкеты", callback_data="admin:anketa")],
            [InlineKeyboardButton(text="Emoji reload", callback_data="admin:emoji_reload")],
        ]
    )


def _extract_country_name_from_form(form_text: str) -> str:
    for line in form_text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        m = re.match(r"^(?:1[\).:-]?|1\s+)(.+)$", raw)
        if m:
            return m.group(1).strip()
    first = next((l.strip() for l in form_text.splitlines() if l.strip()), "")
    return first[:80] if first else "Неизвестная страна"


def bind_admin_handlers(service: NewsService) -> Router:
    @router.message(Command("start"))
    async def start_cmd(message: Message) -> None:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="/write_news")],
                [KeyboardButton(text="📝 Анкета / создать страну")],
            ],
            resize_keyboard=True,
        )
        text = (
            "Бот активен.\n"
            "Команды: /status /pause /resume /write_news /schedule_news /submit_map /rss_add /rss_list /emoji_reload /emoji_list /anketa\n\n"
            "Для /write_news обязательно укажите хештег страны (например #OBS)."
        )
        if message.from_user and message.from_user.id == config.admin_id:
            await message.answer(text, reply_markup=keyboard)
            await message.answer("Админ-панель:", reply_markup=_admin_panel_keyboard())
        else:
            await message.answer(text, reply_markup=keyboard)

    @router.message(Command("admin"))
    async def admin_panel_cmd(message: Message) -> None:
        if not message.from_user or message.from_user.id != config.admin_id:
            await message.answer("Эта панель доступна только администратору.")
            return
        await message.answer("Админ-панель:", reply_markup=_admin_panel_keyboard())

    @router.callback_query(F.data.startswith("admin:"))
    async def admin_panel_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.from_user.id != config.admin_id:
            await callback.answer("Недостаточно прав", show_alert=True)
            return
        await callback.answer()
        action = callback.data.split(":", maxsplit=1)[1]
        if action == "status":
            paused = await service.is_paused()
            await callback.message.answer(f"Статус: {'PAUSED' if paused else 'RUNNING'}\nОчередь: {service.queue.qsize()}")
        elif action == "pause":
            await service.set_paused(True)
            await callback.message.answer("Пауза включена")
        elif action == "resume":
            await service.set_paused(False)
            await callback.message.answer("Пауза отключена")
        elif action == "write_news":
            await state.set_state(WriteNewsState.waiting_text)
            await callback.message.answer("Отправьте текст/медиа новости с хештегом страны.")
        elif action == "anketa":
            await callback.message.answer("Выберите тип регистрации:", reply_markup=_registration_menu_keyboard())
        elif action == "emoji_reload":
            count = await service.refresh_emoji_packs()
            await callback.message.answer(f"Emoji packs reloaded: {count}")

    @router.message(Command("anketa"))
    @router.message(F.text == "📝 Анкета / создать страну")
    @router.message(F.text == "Создать страну")
    async def anketa_menu(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Выберите тип регистрации:", reply_markup=_registration_menu_keyboard())

    @router.callback_query(F.data.startswith("reg:"))
    async def registration_type_callback(callback: CallbackQuery, state: FSMContext) -> None:
        _, reg_type = callback.data.split(":", maxsplit=1)
        if reg_type not in REGISTRATION_TEMPLATES:
            await callback.answer("Неизвестный тип", show_alert=True)
            return
        await state.set_state(RegistrationState.waiting_form)
        await state.update_data(reg_type=reg_type)
        await callback.message.answer(REGISTRATION_TEMPLATES[reg_type])
        await callback.answer()

    @router.message(RegistrationState.waiting_form)
    async def registration_form_flow(message: Message, state: FSMContext) -> None:
        raw_form = (message.text or message.caption or "").strip()
        if not raw_form:
            await message.answer("Отправьте анкету текстом одним сообщением.")
            return

        data = await state.get_data()
        reg_type = str(data.get("reg_type", "person"))
        label = REG_TYPE_LABELS.get(reg_type, reg_type)
        user = message.from_user
        user_id = user.id if user else 0
        username = f"@{user.username}" if user and user.username else "без username"
        token = uuid.uuid4().hex

        await service.db.store_registration_application(token, user_id, reg_type, raw_form)

        admin_text = (
            "Новая заявка на регистрацию\n"
            f"Тип: {label}\n"
            f"User ID: {user_id}\n"
            f"Username: {username}\n"
            f"Token: {token}\n\n"
            f"Анкета:\n{raw_form[:3500]}"
        )
        await message.bot.send_message(config.admin_id, admin_text, reply_markup=_registration_review_keyboard(token))

        if reg_type == "country" and user_id:
            country_name = _extract_country_name_from_form(raw_form)
            await service.db.add_country_leader(country_name, user_id, source="registration")

        await state.clear()
        await message.answer("Анкета отправлена админу в ЛС (@supermegaluti).")

    @router.callback_query(F.data.startswith("regmod:"))
    async def registration_admin_callback(callback: CallbackQuery, state: FSMContext) -> None:
        if callback.from_user.id != config.admin_id:
            await callback.answer("Недостаточно прав", show_alert=True)
            return
        _, action, token = callback.data.split(":", maxsplit=2)
        row = await service.db.get_registration_application(token)
        if not row:
            await callback.answer("Анкета не найдена", show_alert=True)
            return
        user_id, reg_type, form_text, status = row
        if status != "pending":
            await callback.answer("Анкета уже обработана", show_alert=True)
            return

        if action == "approve":
            await service.db.set_registration_application_status(token, "approved")
            await callback.message.answer("Анкета принята")
            await callback.message.bot.send_message(user_id, f"Ваша анкета ({REG_TYPE_LABELS.get(reg_type, reg_type)}) принята администратором.")
        else:
            await state.set_state(AdminState.waiting_registration_reject_reason)
            await state.update_data(reg_token=token, reg_user_id=user_id, reg_type=reg_type)
            await callback.message.answer("Напишите причину отказа этой анкеты одним сообщением.")
        await callback.answer()

    @router.message(AdminState.waiting_registration_reject_reason)
    async def registration_reject_reason(message: Message, state: FSMContext) -> None:
        if not message.from_user or message.from_user.id != config.admin_id:
            return
        reason = (message.text or "").strip()
        if not reason:
            await message.answer("Причина отказа не может быть пустой.")
            return
        data = await state.get_data()
        token = str(data.get("reg_token", ""))
        user_id = int(data.get("reg_user_id", 0))
        reg_type = str(data.get("reg_type", "анкета"))
        await service.db.set_registration_application_status(token, "rejected")
        await message.bot.send_message(
            user_id,
            f"Ваша анкета ({REG_TYPE_LABELS.get(reg_type, reg_type)}) отклонена.\nПричина: {reason}",
        )
        await message.answer("Отказ отправлен пользователю.")
        await state.clear()

    @router.message(Command("status"))
    async def status_cmd(message: Message) -> None:
        paused = await service.is_paused()
        await message.answer(f"Статус: {'PAUSED' if paused else 'RUNNING'}\nОчередь: {service.queue.qsize()}\nTarget: {config.target_channel}")

    @router.message(Command("pause"))
    async def pause_cmd(message: Message) -> None:
        if message.from_user and message.from_user.id != config.admin_id:
            await message.answer("Недостаточно прав")
            return
        await service.set_paused(True)
        await message.answer("Пауза включена")

    @router.message(Command("resume"))
    async def resume_cmd(message: Message) -> None:
        if message.from_user and message.from_user.id != config.admin_id:
            await message.answer("Недостаточно прав")
            return
        await service.set_paused(False)
        await message.answer("Пауза отключена")

    @router.message(Command("write_news"))
    async def write_news_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(WriteNewsState.waiting_text)
        await message.answer("Отправьте текст/медиа новости. Нужен хештег страны (#OBS / #OB / #VL и т.д.)")

    @router.message(WriteNewsState.waiting_text)
    async def write_news_flow(message: Message, state: FSMContext) -> None:
        text = _normalize_hashtags_to_english((message.caption or message.text or "").strip())
        if not text and not (message.photo or message.video or message.animation):
            await message.answer("Пустой текст")
            return
        if "#" not in text:
            await message.answer("Нужен хештег страны (пример: #OBS).")
            return

        claimed_country = _detect_claimed_country(text)
        if claimed_country == "MANUAL":
            await message.answer("Не найден валидный хештег страны.")
            return

        user_id = message.from_user.id if message.from_user else 0
        if not _is_author_allowed_for_country(claimed_country, user_id):
            await message.answer("Вы не можете публиковать новости от лица этой страны.")
            return

        file_id, media_type = _extract_media(message)
        post = IncomingPost(
            source_country=claimed_country,
            source_channel="manual_admin",
            message_id=message.message_id,
            text=text,
            has_media=bool(file_id),
            media_file_id=file_id,
            media_type=media_type,
            submitted_by_user_id=user_id,
        )
        await service.enqueue(post)
        await state.clear()
        await message.answer("Принято в очередь")

    @router.message(Command("schedule_news"))
    async def schedule_news_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(ScheduleState.waiting_payload)
        await message.answer("Формат: YYYY-mm-dd HH:MM | COUNTRY | TEXT")

    @router.message(ScheduleState.waiting_payload)
    async def schedule_news_flow(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        try:
            at_str, country, text = [x.strip() for x in raw.split("|", maxsplit=2)]
            ts = int(datetime.strptime(at_str, "%Y-%m-%d %H:%M").timestamp())
            post_id = await service.db.add_scheduled_post(ts, country, text, message.from_user.id if message.from_user else 0)
            await message.answer(f"Запланировано: id={post_id}")
            await state.clear()
        except Exception:
            await message.answer("Неверный формат. Пример: 2026-02-21 19:30 | Вилония | Текст")

    @router.message(Command("emoji_reload"))
    async def emoji_reload_cmd(message: Message) -> None:
        if message.from_user and message.from_user.id != config.admin_id:
            await message.answer("Недостаточно прав")
            return
        count = await service.refresh_emoji_packs()
        await message.answer(f"Emoji packs reloaded: {count}")

    @router.message(Command("emoji_list"))
    async def emoji_list_cmd(message: Message) -> None:
        if not service.pack_emoji_cache:
            await message.answer("Emoji cache пуст. Используйте /emoji_reload")
            return
        sample = list(service.pack_emoji_cache.items())[:50]
        await message.answer("\n".join([f"{k} -> {v}" for k, v in sample]))

    @router.message(Command("rss_add"))
    async def rss_add_cmd(message: Message) -> None:
        if not message.text:
            return
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Использование: /rss_add KEY https://feed.url")
            return
        key, url = parts[1], parts[2]
        config.rss_feeds[key] = url
        await message.answer(f"RSS добавлен: {key}")

    @router.message(Command("rss_list"))
    async def rss_list_cmd(message: Message) -> None:
        if not config.rss_feeds:
            await message.answer("RSS пуст")
            return
        await message.answer("\n".join([f"{k}: {u}" for k, u in config.rss_feeds.items()]))

    @router.message(Command("submit_map"))
    async def submit_map_cmd(message: Message, state: FSMContext) -> None:
        await state.set_state(MapState.waiting_media)
        await message.answer("Отправьте фото/файл карты и подпись комментария.")

    @router.message(MapState.waiting_media)
    async def submit_map_flow(message: Message, state: FSMContext) -> None:
        file_id, media_type = _extract_media(message)
        comment = (message.caption or message.text or "Военная сводка").strip()
        await service.publish_map_digest(file_id, media_type or "none", comment)
        await message.answer("Карта и сводка опубликованы")
        await state.clear()

    @router.callback_query(F.data.startswith("mod:"))
    async def moderation_callback(callback: CallbackQuery) -> None:
        if callback.from_user.id != config.admin_id:
            await callback.answer("Недостаточно прав", show_alert=True)
            return
        await callback.answer()

        _, action, token = callback.data.split(":", maxsplit=2)
        payload_raw = await service.db.pop_moderation_payload(token)
        if not payload_raw:
            await callback.answer("Запись не найдена", show_alert=True)
            return

        payload = json.loads(payload_raw)
        hash_value = payload.get("hash_value") or content_hash(f"{payload['source_channel']}:{payload['message_id']}:{payload['formatted_text']}")
        post = IncomingPost(
            source_country=payload["source_country"],
            source_channel=payload["source_channel"],
            message_id=payload["message_id"],
            text=payload.get("raw_text") or payload["formatted_text"],
            has_media=payload.get("has_media", False),
            media_file_id=payload.get("media_file_id"),
            media_type=payload.get("media_type"),
            submitted_by_user_id=payload.get("submitted_by_user_id"),
        )

        if action in {"approve", "war_ok"}:
            if post.has_media:
                await service.publish_media_and_mark(post, payload["formatted_text"], hash_value)
            else:
                formatted, entities = service._render_post(post, post.text)
                await service.publish_and_mark(post, formatted, entities, hash_value)
            await callback.message.answer("Одобрено и опубликовано" if action == "approve" else "Классифицировано как операция без ВД: опубликовано")
        else:
            await service.db.mark_processed(post.source_channel, post.message_id, hash_value)
            await callback.message.answer("Отклонено" if action != "war_block" else "Классифицировано как военные действия: отклонено")


    @router.message(F.from_user.as_("u"), F.text.startswith("/"))
    async def antiflood_command_guard(message: Message, u) -> None:  # type: ignore[no-redef]
        if not u:
            return
        ok, reason = await service.check_antiflood(u.id)
        if not ok:
            await message.answer(reason)

    @router.message(F.from_user.as_("u"), F.text, ~F.text.startswith("/"))
    async def antiflood_guard(message: Message, u) -> None:  # type: ignore[no-redef]
        if not u:
            return
        ok, reason = await service.check_antiflood(u.id)
        if not ok:
            await message.answer(reason)

    return router
