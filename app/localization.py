from app.config import config


BOT_TEXTS: dict[str, dict[str, str]] = {
    "ru": {
        "bot_active": "Бот активен.\nИспользуйте inline-кнопки ниже.\n\nДля публикации новости укажите корректный хештег страны (например #OBS).",
        "mobilization_no_country": "Нет страны для мобилизации",
        "mobilization_unknown_type": "Неизвестный тип мобилизации",
        "mobilization_unknown_action": "Неизвестное действие мобилизации",
        "mobilization_force_reason_prompt": "Введите причину принудительной остановки мобилизации.",
        "mobilization_blocked": "Нельзя запустить мобилизацию.\nПричина: {reason}\n\nНужна подтверждающая новость (мобилизация/синонимы) по вашей стране за последние 23 дня.",
        "mobilization_amount_prompt": "Введите количество для мобилизации типа «{label}» ({min_gain}-{max_gain}).",
        "registration_choose_type": "Выберите тип регистрации:",
        "admin_panel_title": "Админ-панель:",
        "stats_office_required": "Доступ к статистике только для пользователей с подтверждённой ролью.",
        "news_office_required": "Для использования бота нужна зарегистрированная страна или подтверждённая должность.",
    },
    "en": {
        "bot_active": "Bot is active.\nUse the inline buttons below.\n\nTo publish news, add a valid country hashtag (for example #OBS).",
        "mobilization_no_country": "No country is available for mobilization",
        "mobilization_unknown_type": "Unknown mobilization type",
        "mobilization_unknown_action": "Unknown mobilization action",
        "mobilization_force_reason_prompt": "Send the reason for force-finishing mobilization.",
        "mobilization_blocked": "Mobilization cannot be started.\nReason: {reason}\n\nA confirming news post (mobilization/synonyms) for your country is required within the last 23 days.",
        "mobilization_amount_prompt": "Enter amount for mobilization type “{label}” ({min_gain}-{max_gain}).",
        "registration_choose_type": "Choose registration type:",
        "admin_panel_title": "Admin panel:",
        "stats_office_required": "Statistics are available only to users with a confirmed role.",
        "news_office_required": "Using the bot requires a registered country or confirmed office.",
    },
}


def t(key: str, locale: str | None = None, **kwargs: object) -> str:
    lang = (locale or getattr(config, "bot_locale", "ru") or "ru").lower()
    template = BOT_TEXTS.get(lang, BOT_TEXTS["ru"]).get(key, BOT_TEXTS["ru"].get(key, key))
    return template.format(**kwargs)
