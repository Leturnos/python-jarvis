import logging

def setup_logger():
    """Configures the logging system for console and file output."""
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        handlers=[
            logging.FileHandler("jarvis.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("Jarvis")

logger = setup_logger()
