"""Main entry point for ICalArchive."""
import sys
import uvicorn
from pathlib import Path
from .app import create_app


def main():
    """Run the application."""
    data_dir = Path("/data")
    
    # Allow override via environment or command line
    if len(sys.argv) > 1:
        data_dir = Path(sys.argv[1])
    
    # Create app
    app = create_app(data_dir)
    
    # Get port from config
    from .config import ConfigManager
    config_manager = ConfigManager(data_dir / "config.toml")
    config = config_manager.load()
    
    # Run on UI port (for development, we'll use one server)
    # In production, you'd run two separate instances
    port = config.ui_port
    
    print(f"Starting ICalArchive on port {port}")
    print(f"Data directory: {data_dir}")
    print(f"Web UI: http://localhost:{port}")
    print(f"Calendar feeds: http://localhost:{port}/cal/<name>.ics")
    
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
