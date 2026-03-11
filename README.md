# Telegram RP News Aggregator Bot

Production-ready асинхронный Telegram-агрегатор RP-новостей для Railway.

## Возможности

- Гибридная архитектура:
  - **Userbot (Telethon)** слушает источники мгновенно.
  - **Userbot (Telethon)** публикует в канал от вашего аккаунта.
- Почти мгновенная реакция на новые посты (очередь + async worker).
- Строгая фильтрация RP-контента (deny by default).
- Блокировка военного/OOC/meta/real-world контента.
- Анти-дубли на SHA-256 + SQLite.
- Авто-переписывание формулировок (например `мы строим` → `{страна} строит`).
- Форматирование под шаблон:
  - `👀` заголовок
  - `✔️` краткая суть
  - emoji по типу новости
  - авто-хештеги стран по упоминаниям (например `#VL #TNR`)
- Медиа-посты не публикуются автоматически, отправляются админу на модерацию с кнопками.
- Военные действия (атаки/обстрелы/штурмы) блокируются автоматически; новости о подготовке/оборонке уходят админу на классификацию: «операция без ВД» или «военные действия».
- Упоминания неизвестных RP-стран в форматах «Республика/Королевство/Государство ...» отклоняются фильтром.

- Источники с `+invite` (без публичного username) нельзя стабильно подписать через `events.NewMessage(chats=...)`; бот их пропускает и логирует предупреждение. Для таких источников лучше указать публичный username или numeric ID после вступления в чат.
- Команда только `/start`; остальные действия выполняются кнопками и callback-меню.
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

- `/start` — открывает меню кнопок.
- Админские действия (`статус/пауза/резюме/reload`) доступны через кнопку «⚙️ Админ-панель» только администратору.
- Публикация новости и анкеты выполняются через кнопки в меню.
- По анкетам админ получает кнопки «Принять анкету / Отклонить анкету»; при отклонении нужно отправить причину, и она уходит пользователю.
- Русские/невалидные хештеги в ручной новости автоматически приводятся к английским тегам страны (например `#Вилония` -> `#VL`).
- Встроенные emoji из текста новости удаляются при проверке/нормализации, оформление emoji добавляется форматтером.
- Очень длинные новости автоматически сокращаются в пересказ и получают ссылку на оригинал (если доступна публичная ссылка источника).
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
- `/schedule_news` — schedule delayed publication (`YYYY-mm-dd HH:MM | COUNTRY | TEXT`).
- `/rss_add KEY URL` and `/rss_list` — runtime RSS integration.
- `/submit_map` — publishes a map digest (photo/file + auto-styled war summary).
- Media from `/write_news` goes to admin moderation and is published only after approval.
- Anti-flood guard with temporary account blocking when user exceeds message rate.
- War posts are allowed only with RP-process wording and army-size sanity checks (50..200).
- Aggressive log rotation: 1KB log chunks + spam dedup filter.

### Premium emoji note
Bot publishes premium emoji through HTML tags:
`<tg-emoji emoji-id="..."></tg-emoji>`
The IDs are configured in `app/config.py` under `premium_emoji_ids`.


### Entity-based custom emoji
Публикация в канал идёт через Telethon `send_message(..., formatting_entities=...)` и `MessageEntityCustomEmoji`, без Markdown/HTML тегов.

Для загрузки паков как "стикеров" используйте:
- `emoji_packs` в `app/config.py` (ссылки `https://t.me/addemoji/...`),
- команду `/emoji_reload` (перезагрузка и кэш в `app/storage/emojis.json`),
- команду `/emoji_list` (просмотр первых ID из кэша).
- По умолчанию подключён только `NewsEmoji`; если у вас другие паки, добавьте их ссылки в `config.emoji_packs` и выполните `/emoji_reload`.
