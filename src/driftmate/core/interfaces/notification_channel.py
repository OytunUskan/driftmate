from collections.abc import Callable
from typing import Protocol

from driftmate.core.models.notification import Action, MessageRef


class NotificationChannel(Protocol):
    def sendMessage(self, text: str, actions: list[Action]) -> MessageRef: ...

    def updateMessage(
        self,
        ref: MessageRef,
        text: str,
        actions: list[Action] | None = None,
    ) -> None: ...

    def onAction(self, callback: Callable[[str, dict], None]) -> None: ...
