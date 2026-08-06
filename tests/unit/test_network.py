import time
from core.infra.network import check_internet_connection_async


def test_check_internet_connection_async_returns_bool_without_blocking():
    start = time.time()
    # Fast check with small timeout
    is_online = check_internet_connection_async(host="127.0.0.1", port=1, timeout=0.2)
    elapsed = time.time() - start
    assert isinstance(is_online, bool)
    assert is_online is False
    assert elapsed < 0.5
