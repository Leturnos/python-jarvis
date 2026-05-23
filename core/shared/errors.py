class JarvisError(Exception):
    """Base exception for all Jarvis-related errors."""
    pass

class TechnicalError(JarvisError):
    """
    Exception raised for transient failures that SHOULD trigger a retry.
    Examples: STT timeout, API issues, network failures.
    """
    pass

class BusinessError(JarvisError):
    """
    Exception raised for logical failures that SHOULD NOT trigger a retry.
    Examples: Empty history, Policy blocked, unrecognized command.
    """
    pass
