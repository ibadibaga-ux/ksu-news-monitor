# KSU News Monitor

Ежедневный мониторинг новостей **Херсонского государственного университета (ХДУ / KSU)** с отправкой дайджеста в Telegram в **09:30 по киевскому времени (`Europe/Kyiv`)** через GitHub Actions.

## Источники

1. **Официальный сайт `kspu.edu`** — парсинг RSS-ленты `https://kspu.edu/rss` с автоматическим HTML-фолбэком на `https://kspu.edu/default`.
2. **Google News RSS** — поиск упоминаний `"Херсонський державний університет"` и `"Kherson State University"` (с фильтрацией зеркал `kspu.edu` и нерелевантных вузов).
3. **Telegram `@ksuniver`** — чтение публичного веб-превью канала `https://t.me/s/ksuniver` (без необходимости авторизации MTProto).

## Как работает расписание 09:30 по Киеву (зима / лето)

GitHub Actions поддерживает `cron` только в UTC, поэтому в [`.github/workflows/daily-digest.yml`](.github/workflows/daily-digest.yml) указаны два расписания:
- `30 6 * * *` — **06:30 UTC** → **09:30 EEST** (летнее время, UTC+3)
- `30 7 * * *` — **07:30 UTC** → **09:30 EET** (зимнее время, UTC+2)

Перед запуском мониторинга шаг `--check-schedule` сверяет `github.event.schedule` с текущим смещением `ZoneInfo("Europe/Kyiv")`. Лишний запуск пропускается, а нужный выполняется корректно даже при задержках очереди GitHub Actions.

## Защита от дублей (`state.json`)

Все отправленные новости сохраняются в [`state.json`](state.json) и автоматически коммитятся обратно в репозиторий после запуска:
- дедупликация по уникальному ID источника (`kspu:<newsId>`, `gnews:<hash>`, `tg:ksuniver/<post_id>`);
- дополнительная дедупликация по нормализованному URL и заголовку (защита от кросс-постов между сайтом и СМИ);
- защита от повторной отправки дайджеста в один и тот же киевский день (`last_digest_kyiv_date`);
- автоматическая очистка записей старше 180 дней (`state_retention_days`).

## Настройка в GitHub

1. Создайте Telegram-бота через `@BotFather` и получите токен.
2. Узнайте `chat_id` (личный чат, группа или канал, куда добавлен бот).
3. В репозитории откройте **Settings → Secrets and variables → Actions → Secrets** и добавьте:
   - `TELEGRAM_BOT_TOKEN` — токен бота
   - `TELEGRAM_CHAT_ID` — ID чата/канала (например `-1001234567890`)
4. *(Опционально)* В **Actions → Variables** можно задать:
   - `MAX_AGE_HOURS` (по умолчанию `72`) — максимальный возраст новостей для попадания в дайджест
   - `SEND_EMPTY_DIGEST` (по умолчанию `false`) — отправлять ли сообщение, если новых новостей нет
   - `GOOGLE_NEWS_QUERIES` — список запросов через `;`

Для ручной проверки откройте **Actions → Daily KSU News Digest → Run workflow** (есть режим `dry_run` без отправки в Telegram и изменения `state.json`).

## Локальный запуск и тесты

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Прогнать тесты
pytest -v

# Тестовый прогон без отправки в Telegram
DRY_RUN=true PYTHONPATH=src python -m ksu_news_monitor
```
