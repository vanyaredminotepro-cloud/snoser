import json
import logging
import re
import uuid

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import config
from app.core.models import IncomingPost
from app.core.services import NewsService
from app.utils.text_tools import content_hash

logger = logging.getLogger(__name__)
router = Router(name="admin")


class WriteNewsState(StatesGroup):
    waiting_text = State()


class RegistrationState(StatesGroup):
    waiting_form = State()


class AdminState(StatesGroup):
    waiting_registration_reject_reason = State()
    waiting_moderation_fix = State()
    waiting_appeal = State()
    waiting_tag_update = State()
    waiting_source_update = State()


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




def _extract_final_hashtag(text: str) -> str | None:
    m = re.search(r"#([A-Za-zА-Яа-я0-9_]+)\s*$", text.strip())
    return f"#{m.group(1)}" if m else None


def _normalize_single_hashtag(tag: str) -> str:
    upper = tag.upper()
    alias_map = {"#ТНР": "#TNR", "#КК8": "#KK8", "#LEKSY": "#LKS"}
    return alias_map.get(upper, upper)


def _country_by_hashtag(tag: str) -> str | None:
    normalized = _normalize_single_hashtag(tag)
    for country, tags in config.country_hashtags.items():
        if normalized in {t.upper() for t in tags}:
            return country
    return None


def _is_news_submission(text: str, state_name: str | None) -> bool:
    if state_name == WriteNewsState.waiting_text.state:
        return True
    return "#" in text

def _is_author_allowed_for_country(country: str, user_id: int) -> bool:
    allowed_ids = config.manual_country_authors.get(country)
    if not allowed_ids:
        return True
    return user_id in allowed_ids or user_id == config.admin_id


def _user_allowed_countries(user_id: int) -> list[str]:
    if user_id == config.admin_id:
        return []
    return [country for country, ids in config.manual_country_authors.items() if user_id in ids]


def _apply_admin_fix(raw_text: str, instructions: str) -> str:
    fixed = raw_text
    repl_found = False
    for chunk in instructions.split(";"):
        if "->" not in chunk:
            continue
        old, new = [x.strip() for x in chunk.split("->", maxsplit=1)]
        if old:
            fixed = fixed.replace(old, new)
            repl_found = True

    for old, new in re.findall(r"(?i)замени\s+['\"]?(.+?)['\"]?\s+на\s+['\"]?(.+?)['\"]?(?:$|;)", instructions):
        old = old.strip()
        new = new.strip()
        if old:
            fixed = fixed.replace(old, new)
            repl_found = True

    if not repl_found:
        return instructions.strip() or raw_text
    return fixed


REG_TYPE_LABELS = {
    "person": "Известный человек",
    "group": "Группировка",
    "country": "Страна",
    "movement": "Движение",
    "party": "Партия",
}

REGISTRATION_TEMPLATES = {
    "country": """Шаблон анкеты для страны:\n\n1. Название вашей страны\n2. Количество солдат в стране (от 10 до 20)\n3. Количество граждан (от 25 до 40)\n4. Территория для регистрации\n5. Флаг вашей страны\n6. Гимн страны (необязательно)\n7. Позывной/имя руководителя страны\n8. Местоположение столицы\n9. Бюджет страны (50-100 тыс. вирт рублей)\n10. Цвет страны на карте (нельзя: серый/белый/чёрный)\n\nОтправьте заполненную анкету одним сообщением.""",
    "group": """Шаблон анкеты для группировки:\n\n1. Префикс группировки (ЧВК, ДШРГ и т.д.)\n2. Название и полное звучание\n3. Зависимая/независимая\n4. Задачи группировки\n5. Численность (20-40)\n6. Позывной командира\n7. Страна базирования (если зависима)\n8. Бюджет (20-35 тыс. вирт-рублей)\n\nОтправьте заполненную анкету одним сообщением.""",
    "person": """Шаблон анкеты для известного человека:\n\n1. Ненастоящее имя/позывной\n2. Страна деятельности\n3. С чем связана деятельность\n4. Работа\n5. Деньги (10-15 тыс. вирт рублей)\n\nОтправьте заполненную анкету одним сообщением.""",
    "movement": """Шаблон анкеты для движения:\n\n1. Название движения\n2. Идеология/цель\n3. Лидер\n4. Страна деятельности\n5. Краткий план действий\n\nОтправьте заполненную анкету одним сообщением.""",
    "party": """Шаблон анкеты для партии:\n\n1. Название партии\n2. Лидер партии\n3. Политическая программа\n4. Страна деятельности\n5. Цели на ближайший период\n\nОтправьте заполненную анкету одним сообщением.""",
}


def _registration_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Зарегистрироваться как известный человек", callback_data="reg:person")],
            [InlineKeyboardButton(text="Зарегистрироваться как группировка", callback_data="reg:group")],
            [InlineKeyboardButton(text="Зарегистрироваться как страна", callback_data="reg:country")],
            [InlineKeyboardButton(text="Создать движение", callback_data="reg:movement")],
            [InlineKeyboardButton(text="Создать партию", callback_data="reg:party")],
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
            [InlineKeyboardButton(text="Статистика новостей", callback_data="admin:news_stats")],
            [InlineKeyboardButton(text="Пауза", callback_data="admin:pause"), InlineKeyboardButton(text="Резюме", callback_data="admin:resume")],
            [InlineKeyboardButton(text="Написать новость", callback_data="admin:write_news")],
            [InlineKeyboardButton(text="Анкеты", callback_data="admin:anketa")],
            [InlineKeyboardButton(text="Хештеги (добавить/изменить)", callback_data="admin:tags")],
            [InlineKeyboardButton(text="Организации/источники", callback_data="admin:sources")],
            [InlineKeyboardButton(text="HTML исследование (beta)", callback_data="admin:html_probe")],
            [InlineKeyboardButton(text="Emoji reload", callback_data="admin:emoji_reload")],
        ]
    )


def _main_menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📰 Написать новость", callback_data="menu:write_news")],
        [InlineKeyboardButton(text="📝 Анкета / создать страну", callback_data="menu:anketa")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")],
        [InlineKeyboardButton(text="📊 Статистика стран (скоро)", callback_data="menu:country_stats")],
        [InlineKeyboardButton(text="🧾 Оспорить отклонение", callback_data="menu:appeal")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="menu:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    @router.message(F.text == "/start")
    async def start_cmd(message: Message) -> None:
        is_admin = bool(message.from_user and message.from_user.id == config.admin_id)
        text = (
            "Бот активен.\n"
            "Используйте inline-кнопки ниже.\n\n"
            "Для публикации новости укажите корректный хештег страны (например #OBS)."
        )
        await message.answer(text, reply_markup=_main_menu_keyboard(is_admin))

    @router.callback_query(F.data.startswith("menu:"))
    async def menu_callbacks(callback: CallbackQuery, state: FSMContext) -> None:
        action = callback.data.split(":", maxsplit=1)[1]
        is_admin = callback.from_user.id == config.admin_id
        await callback.answer()

        if action == "write_news":
            await state.set_state(WriteNewsState.waiting_text)
            await callback.message.answer("Отправьте текст/медиа новости. Нужен хештег страны (#OBS / #OB / #VL и т.д.)")
            return
        if action == "anketa":
            await state.clear()
            await callback.message.answer("Выберите тип регистрации:", reply_markup=_registration_menu_keyboard())
            return
        if action == "stats":
            day, week, month, total = await service.db.news_stats()
            await callback.message.answer(
                f"Общая статистика новостей\nЗа день: {day}\nЗа неделю: {week}\nЗа месяц: {month}\nЗа всё время: {total}"
            )
            return
        if action == "country_stats":
            rows = await service.db.list_country_stats()
            if not rows:
                await callback.message.answer("Статистика стран: скоро (пока нет данных).")
            else:
                lines = ["Статистика стран:"]
                for country, budget, army, life in rows[:20]:
                    lines.append(f"{country}: Бюджет={budget}, Армия={army}, Уровень жизни={life}")
                await callback.message.answer("\n".join(lines))
            return
        if action == "appeal":
            await state.set_state(AdminState.waiting_appeal)
            await callback.message.answer("Отправьте текст апелляции одним сообщением. Мы перешлём админу.")
            return
        if action == "admin":
            if not is_admin:
                await callback.message.answer("Эта панель доступна только администратору.")
                return
            await callback.message.answer("Админ-панель:", reply_markup=_admin_panel_keyboard())
            return

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
        elif action == "news_stats":
            day, week, month, total = await service.db.news_stats()
            await callback.message.answer(
                f"Статистика новостей\nЗа день: {day}\nЗа неделю: {week}\nЗа месяц: {month}\nЗа всё время: {total}"
            )
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
        elif action == "tags":
            await state.set_state(AdminState.waiting_tag_update)
            await callback.message.answer(
                "Отправьте: НазваниеСтраны | #TAG1,#TAG2\n"
                "Пример: Зитор | #ZT"
            )
        elif action == "sources":
            await state.set_state(AdminState.waiting_source_update)
            await callback.message.answer(
                "Отправьте: НазваниеОрганизации | ссылка/username\n"
                "Пример: ДШРГ Торнадо | https://t.me/DSHRGTornado"
            )
        elif action == "html_probe":
            await callback.message.answer(
                "<b>HTML beta</b>\n<i>Тест форматирования</i>\n<blockquote>Цитата для исследования рендера</blockquote>",
                parse_mode="HTML",
            )
        elif action == "emoji_reload":
            count = await service.refresh_emoji_packs()
            await callback.message.answer(f"Emoji packs reloaded: {count}")

    @router.message(AdminState.waiting_tag_update)
    async def tag_update_flow(message: Message, state: FSMContext) -> None:
        if not message.from_user or message.from_user.id != config.admin_id:
            return
        raw = (message.text or "").strip()
        if "|" not in raw:
            await message.answer("Неверный формат. Используйте: Страна | #TAG1,#TAG2")
            return
        country, tags_raw = [x.strip() for x in raw.split("|", maxsplit=1)]
        tags = [t.strip().upper() for t in tags_raw.split(",") if t.strip()]
        tags = [t if t.startswith("#") else f"#{t}" for t in tags]
        if not country or not tags:
            await message.answer("Пустое значение страны или тегов.")
            return
        config.country_hashtags[country] = tags
        await service.db.set_state("cfg:country_hashtags", json.dumps(config.country_hashtags, ensure_ascii=False))
        await message.answer(f"Обновлено: {country} -> {', '.join(tags)}")
        await state.clear()

    @router.message(AdminState.waiting_source_update)
    async def source_update_flow(message: Message, state: FSMContext) -> None:
        if not message.from_user or message.from_user.id != config.admin_id:
            return
        raw = (message.text or "").strip()
        if "|" not in raw:
            await message.answer("Неверный формат. Используйте: Организация | ссылка/username")
            return
        org, source_raw = [x.strip() for x in raw.split("|", maxsplit=1)]
        source = source_raw
        source = re.sub(r"^https?://t.me/", "", source, flags=re.IGNORECASE).strip()
        if source and not source.startswith("+") and not source.startswith("@"):
            source = f"@{source}"
        if not org or not source:
            await message.answer("Пустое название организации или источника.")
            return
        config.source_channels[org] = source
        await service.db.set_state("cfg:source_channels", json.dumps(config.source_channels, ensure_ascii=False))
        await message.answer(f"Источник обновлён: {org} -> {source}")
        await state.clear()

    @router.message(AdminState.waiting_appeal)
    async def appeal_flow(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if not text:
            await message.answer("Текст апелляции пуст.")
            return
        user = message.from_user
        await message.bot.send_message(
            config.admin_id,
            f"Апелляция от пользователя\nID: {user.id if user else 0}\n"
            f"Username: @{user.username if user and user.username else 'none'}\n\n{text[:3500]}",
        )
        await message.answer("Апелляция отправлена админу.")
        await state.clear()

    @router.callback_query(F.data.startswith("reg:"))
    async def registration_type_callback(callback: CallbackQuery, state: FSMContext) -> None:
        _, reg_type = callback.data.split(":", maxsplit=1)
        if await service.db.has_approved_registration(callback.from_user.id, reg_type):
            await callback.answer("Вы уже зарегистрированы в этой категории.", show_alert=True)
            return
        if reg_type in {"movement", "party"}:
            if await service.db.is_country_leader(callback.from_user.id):
                await callback.answer("Недоступно: у вас уже есть страна/группировка.", show_alert=True)
                return
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
            if reg_type == "country" and user_id:
                country_name = _extract_country_name_from_form(form_text)
                await service.db.add_country_leader(country_name, user_id, source="registration")
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

    @router.message(WriteNewsState.waiting_text)
    async def write_news_flow(message: Message, state: FSMContext) -> None:
        text = _normalize_hashtags_to_english((message.caption or message.text or "").strip())
        state_data = await state.get_data()
        pending_text = str(state_data.get("pending_news_text", "")).strip()

        if pending_text and re.fullmatch(r"#[A-Za-zА-Яа-я0-9_]+", text):
            text = f"{pending_text}\n{text}"

        if not text and not (message.photo or message.video or message.animation):
            await message.answer("Пустой текст")
            return
        final_tag = _extract_final_hashtag(text)
        if not final_tag:
            await state.update_data(pending_news_text=text)
            await message.answer("Нужен хештег страны в конце новости (пример: #OBS). Отправьте хештег отдельным сообщением.")
            return

        body = re.sub(r"#[A-Za-zА-Яа-я0-9_]+\s*$", "", text).strip()
        if not body:
            await message.answer("Сначала отправьте текст новости, затем хештег страны.")
            return

        normalized_tag = _normalize_single_hashtag(final_tag)
        claimed_country = _country_by_hashtag(normalized_tag)
        if not claimed_country:
            await message.answer("Не найден валидный хештег страны.")
            return

        if normalized_tag != final_tag.upper():
            text = re.sub(r"#[A-Za-zА-Яа-я0-9_]+\s*$", normalized_tag, text.strip())

        user_id = message.from_user.id if message.from_user else 0
        if not _is_author_allowed_for_country(claimed_country, user_id):
            allowed = _user_allowed_countries(user_id)
            if allowed:
                tags = ", ".join(config.country_hashtags.get(allowed[0], ["#RP"]))
                await message.answer(f"Вы не можете публиковать новости от лица этой страны. Твой настоящий хештег: {tags}")
            else:
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
        await state.update_data(pending_news_text="")
        await state.clear()
        await message.answer("Принято в очередь")
    @router.callback_query(F.data.startswith("mod:"))
    async def moderation_callback(callback: CallbackQuery, state: FSMContext) -> None:
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

        if action == "approve":
            if post.has_media:
                await service.publish_media_and_mark(post, payload["formatted_text"], hash_value)
            else:
                formatted, entities = service._render_post(post, post.text)
                await service.publish_and_mark(post, formatted, entities, hash_value)
            await callback.message.answer("Одобрено и опубликовано")
            return

        if action == "edit":
            await state.set_state(AdminState.waiting_moderation_fix)
            await state.update_data(mod_token=token, mod_payload=payload)
            await callback.message.answer(
                "Напиши, что нужно исправить.\n"
                "Формат: старое -> новое; старое2 -> новое2\n"
                "Или отправь полностью исправленный текст."
            )
            return

        if action == "reject":
            await service.db.mark_processed(post.source_channel, post.message_id, hash_value)
            await callback.message.answer("Отклонено")
            return

        if action == "war_block":
            await service.db.mark_processed(post.source_channel, post.message_id, hash_value)
            await callback.message.answer("Классифицировано как военные действия: отклонено")
            return

    @router.message(AdminState.waiting_moderation_fix)
    async def moderation_fix_flow(message: Message, state: FSMContext) -> None:
        if not message.from_user or message.from_user.id != config.admin_id:
            return
        data = await state.get_data()
        payload = data.get("mod_payload")
        if not isinstance(payload, dict):
            await message.answer("Не найден payload модерации. Повторите действие.")
            await state.clear()
            return

        raw_text = str(payload.get("raw_text") or payload.get("formatted_text") or "")
        instruction = (message.text or "").strip()
        fixed_text = _apply_admin_fix(raw_text, instruction)

        post = IncomingPost(
            source_country=payload["source_country"],
            source_channel=payload["source_channel"],
            message_id=payload["message_id"],
            text=fixed_text,
            has_media=payload.get("has_media", False),
            media_file_id=payload.get("media_file_id"),
            media_type=payload.get("media_type"),
            submitted_by_user_id=payload.get("submitted_by_user_id"),
        )
        hash_value = payload.get("hash_value") or content_hash(f"{post.source_channel}:{post.message_id}:{fixed_text}")

        if post.has_media:
            formatted, _ = service._render_post(post, fixed_text)
            await service.publish_media_and_mark(post, formatted, hash_value)
        else:
            formatted, entities = service._render_post(post, fixed_text)
            await service.publish_and_mark(post, formatted, entities, hash_value)
        await message.answer("Исправлено и опубликовано.")
        await state.clear()


    @router.message(F.text)
    async def antiflood_news_guard(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        current_state = await state.get_state()
        if not _is_news_submission(text, current_state):
            return
        if not message.from_user:
            return
        ok, reason = await service.check_antiflood(message.from_user.id)
        if not ok:
            await message.answer(reason)

    return router
