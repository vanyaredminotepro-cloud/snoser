from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def moderation_keyboard(token: str, review_mode: str = "default") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Новость полностью соблюдает РП", callback_data=f"mod:approve:{token}"),
                InlineKeyboardButton(text="Поправить", callback_data=f"mod:edit:{token}"),
            ]
        ]
    )
