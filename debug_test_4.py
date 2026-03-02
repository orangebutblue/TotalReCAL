import httpx, urllib.parse

c1 = httpx.Client(base_url="http://localhost:8011")
events1 = c1.get("/api/events").json()['events']
print("Got events:", [e['uid'] for e in events1])
uid1 = [e['uid'] for e in events1 if e['summary'] == 'Event 1 from Base'][0]
quoted_uid1 = urllib.parse.quote(uid1, safe='')
print("UID1:", uid1, "| Quoted:", quoted_uid1)

res = c1.post(f"/api/events/{quoted_uid1}/hide")
print("Hide response:", res.status_code, res.text)

r2 = c1.get("/cal/out1.ics")
print("Is Event 1 in feed1?", "Event 1 from Base" in r2.text)

import json
series_data = json.load(open('data1/series.json'))
print("Hidden series:", series_data.get('hidden'))
