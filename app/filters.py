import re
from typing import List, Set
from datetime import datetime
from dateutil import parser as date_parser
from app.models import StoredEvent, Output, FilterRule, AutoHideRule
from app.storage import Storage


class FilterService:
    """Service to filter events based on output configurations."""
    
    def __init__(self, storage: Storage):
        self.storage = storage
    
    def filter_events(self, output: Output) -> List[StoredEvent]:
        """Filter events based on output configuration."""
        all_events = list(self.storage.get_all_events().values())
        
        # Start with all events
        filtered_events = all_events[:]
        
        # Apply filter rules
        if output.filter_rules:
            filtered_events = self._apply_filter_rules(filtered_events, output.filter_rules)
        
        # Apply manual hiding
        filtered_events = [e for e in filtered_events if not e.manually_hidden]
        
        # Apply auto-hide rules
        if output.auto_hide_rules:
            filtered_events = self._apply_auto_hide_rules(filtered_events, output.auto_hide_rules)
        
        return filtered_events
    
    def _apply_filter_rules(self, events: List[StoredEvent], rules: List[FilterRule]) -> List[StoredEvent]:
        """Apply filter rules to events."""
        filtered = []
        
        for event in events:
            include = True
            
            for rule in rules:
                if rule.type == "category":
                    matches = rule.pattern in event.categories
                elif rule.type == "regex_summary":
                    matches = bool(re.search(rule.pattern, event.summary or "", re.IGNORECASE))
                elif rule.type == "regex_description":
                    matches = bool(re.search(rule.pattern, event.description or "", re.IGNORECASE))
                else:
                    matches = False
                
                if rule.exclude and matches:
                    include = False
                    break
                elif not rule.exclude and not matches:
                    # For include rules, at least one must match
                    # This is simplified - you might want different logic
                    pass
            
            if include:
                filtered.append(event)
        
        return filtered
    
    def _apply_auto_hide_rules(self, events: List[StoredEvent], rule_ids: List[str]) -> List[StoredEvent]:
        """Apply auto-hide rules based on time overlap."""
        hidden_uids: Set[str] = set()
        
        for rule_id in rule_ids:
            rule = self.storage.get_auto_hide_rule(rule_id)
            if not rule or not rule.enabled:
                continue
            
            # Find events matching each pattern
            pattern1_events = []
            pattern2_events = []
            
            for event in events:
                if re.search(rule.pattern1, event.summary or "", re.IGNORECASE):
                    pattern1_events.append(event)
                if re.search(rule.pattern2, event.summary or "", re.IGNORECASE):
                    pattern2_events.append(event)
            
            # Check for time overlaps
            for event1 in pattern1_events:
                for event2 in pattern2_events:
                    if event1.uid == event2.uid:
                        continue
                    
                    if self._events_overlap(event1, event2):
                        # Hide the specified pattern
                        if rule.hide_pattern == "1":
                            hidden_uids.add(event1.uid)
                        elif rule.hide_pattern == "2":
                            hidden_uids.add(event2.uid)
        
        # Filter out hidden events
        return [e for e in events if e.uid not in hidden_uids]
    
    def _events_overlap(self, event1: StoredEvent, event2: StoredEvent) -> bool:
        """Check if two events overlap in time."""
        try:
            if not event1.dtstart or not event2.dtstart:
                return False
            
            # Parse dates
            start1 = date_parser.parse(event1.dtstart)
            end1 = date_parser.parse(event1.dtend) if event1.dtend else start1
            start2 = date_parser.parse(event2.dtstart)
            end2 = date_parser.parse(event2.dtend) if event2.dtend else start2
            
            # Check overlap: events overlap if start1 < end2 and start2 < end1
            return start1 < end2 and start2 < end1
            
        except Exception as e:
            print(f"Error checking overlap: {e}")
            return False
