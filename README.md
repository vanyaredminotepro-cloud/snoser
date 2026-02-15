# Telegram RP News Aggregator Bot

Production-ready асинхронный Telegram-агрегатор RP-новостей для Railway.

## Возможности

- Гибридная архитектура:
  - **Userbot (Telethon)** слушает источники мгновенно.
  - **Bot (aiogram)** публикует в канал и принимает команды.
- Почти мгновенная реакция на новые посты (очередь + async worker).
- Строгая фильтрация RP-контента (deny by default).
- Блокировка военного/OOC/meta/real-world контента.
- Анти-дубли на SHA-256 + SQLite.
- Авто-переписывание формулировок (например `мы строим` → `{страна} строит`).
- Форматирование под шаблон:
  - `👀` заголовок
  - `✔️` краткая суть
  - emoji по типу новости
  - хештег страны
- Медиа-посты не публикуются автоматически, отправляются админу на модерацию с кнопками.
- Команды `/start /status /pause /resume /write_news`.
- Логирование в:
  - console
  - `logs/bot.log`
  - `logs/errors.log`

## Структура проекта

```text
/app
  /core
  /handlers
  /filters
  /parsers
  /moderation
  /formatters
  /storage
  /utils
  main.py
  config.py
  bot.py

/requirements.txt
/Dockerfile
/railway.json
/README.md
```

## Конфигурация

Все настройки находятся в `app/config.py` в классе `Config`.

Изменяемые параметры:
- источники
- хештеги стран
- target channel
- admin id
- задержка публикации (до 3 сек)
- путь SQLite

## Запуск локально

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

Для Windows также поддерживается:

```bash
python app/main.py
```

Если запускаете `python app/bot.py`, теперь это тоже полноценный старт runtime.

При первом старте Telethon автоматически запустит интерактивный вход (телефон/код) для userbot-сессии. После успешного входа `.session` сохранится, и повторная авторизация не потребуется.

## Railway Deploy

1. Push репозиторий в GitHub.
2. Создать новый Railway project из GitHub repo.
3. Railway автоматически использует `Dockerfile`.
4. Проверить логи деплоя.
5. Убедиться, что бот онлайн и видит источники.

## Админ-гайд

- `/status` — состояние, размер очереди, target.
- `/pause` — поставить публикацию на паузу.
- `/resume` — возобновить публикацию.
- `/write_news` — ручная публикация новости с валидацией.
- Модерация медиа:
  - бот отправляет пост админу;
  - кнопки `Одобрить` / `Отклонить`.

## Надежность и производительность

- Async-only I/O.
- Очередь обработки ограничена (`maxsize=2000`) для memory safety.
- SQLite для устойчивости к рестартам.
- Авто-restart на Railway (`ON_FAILURE`).
- uvloop для ускорения event loop.

## Важные примечания

- Default policy: **DENY BY DEFAULT**.
- Лучше пропустить сомнительную новость, чем опубликовать non-RP.
- Военные и OOC-посты не публикуются.


### Windows quick start (Python 3.10+)

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

> Можно запускать как `python -m app.main`, так и `python app/main.py` (и `python app/bot.py` тоже поддерживается).
> При первом запуске в терминале введите телефон и код Telegram для создания `.session`.
