import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from core.infra.logger_config import logger


class JobType(Enum):
    LLM_DYNAMIC = auto()
    WAKEWORD = auto()
    SYSTEM = auto()
    REPLAY = auto()
    CREATE_MACRO = auto()


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    TIMEOUT = "timeout"


@dataclass
class Job:
    type: JobType
    payload: Any
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    payload_text: str | None = None
    status: JobStatus = JobStatus.PENDING
    retries: int = 0
    max_retries: int = 2
    timeout: float | None = 30.0
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None


class JobManager:
    def __init__(self) -> None:
        self.history: deque[Job] = deque(maxlen=50)

    def add_job(self, job: Job) -> None:
        self.history.append(job)
        logger.info(f"Job added to history: {job.id} ({job.type.name})")


# Singleton instance
job_manager = JobManager()
