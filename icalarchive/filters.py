"""Event filtering system."""
import re
from typing import List, Set, Optional, Dict
from datetime import datetime
from icalendar import Event
from .config import OutputConfig, RuleConfig


class FilterEngine:
    """Filters events based on rules and output configurations."""
    
    def __init__(self, hidden_uids: Set[str], rules: List[RuleConfig]):
        self.hidden_uids = hidden_uids
        self.rules = rules
    
    def is_hidden_by_rules(self, event: Event, all_events: Dict[str, Event]) -> bool:
        """Check if event should be hidden by auto-rules."""
        for rule in self.rules:
            if rule.rule_type in ['category_exclude', 'summary_regex', 'description_regex']:
                if self.matches_rule(rule, event, all_events):
                    return True
        return False
    
    def matches_rule(self, rule: RuleConfig, event: Event, all_events: Dict[str, Event]) -> bool:
        """Evaluate if an event matches the condition of a rule natively."""
        if rule.rule_type == 'category_exclude':
            categories = self._get_categories(event)
            exclude = rule.params.get('categories', [])
            return any(cat in exclude for cat in categories)
        
        elif rule.rule_type in ['summary_regex', 'add_to_series']:
            pattern = rule.params.get('pattern', '')
            summary = str(event.get('SUMMARY', ''))
            return bool(re.search(pattern, summary, re.IGNORECASE))
        
        elif rule.rule_type == 'description_regex':
            pattern = rule.params.get('pattern', '')
            description = str(event.get('DESCRIPTION', ''))
            return bool(re.search(pattern, description, re.IGNORECASE))
        
        # overlap_conflict is more complex and skipped for now
        return False
    
    def filter_for_output(self, events: Dict[str, Event], output_config: OutputConfig) -> Dict[str, Event]:
        """Filter events for a specific output feed."""
        filtered = {}
        
        for uid, event in events.items():
            # Skip manually hidden
            if uid in self.hidden_uids:
                continue
            
            # Skip if hidden by rules
            if self.is_hidden_by_rules(event, events):
                continue
            
            # Apply output filters
            if not self._matches_output_filters(uid, event, output_config):
                continue
            
            filtered[uid] = event
        
        return filtered
    
    def _matches_output_filters(self, uid: str, event: Event, config: OutputConfig) -> bool:
        """Check if event matches output filter criteria."""
        # Include sources filter
        if config.include_sources:
            source = uid.split('::', 1)[0]
            if source not in config.include_sources:
                return False
        
        # Category filters
        categories = self._get_categories(event)
        
        if config.filter_by_category:
            if not any(cat in config.filter_by_category for cat in categories):
                return False
        
        if config.exclude_category:
            if any(cat in config.exclude_category for cat in categories):
                return False
        
        # Summary regex filters
        summary = str(event.get('SUMMARY', ''))
        
        if config.include_summary_regex:
            if not re.search(config.include_summary_regex, summary, re.IGNORECASE):
                return False
        
        if config.exclude_summary_regex:
            if re.search(config.exclude_summary_regex, summary, re.IGNORECASE):
                return False
        
        return True
    
    def _get_categories(self, event: Event) -> List[str]:
        """Extract categories from an event."""
        categories = event.get('CATEGORIES', [])
        if isinstance(categories, str):
            return [cat.strip() for cat in categories.split(',')]
        elif hasattr(categories, 'cats'):
            return categories.cats
        elif isinstance(categories, list):
            return categories
        return []
