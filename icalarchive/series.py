import json
import os
from typing import Dict, List, Set

class SeriesManager:
    def __init__(self, data_dir: str):
        self.file_path = os.path.join(data_dir, 'series.json')
        # Structure: { "series_id_or_name": { "name": "Series Name", "event_uids": ["uid1", "uid2"] } }
        self._cache: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
            except Exception as e:
                print(f"Error loading series: {e}")
                self._cache = {}
        else:
            self._cache = {}

    def _save(self):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=4)
        except Exception as e:
            print(f"Error saving series: {e}")

    def get_all_series(self) -> Dict[str, dict]:
        return self._cache

    def create_series(self, name: str) -> str:
        series_id = name.lower().replace(" ", "_")
        # Ensure unique ID
        base_id = series_id
        counter = 1
        while series_id in self._cache:
            series_id = f"{base_id}_{counter}"
            counter += 1
            
        self._cache[series_id] = {
            "name": name,
            "event_uids": []
        }
        self._save()
        return series_id

    def delete_series(self, series_id: str) -> bool:
        if series_id in self._cache:
            del self._cache[series_id]
            self._save()
            return True
        return False

    def add_event_to_series(self, series_id: str, uid: str) -> bool:
        if series_id not in self._cache:
            return False
            
        if uid not in self._cache[series_id]["event_uids"]:
            self._cache[series_id]["event_uids"].append(uid)
            self._save()
        return True

    def remove_event_from_series(self, series_id: str, uid: str) -> bool:
        if series_id not in self._cache:
            return False
            
        if uid in self._cache[series_id]["event_uids"]:
            self._cache[series_id]["event_uids"].remove(uid)
            self._save()
            return True
        return False
        
    def get_series_for_event(self, uid: str) -> List[dict]:
        """Return a list of all series that contain this specific event UID."""
        containing_series = []
        for s_id, data in self._cache.items():
            if uid in data.get("event_uids", []):
                containing_series.append({"id": s_id, "name": data["name"]})
        return containing_series
