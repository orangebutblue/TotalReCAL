"""Main FastAPI application."""
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from icalendar import Calendar

from .config import ConfigManager, SourceConfig, OutputConfig, RuleConfig
from .storage import EventStore, HiddenEventsManager
from .fetcher import Fetcher, FetchError
from .filters import FilterEngine
from .scheduler import FetchScheduler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Global state
class AppState:
    data_dir: Path
    config_manager: ConfigManager
    event_store: EventStore
    hidden_manager: HiddenEventsManager
    fetcher: Fetcher
    scheduler: FetchScheduler


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting ICalArchive")
    state.scheduler.start()
    
    # Schedule all sources
    config = state.config_manager.load()
    for source_name, source_config in config.sources.items():
        state.scheduler.schedule_source(source_name, source_config, fetch_source)
    
    yield
    
    # Shutdown
    logger.info("Shutting down ICalArchive")
    state.scheduler.shutdown()


app = FastAPI(title="ICalArchive", lifespan=lifespan)

# Templates
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# Pydantic models
class SourceCreate(BaseModel):
    name: str
    url: str
    fetch_interval_minutes: int = 30


class SourceUpdate(BaseModel):
    url: Optional[str] = None
    fetch_interval_minutes: Optional[int] = None
    enabled: Optional[bool] = None


class OutputCreate(BaseModel):
    name: str
    filter_by_category: List[str] = []
    exclude_category: List[str] = []
    include_summary_regex: Optional[str] = None
    exclude_summary_regex: Optional[str] = None
    include_sources: List[str] = []


class RuleCreate(BaseModel):
    rule_type: str
    params: Dict[str, Any] = {}


# Helper functions
async def fetch_source(source_name: str):
    """Fetch and store events from a source."""
    config = state.config_manager.load()
    source_config = config.sources.get(source_name)
    
    if not source_config:
        logger.warning(f"Source {source_name} not found in config")
        return
    
    try:
        calendar = await state.fetcher.fetch(source_name, source_config.url)
        
        # Save snapshot
        state.event_store.save_source_snapshot(source_name, calendar.to_ical())
        
        # Merge into store
        new_count = state.event_store.merge_events(source_name, calendar)
        logger.info(f"Added {new_count} new events from {source_name}")
        
    except FetchError as e:
        logger.error(f"Failed to fetch {source_name}: {e}")


def build_output_calendar(output_name: str) -> Calendar:
    """Build an output calendar with filtering applied."""
    config = state.config_manager.load()
    output_config = config.outputs.get(output_name)
    
    if not output_config:
        raise HTTPException(status_code=404, detail="Output not found")
    
    # Load all events
    all_events = state.event_store.load_all_events()
    
    # Apply filters
    hidden_uids = state.hidden_manager.load()
    filter_engine = FilterEngine(hidden_uids, config.rules)
    filtered_events = filter_engine.filter_for_output(all_events, output_config)
    
    # Build calendar
    cal = Calendar()
    cal.add('prodid', '-//ICalArchive//EN')
    cal.add('version', '2.0')
    cal.add('X-WR-CALNAME', output_name)
    
    for event in filtered_events.values():
        cal.add_component(event)
    
    return cal


# Calendar feed endpoints
@app.get("/cal/{name}.ics")
async def get_calendar_feed(name: str):
    """Serve an output calendar feed."""
    try:
        cal = build_output_calendar(name)
        return Response(
            content=cal.to_ical(),
            media_type="text/calendar",
            headers={
                "Content-Disposition": f'attachment; filename="{name}.ics"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building calendar {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Source API endpoints
@app.get("/api/sources")
async def list_sources():
    """List all sources."""
    config = state.config_manager.load()
    sources = []
    
    for name, src_config in config.sources.items():
        stats = state.event_store.get_source_stats(name)
        sources.append({
            'name': name,
            'url': src_config.url,
            'fetch_interval_minutes': src_config.fetch_interval_minutes,
            'enabled': src_config.enabled,
            'event_count': stats['event_count'],
            'last_fetch': stats['last_fetch'].isoformat() if stats['last_fetch'] else None,
        })
    
    return sources


@app.post("/api/sources")
async def create_source(source: SourceCreate):
    """Create a new source."""
    config = state.config_manager.load()
    
    if source.name in config.sources:
        raise HTTPException(status_code=400, detail="Source already exists")
    
    source_config = SourceConfig(
        url=source.url,
        fetch_interval_minutes=source.fetch_interval_minutes,
    )
    config.sources[source.name] = source_config
    state.config_manager.save(config)
    
    # Schedule the source
    state.scheduler.schedule_source(source.name, source_config, fetch_source)
    
    return {"status": "created", "name": source.name}


@app.patch("/api/sources/{name}")
async def update_source(name: str, update: SourceUpdate):
    """Update a source."""
    config = state.config_manager.load()
    
    if name not in config.sources:
        raise HTTPException(status_code=404, detail="Source not found")
    
    source_config = config.sources[name]
    
    if update.url is not None:
        source_config.url = update.url
    if update.fetch_interval_minutes is not None:
        source_config.fetch_interval_minutes = update.fetch_interval_minutes
    if update.enabled is not None:
        source_config.enabled = update.enabled
    
    state.config_manager.save(config)
    
    # Reschedule with new interval
    state.scheduler.reschedule_source(name, source_config, fetch_source)
    
    return {"status": "updated"}


@app.delete("/api/sources/{name}")
async def delete_source(name: str):
    """Delete a source."""
    config = state.config_manager.load()
    
    if name not in config.sources:
        raise HTTPException(status_code=404, detail="Source not found")
    
    del config.sources[name]
    state.config_manager.save(config)
    
    # Unschedule
    state.scheduler.unschedule_source(name)
    
    return {"status": "deleted"}


@app.post("/api/sources/{name}/fetch")
async def trigger_fetch(name: str):
    """Trigger immediate fetch for a source."""
    config = state.config_manager.load()
    
    if name not in config.sources:
        raise HTTPException(status_code=404, detail="Source not found")
    
    await fetch_source(name)
    
    return {"status": "fetched"}


# Event API endpoints
@app.get("/api/events")
async def list_events(
    page: int = 1,
    per_page: int = 50,
    source: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
):
    """List events with filtering and pagination."""
    all_events = state.event_store.load_all_events()
    hidden_uids = state.hidden_manager.load()
    
    # Filter events
    filtered = []
    for uid, event in all_events.items():
        if source and not uid.startswith(f"{source}::"):
            continue
        
        if category:
            event_cats = []
            cats = event.get('CATEGORIES', [])
            if isinstance(cats, str):
                event_cats = [c.strip() for c in cats.split(',')]
            if category not in event_cats:
                continue
        
        if search:
            summary = str(event.get('SUMMARY', ''))
            if search.lower() not in summary.lower():
                continue
        
        filtered.append({
            'uid': uid,
            'source': uid.split('::', 1)[0],
            'summary': str(event.get('SUMMARY', '')),
            'start': str(event.get('DTSTART', '')),
            'end': str(event.get('DTEND', '')),
            'categories': event.get('CATEGORIES', []),
            'hidden': uid in hidden_uids,
        })
    
    # Paginate
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    
    return {
        'events': filtered[start:end],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page,
    }


@app.post("/api/events/{uid}/hide")
async def hide_event(uid: str):
    """Hide an event."""
    state.hidden_manager.hide(uid)
    return {"status": "hidden"}


@app.post("/api/events/{uid}/show")
async def unhide_event(uid: str):
    """Unhide an event."""
    state.hidden_manager.unhide(uid)
    return {"status": "shown"}


# Output API endpoints
@app.get("/api/outputs")
async def list_outputs():
    """List all outputs."""
    config = state.config_manager.load()
    return [
        {
            'name': name,
            **output_config.__dict__,
        }
        for name, output_config in config.outputs.items()
    ]


@app.post("/api/outputs")
async def create_output(output: OutputCreate):
    """Create a new output."""
    config = state.config_manager.load()
    
    if output.name in config.outputs:
        raise HTTPException(status_code=400, detail="Output already exists")
    
    output_config = OutputConfig(
        filter_by_category=output.filter_by_category,
        exclude_category=output.exclude_category,
        include_summary_regex=output.include_summary_regex,
        exclude_summary_regex=output.exclude_summary_regex,
        include_sources=output.include_sources,
    )
    config.outputs[output.name] = output_config
    state.config_manager.save(config)
    
    return {"status": "created", "name": output.name}


@app.delete("/api/outputs/{name}")
async def delete_output(name: str):
    """Delete an output."""
    config = state.config_manager.load()
    
    if name not in config.outputs:
        raise HTTPException(status_code=404, detail="Output not found")
    
    del config.outputs[name]
    state.config_manager.save(config)
    
    return {"status": "deleted"}


# Rule API endpoints
@app.get("/api/rules")
async def list_rules():
    """List all rules."""
    config = state.config_manager.load()
    return [rule.__dict__ for rule in config.rules]


@app.post("/api/rules")
async def create_rule(rule: RuleCreate):
    """Create a new rule."""
    config = state.config_manager.load()
    
    rule_id = f"rule_{len(config.rules) + 1}"
    rule_config = RuleConfig(
        rule_id=rule_id,
        rule_type=rule.rule_type,
        params=rule.params,
    )
    config.rules.append(rule_config)
    state.config_manager.save(config)
    
    return {"status": "created", "rule_id": rule_id}


@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a rule."""
    config = state.config_manager.load()
    
    config.rules = [r for r in config.rules if r.rule_id != rule_id]
    state.config_manager.save(config)
    
    return {"status": "deleted"}


# Web UI endpoints
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard page."""
    config = state.config_manager.load()
    all_events = state.event_store.load_all_events()
    
    source_stats = []
    for name in config.sources:
        stats = state.event_store.get_source_stats(name)
        source_stats.append({
            'name': name,
            'event_count': stats['event_count'],
            'last_fetch': stats['last_fetch'],
        })
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "source_count": len(config.sources),
        "output_count": len(config.outputs),
        "total_events": len(all_events),
        "sources": source_stats,
    })


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request, page: int = 1, source: str = None):
    """Events page."""
    result = await list_events(page=page, per_page=50, source=source)
    config = state.config_manager.load()
    
    return templates.TemplateResponse("events.html", {
        "request": request,
        "events": result['events'],
        "page": result['page'],
        "pages": result['pages'],
        "sources": list(config.sources.keys()),
        "selected_source": source,
    })


@app.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    """Sources page."""
    sources = await list_sources()
    
    return templates.TemplateResponse("sources.html", {
        "request": request,
        "sources": sources,
    })


@app.get("/outputs", response_class=HTMLResponse)
async def outputs_page(request: Request):
    """Outputs page."""
    outputs = await list_outputs()
    config = state.config_manager.load()
    
    return templates.TemplateResponse("outputs.html", {
        "request": request,
        "outputs": outputs,
        "sources": list(config.sources.keys()),
    })


@app.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    """Rules page."""
    rules = await list_rules()
    
    return templates.TemplateResponse("rules.html", {
        "request": request,
        "rules": rules,
    })


def create_app(data_dir: Path) -> FastAPI:
    """Create and configure the FastAPI application."""
    state.data_dir = data_dir
    state.config_manager = ConfigManager(data_dir / "config.toml")
    state.event_store = EventStore(data_dir)
    state.hidden_manager = HiddenEventsManager(data_dir)
    state.fetcher = Fetcher()
    state.scheduler = FetchScheduler()
    
    return app
