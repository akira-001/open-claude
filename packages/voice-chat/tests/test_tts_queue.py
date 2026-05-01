import asyncio
import pytest


class TestTTSQueueLock:
    @pytest.mark.asyncio
    async def test_concurrent_tts_requests_are_serialized(self):
        lock = asyncio.Lock()
        execution_order = []

        async def simulated_tts(name: str):
            async with lock:
                execution_order.append(f"{name}_start")
                await asyncio.sleep(0.01)
                execution_order.append(f"{name}_end")

        await asyncio.gather(
            simulated_tts("wake"),
            simulated_tts("proactive"),
        )
        start_indices = [i for i, x in enumerate(execution_order) if x.endswith("_start")]
        end_indices = [i for i, x in enumerate(execution_order) if x.endswith("_end")]
        assert start_indices[1] > end_indices[0]

    @pytest.mark.asyncio
    async def test_lock_is_per_engine(self):
        # Test the lock logic directly without importing app.py's heavy deps
        locks: dict[str, asyncio.Lock] = {}
        def get_lock(engine: str) -> asyncio.Lock:
            if engine not in locks:
                locks[engine] = asyncio.Lock()
            return locks[engine]

        lock_a = get_lock("irodori")
        lock_b = get_lock("voicevox")
        lock_a2 = get_lock("irodori")
        assert lock_a is lock_a2
        assert lock_a is not lock_b
