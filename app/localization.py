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
}


def t(key: str, locale: str | None = None, **kwargs: object) -> str:
    lang = "ru"
    template = BOT_TEXTS[lang].get(key, key)
    return template.format(**kwargs)
