"""
Notification service for Edus Calendar Sync.

Provides utilities for dispatching operational status and error alerts
via Telegram Bot API.
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)


def send_telegram_alert(message, bot_token=None, chat_id=None, session=None, timeout=10):
    """
    Sends an alert message to a designated Telegram chat.
    Retrieves credentials from environment variables if not passed explicitly.

    :param message: Text string to send
    :param bot_token: Optional Telegram Bot token (defaults to TELEGRAM_BOT_TOKEN env)
    :param chat_id: Optional Telegram Chat ID (defaults to TELEGRAM_CHAT_ID env)
    :param session: Optional requests.Session instance
    :param timeout: HTTP request timeout in seconds
    :return: True if sent successfully, False otherwise
    """
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    sess = session or requests.Session()
    try:
        response = sess.post(url, json={"chat_id": chat, "text": message}, timeout=timeout)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"⚠️ Telegram alert failed: {e}")
        return False
