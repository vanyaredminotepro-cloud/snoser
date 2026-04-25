# Repository Overview

## Что это за проект

Этот репозиторий содержит RP news платформу из трёх частей:

1. **Telegram-бот runtime (`app/`)** — получает новости из Telegram-источников и RSS, фильтрует RP-контент, форматирует публикации, отправляет в канал и ведёт модерацию.
2. **Legacy web-панель (`web/`)** — Flask API + простая веб-страница для стран/техдерева/активных исследований.
3. **Новая web_research-панель (`web_research/`)** — отдельный Flask-сервис с CORS, историей исследований и расширенным контролем тех-исследований.

## Структура по директориям

### `app/`
- `main.py` — entrypoint рантайма, запуск healthcheck-сервера, инициализация БД и сервисов.
- `bot.py` — инициализация Aiogram Bot + Telethon Userbot, обработка новых сообщений из источников.
- `config.py` — загрузка `.env`/env-переменных и все runtime-настройки.
- `core/services.py` — центральная бизнес-логика (очередь постов, фильтрация, форматирование, публикация, scheduler, RSS).
- `storage/database.py` — слой работы с SQLite (состояние, статистика стран, исследования, модерация и пр.).
- `handlers/admin.py` — админ-роуты/кнопки и пользовательские сценарии в Telegram.
- `filters/` — RP и AI фильтры контента.
- `formatters/` — нормализация/форматирование новостей.
- `parsers/` — RSS, авто-перевод, загрузка emoji pack данных.
- `moderation/` — inline-клавиатуры и элементы moderation UX.
- `utils/` — утилиты по тексту (хеши, очистка, удаление эмодзи/хештегов).

### `web/`
- `app.py` — Flask-приложение для базового dashboard API (`/api/countries`, `/api/tech_tree`, `/api/research/*`).
- `templates/index.html`, `static/app.js`, `static/styles.css` — клиентская часть legacy-панели.

### `web_research/`
- `app.py` — независимый Flask API + UI для исследований (в т.ч. история, активные исследования, дерево технологий).
- `config.py` — настройки через env для этого сервиса.
- `templates/index.html`, `static/js/main.js`, `static/css/style.css` — фронтенд панели.
- `requirements.txt` — зависимости отдельного сервиса.

### `tests/`
- Покрытие ключевых узлов: конфиг, RP-фильтры, форматтер, `web` API и `web_research` API.

### Прочее в корне
- `README.md` — основной гайд по запуску и эксплуатации.
- `requirements.txt` — зависимости основного runtime.
- `Dockerfile`, `railway.json` — деплой в Railway.
- `RAILWAY_DEPLOY_GUIDE.md`, `RAILWAY_TROUBLESHOOTING.md` — прод-гайды.
- `scripts/start.sh` — скрипт старта.

## Как связаны компоненты

- Основной поток идёт через `app/main.py -> AppRuntime (app/bot.py) -> NewsService (app/core/services.py) -> Database (app/storage/database.py)`.
- Web-панели (`web/` и `web_research/`) читают и обновляют ту же SQLite-базу, которую использует бота runtime.
- Таким образом, Telegram-часть отвечает за ingestion/публикацию, а web-часть — за визуализацию и управление исследованиями.
