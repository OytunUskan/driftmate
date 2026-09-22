"""Telegram implementation of the NotificationChannel interface.

Uses python-telegram-bot (v20+) long-polling, which requires no public HTTPS
endpoint or ngrok and works from a local WSL2 environment. The sync protocol
is bridged to the async library via a dedicated event-loop thread.
"""

import asyncio
import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from driftmate.channels.common.state_store import InMemoryStateStore, StateStore
from driftmate.core.models.notification import Action, MessageRef

logger = logging.getLogger(__name__)


class TelegramNotificationChannel:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        state_store: StateStore | None = None,
    ) -> None:
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id
        self._state_store = state_store or InMemoryStateStore()
        self._callback: Callable[[str, dict], None] | None = None
        self._analyze_callback: Callable[[str], None] | None = None

        self._loop = asyncio.new_event_loop()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._thread = threading.Thread(
            target=self._loop.run_forever, daemon=True, name="telegram-loop"
        )
        self._thread.start()

    def sendMessage(self, text: str, actions: list[Action]) -> MessageRef:
        self._prepare_actions(actions)

        reply_markup = self._build_keyboard(actions) if actions else None
        message = self._run(
            self._bot.send_message(
                chat_id=self._chat_id, text=text, reply_markup=reply_markup
            )
        )
        return MessageRef(message_id=message.message_id, chat_id=str(self._chat_id))

    def updateMessage(
        self,
        ref: MessageRef,
        text: str,
        actions: list[Action] | None = None,
    ) -> None:
        if actions:
            self._prepare_actions(actions)
        reply_markup = self._build_keyboard(actions) if actions else None
        self._run(
            self._bot.edit_message_text(
                text=text,
                chat_id=ref.chat_id,
                message_id=ref.message_id,
                reply_markup=reply_markup,
            )
        )

    def _prepare_actions(self, actions: list[Action]) -> None:
        for action in actions:
            short_id = uuid.uuid4().hex[:8]
            if action.metadata is not None:
                self._state_store.set(short_id, action.metadata)
            action.id = f"st:{short_id}"

    def onAction(self, callback: Callable[[str, dict], None]) -> None:
        self._callback = callback

    def onAnalyze(self, callback: Callable[[str], None]) -> None:
        self._analyze_callback = callback

    def start(self) -> None:
        if self._callback is None and self._analyze_callback is None:
            raise RuntimeError(
                "onAction or onAnalyze must be registered before start()"
            )
        application = Application.builder().token(self._bot.token).build()
        application.add_handler(CallbackQueryHandler(self._handle_query))
        if self._analyze_callback is not None:
            application.add_handler(CommandHandler("analyze", self._handle_analyze))
        self._run(application.run_polling())

    async def _handle_analyze(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if self._analyze_callback is None:
            return
        user_id = str(update.effective_user.id)
        await update.message.reply_text("Analyzing drift...")
        fut = self._executor.submit(self._analyze_callback, user_id)
        fut.add_done_callback(self._log_future_exception)

    async def _handle_query(self, update: Update, context) -> None:
        query = update.callback_query
        await query.answer()

        data = query.data or ""
        if not data.startswith("st:"):
            return
        metadata = self._state_store.get(data[3:])
        if metadata is None:
            await query.edit_message_text("This action has expired (state was reset).")
            return

        user_id = str(query.from_user.id)
        if self._callback is not None:
            fut = self._executor.submit(self._callback, user_id, metadata)
            fut.add_done_callback(self._log_future_exception)

    @staticmethod
    def _log_future_exception(future) -> None:
        try:
            exc = future.exception()
            if exc is not None:
                logger.error("Error in background executor task: %s", exc, exc_info=exc)
        except Exception:
            pass

    def _run(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    @staticmethod
    def _build_keyboard(actions: list[Action]) -> InlineKeyboardMarkup:
        buttons = [
            [InlineKeyboardButton(text=action.label, callback_data=action.id)]
            for action in actions
        ]
        return InlineKeyboardMarkup(buttons)
