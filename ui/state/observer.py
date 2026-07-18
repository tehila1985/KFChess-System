from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, DefaultDict, Generic, Protocol, TypeVar

E = TypeVar("E")


@dataclass(frozen=True)
class Subscription:
    """Token returned when a callback subscribes to an event type."""

    event_type: type[object]
    callback: Callable[[object], None]


class Subject(Protocol):
    """Minimal Subject contract used by UI subscribers."""

    def subscribe(self, event_type: type[E], callback: Callable[[E], None]) -> Subscription:
        ...

    def unsubscribe(self, subscription: Subscription) -> None:
        ...

    def publish(self, event: object) -> None:
        ...


class EventBus:
    """Simple in-process event bus for UI state notifications."""

    def __init__(self) -> None:
        self._subscribers: DefaultDict[type[object], list[Callable[[object], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[E], callback: Callable[[E], None]) -> Subscription:
        typed_callback = callback  # keep precise callback type at call site
        self._subscribers[event_type].append(typed_callback)
        return Subscription(event_type=event_type, callback=typed_callback)

    def unsubscribe(self, subscription: Subscription) -> None:
        callbacks = self._subscribers.get(subscription.event_type)
        if not callbacks:
            return
        try:
            callbacks.remove(subscription.callback)
        except ValueError:
            return
        if not callbacks:
            self._subscribers.pop(subscription.event_type, None)

    def publish(self, event: object) -> None:
        for callback in list(self._subscribers.get(type(event), [])):
            callback(event)
