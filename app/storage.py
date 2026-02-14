import json
import os
from typing import Dict
from pathlib import Path
from app.models import AppState, Source, StoredEvent, Output, AutoHideRule


class Storage:
    """Flat file storage manager using JSON."""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "state.json"
        self.state = self._load_state()
    
    def _load_state(self) -> AppState:
        """Load application state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                return AppState(**data)
            except Exception as e:
                print(f"Error loading state: {e}")
                return AppState()
        return AppState()
    
    def _save_state(self):
        """Save application state to file."""
        with open(self.state_file, 'w') as f:
            json.dump(self.state.model_dump(mode='json'), f, indent=2, default=str)
    
    # Source operations
    def add_source(self, source: Source):
        self.state.sources[source.id] = source
        self._save_state()
    
    def get_source(self, source_id: str) -> Source | None:
        return self.state.sources.get(source_id)
    
    def get_all_sources(self) -> Dict[str, Source]:
        return self.state.sources
    
    def update_source(self, source_id: str, source: Source):
        if source_id in self.state.sources:
            self.state.sources[source_id] = source
            self._save_state()
    
    def delete_source(self, source_id: str):
        if source_id in self.state.sources:
            del self.state.sources[source_id]
            self._save_state()
    
    # Event operations
    def add_or_update_event(self, event: StoredEvent):
        """Add or update an event (accumulates forever by UID)."""
        self.state.events[event.uid] = event
        self._save_state()
    
    def get_event(self, uid: str) -> StoredEvent | None:
        return self.state.events.get(uid)
    
    def get_all_events(self) -> Dict[str, StoredEvent]:
        return self.state.events
    
    def update_event_hidden_status(self, uid: str, hidden: bool):
        if uid in self.state.events:
            self.state.events[uid].manually_hidden = hidden
            self._save_state()
    
    # Output operations
    def add_output(self, output: Output):
        self.state.outputs[output.id] = output
        self._save_state()
    
    def get_output(self, output_id: str) -> Output | None:
        return self.state.outputs.get(output_id)
    
    def get_all_outputs(self) -> Dict[str, Output]:
        return self.state.outputs
    
    def update_output(self, output_id: str, output: Output):
        if output_id in self.state.outputs:
            self.state.outputs[output_id] = output
            self._save_state()
    
    def delete_output(self, output_id: str):
        if output_id in self.state.outputs:
            del self.state.outputs[output_id]
            self._save_state()
    
    # Auto-hide rule operations
    def add_auto_hide_rule(self, rule: AutoHideRule):
        self.state.auto_hide_rules[rule.id] = rule
        self._save_state()
    
    def get_auto_hide_rule(self, rule_id: str) -> AutoHideRule | None:
        return self.state.auto_hide_rules.get(rule_id)
    
    def get_all_auto_hide_rules(self) -> Dict[str, AutoHideRule]:
        return self.state.auto_hide_rules
    
    def update_auto_hide_rule(self, rule_id: str, rule: AutoHideRule):
        if rule_id in self.state.auto_hide_rules:
            self.state.auto_hide_rules[rule_id] = rule
            self._save_state()
    
    def delete_auto_hide_rule(self, rule_id: str):
        if rule_id in self.state.auto_hide_rules:
            del self.state.auto_hide_rules[rule_id]
            self._save_state()
