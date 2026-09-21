from unittest.mock import MagicMock, patch

from driftmate.channels.telegram.telegram_channel import TelegramNotificationChannel
from driftmate.channels.common.state_store import InMemoryStateStore


def test_telegram_channel_registers_analyze_and_action():
    store = InMemoryStateStore()
    with patch("driftmate.channels.telegram.telegram_channel.Bot"):
        channel = TelegramNotificationChannel(
            bot_token="test_token",
            chat_id="12345",
            state_store=store,
        )

        mock_action_cb = MagicMock()
        mock_analyze_cb = MagicMock()

        channel.onAction(mock_action_cb)
        channel.onAnalyze(mock_analyze_cb)

        assert channel._callback == mock_action_cb
        assert channel._analyze_callback == mock_analyze_cb
