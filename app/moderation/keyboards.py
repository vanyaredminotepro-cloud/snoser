from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def moderation_keyboard(token: str, review_mode: str = "default") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Новость полностью соблюдает РП", callback_data=f"mod:approve:{token}"),
            InlineKeyboardButton(text="Поправить", callback_data=f"mod:edit:{token}"),
        ],
        [
            InlineKeyboardButton(text="Отклонить", callback_data=f"mod:reject:{token}"),
        ],
    ]
    if review_mode == "war":
        rows.append(
            [
                InlineKeyboardButton(text="Классифицировать как военные действия", callback_data=f"mod:war_block:{token}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
