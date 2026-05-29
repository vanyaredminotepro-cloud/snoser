# Telegram RP News Aggregator Bot

Production-ready асинхронный Telegram-агрегатор RP-новостей для Railway.

## Возможности

- Гибридная архитектура:
  - **Userbot (Telethon)** слушает источники мгновенно.
  - **Userbot (Telethon)** публикует в канал от вашего аккаунта.
- Почти мгновенная реакция на новые посты (очередь + async worker).
- Строгая фильтрация RP-контента (deny by default).
- Блокировка токсичного/OOC/real-world контента с понятной причиной для автора новости.
- Анти-дубли на SHA-256 + SQLite.
- Авто-переписывание формулировок (например `мы строим` → `{страна} строит`).
- Форматирование под шаблон:
  - `👀` заголовок
    - emoji по типу новости
  - авто-хештеги стран по упоминаниям (например `#VL #TNR`)
- Медиа-посты не публикуются автоматически, отправляются админу на модерацию с кнопками.
- Военные действия (атаки/обстрелы/штурмы) блокируются автоматически; новости со слабым военным контекстом публикуются с предупреждением.
- Упоминания неизвестных RP-стран в форматах «Республика/Королевство/Государство ...» отклоняются фильтром.
- Расширенная RP-валидация:
  - контроль неизвестных country-хештегов,
  - запрет запрещённого оружия/структур,
  - контроль численности армии в диапазоне 50..200,
  - проверка наличия кадров/видео для прямых военных действий.
- Стратегические авто-циклы:
  - ежедневный экономический цикл (доходы + ресурсы),
  - еженедельные кризисы по индексу риска,
  - ежедневные миссии,
  - авто-завершение технологических проектов.
- Дашборд из 10 метрик:
  - мощь, армия, бюджет, граждане, военная/экономическая эффективность,
  - территориальный прогресс, дипломатия, стабильность, RP-качество.
- Ежемесячные итоги:
  - автопубликация статистики по количеству новостей от стран,
  - награды «Страна месяца» и «Самая активная редакция».

- Источники с `+invite` (без публичного username) нельзя стабильно подписать через `events.NewMessage(chats=...)`; бот их пропускает и логирует предупреждение. Для таких источников лучше указать публичный username или numeric ID после вступления в чат.
- Команда только `/start`; остальные действия выполняются кнопками и callback-меню.
- Для ручной публикации обязателен валидный хештег страны в конце текста; кириллические варианты (`#ТНР`, `#КК8`) автозаменяются.
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

Перед запуском обязательно задайте переменные окружения Telegram:

- `TG_API_ID` (или `API_ID`)
- `TG_API_HASH` (или `API_HASH`)
- `TG_BOT_TOKEN` (или `BOT_TOKEN`)

Пример для Linux/macOS:

```bash
export TG_API_ID=12345678
export TG_API_HASH=0123456789abcdef0123456789abcdef
export TG_BOT_TOKEN=123456:ABCDEF...
python -m app.main
```

Пример для Windows PowerShell:

```powershell
$env:TG_API_ID="12345678"
$env:TG_API_HASH="0123456789abcdef0123456789abcdef"
$env:TG_BOT_TOKEN="123456:ABCDEF..."
python -m app.main
```


Также можно создать `.env` в корне проекта (без кавычек), либо скопировать готовый шаблон: `cp .env.example .env`.

```env
TG_API_ID=12345678
TG_API_HASH=0123456789abcdef0123456789abcdef
TG_BOT_TOKEN=123456:ABCDEF...
```

Дополнительно (для прод/railway) можно задать:

```env
ADMIN_ID=5006629901
ADMIN_USERNAME=@your_admin_username
TARGET_CHANNEL=@your_target_channel
SESSION_NAME=news_userbot
SQLITE_PATH=app/storage/bot_data.sqlite3
LOGS_DIR=logs
PUBLISH_DELAY_SECONDS=0
QUEUE_INGEST_DELAY_MIN=2
QUEUE_INGEST_DELAY_MAX=5
QUEUE_PUBLISH_DELAY_MIN=3
QUEUE_PUBLISH_DELAY_MAX=9
LONG_PAUSE_CHANCE=0.2
LONG_PAUSE_MIN=15
LONG_PAUSE_MAX=20
DAILY_POST_LIMIT=30
PORT=8080
HEALTHCHECK_ENABLED=true
```

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

Подробный гайд: `RAILWAY_DEPLOY_GUIDE.md`  
Частые проблемы и фиксы: `RAILWAY_TROUBLESHOOTING.md`

## Админ-гайд

- `/start` — открывает меню кнопок.
- Админские действия доступны только через кнопку «⚙️ Админ-панель» и inline-кнопки (без отдельных slash-команд).
- В админ-панели доступны: «Хештеги (добавить/изменить)», «Организации/источники», «Управление пользователями», «Снять блокировку с пользователя», «HTML исследование (beta)», «Emoji reload».
- Публикация новости и анкеты выполняются через inline-кнопки меню после /start.
- Для пользователей доступна кнопка «🧾 Оспорить отклонение» (апелляция уходит админу).
- В меню есть:
  - «📊 Статистика» — полный глобальный дашборд (10 метрик + активность новостей),
  - «📊 Статистика стран» — красивая карточка конкретной страны с местами в рейтингах и мощью.
- По анкетам админ получает кнопки «Принять анкету / Отклонить анкету»; при отклонении нужно отправить причину, и она уходит пользователю.
- В анкете есть кнопки «Создать движение» и «Создать партию» (легальная/нелегальная ветка);
  для владельцев уже зарегистрированной страны/структуры новые регистрации блокируются.
- Русские/невалидные хештеги в ручной новости автоматически приводятся к английским тегам страны (например `#Вилония` -> `#VL`).
- Если отправили новость и забыли хештег, бот запоминает текст и ждёт отдельное сообщение с хештегом.
- Встроенные emoji из текста новости удаляются при проверке/нормализации, оформление emoji добавляется форматтером.
- Служебные метки удаляются из текста при публикации (без дополнительных пометок внизу).
- Очень длинные новости автоматически сокращаются в пересказ и получают ссылку на оригинал (если доступна публичная ссылка источника).
- Модерация военных/медиа новостей:
  - бот отправляет пост админу;
  - кнопки `Новость полностью соблюдает РП` / `Поправить`.
- Антифлуд:
  - учитываются callback-действия и команды пользователей,
  - при превышении лимита ставится временный бан (из БД),
  - админ может снять блокировку вручную через панель.

## Надежность и производительность

- Async-only I/O.
- Очередь обработки ограничена (`maxsize=3000`) для memory safety.
- SQLite для устойчивости к рестартам.
- Авто-restart на Railway (`ON_FAILURE`).
- uvloop для ускорения event loop.
- Встроенный health endpoint (`200 OK`) на `PORT` для Railway health checks.

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


## Telegram Premium emoji (custom emoji) guide (Telethon entities)

Сейчас бот использует стандартные emoji-символы. Чтобы отправлять именно Telegram Premium custom emoji, нужно:

1. Взять `custom_emoji_id` нужного emoji (через бота/скрипт, который читает entities из сообщения с premium emoji).
2. Перейти на HTML parse mode (уже включено в `app/core/services.py`).
3. Вставлять emoji в текст как:
   `<tg-emoji emoji-id="1234567890123456789"></tg-emoji>`
4. Подменить символные emoji в `app/formatters/news_formatter.py` на такие теги.

5. Либо заполнить `premium_emoji_ids` в `app/config.py` (ключ = страна, значение = custom emoji id), чтобы бот подставлял premium emoji автоматически.

Пример строки:

```html
<blockquote><tg-emoji emoji-id="1234567890123456789"></tg-emoji> <b>Обоссляндия</b> <i>готовит встречу...</i></blockquote>
```

Важно: без корректного `custom_emoji_id` Telegram покажет обычный fallback или ничего.


## Формат публикации (текущий)

- Убираются префиксы `Важное:`/`Срочно:` и встроенные хештеги из исходника.
- Пост разбивается на абзацы; **каждый абзац начинается с emoji** (premium при наличии id).
- Первый абзац публикуется в `blockquote` с форматом: `<b>Страна</b> <i>текст</i>`.
- Если текст очень длинный, он автоматически сокращается до безопасной длины с `…`.
- Хештеги добавляются автоматически:
  - основной тег страны-источника,
  - дополнительные теги всех стран, упомянутых в новости.

## Custom emoji IDs

Бот уже подключен к вашим ID и использует semantic-ключи в `config.py`:
`DEFAULT`, `IMPORTANT`, `ECONOMY`, `DIPLOMACY`, `WARNING`, `MAP`.

Можно прислать больше ID — просто добавим в `premium_emoji_ids`.


## New operational features
- Публикация запускается через кнопку «📰 Написать новость»; если есть медиа, пост отправляется в админ-модерацию и публикуется после одобрения.
- RSS интеграция остаётся runtime-функцией через конфиг `config.rss_feeds`.
- Anti-flood guard with temporary account blocking when user exceeds message rate.
- War posts are allowed only with RP-process wording, evidence checks and army-size sanity checks (50..200).
- Aggressive log rotation: 1KB log chunks + spam dedup filter.

### Premium emoji note
Bot publishes premium emoji through HTML tags:
`<tg-emoji emoji-id="..."></tg-emoji>`
The IDs are configured in `app/config.py` under `premium_emoji_ids`.


### Entity-based custom emoji
Публикация в канал идёт через Telethon `send_message(..., formatting_entities=...)` и `MessageEntityCustomEmoji`, без Markdown/HTML тегов.

Для загрузки паков как "стикеров" используйте:
- `emoji_packs` в `app/config.py` (ссылки `https://t.me/addemoji/...`),
- кнопку `Emoji reload` в админ-панели (перезагрузка и кэш в `app/storage/emojis.json`).
- По умолчанию подключён только `NewsEmoji`; если у вас другие паки, добавьте их ссылки в `config.emoji_packs` и нажмите `Emoji reload`.

## Веб-исследования

- В главном меню бота есть кнопка **🔬 Исследования (WEB)** — она открывает URL из `WEB_DASHBOARD_URL`.
- Веб-панель находится в `web/` и показывает страны, активные исследования и полное дерево технологий.
- Для защищённого запуска исследований можно задать `WEB_API_TOKEN` и передавать `X-API-Key`.

Запуск:

```bash
pip install -r requirements.txt
python web/app.py
```

## web_research (независимый дисплей исследований)

Новая независимая панель лежит в `web_research/`:

```text
web_research/
├── app.py
├── requirements.txt
├── templates/index.html
├── static/css/style.css
├── static/js/main.js
└── config.py
```

Запуск:

```bash
pip install -r web_research/requirements.txt
python web_research/app.py
```

По умолчанию URL: `https://islam.net`.
