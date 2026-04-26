from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Optional
import uuid
import time
from collections import deque
from core.logger_config import logger

class JobType(Enum):
    LLM_DYNAMIC = auto()
    WAKEWORD = auto()
    SYSTEM = auto()

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
    status: JobStatus = JobStatus.PENDING
    retries: int = 0
    max_retries: int = 2
    timeout: Optional[float] = 30.0
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    error: Optional[str] = None

class JobManager:
    def __init__(self):
        self.history = deque(maxlen=50)

    def add_job(self, job: Job):
        self.history.append(job)
        logger.info(f"Job added to history: {job.id} ({job.type.name})")

# Singleton instance
job_manager = JobManager()
