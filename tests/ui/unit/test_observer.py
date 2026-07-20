from ui.state.observer import EventBus


class SampleEvent:
    def __init__(self, value: int) -> None:
        self.value = value


def test_publish_calls_subscriber() -> None:
    """Verify publish calls subscriber."""
    bus = EventBus()
    seen: list[int] = []

    bus.subscribe(SampleEvent, lambda event: seen.append(event.value))
    bus.publish(SampleEvent(7))

    assert seen == [7]


def test_unsubscribe_stops_notifications() -> None:
    """Verify unsubscribe stops notifications."""
    bus = EventBus()
    seen: list[int] = []

    subscription = bus.subscribe(SampleEvent, lambda event: seen.append(event.value))
    bus.unsubscribe(subscription)
    bus.publish(SampleEvent(9))

    assert seen == []


def test_multiple_subscribers_receive_same_event() -> None:
    """Verify multiple subscribers receive same event."""
    bus = EventBus()
    seen_a: list[int] = []
    seen_b: list[int] = []

    bus.subscribe(SampleEvent, lambda event: seen_a.append(event.value))
    bus.subscribe(SampleEvent, lambda event: seen_b.append(event.value))

    bus.publish(SampleEvent(3))

    assert seen_a == [3]
    assert seen_b == [3]
