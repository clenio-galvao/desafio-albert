import pytest

from chatbot.application.stream_gate import ConcurrentStreamGate, UnlimitedStreamGate


def test_stream_gate_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        ConcurrentStreamGate(0)


async def test_unlimited_stream_gate_never_blocks() -> None:
    gate = UnlimitedStreamGate()

    assert await gate.try_acquire() is True
    assert await gate.try_acquire() is True
    await gate.release()


async def test_concurrent_stream_gate_rejects_when_at_limit() -> None:
    gate = ConcurrentStreamGate(1)

    assert await gate.try_acquire() is True
    assert await gate.try_acquire() is False


async def test_concurrent_stream_gate_allows_acquire_after_release() -> None:
    gate = ConcurrentStreamGate(1)
    await gate.try_acquire()

    await gate.release()

    assert await gate.try_acquire() is True


async def test_concurrent_stream_gate_release_is_idempotent_at_zero() -> None:
    gate = ConcurrentStreamGate(1)
    await gate.try_acquire()
    await gate.release()

    await gate.release()

    assert gate.active == 0
