# Quick Start Guide for ICalArchive

## Installation

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/orangebutblue/TotalReCAL.git
cd TotalReCAL

# Start with docker-compose
docker-compose up -d

# Access the Web UI
open http://localhost:8001
```

### Option 2: Python Installation

```bash
# Clone the repository
git clone https://github.com/orangebutblue/TotalReCAL.git
cd TotalReCAL

# Install the package
pip install .

# Create a data directory
mkdir data

# Run the service
python -m icalarchive ./data
```

## First Steps

1. **Open the Web UI** at http://localhost:8001

2. **Add a Source**:
   - Navigate to "Sources" page
   - Fill in the form:
     - **Name**: A unique identifier (e.g., "work")
     - **URL**: The iCal feed URL
     - **Interval**: Fetch interval in minutes (e.g., 30)
   - Click "Add Source"

3. **Create an Output Feed**:
   - Navigate to "Outputs" page
   - Fill in the form:
     - **Name**: Output feed name (e.g., "all" or "work_only")
     - Configure filters as needed
   - Click "Add Output"

4. **Subscribe to Your Feed**:
   - Your filtered calendar feed is available at:
     `http://localhost:8000/cal/<output_name>.ics`
   - Add this URL to your calendar application

## Example Configuration

Here's a sample workflow:

```python
# 1. Add a work calendar source
POST /api/sources
{
  "name": "work",
  "url": "https://calendar.google.com/calendar/ical/work@example.com/public/basic.ics",
  "fetch_interval_minutes": 30
}

# 2. Add a personal calendar source
POST /api/sources
{
  "name": "personal",
  "url": "https://calendar.google.com/calendar/ical/personal@example.com/public/basic.ics",
  "fetch_interval_minutes": 60
}

# 3. Create an "all" output feed (no filters)
POST /api/outputs
{
  "name": "all"
}

# 4. Create a "work_only" output feed
POST /api/outputs
{
  "name": "work_only",
  "filter_by_category": ["Work"],
  "include_sources": ["work"]
}

# 5. Subscribe to the feeds
# All events: http://localhost:8000/cal/all.ics
# Work only: http://localhost:8000/cal/work_only.ics
```

## Auto-Hide Rules

Create rules to automatically hide events:

1. **By Category**:
   - Rule Type: "Exclude by Category"
   - Categories: ["Cancelled", "Spam"]

2. **By Summary Pattern**:
   - Rule Type: "Hide by Summary Regex"
   - Pattern: `(cancelled|postponed)`

3. **By Description Pattern**:
   - Rule Type: "Hide by Description Regex"
   - Pattern: `spam|test`

## Manual Event Hiding

1. Navigate to "Events" page
2. Find the event you want to hide
3. Click the "Hide" button
4. The event will be excluded from all output feeds

## API Usage

All features are available via REST API:

```bash
# List all sources
curl http://localhost:8001/api/sources

# Trigger manual fetch
curl -X POST http://localhost:8001/api/sources/work/fetch

# List all events
curl http://localhost:8001/api/events

# Hide an event
curl -X POST http://localhost:8001/api/events/SOURCE::UID/hide
```

## Data Backup

Simply copy the `/data` directory:

```bash
# Backup
cp -r ./data ./data-backup-$(date +%Y%m%d)

# Restore
cp -r ./data-backup-20240215 ./data
```

## Troubleshooting

### Port already in use
Edit `config.toml` to change ports:
```toml
calendar_port = 8002
ui_port = 8003
```

### Source fetch failing
- Check the URL is accessible
- Check the URL returns valid iCal format
- View logs for error messages

### Events not appearing
- Ensure source has been fetched at least once
- Check if events are hidden (Events page)
- Verify output filters aren't excluding them

## Advanced Configuration

Edit `config.toml` directly for bulk changes:

```toml
calendar_port = 8000
ui_port = 8001

[sources.work]
url = "https://example.com/work.ics"
fetch_interval_minutes = 30
enabled = true

[outputs.all]
filter_by_category = []
exclude_category = []
include_sources = []

[outputs.work_only]
filter_by_category = ["Work"]
include_sources = ["work"]

[[rules]]
rule_id = "rule_1"
rule_type = "category_exclude"
params = {categories = ["Spam", "Cancelled"]}
```

## Need Help?

- Check the [README](README.md) for full documentation
- Review API endpoints in the main documentation
- Check server logs for detailed error messages
