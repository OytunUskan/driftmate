"""Telegram handlers must only act on updates from the configured chat."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from driftmate.channels.common.state_store import InMemoryStateStore
from driftmate.channels.telegram.telegram_channel import TelegramNotificationChannel

CONFIGURED_CHAT = "12345"


def _channel():
    store = InMemoryStateStore()
    with patch("driftmate.channels.telegram.telegram_channel.Bot"):
        channel = TelegramNotificationChannel(
            bot_token="test_token", chat_id=CONFIGURED_CHAT, state_store=store
        )
    return channel, store


def _set_chat(obj, chat_id):
    """Expose the chat id through every attribute path python-telegram-bot offers."""
    obj.chat_id = chat_id
    obj.chat.id = chat_id


def _update(chat_id, user_id=777):
    update = MagicMock()
    update.effective_chat.id = chat_id
    _set_chat(update.effective_message, chat_id)
    _set_chat(update.message, chat_id)
    update.message.reply_text = AsyncMock()
    update.effective_user.id = user_id
    query = update.callback_query
    _set_chat(query.message, chat_id)
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.from_user.id = user_id
    return update


def _drain(channel):
    channel._executor.shutdown(wait=True)


def test_callback_from_configured_chat_is_dispatched():
    channel, store = _channel()
    action_cb = MagicMock()
    channel.onAction(action_cb)
    store.set("abc123", {"action": "approve", "component": "nginx"})
    update = _update(int(CONFIGURED_CHAT))
    update.callback_query.data = "st:abc123"

    asyncio.run(channel._handle_query(update, None))
    _drain(channel)

    action_cb.assert_called_once()
    assert action_cb.call_args[0][1] == {"action": "approve", "component": "nginx"}


def test_callback_from_other_chat_is_ignored():
    channel, store = _channel()
    action_cb = MagicMock()
    channel.onAction(action_cb)
    store.set("abc123", {"action": "approve", "component": "nginx"})
    update = _update(999)
    update.callback_query.data = "st:abc123"

    asyncio.run(channel._handle_query(update, None))
    _drain(channel)

    action_cb.assert_not_called()


def test_analyze_from_configured_chat_is_dispatched():
    channel, _ = _channel()
    analyze_cb = MagicMock()
    channel.onAnalyze(analyze_cb)

    asyncio.run(channel._handle_analyze(_update(int(CONFIGURED_CHAT)), None))
    _drain(channel)

    analyze_cb.assert_called_once()


def test_analyze_from_other_chat_is_ignored():
    channel, _ = _channel()
    analyze_cb = MagicMock()
    channel.onAnalyze(analyze_cb)

    asyncio.run(channel._handle_analyze(_update(999), None))
    _drain(channel)

    analyze_cb.assert_not_called()
