from icalendar import Calendar
from typing import List
from app.models import StoredEvent, Output
from app.filters import FilterService


class ICalGenerator:
    """Service to generate iCal output feeds."""
    
    def __init__(self, filter_service: FilterService):
        self.filter_service = filter_service
    
    def generate_output_feed(self, output: Output) -> str:
        """Generate an iCal feed for the given output configuration."""
        # Get filtered events
        events = self.filter_service.filter_events(output)
        
        # Create calendar
        cal = Calendar()
        cal.add('prodid', '-//TotalReCAL//EN')
        cal.add('version', '2.0')
        cal.add('x-wr-calname', output.name)
        if output.description:
            cal.add('x-wr-caldesc', output.description)
        
        # Add events
        for event in events:
            try:
                # Parse the raw iCal event and add to calendar
                from icalendar import Event
                vevent = Event.from_ical(event.raw_ical)
                cal.add_component(vevent)
            except Exception as e:
                print(f"Error adding event {event.uid}: {e}")
        
        return cal.to_ical().decode('utf-8')
