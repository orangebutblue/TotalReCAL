"""Main FastAPI application."""
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Literal
from contextlib import asynccontextmanager

import os
from fastapi import FastAPI, HTTPException, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from icalendar import Calendar

from .config import ConfigManager, SourceConfig, OutputConfig
from .storage import EventStore
from .fetcher import Fetcher, FetchError
from .scheduler import FetchScheduler
from .series import SeriesManager

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
    fetcher: Fetcher
    scheduler: FetchScheduler
    series_manager: SeriesManager


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Ensure app components are initialized if running directly via uvicorn hook (e.g. docker-compose)
    if not hasattr(state, 'scheduler'):
        data_dir = Path(os.environ.get("ICAL_DATA_DIR", "./data"))
        create_app(data_dir)

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
import importlib.metadata
import os
from datetime import datetime

try:
    __version__ = importlib.metadata.version('icalarchive')
except Exception:
    __version__ = '0.4.0'

# Automatically generate dynamic build numbers during development
try:
    src_dir = Path(__file__).parent
    mod_times = [f.stat().st_mtime for f in src_dir.rglob('*') if f.is_file() and f.suffix in ('.py', '.html')]
    if mod_times:
        build_stamp = datetime.fromtimestamp(max(mod_times)).strftime('%y%m%d.%H%M')
        __version__ = f"{__version__}-dev.{build_stamp}"
except Exception:
    pass

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals['app_version'] = f"v{__version__}"


class SourceCreate(BaseModel):
    name: str
    url: str
    fetch_interval_minutes: int = 30
    color: str = "#0d6efd"


class SourceUpdate(BaseModel):
    url: Optional[str] = None
    fetch_interval_minutes: Optional[int] = None
    enabled: Optional[bool] = None
    color: Optional[str] = None


class OutputCreate(BaseModel):
    name: str
    filter_by_category: List[str] = []
    exclude_category: List[str] = []
    include_summary_regex: Optional[str] = None
    exclude_summary_regex: Optional[str] = None
    include_sources: List[str] = []


class RuleCreate(BaseModel):
    rule_type: Literal["hide_event", "add_to_series", "category_exclude", "summary_regex", "description_regex"]
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
        
        # Process add_to_series rules dynamically (DEPRECATED - now handled purely via resolution math on query)
        pass
        
        
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
    
    # Apply filters mathematically via Set theory
    hidden_uids = state.series_manager.resolve_series("hidden", all_events)
    
    import re
    filtered_events = {}
    for uid, event in all_events.items():
        if uid in hidden_uids:
            continue
            
        if output_config.include_sources:
            source = uid.split('::', 1)[0]
            if source not in output_config.include_sources:
                continue
                
        categories = event.get('CATEGORIES', [])
        if isinstance(categories, str):
            categories = [cat.strip() for cat in categories.split(',')]
        elif hasattr(categories, 'cats'):
            categories = categories.cats
        elif not isinstance(categories, list):
            categories = []
            
        if output_config.filter_by_category and not any(cat in output_config.filter_by_category for cat in categories):
            continue
            
        if output_config.exclude_category and any(cat in output_config.exclude_category for cat in categories):
            continue
            
        summary = str(event.get('SUMMARY', ''))
        
        if output_config.include_summary_regex and not re.search(output_config.include_summary_regex, summary, re.IGNORECASE):
            continue
            
        if output_config.exclude_summary_regex and re.search(output_config.exclude_summary_regex, summary, re.IGNORECASE):
            continue
            
        filtered_events[uid] = event
    
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
            'color': getattr(src_config, 'color', '#0d6efd'),
            'event_count': stats['event_count'],
            'last_fetch': stats['last_fetch'].isoformat() if stats['last_fetch'] else None,
        })
    
    return sources


from fastapi import FastAPI, HTTPException, Request, Response, Form, BackgroundTasks

@app.post("/api/sources")
async def create_source(source: SourceCreate, background_tasks: BackgroundTasks):
    """Create a new source and fetch immediately."""
    config = state.config_manager.load()
    
    if source.name in config.sources:
        raise HTTPException(status_code=400, detail="Source already exists")
    
    source_config = SourceConfig(
        url=source.url,
        fetch_interval_minutes=source.fetch_interval_minutes,
        color=source.color,
    )
    config.sources[source.name] = source_config
    state.config_manager.save(config)
    
    # Schedule the source
    state.scheduler.schedule_source(source.name, source_config, fetch_source)
    
    # Trigger an immediate background fetch for instant UX
    background_tasks.add_task(fetch_source, source.name)
    
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
    if update.color is not None:
        source_config.color = update.color
    
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

@app.post("/api/sources/{name}/deduplicate")
async def trigger_deduplicate(name: str):
    """Trigger retroactive deduplication for a source."""
    config = state.config_manager.load()
    
    if name not in config.sources:
        raise HTTPException(status_code=404, detail="Source not found")
        
    removed_count = state.event_store.deduplicate_store(name)
    return {"status": "deduplicated", "removed_count": removed_count}


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
    hidden_uids = state.series_manager.resolve_series("hidden", all_events)
    
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
    print("====== DEBUG UID POST ======", repr(uid), flush=True)
    state.series_manager.add_event_to_series("hidden", uid)
    return {"status": "hidden"}

@app.post("/api/events/{uid}/show")
async def unhide_event(uid: str):
    """Unhide an event."""
    state.series_manager.remove_event_from_series("hidden", uid)
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
    """List all global hide rules and series auto-assign rules."""
    all_rules = []
    
    # 1. System Hidden Rules
    hidden_series = state.series_manager._cache.get("hidden", {})
    patterns = hidden_series.get("match_patterns", [])
    all_rules.extend([{"rule_id": p, "rule_type": "summary_regex", "series": "hidden", "params": {"pattern": p}} for p in patterns])
    
    # 2. Custom Series Rules
    for sid, sdata in state.series_manager.get_all_series().items():
        if sid == "hidden":
            continue
        patterns = sdata.get("match_patterns", [])
        all_rules.extend([{"rule_id": p, "rule_type": "summary_regex", "series": sdata["name"], "series_id": sid, "params": {"pattern": p}} for p in patterns])
        
    return all_rules

@app.post("/api/rules")
async def create_rule(rule: RuleCreate):
    """Create a new global hide rule (adds to hidden series match patterns)."""
    if rule.rule_type == 'add_to_series':
        raise HTTPException(status_code=400, detail="Use the Series API for add_to_series")
        
    pattern = rule.params.get('pattern')
    if not pattern:
        raise HTTPException(status_code=400, detail="Missing pattern")
        
    hidden_series = state.series_manager._cache.get("hidden", {})
    patterns = hidden_series.setdefault("match_patterns", [])
    
    if pattern in patterns:
        raise HTTPException(status_code=400, detail="Rule already exists")
        
    patterns.append(pattern)
    state.series_manager._save()
    
    import base64
    rule_id = base64.b64encode(pattern.encode()).decode()
    return {"status": "created", "rule_id": rule_id}

@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a global hide rule (removes from hidden series match patterns)."""
    import base64
    try:
        pattern = base64.b64decode(rule_id.encode()).decode()
    except Exception:
        pattern = rule_id # Fallback if frontend sends raw string
        
    hidden_series = state.series_manager._cache.get("hidden", {})
    patterns = hidden_series.get("match_patterns", [])
    
    if pattern in patterns:
        patterns.remove(pattern)
        state.series_manager._save()
        
    return {"status": "deleted"}


# Web UI endpoints
@app.get("/")
async def root():
    """Redirect root directly to the Calendar view."""
    return RedirectResponse(url="/calendar")


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request):
    """Events page."""
    config = state.config_manager.load()
    
    return templates.TemplateResponse("events.html", {
        "request": request,
        "sources": list(config.sources.keys()),
    })


@app.get("/api/events/all")
async def get_all_events():
    """Get all events unpaginated for client-side search."""
    all_events = state.event_store.load_all_events()
    
    # Mathematical O(N) Reverse-Indexing
    hidden_uids = state.series_manager.resolve_series("hidden", all_events)
    
    uid_to_series = {}
    for sid, sdata in state.series_manager.get_all_series().items():
        if sid == "hidden":
            continue
        resolved_uids = state.series_manager.resolve_series(sid, all_events)
        for r_uid in resolved_uids:
            if r_uid not in uid_to_series:
                uid_to_series[r_uid] = []
            uid_to_series[r_uid].append({"id": sid, "name": sdata["name"], "color": sdata.get("color")})
            
    events_out = []
    for uid, event in all_events.items():
        start = event.get('DTSTART')
        end = event.get('DTEND')
        source_name = uid.split('::', 1)[0]
        
        events_out.append({
            'uid': uid,
            'summary': str(event.get('SUMMARY', '')),
            'source': source_name,
            'start': start.dt.isoformat() if start and hasattr(start, 'dt') else "",
            'end': end.dt.isoformat() if end and hasattr(end, 'dt') else "",
            'hidden': uid in hidden_uids,
            'in_series': uid in uid_to_series
        })
        
    events_out.sort(key=lambda x: x['start'], reverse=True)
    return events_out


@app.get("/api/calendar-events")
async def get_calendar_events(source: Optional[str] = None, show_hidden: bool = True):
    """Feed for FullCalendar.js."""
    all_events = state.event_store.load_all_events()
    config = state.config_manager.load()
    
    # Mathematical O(N) Reverse-Indexing
    hidden_uids = state.series_manager.resolve_series("hidden", all_events)
    uid_to_series = {}
    for sid, sdata in state.series_manager.get_all_series().items():
        if sid == "hidden":
            continue
        resolved_uids = state.series_manager.resolve_series(sid, all_events)
        for r_uid in resolved_uids:
            if r_uid not in uid_to_series:
                uid_to_series[r_uid] = []
            uid_to_series[r_uid].append({"id": sid, "name": sdata["name"], "color": sdata.get("color")})
            
    events_out = []
    for uid, event in all_events.items():
        if source and not uid.startswith(f"{source}::"):
            continue
            
        hidden = uid in hidden_uids
        if hidden and not show_hidden:
            continue
            
        start = event.get('DTSTART')
        end = event.get('DTEND')
        
        # Format dates for FC
        start_str = start.dt.isoformat() if start else ""
        end_str = end.dt.isoformat() if end else ""
            
        source_name = uid.split('::', 1)[0]
        source_color = getattr(config.sources.get(source_name, {}), 'color', '#0d6efd')
        
        # Pull mapped series instantly
        assigned_series = uid_to_series.get(uid, [])
        is_in_series = len(assigned_series) > 0
        
        title_prefix = "🔗 " if is_in_series else ""
        title = title_prefix + str(event.get('SUMMARY', ''))
        
        # Determine Color Priority
        final_color = '#dc3545' if hidden else source_color
        if is_in_series and not hidden:
            s_color = assigned_series[0].get('color')
            if s_color and s_color != '#6c757d': # Allow legacy overrides to fallback safely
                final_color = s_color
            
        events_out.append({
            'id': uid,
            'title': title,
            'start': start_str,
            'end': end_str,
            'color': final_color,
            'extendedProps': {
                'source': source_name,
                'hidden': hidden,
                'series': [s['name'] for s in assigned_series],
                'series_ids': [s['id'] for s in assigned_series],
                'location': str(event.get('LOCATION', '')),
                'description': str(event.get('DESCRIPTION', ''))
            }
        })
    return events_out


@app.get("/calendar", response_class=HTMLResponse)
async def calendar_page(request: Request):
    """Calendar view page."""
    config = state.config_manager.load()
    return templates.TemplateResponse("calendar.html", {
        "request": request,
        "sources": list(config.sources.keys())
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
    all_rules = await list_rules()
    
    # Filter out Series rules so they only appear in their dedicated workspace
    hide_rules = [r for r in all_rules if r.get('rule_type') != 'add_to_series']
    
    return templates.TemplateResponse("rules.html", {
        "request": request,
        "rules": hide_rules,
        "series_data": state.series_manager.get_all_series()
    })


class SeriesCreate(BaseModel):
    name: str

class SeriesEventParams(BaseModel):
    uid: str

class SeriesColorUpdate(BaseModel):
    color: Optional[str] = None

@app.get("/api/series")
async def list_series():
    return state.series_manager.get_all_series()

@app.post("/api/series")
async def create_series_api(series: SeriesCreate):
    sid = state.series_manager.create_series(series.name)
    return {"status": "created", "series_id": sid}

@app.delete("/api/series/{series_id}")
async def delete_series_api(series_id: str):
    if state.series_manager.delete_series(series_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Series not found")

@app.put("/api/series/{series_id}/color")
async def update_series_color_api(series_id: str, payload: SeriesColorUpdate):
    if state.series_manager.update_series_color(series_id, payload.color):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Series not found")

@app.post("/api/series/{series_id}/events")
async def add_event_to_series_api(series_id: str, params: SeriesEventParams):
    if state.series_manager.add_event_to_series(series_id, params.uid):
        return {"status": "added"}
    raise HTTPException(status_code=404, detail="Series not found")

@app.delete("/api/series/{series_id}/events/{uid}")
async def remove_event_from_series_api(series_id: str, uid: str):
    if state.series_manager.remove_event_from_series(series_id, uid):
        return {"status": "removed"}
    raise HTTPException(status_code=404, detail="Series not found")

@app.get("/series/{series_id}", response_class=HTMLResponse)
async def series_detail_page(request: Request, series_id: str):
    """View details, assigned events, and rules for a specific series."""
    series_map = state.series_manager.get_all_series()
    if series_id not in series_map:
        raise HTTPException(status_code=404, detail="Series not found")
        
    s_data = series_map[series_id]
    all_events = state.event_store.load_all_events()
    
    # Resolve actual event objects bound to this series dynamically
    bound_uids = state.series_manager.resolve_series(series_id, all_events)
    bound_events = []
    for uid in bound_uids:
        if uid in all_events:
            ev = all_events[uid]
            start = ev.get('DTSTART')
            end = ev.get('DTEND')
            bound_events.append({
                'uid': uid,
                'title': str(ev.get('SUMMARY', '')),
                'start': start.dt.isoformat() if start and hasattr(start, 'dt') else "",
                'end': end.dt.isoformat() if end and hasattr(end, 'dt') else ""
            })
            
    # Sort chronologically
    bound_events.sort(key=lambda x: x['start'])
    
    # Resolve rules affecting this series natively from the Series object
    patterns = s_data.get('match_patterns', [])
    series_rules = [{"rule_id": p, "params": {"pattern": p}} for p in patterns]
    
    return templates.TemplateResponse("series_detail.html", {
        "request": request,
        "series_data": series_map,
        "series": s_data,
        "series_id": series_id,
        "events": bound_events,
        "rules": series_rules
    })

@app.put("/api/series/{series_id}/rename")
async def rename_series_endpoint(series_id: str, request: Request):
    """Update the visual alias of an existing Series."""
    payload = await request.json()
    new_name = payload.get('name')
    if not new_name:
        raise HTTPException(status_code=400, detail="Missing new name")
        
    s_map = state.series_manager.get_all_series()
    if series_id not in s_map:
        raise HTTPException(status_code=404, detail="Series not found")
        
    s_map[series_id]['name'] = new_name
    state.series_manager._save()
    return {"status": "renamed", "name": new_name}

@app.get("/series", response_class=HTMLResponse)
async def series_page(request: Request):
    """Series page directly mapping visual timelines and management."""
    all_events = state.event_store.load_all_events()
    
    clean_events = {}
    for uid, ev in all_events.items():
        start = ev.get('DTSTART')
        end = ev.get('DTEND')
        clean_events[uid] = {
            'uid': uid,
            'title': str(ev.get('SUMMARY', '')),
            'start': start.dt.isoformat() if start and hasattr(start, 'dt') else "",
            'end': end.dt.isoformat() if end and hasattr(end, 'dt') else "",
            'source': uid.split('::', 1)[0]
        }
        
    display_series = {}
    for sid, sdata in state.series_manager.get_all_series().items():
        if sid == "hidden":
            continue
        resolved = state.series_manager.resolve_series(sid, all_events)
        display_series[sid] = dict(sdata)
        display_series[sid]['event_uids'] = list(resolved)
        
    return templates.TemplateResponse("series.html", {
        "request": request,
        "series_data": display_series,
        "events": clean_events
    })


def create_app(data_dir: Path) -> FastAPI:
    """Create and configure the FastAPI application."""
    state.data_dir = data_dir
    state.config_manager = ConfigManager(data_dir / "config.toml")
    state.event_store = EventStore(data_dir)
    state.fetcher = Fetcher()
    state.scheduler = FetchScheduler()
    state.series_manager = SeriesManager(data_dir)
    
    return app

@app.post("/api/series/{series_id}/rules")
async def create_series_rule(series_id: str, payload: dict):
    """Create a pattern rule bounded natively to a specific series."""
    series_map = state.series_manager.get_all_series()
    if series_id not in series_map:
        raise HTTPException(status_code=404, detail="Series not found")
        
    pattern = payload.get('pattern')
    if not pattern:
        raise HTTPException(status_code=400, detail="Missing regex pattern")
        
    s_data = series_map[series_id]
    patterns = s_data.get('match_patterns', [])
    
    if pattern in patterns:
        raise HTTPException(status_code=400, detail="An identical rule pattern already exists for this series.")
        
    patterns.append(pattern)
    s_data['match_patterns'] = patterns
    state.series_manager._save()
            
    return {"status": "created", "pattern": pattern}

@app.delete("/api/series/{series_id}/rules/{pattern}")
async def delete_series_rule(series_id: str, pattern: str):
    """Delete a regex pattern bound natively to a specific series."""
    import urllib.parse
    decoded_pattern = urllib.parse.unquote(pattern)
    
    series_map = state.series_manager.get_all_series()
    if series_id not in series_map:
        raise HTTPException(status_code=404, detail="Series not found")
        
    s_data = series_map[series_id]
    patterns = s_data.get('match_patterns', [])
    
    if decoded_pattern in patterns:
        patterns.remove(decoded_pattern)
        s_data['match_patterns'] = patterns
        state.series_manager._save()
        
    return {"status": "deleted"}
