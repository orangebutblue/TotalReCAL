from pathlib import Path
from icalendar import Calendar, Event
from datetime import datetime
from icalarchive.storage import EventStore
import tempfile

def test_retroactive_deduplication():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        store = EventStore(data_dir)
        source_name = "test_source"
        
        cal = Calendar()
        cal.add('prodid', '-//ICalArchive//EN')
        cal.add('version', '2.0')
        
        # Event 1
        e1 = Event()
        e1.add('UID', 'uid1@test')
        e1.add('SUMMARY', 'Doctor Appointment')
        e1.add('DTSTART', datetime(2023, 1, 1, 10, 0, 0))
        e1.add('DTEND', datetime(2023, 1, 1, 11, 0, 0))
        e1.add('LOCATION', 'Clinic Name')
        cal.add_component(e1)
        
        # Event 2 (Duplicate signature, different UID)
        e2 = Event()
        e2.add('UID', 'uid2@changed')
        e2.add('SUMMARY', 'Doctor Appointment')
        e2.add('DTSTART', datetime(2023, 1, 1, 10, 0, 0))
        e2.add('DTEND', datetime(2023, 1, 1, 11, 0, 0))
        e2.add('LOCATION', 'Clinic Name')
        cal.add_component(e2)
        
        # Event 3 (Different signature entirely)
        e3 = Event()
        e3.add('UID', 'uid3@test')
        e3.add('SUMMARY', 'Dentist Appointment')
        e3.add('DTSTART', datetime(2023, 1, 2, 10, 0, 0))
        e3.add('DTEND', datetime(2023, 1, 2, 11, 0, 0))
        e3.add('LOCATION', 'Tooth Place')
        cal.add_component(e3)
        
        # Manually write dirty state directly bypassing deduplication merge check
        store_path = store.get_store_path(source_name)
        with open(store_path, 'wb') as f:
            f.write(cal.to_ical())
            
        # Ensure 3 events loaded initially
        events_pre = store.load_store(source_name)
        assert len(events_pre) == 3
        
        # Run Deduplication
        removed = store.deduplicate_store(source_name)
        
        # Verify Results
        assert removed == 1
        
        events_post = store.load_store(source_name)
        assert len(events_post) == 2
        
        # Verify e3 is untouched and one of e1/e2 remains
        summaries = [str(ev.get('SUMMARY')) for ev in events_post.values()]
        assert summaries.count("Doctor Appointment") == 1
        assert summaries.count("Dentist Appointment") == 1
        print("Success! Deduplication stripped duplicate signature but kept unique.")

if __name__ == '__main__':
    test_retroactive_deduplication()
