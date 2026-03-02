import json
import os
from typing import Dict, List, Set, Optional

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
        self._migrate()

    def _migrate(self):
        migrated = False
        for sid, data in self._cache.items():
            if "event_uids" in data:
                data["manual_includes"] = data.pop("event_uids")
                migrated = True
            if "manual_excludes" not in data:
                data["manual_excludes"] = []
                migrated = True
            if "scope" not in data:
                data["scope"] = []
                migrated = True
            if "match_patterns" not in data:
                data["match_patterns"] = []
                migrated = True

        if "hidden" not in self._cache:
            self._cache["hidden"] = {
                "name": "Hidden Events",
                "color": None,
                "scope": [],
                "match_patterns": [],
                "manual_includes": [],
                "manual_excludes": []
            }
            migrated = True

        if migrated:
            self._save()
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
            "color": None,
            "scope": [],
            "match_patterns": [],
            "manual_includes": [],
            "manual_excludes": []
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
            
        if uid in self._cache[series_id]["manual_excludes"]:
            self._cache[series_id]["manual_excludes"].remove(uid)

        if uid not in self._cache[series_id]["manual_includes"]:
            self._cache[series_id]["manual_includes"].append(uid)
            self._save()
        return True

    def remove_event_from_series(self, series_id: str, uid: str) -> bool:
        if series_id not in self._cache:
            return False
            
        if uid in self._cache[series_id]["manual_includes"]:
            self._cache[series_id]["manual_includes"].remove(uid)
            
        if uid not in self._cache[series_id]["manual_excludes"]:
            self._cache[series_id]["manual_excludes"].append(uid)
            
        self._save()
        return True

    def update_series_color(self, series_id: str, color: Optional[str]) -> bool:
        if series_id in self._cache:
            self._cache[series_id]["color"] = color
            self._save()
            return True
        return False
        
    def get_series_for_event(self, uid: str, all_events: Dict) -> List[dict]:
        """Return a list of all series that contain this specific event UID after full resolution."""
        containing_series = []
        for sid, sdata in self._cache.items():
            if sid == "hidden":
                continue # Typically don't show the hidden series badge 
            resolved = self.resolve_series(sid, all_events)
            if uid in resolved:
                containing_series.append({"id": sid, "name": sdata["name"], "color": sdata.get("color")})
        return containing_series

    def resolve_series(self, series_id: str, all_events: Dict, resolved_path: Optional[Set[str]] = None) -> Set[str]:
        if resolved_path is None:
            resolved_path = set()
            
        if series_id in resolved_path:
            return set() # Prevent cyclic dependency infinite loops
            
        resolved_path.add(series_id)
        
        if series_id not in self._cache:
            resolved_path.remove(series_id)
            return set()
        
        series = self._cache[series_id]
        
        # 1. Resolve Scope
        scope_uids = set()
        scopes = series.get("scope", [])
        if not scopes:
            # Empty scope means all events globally universe
            scope_uids = set(all_events.keys())
        else:
            for s_id in scopes:
                scope_uids.update(self.resolve_series(s_id, all_events, resolved_path))
                
        # 2. Filter Pattern Evaluation
        matched_uids = set()
        patterns = series.get("match_patterns", [])
        
        has_star = "*" in patterns
        compiled_patterns = []
        
        import re
        for p in patterns:
            if p and p != "*":
                try:
                    compiled_patterns.append(re.compile(p, re.IGNORECASE))
                except Exception:
                    pass
        
        if has_star:
            matched_uids = set(scope_uids)
        elif compiled_patterns:
            for uid in scope_uids:
                event = all_events.get(uid)
                if event:
                    summary = str(event.get('SUMMARY', ''))
                    if any(cp.search(summary) for cp in compiled_patterns):
                        matched_uids.add(uid)

        # 3. Apply Forced Includes overrides
        manual_includes = set(series.get("manual_includes", []))
        
        # 4. Apply Forced Excludes overrides
        manual_excludes = set(series.get("manual_excludes", []))
        
        # Final mathematical Set Resolution Pipeline
        output_uids = (matched_uids | manual_includes) - manual_excludes
        
        resolved_path.remove(series_id)
        return output_uids & set(all_events.keys())
