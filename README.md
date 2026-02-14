# ICalArchive - Total Recall for iCal Feeds

ICalArchive is a service that subscribes to external iCal feeds, accumulates all events permanently (never deletes), and re-serves them as filtered output feeds. Unlike source calendars that prune history, this service retains everything forever.

## Features

- **Permanent Event Storage**: Subscribe to N external iCal feeds and accumulate all events in append-only storage
- **Smart Filtering**: Create M filtered output feeds with category filters, regex patterns, and auto-hide rules
- **Flexible Scheduling**: Per-source configurable fetch intervals with live updates (no restart required)
- **Web UI**: Server-rendered HTML interface for managing sources, outputs, events, and rules
- **No Database**: Uses flat files for storage - backup is just copying `/data`
- **Docker Ready**: Includes `docker-compose.yml` for easy deployment

## Quick Start

### Using Docker Compose

```bash
docker-compose up -d
```

Access the Web UI at http://localhost:8001

### Manual Installation

```bash
# Install dependencies
pip install .

# Run the service
python -m icalarchive /path/to/data
```

## Configuration

Configuration is stored in `/data/config.toml`. You can manage it via the Web UI or edit directly:

```toml
[sources.work]
url = "https://example.com/work.ics"
fetch_interval_minutes = 30

[outputs.work_only]
filter_by_category = ["Work"]

[outputs.all]
# no filters — serves everything not hidden
```

## Storage Layout

```
/data
  /store/        # Accumulated events, one .ics per source (append-only)
  /sources/      # Latest raw fetched .ics snapshots
  config.toml    # Sources, outputs, rules, intervals
  hidden.json    # Manually hidden event UIDs
```

## API Endpoints

### Calendar Feeds
- `GET /cal/{name}.ics` - Serve output feed

### Sources
- `GET/POST /api/sources` - List/add sources
- `PATCH /api/sources/{name}` - Update source
- `DELETE /api/sources/{name}` - Remove source
- `POST /api/sources/{name}/fetch` - Trigger immediate fetch

### Events
- `GET /api/events` - List events (paginated, filterable)
- `POST /api/events/{uid}/hide` - Hide event
- `POST /api/events/{uid}/show` - Unhide event

### Outputs
- `GET/POST /api/outputs` - List/add outputs
- `DELETE /api/outputs/{name}` - Remove output

### Rules
- `GET/POST /api/rules` - List/add auto-hide rules
- `DELETE /api/rules/{id}` - Delete rule

## Web UI

The Web UI provides a complete interface for managing the service:

- **Dashboard**: Overview of sources, outputs, and total events
- **Events**: Browse and search events, toggle hidden status
- **Sources**: Add/edit/delete sources, adjust fetch intervals, trigger manual fetches
- **Outputs**: Configure filtered output feeds
- **Rules**: Set up auto-hide rules based on categories or regex patterns

## Tech Stack

- Python 3.11+
- FastAPI for web framework
- APScheduler for scheduled fetching
- icalendar + recurring_ical_events for iCal parsing
- Jinja2 for HTML templating
- Bootstrap 5 for UI styling

## License

MIT