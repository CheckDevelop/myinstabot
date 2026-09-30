# Instagram + Telegram + Render + Supabase

The original Instagram automation module is kept as `instagram_bot.py`.
The deployment layer wraps it instead of rewriting its Instagram `Client` calls.

## Environment variables

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_ID`
- `INSTAGRAM_SESSION`
- `VLESS_URL`

## Telegram

- `/start`
- `/status`
- `/stats`
- `/activity`
- `/run saved`
- `/run collect <location> <location_number>`
- `/stop`

## Important

The JSON state files used by the original program are mirrored locally for compatibility,
but PostgreSQL is the persistent source of truth. Render's local filesystem is not relied on
for long-term state.
