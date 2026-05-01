import pytest
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_synthesize():
    """synthesize_speech のモック — 固定WAVバイトを返す"""
    sample_rate = 16000
    num_samples = sample_rate  # 1秒
    data_size = num_samples * 2  # 16-bit mono
    file_size = 36 + data_size
    wav = bytearray(b'RIFF')
    wav += file_size.to_bytes(4, 'little')
    wav += b'WAVEfmt '
    wav += (16).to_bytes(4, 'little')
    wav += (1).to_bytes(2, 'little')   # PCM
    wav += (1).to_bytes(2, 'little')   # mono
    wav += sample_rate.to_bytes(4, 'little')
    wav += (sample_rate * 2).to_bytes(4, 'little')
    wav += (2).to_bytes(2, 'little')
    wav += (16).to_bytes(2, 'little')
    wav += b'data'
    wav += data_size.to_bytes(4, 'little')
    wav += b'\x00' * data_size
    return bytes(wav)


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: run async test via asyncio.run")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    if "asyncio" not in pyfuncitem.keywords:
        return None

    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None

    kwargs = {
        name: pyfuncitem.funcargs[name]
        for name in pyfuncitem._fixtureinfo.argnames
    }
    asyncio.run(test_func(**kwargs))
    return True
