import httpx
import time
import subprocess
import os

proc = subprocess.Popen(["./venv/bin/python", "-m", "icalarchive", "data98"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(2)

try:
    c = httpx.Client(base_url="http://localhost:8001")
    
    print("Posting an event hide...")
    res = c.post("/api/events/test%3A%3Auid1%40test/hide")
    print("Hide Res:", res.status_code, res.text)
    
    print("Checking series.json...")
    with open("data98/series.json") as f:
        print(f.read())
finally:
    proc.terminate()
    o, e = proc.communicate()
    print("--- SERVER STDOUT ---")
    print(o)
    print("--- SERVER STDERR ---")
    print(e)
