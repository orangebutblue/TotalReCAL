import httpx
from icalendar import Calendar
from datetime import datetime
from typing import List
from app.models import Source, StoredEvent
from app.storage import Storage


class FeedFetcher:
    """Service to fetch and parse remote iCal feeds."""
    
    def __init__(self, storage: Storage):
        self.storage = storage
    
    async def fetch_source(self, source: Source) -> List[StoredEvent]:
        """Fetch and parse a single iCal source."""
        events = []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(str(source.url))
                response.raise_for_status()
                
                # Parse iCal data
                cal = Calendar.from_ical(response.content)
                
                for component in cal.walk():
                    if component.name == "VEVENT":
                        event = self._parse_event(component, source.id)
                        if event:
                            events.append(event)
                
                # Update source last_fetch time
                source.last_fetch = datetime.utcnow()
                self.storage.update_source(source.id, source)
                
        except Exception as e:
            print(f"Error fetching source {source.id} ({source.url}): {e}")
        
        return events
    
    def _parse_event(self, component, source_id: str) -> StoredEvent | None:
        """Parse a single VEVENT component into a StoredEvent."""
        try:
            uid = str(component.get('uid', ''))
            if not uid:
                return None
            
            # Get existing event if any
            existing_event = self.storage.get_event(uid)
            
            # Extract event data
            summary = str(component.get('summary', '')) if component.get('summary') else None
            description = str(component.get('description', '')) if component.get('description') else None
            
            # Parse categories
            categories = []
            if component.get('categories'):
                cat_val = component.get('categories')
                if hasattr(cat_val, 'cats'):  # icalendar Categories object
                    categories = cat_val.cats
                elif isinstance(cat_val, list):
                    categories = cat_val
                elif isinstance(cat_val, str):
                    categories = [cat_val]
            
            # Get date/time strings
            dtstart = None
            if component.get('dtstart'):
                dtstart = component.get('dtstart').to_ical().decode('utf-8')
            
            dtend = None
            if component.get('dtend'):
                dtend = component.get('dtend').to_ical().decode('utf-8')
            
            # Raw iCal representation
            raw_ical = component.to_ical().decode('utf-8')
            
            # Create or update event
            if existing_event:
                # Update existing event but preserve first_seen and manually_hidden
                event = StoredEvent(
                    uid=uid,
                    source_id=source_id,
                    raw_ical=raw_ical,
                    summary=summary,
                    description=description,
                    categories=categories,
                    dtstart=dtstart,
                    dtend=dtend,
                    first_seen=existing_event.first_seen,
                    last_updated=datetime.utcnow(),
                    manually_hidden=existing_event.manually_hidden
                )
            else:
                event = StoredEvent(
                    uid=uid,
                    source_id=source_id,
                    raw_ical=raw_ical,
                    summary=summary,
                    description=description,
                    categories=categories,
                    dtstart=dtstart,
                    dtend=dtend
                )
            
            return event
            
        except Exception as e:
            print(f"Error parsing event: {e}")
            return None
    
    async def fetch_all_sources(self):
        """Fetch all enabled sources and store events."""
        sources = self.storage.get_all_sources()
        
        for source_id, source in sources.items():
            if source.enabled:
                events = await self.fetch_source(source)
                
                # Store/update all events
                for event in events:
                    self.storage.add_or_update_event(event)
                
                print(f"Fetched {len(events)} events from source {source.name}")
