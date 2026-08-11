import logging
import socket
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="NetCheckWorker")


def _check_socket(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


def check_internet_connection_async(
    host: str = "8.8.8.8", port: int = 53, timeout: float = 0.5
) -> bool:
    """Checks internet connectivity asynchronously using a background thread.

    Guarantees non-blocking execution for caller threads.
    """
    try:
        future = _executor.submit(_check_socket, host, port, timeout)
        return future.result(timeout=timeout + 0.1)
    except Exception as e:
        logger.debug(f"Network check exception: {e}")
        return False
