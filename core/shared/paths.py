import sys
from pathlib import Path


def get_app_root() -> Path:
    """Returns the base application directory whether running from source or frozen binary."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.absolute()
    return Path(__file__).parent.parent.parent.absolute()
