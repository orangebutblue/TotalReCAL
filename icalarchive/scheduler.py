"""Scheduler for periodic feed fetching."""
import logging
from typing import Dict, Callable, Awaitable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from .config import SourceConfig

logger = logging.getLogger(__name__)


class FetchScheduler:
    """Manages scheduled fetching of iCal sources."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.job_ids: Dict[str, str] = {}
    
    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")
    
    def shutdown(self):
        """Shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
    
    def schedule_source(
        self,
        source_name: str,
        config: SourceConfig,
        fetch_func: Callable[[str], Awaitable[None]]
    ):
        """Schedule a source for periodic fetching."""
        # Remove existing job if any
        self.unschedule_source(source_name)
        
        if not config.enabled:
            logger.info(f"Source {source_name} is disabled, not scheduling")
            return
        
        # Create new job
        job_id = f"fetch_{source_name}"
        trigger = IntervalTrigger(minutes=config.fetch_interval_minutes)
        
        self.scheduler.add_job(
            fetch_func,
            trigger=trigger,
            args=[source_name],
            id=job_id,
            replace_existing=True,
            max_instances=1,
        )
        
        self.job_ids[source_name] = job_id
        logger.info(
            f"Scheduled {source_name} to fetch every {config.fetch_interval_minutes} minutes"
        )
    
    def unschedule_source(self, source_name: str):
        """Remove scheduled job for a source."""
        job_id = self.job_ids.get(source_name)
        if job_id:
            try:
                self.scheduler.remove_job(job_id)
                del self.job_ids[source_name]
                logger.info(f"Unscheduled {source_name}")
            except Exception as e:
                logger.warning(f"Failed to unschedule {source_name}: {e}")
    
    def reschedule_source(
        self,
        source_name: str,
        config: SourceConfig,
        fetch_func: Callable[[str], Awaitable[None]]
    ):
        """Reschedule a source with updated interval."""
        self.schedule_source(source_name, config, fetch_func)
    
    def get_next_run_time(self, source_name: str):
        """Get the next scheduled run time for a source."""
        job_id = self.job_ids.get(source_name)
        if job_id:
            job = self.scheduler.get_job(job_id)
            if job:
                return job.next_run_time
        return None
