"""
src/audit/audit_logger.py
=========================
Security Audit Logging for Agency-Level Command Portal.
Records all sensitive authority interactions, incident acknowledgements,
resolutions, evidence inspections, and configuration reviews.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

class AuditLogger:
    """Appends and queries security audit events from JSONL storage."""

    def __init__(self, log_path: str = "data/audit/audit_log.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # In-memory recent cache
        self._cache: List[Dict[str, Any]] = []
        self._load_cache()

    def _load_cache(self, limit: int = 200) -> None:
        if not self.log_path.exists():
            return
        try:
            entries = []
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            continue
            self._cache = entries[-limit:]
        except Exception as e:
            print(f"[AuditLogger] Error loading cache: {e}")

    def log(
        self,
        action: str,
        actor: str = "Commander",
        role: str = "HIGHER_AUTHORITY",
        target_id: Optional[str] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an audit entry and persist it immediately."""
        entry = {
            "id": f"aud_{int(time.time() * 1000)}",
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "actor": actor,
            "role": role,
            "target_id": target_id,
            "details": details or "",
            "ip_address": ip_address or "127.0.0.1",
        }

        # Append to cache
        self._cache.append(entry)
        if len(self._cache) > 500:
            self._cache.pop(0)

        # Write to disk
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[AuditLogger] Failed to write log: {e}")

        return entry

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent audit log entries, newest first."""
        return list(reversed(self._cache[-limit:]))


# Global singleton
audit_logger = AuditLogger()
