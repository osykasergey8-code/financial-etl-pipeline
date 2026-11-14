"""Optional Telegram notification. Does nothing unless TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID are set in .env. A failed notification never stops the pipeline."""
import os
import logging
import requests

log = logging.getLogger("etl")


def build_summary(base, clean, rejected, elapsed):
    lines = [f"ETL OK: {len(clean)} rates loaded, {len(rejected)} rejected ({elapsed:.1f}s)"]
    for r in clean[:6]:
        lines.append(f"{base}->{r['target_currency']}: {r['rate']}")
    for rej in rejected[:5]:
        lines.append(f"REJECTED {rej['currency']}: {rej['reason']}")
    return "\n".join(lines)


def send_telegram(text, token=None, chat_id=None):
    token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:3500]},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:  # never break the ETL because of a notification
        log.warning(f"Telegram notification failed: {type(e).__name__}")
        return False
