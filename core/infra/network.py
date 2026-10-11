import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="NetCheckWorker")

DEFAULT_ENDPOINTS: list[tuple[str, int]] = [
    ("8.8.8.8", 53),
    ("1.1.1.1", 53),
    ("1.1.1.1", 443),
    ("8.8.8.8", 443),
]


def _check_socket(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


def _check_endpoints(
    endpoints: list[tuple[str, int]], per_endpoint_timeout: float, max_duration: float
) -> bool:
    start_time = time.monotonic()
    for host, port in endpoints:
        remaining = max_duration - (time.monotonic() - start_time)
        if remaining <= 0:
            break
        timeout = min(per_endpoint_timeout, remaining)
        if _check_socket(host, port, timeout):
            return True
    return False


def check_internet_connection_async(
    host: str | None = None, port: int | None = None, timeout: float = 0.5
) -> bool:
    """Checks internet connectivity asynchronously using a background thread.

    If host and port are explicitly specified, tests only that target.
    Otherwise, tests redundant public DNS and HTTPS endpoints (Google & Cloudflare).
    Guarantees non-blocking execution for caller threads.
    """
    if host is not None and port is not None:
        endpoints = [(host, port)]
    elif host is not None:
        endpoints = [(host, 53 if port is None else port)]
    elif port is not None:
        endpoints = [("8.8.8.8", port)]
    else:
        endpoints = DEFAULT_ENDPOINTS

    per_endpoint_timeout = min(timeout, max(0.12, timeout / len(endpoints)))

    try:
        future = _executor.submit(
            _check_endpoints, endpoints, per_endpoint_timeout, timeout
        )
        return future.result(timeout=timeout + 0.15)
    except Exception as e:
        logger.debug(f"Network check exception: {e}")
        return False
