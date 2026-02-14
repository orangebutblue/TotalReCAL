# TotalReCAL

A Python/FastAPI service that subscribes to remote iCal feeds, accumulates events forever, and re-serves filtered output iCal feeds.

## Features

- **Subscribe to N remote iCal feeds**: Add multiple calendar sources
- **Accumulate events forever by UID**: Events are never deleted, even if removed from source
- **Re-serve M filtered output feeds**: Create multiple output feeds with different filter configurations
- **Flat file storage**: No database required, uses JSON for persistence
- **Powerful filtering**:
  - Filter by CATEGORIES field
  - Filter by summary/description regex patterns
  - Manual per-event hiding
  - Auto-hide rules based on time overlap between event patterns
- **Minimal Jinja2 web UI**: Manage sources, outputs, rules, and events through a simple web interface

## Installation

1. Clone the repository:
```bash
git clone https://github.com/orangebutblue/TotalReCAL.git
cd TotalReCAL
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

2. Open your browser and navigate to `http://localhost:8000`

3. Add iCal sources, create output feeds, and configure filters through the web UI

## API Endpoints

### Sources
- `GET /api/sources` - List all sources
- `POST /api/sources` - Create a new source
- `GET /api/sources/{source_id}` - Get a source
- `PUT /api/sources/{source_id}` - Update a source
- `DELETE /api/sources/{source_id}` - Delete a source
- `POST /api/sources/{source_id}/fetch` - Manually fetch a source

### Outputs
- `GET /api/outputs` - List all outputs
- `POST /api/outputs` - Create a new output
- `GET /api/outputs/{output_id}` - Get an output
- `PUT /api/outputs/{output_id}` - Update an output
- `DELETE /api/outputs/{output_id}` - Delete an output

### Events
- `GET /api/events` - List all events
- `POST /api/events/{uid}/hide` - Hide an event
- `POST /api/events/{uid}/show` - Show an event

### Auto-Hide Rules
- `GET /api/auto-hide-rules` - List all rules
- `POST /api/auto-hide-rules` - Create a new rule
- `PUT /api/auto-hide-rules/{rule_id}` - Update a rule
- `DELETE /api/auto-hide-rules/{rule_id}` - Delete a rule

### iCal Feeds
- `GET /feeds/{output_id}.ics` - Get filtered iCal feed

## Web UI

- `/` - Home page
- `/sources` - Manage iCal sources
- `/outputs` - Manage output feeds
- `/events` - View and hide/show events
- `/rules` - Manage auto-hide rules

## Data Storage

All data is stored in the `data/` directory as JSON files. The application state is persisted in `data/state.json`.

## Example Use Cases

1. **Aggregate multiple work calendars**: Combine calendars from different teams into one feed
2. **Filter personal events**: Create a work-safe calendar by filtering out personal categories
3. **Auto-hide overlapping events**: Automatically hide on-call events when you're on vacation
4. **Archive all events**: Keep a permanent record of all calendar events, even after they're deleted from the source

## License

MIT