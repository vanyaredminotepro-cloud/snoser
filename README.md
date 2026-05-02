# TikTok Automation Bot

Репозиторий очищен от функциональности автопостинга новостей — в `app/` оставлен только TikTok-бот.

## Что умеет бот
- Принимать MP4 (до 50 МБ) через Telegram и складывать в очередь.
- Публиковать **следующее** видео из очереди по расписанию или вручную.
- Собирать статистику TikTok в SQLite каждые 6 часов.
- Управляться через inline-кнопки и callbacks (`/start` только открывает панель).

## Запуск
```bash
pip install -r requirements.txt
python -m playwright install chromium
python bot.py
```

## Переменные окружения
См. `.env.example`.

Обязательная:
- `TG_BOT_TOKEN`

Для публикации в TikTok также нужны:
- `TIKTOK_LOGIN`
- `TIKTOK_PASSWORD`

## Railway
Используется `Procfile`:
```text
worker: python bot.py
```
