from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def moderation_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"mod:approve:{token}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"mod:reject:{token}"),
            ]
        ]
    )
