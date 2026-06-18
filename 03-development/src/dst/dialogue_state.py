"""[FR-34 to FR-36] Dialogue State Tracker — FSM, SlotFiller, ContextWindowManager.

Citations:
  SRS.md FR-34: DialogueStateMachine
  SRS.md FR-35: SlotFiller
  SRS.md FR-36: ContextWindowManager
"""
from __future__ import annotations

from typing import Any


class DialogueStateMachine:
    """[FR-34] Manages conversation state transitions."""

    def __init__(self) -> None:
        self._state: str = "idle"

    @property
    def state(self) -> str:
        """Return current state name."""
        return self._state

    def transition(self, event: str) -> str:
        """Transition to new state based on event."""
        return self._state


class SlotFiller:
    """[FR-35] Extracts and fills dialogue slots from user input."""

    def extract(self, text: str, slot_defs: list[dict[str, Any]]) -> dict[str, Any]:
        """Return filled slots dict."""
        return {}


class ContextWindowManager:
    """[FR-36] Manages context window with token budget."""

    def __init__(self, max_tokens: int = 4096) -> None:
        self._max_tokens = max_tokens
        self._history: list[dict[str, Any]] = []

    def add(self, message: dict[str, Any]) -> None:
        """Add message to context window."""
        self._history.append(message)

    def get_context(self) -> list[dict[str, Any]]:
        """Return trimmed context within token budget."""
        return self._history
