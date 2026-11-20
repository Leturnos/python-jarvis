import time

import pytest

from core.infra import network
from core.infra.network import check_internet_connection_async, reset_connectivity_cache


@pytest.fixture(autouse=True)
def _reset_network_cache():
    reset_connectivity_cache()
    yield
    reset_connectivity_cache()


def test_check_internet_connection_async_returns_bool_without_blocking():
    start = time.time()
    # Fast check with small timeout
    is_online = check_internet_connection_async(host="127.0.0.1", port=1, timeout=0.2)
    elapsed = time.time() - start
    assert isinstance(is_online, bool)
    assert is_online is False
    assert elapsed < 0.5


def test_check_internet_connection_fallback_to_second_endpoint(monkeypatch):
    from core.infra import network

    attempts = []

    def mock_check_socket(host: str, port: int, timeout: float) -> bool:
        attempts.append((host, port))
        # First endpoint (8.8.8.8:53) fails (e.g. DNS blocked), second succeeds
        if port == 53:
            return False
        return True

    monkeypatch.setattr(network, "_check_socket", mock_check_socket)

    is_online = network.check_internet_connection_async(timeout=0.5)
    assert is_online is True
    # Verify that multiple endpoints were attempted until success
    assert len(attempts) >= 2


def test_check_internet_connection_all_fail(monkeypatch):
    from core.infra import network

    def mock_check_socket(host: str, port: int, timeout: float) -> bool:
        return False

    monkeypatch.setattr(network, "_check_socket", mock_check_socket)

    is_online = network.check_internet_connection_async(timeout=0.5)
    assert is_online is False


def test_check_internet_connection_caches_positive_result_only(monkeypatch):
    calls = 0

    def mock_check_socket(host: str, port: int, timeout: float) -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(network, "_check_socket", mock_check_socket)

    assert network.check_internet_connection_async(timeout=0.5) is True
    assert calls == 1

    # Second call within TTL reuses cached positive result without opening sockets
    assert network.check_internet_connection_async(timeout=0.5) is True
    assert calls == 1

    # Negative results must never be cached so recovery is immediate
    reset_connectivity_cache()
    monkeypatch.setattr(network, "_check_socket", lambda h, p, t: False)
    assert network.check_internet_connection_async(timeout=0.5) is False

    monkeypatch.setattr(network, "_check_socket", mock_check_socket)
    assert network.check_internet_connection_async(timeout=0.5) is True
    assert calls == 2
