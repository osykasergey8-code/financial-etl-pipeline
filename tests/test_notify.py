import sys
sys.path.insert(0, ".")
from unittest import mock
import notify


def test_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with mock.patch("notify.requests.post") as post:
        assert notify.send_telegram("x") is False
        post.assert_not_called()


def test_sends_message():
    with mock.patch("notify.requests.post") as post:
        assert notify.send_telegram("hello", token="T", chat_id="1") is True
        url = post.call_args[0][0]
        assert url == "https://api.telegram.org/botT/sendMessage"
        assert post.call_args[1]["json"] == {"chat_id": "1", "text": "hello"}


def test_failure_does_not_raise():
    with mock.patch("notify.requests.post", side_effect=RuntimeError("boom")):
        assert notify.send_telegram("x", token="T", chat_id="1") is False


def test_summary_contains_rejections():
    s = notify.build_summary("USD", [{"target_currency": "EUR", "rate": 0.9}],
                             [{"currency": "GBP", "reason": "zero"}], 1.2)
    assert "1 rates loaded, 1 rejected" in s and "USD->EUR: 0.9" in s and "REJECTED GBP: zero" in s
