from icalendar import Event
from datetime import datetime

e1 = Event()
e1.add('SUMMARY', 'Test Event')
e1.add('DTSTART', datetime(2023, 1, 1, 10, 0, 0))
e1.add('DTEND', datetime(2023, 1, 1, 11, 0, 0))
e1.add('LOCATION', 'Room 1')

e2 = Event()
e2.add('SUMMARY', 'Test Event')
e2.add('DTSTART', datetime(2023, 1, 1, 10, 0, 0))
e2.add('DTEND', datetime(2023, 1, 1, 11, 0, 0))
e2.add('LOCATION', 'Room 1')

def get_prop(comp, prop):
    p = comp.get(prop)
    return p.to_ical() if hasattr(p, 'to_ical') else p

print(get_prop(e1, 'SUMMARY'))
print(get_prop(e1, 'DTSTART'))
print(get_prop(e1, 'SUMMARY') == get_prop(e2, 'SUMMARY'))
print(get_prop(e1, 'DTSTART') == get_prop(e2, 'DTSTART'))

