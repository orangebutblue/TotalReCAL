"""Storage management for events and hidden events."""
import json
from pathlib import Path
from typing import Set, Dict, List, Optional
from datetime import datetime
from icalendar import Calendar, Event
import threading


class EventStore:
    """Manages append-only event storage per source."""
    
    def __init__(self, data_dir: Path):
        self.store_dir = data_dir / "store"
        self.sources_dir = data_dir / "sources"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        
        # Performance Cache
        # Map source_name -> (file_mtime_float, dict_of_events)
        self._cache: Dict[str, tuple[float, Dict[str, Event]]] = {}
    
    def get_store_path(self, source_name: str) -> Path:
        """Get path to store file for a source."""
        return self.store_dir / f"{source_name}.ics"
    
    def get_source_path(self, source_name: str) -> Path:
        """Get path to latest source snapshot."""
        return self.sources_dir / f"{source_name}.ics"
    
    def save_source_snapshot(self, source_name: str, content: bytes) -> None:
        """Save the latest raw fetched snapshot."""
        path = self.get_source_path(source_name)
        with self._lock:
            with open(path, 'wb') as f:
                f.write(content)
    
    def load_store(self, source_name: str) -> Dict[str, Event]:
        """Load all events from store for a source, keyed by prefixed UID."""
        path = self.get_store_path(source_name)
        if not path.exists():
            return {}
            
        try:
            current_mtime = path.stat().st_mtime
            
            # Check cache
            if source_name in self._cache:
                cached_mtime, cached_events = self._cache[source_name]
                if cached_mtime == current_mtime:
                    return cached_events
                    
            with open(path, 'rb') as f:
                cal = Calendar.from_ical(f.read())
            
            events = {}
            for component in cal.walk('VEVENT'):
                uid = component.get('UID')
                if uid:
                    prefixed_uid = f"{source_name}::{uid}"
                    events[prefixed_uid] = component
            
            # Update cache
            self._cache[source_name] = (current_mtime, events)
            return events
        except Exception:
            return {}
    
    def load_all_events(self) -> Dict[str, Event]:
        """Load all events from all sources."""
        all_events = {}
        for store_file in self.store_dir.glob("*.ics"):
            source_name = store_file.stem
            events = self.load_store(source_name)
            all_events.update(events)
        return all_events
    
    def merge_events(self, source_name: str, new_calendar: Calendar) -> int:
        """Merge new events into store. Returns count of new events added."""
        existing = self.load_store(source_name)
        new_count = 0
        
        def get_prop_val(comp, prop):
            p = comp.get(prop)
            return p.to_ical() if hasattr(p, 'to_ical') else p
        
        # Build signatures for existing events to quickly find duplicates
        existing_signatures = set()
        for evt in existing.values():
            sig = (
                get_prop_val(evt, 'SUMMARY'),
                get_prop_val(evt, 'DTSTART'),
                get_prop_val(evt, 'DTEND'),
                get_prop_val(evt, 'LOCATION')
            )
            existing_signatures.add(sig)
        
        # Extract events from new calendar
        new_events = {}
        for component in new_calendar.walk('VEVENT'):
            uid = component.get('UID')
            if not uid:
                continue
                
            sig = (
                get_prop_val(component, 'SUMMARY'),
                get_prop_val(component, 'DTSTART'),
                get_prop_val(component, 'DTEND'),
                get_prop_val(component, 'LOCATION')
            )
            
            prefixed_uid = f"{source_name}::{uid}"
            
            if sig not in existing_signatures and prefixed_uid not in existing and prefixed_uid not in new_events:
                new_events[prefixed_uid] = component
                existing_signatures.add(sig)
                new_count += 1
        
        if new_count == 0:
            return 0
        
        # Append new events to store
        with self._lock:
            path = self.get_store_path(source_name)
            
            # Create or load existing calendar
            if path.exists():
                with open(path, 'rb') as f:
                    store_cal = Calendar.from_ical(f.read())
            else:
                store_cal = Calendar()
                store_cal.add('prodid', '-//ICalArchive//EN')
                store_cal.add('version', '2.0')
            
            # Add new events
            for event in new_events.values():
                store_cal.add_component(event)
            
            # Save
            with open(path, 'wb') as f:
                f.write(store_cal.to_ical())
                
            # Invalidate cache so it recalculates cleanly next time,
            # or pre-fill it here if needed. Next load_store will cache it.
            if source_name in self._cache:
                del self._cache[source_name]
        
        return new_count
    
    def get_source_stats(self, source_name: str) -> Dict:
        """Get statistics for a source."""
        events = self.load_store(source_name)
        snapshot_path = self.get_source_path(source_name)
        
        last_fetch = None
        if snapshot_path.exists():
            # Use UTC-aware datetime for consistency
            from datetime import timezone
            timestamp = snapshot_path.stat().st_mtime
            last_fetch = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        
        return {
            'event_count': len(events),
            'last_fetch': last_fetch,
        }

    def deduplicate_store(self, source_name: str) -> int:
        """Remove duplicate events from an existing store. Returns number of removed duplicates."""
        existing_events = self.load_store(source_name)
        if not existing_events:
            return 0
            
        def get_prop_val(comp, prop):
            p = comp.get(prop)
            return p.to_ical() if hasattr(p, 'to_ical') else p
            
        unique_signatures = set()
        deduplicated_events = {}
        removed_count = 0
        
        for uid, component in existing_events.items():
            sig = (
                get_prop_val(component, 'SUMMARY'),
                get_prop_val(component, 'DTSTART'),
                get_prop_val(component, 'DTEND'),
                get_prop_val(component, 'LOCATION')
            )
            
            if sig not in unique_signatures:
                unique_signatures.add(sig)
                deduplicated_events[uid] = component
            else:
                removed_count += 1
                
        if removed_count == 0:
            return 0
            
        # Resave deduplicated events
        with self._lock:
            path = self.get_store_path(source_name)
            
            store_cal = Calendar()
            store_cal.add('prodid', '-//ICalArchive//EN')
            store_cal.add('version', '2.0')
            
            for event in deduplicated_events.values():
                store_cal.add_component(event)
                
            with open(path, 'wb') as f:
                f.write(store_cal.to_ical())
                
            if source_name in self._cache:
                del self._cache[source_name]
                
        return removed_count
