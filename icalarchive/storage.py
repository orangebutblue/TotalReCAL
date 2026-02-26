"""Storage management for events and hidden events."""
import json
from pathlib import Path
from typing import Set, Dict, List, Optional
from datetime import datetime
from icalendar import Calendar, Event
import threading


class HiddenEventsManager:
    """Manages manually hidden events via hidden.json."""
    
    def __init__(self, data_dir: Path):
        self.hidden_file = data_dir / "hidden.json"
        self.hidden_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        
    def load(self) -> Set[str]:
        """Load hidden event UIDs."""
        if not self.hidden_file.exists():
            return set()
        
        with open(self.hidden_file, 'r') as f:
            data = json.load(f)
        return set(data.get('hidden', []))
    
    def save(self, hidden: Set[str]) -> None:
        """Save hidden event UIDs."""
        with self._lock:
            with open(self.hidden_file, 'w') as f:
                json.dump({'hidden': sorted(list(hidden))}, f, indent=2)
    
    def hide(self, uid: str) -> None:
        """Mark an event as hidden."""
        hidden = self.load()
        hidden.add(uid)
        self.save(hidden)
    
    def unhide(self, uid: str) -> None:
        """Unmark an event as hidden."""
        hidden = self.load()
        hidden.discard(uid)
        self.save(hidden)
    
    def is_hidden(self, uid: str) -> bool:
        """Check if an event is hidden."""
        return uid in self.load()


class EventStore:
    """Manages append-only event storage per source."""
    
    def __init__(self, data_dir: Path):
        self.store_dir = data_dir / "store"
        self.sources_dir = data_dir / "sources"
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
    
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
            with open(path, 'rb') as f:
                cal = Calendar.from_ical(f.read())
            
            events = {}
            for component in cal.walk('VEVENT'):
                uid = component.get('UID')
                if uid:
                    prefixed_uid = f"{source_name}::{uid}"
                    events[prefixed_uid] = component
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
        
        # Extract events from new calendar
        new_events = {}
        for component in new_calendar.walk('VEVENT'):
            uid = component.get('UID')
            if uid:
                prefixed_uid = f"{source_name}::{uid}"
                if prefixed_uid not in existing:
                    new_events[prefixed_uid] = component
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
