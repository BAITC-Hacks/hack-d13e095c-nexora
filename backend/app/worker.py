import asyncio
import contextlib
import logging
import signal

from app.config import get_settings
from app.db.session import create_database
from app.services.job_service import JobService
from app.services.meeting_processor import MeetingProcessor
from app.utils.errors import LeaseLost, PipelineError

logger = logging.getLogger("meeting_worker")


async def run_job(processor: MeetingProcessor, jobs: JobService, job_id, owner):
    async def heartbeat():
        while True:
            await asyncio.sleep(jobs.settings.job_lease_seconds / 3)
            if not await jobs.heartbeat(job_id, owner):
                return

    pulse = asyncio.create_task(heartbeat())
    try:
        await processor.process_meeting(job_id, owner)
        logger.info("job=%s result=succeeded", job_id)
    except LeaseLost:
        logger.warning("job=%s result=lease_lost", job_id)
    except Exception as exc:
        code = exc.code if isinstance(exc, PipelineError) else "PROCESSING_FAILED"
        logger.error("job=%s error_code=%s error_type=%s", job_id, code, type(exc).__name__)
        with contextlib.suppress(LeaseLost):
            await jobs.fail(job_id, owner, code)
    finally:
        pulse.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await pulse


async def main():
    settings = get_settings()
    engine, factory = create_database(settings)
    jobs, processor = JobService(factory, settings), MeetingProcessor(factory, settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    try:
        while not stop.is_set():
            claimed = await jobs.claim()
            if claimed:
                await run_job(processor, jobs, *claimed)
            else:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), settings.worker_poll_seconds)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
