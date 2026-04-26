# Design Spec: Core Job Queue System

## 1. Goal
Implement a typed Job system and a JobManager to track job history. This provides the foundation for a structured job queue with retries, status tracking, and history auditing.

## 2. Architecture

### 2.1 Enums
- `JobType`: Defines the source or category of the job.
    - `LLM_DYNAMIC`
    - `WAKEWORD`
    - `SYSTEM`
- `JobStatus`: Tracks the current state of a job.
    - `PENDING`
    - `RUNNING`
    - `COMPLETED`
    - `FAILED`
    - `RETRYING`
    - `TIMEOUT`

### 2.2 Job Data Model
A `Job` is a dataclass containing:
- `type: JobType`
- `payload: Any`
- `id: str` (UUID4 string, auto-generated)
- `status: JobStatus` (Default: `PENDING`)
- `retries: int` (Initial: 0)
- `max_retries: int` (Default: 2)
- `timeout: Optional[float]` (Default: 30.0)
- `created_at: float` (Timestamp, auto-generated)
- `finished_at: Optional[float]` (Default: None)
- `error: Optional[str]` (Default: None)

### 2.3 JobManager
A class to manage the job history.
- `history`: A `collections.deque` with `maxlen=50` to store the last 50 jobs.
- `job_manager`: A singleton instance of `JobManager`.

## 3. Implementation Details
- Use `uuid` for ID generation.
- Use `time.time()` for timestamps.
- Use `core.logger_config` for logging.

## 4. Verification
- Verify `Job` instantiation with default values.
- Verify `JobManager` history limit.
- Verify singleton export.
