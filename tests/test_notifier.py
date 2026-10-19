import os
import unittest
from unittest.mock import MagicMock, patch
from notifier import send_telegram_alert


class TestNotifier(unittest.TestCase):
    def test_send_telegram_alert_no_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            res = send_telegram_alert("Hello alert")
            self.assertFalse(res)

    def test_send_telegram_alert_success(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_session.post.return_value = mock_resp

        res = send_telegram_alert(
            message="Status: OK",
            bot_token="123456:ABC-DEF",
            chat_id="998877",
            session=mock_session
        )
        self.assertTrue(res)
        mock_session.post.assert_called_once_with(
            "https://api.telegram.org/bot123456:ABC-DEF/sendMessage",
            json={"chat_id": "998877", "text": "Status: OK"},
            timeout=10
        )

    def test_send_telegram_alert_failure(self):
        mock_session = MagicMock()
        mock_session.post.side_effect = ConnectionError("Connection refused")

        res = send_telegram_alert(
            message="Alert",
            bot_token="token",
            chat_id="chat",
            session=mock_session
        )
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
