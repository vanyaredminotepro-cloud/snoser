# TikTok Automation Bot

Репозиторий очищен от функциональности автопостинга новостей.

Оставлен только бот для:
- загрузки видео через Telegram в очередь,
- автопостинга в TikTok,
- сбора статистики TikTok,
- управления через inline-меню Telegram.

## Запуск

```bash
pip install -r requirements.txt
python -m playwright install chromium
python bot.py
```

## Переменные окружения

См. `.env.example`.
Обязательные:
- `TG_BOT_TOKEN`
- `TIKTOK_LOGIN`
- `TIKTOK_PASSWORD`

## Railway

Используется `Procfile`:

```text
worker: python bot.py
```
