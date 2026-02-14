from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Form
from fastapi.responses import Response, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import asyncio
import uuid
from typing import Optional

from app.storage import Storage
from app.models import Source, Output, FilterRule, AutoHideRule
from app.fetcher import FeedFetcher
from app.filters import FilterService
from app.generator import ICalGenerator

# Initialize storage
storage = Storage()
fetcher = FeedFetcher(storage)
filter_service = FilterService(storage)
generator = ICalGenerator(filter_service)

# Background task for periodic fetching
async def periodic_fetch():
    """Periodically fetch all sources."""
    while True:
        try:
            await fetcher.fetch_all_sources()
        except Exception as e:
            print(f"Error in periodic fetch: {e}")
        await asyncio.sleep(300)  # Fetch every 5 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task
    task = asyncio.create_task(periodic_fetch())
    yield
    # Cancel background task on shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="TotalReCAL", lifespan=lifespan)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# === API Endpoints ===

# Sources
@app.get("/api/sources")
def list_sources():
    return list(storage.get_all_sources().values())


@app.post("/api/sources")
def create_source(source: Source):
    if source.id in storage.get_all_sources():
        raise HTTPException(status_code=400, detail="Source ID already exists")
    storage.add_source(source)
    return source


@app.get("/api/sources/{source_id}")
def get_source(source_id: str):
    source = storage.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@app.put("/api/sources/{source_id}")
def update_source(source_id: str, source: Source):
    if source_id not in storage.get_all_sources():
        raise HTTPException(status_code=404, detail="Source not found")
    storage.update_source(source_id, source)
    return source


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: str):
    if source_id not in storage.get_all_sources():
        raise HTTPException(status_code=404, detail="Source not found")
    storage.delete_source(source_id)
    return {"status": "deleted"}


@app.post("/api/sources/{source_id}/fetch")
async def fetch_source(source_id: str):
    source = storage.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    events = await fetcher.fetch_source(source)
    for event in events:
        storage.add_or_update_event(event)
    return {"status": "fetched", "events": len(events)}


# Outputs
@app.get("/api/outputs")
def list_outputs():
    return list(storage.get_all_outputs().values())


@app.post("/api/outputs")
def create_output(output: Output):
    if output.id in storage.get_all_outputs():
        raise HTTPException(status_code=400, detail="Output ID already exists")
    storage.add_output(output)
    return output


@app.get("/api/outputs/{output_id}")
def get_output(output_id: str):
    output = storage.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    return output


@app.put("/api/outputs/{output_id}")
def update_output(output_id: str, output: Output):
    if output_id not in storage.get_all_outputs():
        raise HTTPException(status_code=404, detail="Output not found")
    storage.update_output(output_id, output)
    return output


@app.delete("/api/outputs/{output_id}")
def delete_output(output_id: str):
    if output_id not in storage.get_all_outputs():
        raise HTTPException(status_code=404, detail="Output not found")
    storage.delete_output(output_id)
    return {"status": "deleted"}


# iCal feed serving
@app.get("/feeds/{output_id}.ics")
def serve_feed(output_id: str):
    output = storage.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    
    ical_content = generator.generate_output_feed(output)
    return Response(content=ical_content, media_type="text/calendar")


# Events
@app.get("/api/events")
def list_events(source_id: Optional[str] = None):
    events = storage.get_all_events()
    if source_id:
        events = {k: v for k, v in events.items() if v.source_id == source_id}
    return list(events.values())


@app.post("/api/events/{uid}/hide")
def hide_event(uid: str):
    event = storage.get_event(uid)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    storage.update_event_hidden_status(uid, True)
    return {"status": "hidden"}


@app.post("/api/events/{uid}/show")
def show_event(uid: str):
    event = storage.get_event(uid)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    storage.update_event_hidden_status(uid, False)
    return {"status": "shown"}


# Auto-hide rules
@app.get("/api/auto-hide-rules")
def list_auto_hide_rules():
    return list(storage.get_all_auto_hide_rules().values())


@app.post("/api/auto-hide-rules")
def create_auto_hide_rule(rule: AutoHideRule):
    if rule.id in storage.get_all_auto_hide_rules():
        raise HTTPException(status_code=400, detail="Rule ID already exists")
    storage.add_auto_hide_rule(rule)
    return rule


@app.put("/api/auto-hide-rules/{rule_id}")
def update_auto_hide_rule(rule_id: str, rule: AutoHideRule):
    if rule_id not in storage.get_all_auto_hide_rules():
        raise HTTPException(status_code=404, detail="Rule not found")
    storage.update_auto_hide_rule(rule_id, rule)
    return rule


@app.delete("/api/auto-hide-rules/{rule_id}")
def delete_auto_hide_rule(rule_id: str):
    if rule_id not in storage.get_all_auto_hide_rules():
        raise HTTPException(status_code=404, detail="Rule not found")
    storage.delete_auto_hide_rule(rule_id)
    return {"status": "deleted"}


# === Web UI Endpoints ===

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    sources = list(storage.get_all_sources().values())
    return templates.TemplateResponse("sources.html", {
        "request": request,
        "sources": sources
    })


@app.get("/sources/add", response_class=HTMLResponse)
async def add_source_page(request: Request):
    return templates.TemplateResponse("source_form.html", {"request": request, "source": None})


@app.post("/sources/add")
async def add_source_form(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    fetch_interval: int = Form(60)
):
    source_id = str(uuid.uuid4())
    source = Source(
        id=source_id,
        name=name,
        url=url,
        fetch_interval_minutes=fetch_interval
    )
    storage.add_source(source)
    return RedirectResponse(url="/sources", status_code=303)


@app.get("/sources/{source_id}/edit", response_class=HTMLResponse)
async def edit_source_page(request: Request, source_id: str):
    source = storage.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return templates.TemplateResponse("source_form.html", {"request": request, "source": source})


@app.post("/sources/{source_id}/edit")
async def edit_source_form(
    request: Request,
    source_id: str,
    name: str = Form(...),
    url: str = Form(...),
    fetch_interval: int = Form(60),
    enabled: bool = Form(False)
):
    source = Source(
        id=source_id,
        name=name,
        url=url,
        fetch_interval_minutes=fetch_interval,
        enabled=enabled
    )
    storage.update_source(source_id, source)
    return RedirectResponse(url="/sources", status_code=303)


@app.post("/sources/{source_id}/delete")
async def delete_source_form(source_id: str):
    storage.delete_source(source_id)
    return RedirectResponse(url="/sources", status_code=303)


@app.get("/outputs", response_class=HTMLResponse)
async def outputs_page(request: Request):
    outputs = list(storage.get_all_outputs().values())
    return templates.TemplateResponse("outputs.html", {
        "request": request,
        "outputs": outputs
    })


@app.get("/outputs/add", response_class=HTMLResponse)
async def add_output_page(request: Request):
    rules = list(storage.get_all_auto_hide_rules().values())
    return templates.TemplateResponse("output_form.html", {
        "request": request,
        "output": None,
        "auto_hide_rules": rules
    })


@app.post("/outputs/add")
async def add_output_form(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
):
    output_id = str(uuid.uuid4())
    output = Output(
        id=output_id,
        name=name,
        description=description
    )
    storage.add_output(output)
    return RedirectResponse(url=f"/outputs/{output_id}/edit", status_code=303)


@app.get("/outputs/{output_id}/edit", response_class=HTMLResponse)
async def edit_output_page(request: Request, output_id: str):
    output = storage.get_output(output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    rules = list(storage.get_all_auto_hide_rules().values())
    return templates.TemplateResponse("output_form.html", {
        "request": request,
        "output": output,
        "auto_hide_rules": rules
    })


@app.post("/outputs/{output_id}/delete")
async def delete_output_form(output_id: str):
    storage.delete_output(output_id)
    return RedirectResponse(url="/outputs", status_code=303)


@app.get("/events", response_class=HTMLResponse)
async def events_page(request: Request, source_id: Optional[str] = None):
    events = list(storage.get_all_events().values())
    if source_id:
        events = [e for e in events if e.source_id == source_id]
    # Sort by date
    events.sort(key=lambda e: e.first_seen, reverse=True)
    sources = storage.get_all_sources()
    return templates.TemplateResponse("events.html", {
        "request": request,
        "events": events,
        "sources": sources,
        "selected_source": source_id
    })


@app.post("/events/{uid}/hide")
async def hide_event_form(uid: str):
    storage.update_event_hidden_status(uid, True)
    return RedirectResponse(url="/events", status_code=303)


@app.post("/events/{uid}/show")
async def show_event_form(uid: str):
    storage.update_event_hidden_status(uid, False)
    return RedirectResponse(url="/events", status_code=303)


@app.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    rules = list(storage.get_all_auto_hide_rules().values())
    return templates.TemplateResponse("rules.html", {
        "request": request,
        "rules": rules
    })


@app.get("/rules/add", response_class=HTMLResponse)
async def add_rule_page(request: Request):
    return templates.TemplateResponse("rule_form.html", {"request": request, "rule": None})


@app.post("/rules/add")
async def add_rule_form(
    request: Request,
    name: str = Form(...),
    pattern1: str = Form(...),
    pattern2: str = Form(...),
    hide_pattern: str = Form(...)
):
    rule_id = str(uuid.uuid4())
    rule = AutoHideRule(
        id=rule_id,
        name=name,
        pattern1=pattern1,
        pattern2=pattern2,
        hide_pattern=hide_pattern
    )
    storage.add_auto_hide_rule(rule)
    return RedirectResponse(url="/rules", status_code=303)


@app.get("/rules/{rule_id}/edit", response_class=HTMLResponse)
async def edit_rule_page(request: Request, rule_id: str):
    rule = storage.get_auto_hide_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return templates.TemplateResponse("rule_form.html", {"request": request, "rule": rule})


@app.post("/rules/{rule_id}/edit")
async def edit_rule_form(
    request: Request,
    rule_id: str,
    name: str = Form(...),
    pattern1: str = Form(...),
    pattern2: str = Form(...),
    hide_pattern: str = Form(...),
    enabled: bool = Form(False)
):
    rule = AutoHideRule(
        id=rule_id,
        name=name,
        pattern1=pattern1,
        pattern2=pattern2,
        hide_pattern=hide_pattern,
        enabled=enabled
    )
    storage.update_auto_hide_rule(rule_id, rule)
    return RedirectResponse(url="/rules", status_code=303)


@app.post("/rules/{rule_id}/delete")
async def delete_rule_form(rule_id: str):
    storage.delete_auto_hide_rule(rule_id)
    return RedirectResponse(url="/rules", status_code=303)
