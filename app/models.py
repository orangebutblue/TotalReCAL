from typing import Optional, Dict, List, Any
from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime


class Source(BaseModel):
    """Represents a remote iCal feed source."""
    id: str
    name: str
    url: HttpUrl
    enabled: bool = True
    last_fetch: Optional[datetime] = None
    fetch_interval_minutes: int = 60


class StoredEvent(BaseModel):
    """Represents an accumulated event (never deleted)."""
    uid: str
    source_id: str
    raw_ical: str  # Original iCal event string
    summary: Optional[str] = None
    description: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    dtstart: Optional[str] = None
    dtend: Optional[str] = None
    first_seen: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    manually_hidden: bool = False


class FilterRule(BaseModel):
    """Represents a filter rule for output feeds."""
    type: str  # "category", "regex_summary", "regex_description"
    pattern: str  # Category name or regex pattern
    exclude: bool = False  # If True, exclude matching events; if False, include


class AutoHideRule(BaseModel):
    """Represents an auto-hide rule based on time overlap."""
    id: str
    name: str
    pattern1: str  # Regex pattern for first event
    pattern2: str  # Regex pattern for second event
    hide_pattern: str  # Which pattern to hide ("1" or "2")
    enabled: bool = True


class Output(BaseModel):
    """Represents a filtered output iCal feed."""
    id: str
    name: str
    description: Optional[str] = None
    filter_rules: List[FilterRule] = Field(default_factory=list)
    auto_hide_rules: List[str] = Field(default_factory=list)  # IDs of AutoHideRules


class AppState(BaseModel):
    """Application state for flat file storage."""
    sources: Dict[str, Source] = Field(default_factory=dict)
    events: Dict[str, StoredEvent] = Field(default_factory=dict)  # Key is UID
    outputs: Dict[str, Output] = Field(default_factory=dict)
    auto_hide_rules: Dict[str, AutoHideRule] = Field(default_factory=dict)
