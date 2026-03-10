from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def moderation_keyboard(token: str, review_mode: str = "default") -> InlineKeyboardMarkup:
    if review_mode == "war":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Это операция (без ВД)", callback_data=f"mod:war_ok:{token}"),
                    InlineKeyboardButton(text="Это военные действия", callback_data=f"mod:war_block:{token}"),
                ]
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Одобрить", callback_data=f"mod:approve:{token}"),
                InlineKeyboardButton(text="Отклонить", callback_data=f"mod:reject:{token}"),
            ]
        ]
    )
