"""iCal feed fetcher."""
import httpx
import logging
from datetime import datetime
from icalendar import Calendar
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Error during fetch operation."""
    pass


class Fetcher:
    """Fetches iCal feeds from remote URLs."""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.last_fetch_times: Dict[str, datetime] = {}
    
    async def fetch(self, source_name: str, url: str) -> Calendar:
        """Fetch an iCal feed from a URL."""
        logger.info(f"Fetching {source_name} from {url}")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                content = response.content
                
                # Parse calendar
                try:
                    calendar = Calendar.from_ical(content)
                except Exception as e:
                    raise FetchError(f"Failed to parse iCal: {e}")
                
                self.last_fetch_times[source_name] = datetime.now()
                logger.info(f"Successfully fetched {source_name}")
                
                return calendar
                
        except httpx.HTTPError as e:
            raise FetchError(f"HTTP error fetching {url}: {e}")
        except Exception as e:
            raise FetchError(f"Error fetching {url}: {e}")
    
    def get_last_fetch_time(self, source_name: str) -> Optional[datetime]:
        """Get the last fetch time for a source."""
        return self.last_fetch_times.get(source_name)
