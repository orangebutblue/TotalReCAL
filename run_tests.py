import httpx
import time
import sys
import subprocess
import shutil
from pathlib import Path

BASE_DIR = Path("/home/nezha/Documents/projects/TotalReCAL")
PYTHON = BASE_DIR / "venv" / "bin" / "python"

def start_instance(data_dir: str, port: int):
    path = BASE_DIR / data_dir
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    
    config_str = f"ui_port = {port}\ncalendar_port = {port}\n"
    with open(path / "config.toml", "w") as f:
        f.write(config_str)
        
    proc = subprocess.Popen([str(PYTHON), "-m", "icalarchive", str(path)],
                            cwd=BASE_DIR,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    return proc

def wait_for_server(port, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(f"http://localhost:{port}/")
            if r.status_code == 200:
                print(f"Server {port} is up")
                return True
        except:
            pass
        time.sleep(0.5)
    raise Exception(f"Server on port {port} didn't start")

def create_ics(filepath: Path, title: str, uid: str):
    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//TotalReCAL Test//EN
BEGIN:VEVENT
UID:{uid}
SUMMARY:{title}
DTSTART:20260301T100000Z
DTEND:20260301T110000Z
END:VEVENT
END:VCALENDAR"""
    with open(filepath, "w") as f:
        f.write(ics)

def main():
    print("Setting up static file server for mock ICS feeds...")
    static_dir = BASE_DIR / "test_calendars"
    if static_dir.exists():
        shutil.rmtree(static_dir)
    static_dir.mkdir()
    
    create_ics(static_dir / "cal1.ics", "Event 1 from Base", "uid1@test")
    create_ics(static_dir / "cal2.ics", "Event 2 from Base", "uid2@test")
    
    fs_proc = subprocess.Popen([str(PYTHON), "-m", "http.server", "8080"], cwd=static_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    
    procs = []
    
    try:
        # --- TEST CASE 1 ---
        print("\n\n====== TEST CASE 1 ======")
        print("Starting Instance 1 (port 8011)...")
        proc1 = start_instance("data1", 8011)
        procs.append(proc1)
        wait_for_server(8011)
        
        c1 = httpx.Client(base_url="http://localhost:8011")
        
        print("Subscribing to calendar...")
        c1.post("/api/sources", json={"name": "src1", "url": "http://localhost:8080/cal1.ics", "fetch_interval_minutes": 30})
        print("Forcing fetch...")
        c1.post("/api/sources/src1/fetch")
        time.sleep(0.5)
        
        print("Checking Display Contents (List Events API)...")
        events1 = c1.get("/api/events").json()['events']
        assert len(events1) > 0, "No events found"
        assert events1[0]['summary'] == "Event 1 from Base", "Incorrect Event summary"
        print(f" -> Found Event: {events1[0]['summary']}")
        
        print("Providing Feed (Creating Output)...")
        c1.post("/api/outputs", json={"name": "out1", "include_sources": [], "filter_by_category": [], "exclude_category": []})
        
        print("Checking Feed Correctness...")
        feed1 = c1.get("/cal/out1.ics").text
        assert "Event 1 from Base" in feed1, "Event not present in ICS feed!"
        print(" -> Output feed contains event correctly. Test Case 1 PASSED.")

        # --- TEST CASE 2 ---
        print("\n\n====== TEST CASE 2 ======")
        # Manual ICS data import is effectively exactly what we just did (pointing config to a static .ics file we just created).
        # We will create another source with our second example output.
        print("Importing another manually created ICS into Instance 1...")
        c1.post("/api/sources", json={"name": "src2", "url": "http://localhost:8080/cal2.ics", "fetch_interval_minutes": 30})
        c1.post("/api/sources/src2/fetch")
        time.sleep(0.5)
        
        print("Starting Instance 2 (port 8012)...")
        proc2 = start_instance("data2", 8012)
        procs.append(proc2)
        wait_for_server(8012)
        c2 = httpx.Client(base_url="http://localhost:8012")
        
        print("Instance 2 subscribing to Instance 1's feed...")
        c2.post("/api/sources", json={"name": "dep_feed", "url": "http://localhost:8011/cal/out1.ics", "fetch_interval_minutes": 30})
        c2.post("/api/sources/dep_feed/fetch")
        time.sleep(0.5)
        
        events2 = c2.get("/api/events").json()['events']
        summaries = [e['summary'] for e in events2]
        print(f" -> Instance 2 fetched summaries: {summaries}")
        assert "Event 1 from Base" in summaries, "Event 1 missing in instance 2"
        assert "Event 2 from Base" in summaries, "Event 2 missing in instance 2"
        print(" -> Events from Instance 1 successfully fetched by Instance 2. Test Case 2 PASSED.")
        
        # --- TEST CASE 3 ---
        print("\n\n====== TEST CASE 3 ======")
        # We have instance 1 (with Event 1 & 2), and instance 2.
        # Let's cleanly set up Instance 2 to provide its own feed with ONLY Event 2, and Instance 1 providing Event 1.
        # Wait, for true separation, let me just create an output in Instance 2:
        c2.post("/api/outputs", json={"name": "out2", "include_sources": []})
        
        print("Starting Instance 3 (port 8013)...")
        proc3 = start_instance("data3", 8013)
        procs.append(proc3)
        wait_for_server(8013)
        c3 = httpx.Client(base_url="http://localhost:8013")
        
        print("Instance 3 subscribing to feed from Instance 1 and feed from Instance 2...")
        c3.post("/api/sources", json={"name": "from_1", "url": "http://localhost:8011/cal/out1.ics", "fetch_interval_minutes": 30})
        c3.post("/api/sources", json={"name": "from_2", "url": "http://localhost:8012/cal/out2.ics", "fetch_interval_minutes": 30})
        c3.post("/api/sources/from_1/fetch")
        c3.post("/api/sources/from_2/fetch")
        time.sleep(0.5)
        
        print("Creating aggregator Output in Instance 3...")
        c3.post("/api/outputs", json={"name": "out3", "include_sources": []})
        
        print("Checking aggregator Output correctness...")
        feed3 = c3.get("/cal/out3.ics").text
        assert "Event 1 from Base" in feed3, "Missing Event 1 in aggregator"
        assert "Event 2 from Base" in feed3, "Missing Event 2 in aggregator"
        print(" -> Aggregator feed successfully contains events from all upstream sources! Test Case 3 PASSED.")
        
        # --- TEST CASE 4 ---
        print("\n\n====== TEST CASE 4 ======")
        print("Instance 1 has 'Event 1 from Base'. App hides/removes them from output feed, not by destroying DB items. Hiding it...")
        # Get its uid
        uid1 = [e['uid'] for e in events1 if e['summary'] == 'Event 1 from Base'][0]
        # Quote uid1 because it has @
        import urllib.parse
        c1.post(f"/api/events/{urllib.parse.quote(uid1, safe='')}/hide")
        
        print("Verifying it is deleted/hidden from Instance 1's feed...")
        feed1 = c1.get("/cal/out1.ics").text
        assert "Event 1 from Base" not in feed1, "Event 1 should be successfully deleted/hidden from Instance 1 feed"
        print(" -> Event 1 successfully removed from Instance 1 provided feed.")
        
        print("Fetching latest changes in Instance 3...")
        c3.post("/api/sources/from_1/fetch")
        time.sleep(0.5)
        
        print("Checking Instance 3 output feed for the missing event...")
        feed3_new = c3.get("/cal/out3.ics").text
        if "Event 1 from Base" in feed3_new:
            print(" -> Event 1 IS STILL RETAINED in Instance 3 because of permanent accumulation! The program perfectly handles disappearing events. Test Case 4 PASSED.")
        else:
            print(" -> ERROR: Event 1 vanished from Instance 3.")
            sys.exit(1)
            
    finally:
        print("\nCleaning up processes...")
        fs_proc.terminate()
        for p in procs:
            p.terminate()

if __name__ == "__main__":
    main()
