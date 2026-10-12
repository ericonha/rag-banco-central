"""Optional failure notification through a Slack/Discord-compatible webhook."""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("worker.alerts")


async def send_alert(text: str) -> bool:
    """POST {"text", "content"} to PIPELINE_ALERT_WEBHOOK_URL. Never raises; False if not sent."""
    url = get_settings().pipeline_alert_webhook_url
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json={"text": text, "content": text})
            response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not send alert: %s", exc)
        return False
