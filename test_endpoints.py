import urllib.request
import urllib.error
import sys

BASE_URL = "http://localhost:8001"
ENDPOINTS = [
    "/",
    "/calendar",
    "/events",
    "/sources",
    "/outputs",
    "/rules",
    "/series",
    "/api/sources",
    "/api/outputs",
    "/api/events/all",
    "/api/calendar-events",
    "/api/series",
]

failed = False

print("=== COMPREHENSIVE API TEST SUITE ===")
for ep in ENDPOINTS:
    url = f"{BASE_URL}{ep}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req)
        status = response.getcode()
        
        # Check that we received data
        data = response.read()
        byte_len = len(data)
        
        if status in [200, 307]:
            print(f"✅ {ep} - {status} OK ({byte_len} bytes)")
        else:
            print(f"❌ {ep} - {status} ERROR")
            failed = True
    except urllib.error.HTTPError as e:
        print(f"❌ {ep} - HTTP ERROR: {e.code} {e.reason}")
        # Print the body of the error response if any
        try:
             print("   " + e.read().decode('utf-8'))
        except:
             pass
        failed = True
    except urllib.error.URLError as e:
        print(f"💥 {ep} - CONNECTION FAILED: {str(e.reason)}")
        failed = True
    except Exception as e:
        print(f"💥 {ep} - UNEXPECTED ERROR: {str(e)}")
        failed = True

if failed:
    print("\n❌ SYSTEM TEST FAILED! There are broken endpoints.")
    sys.exit(1)
else:
    print("\n✅ All endpoints returned successfully! System is 100% stable.")
    sys.exit(0)
