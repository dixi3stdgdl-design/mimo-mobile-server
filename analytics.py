"""
Persistent analytics and telemetry module.

Stores:
- Connection events (daily unique users, session duration)
- Feature usage (chat, files, terminal, remote desktop)
- Performance metrics (latency, throughput)

Storage: SQLite (no external deps required)
"""

import os
import sqlite3
import time
import threading
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from collections import defaultdict


class AnalyticsDB:
    """SQLite-based analytics storage."""

    def __init__(self, db_path: str = None):
        # Try multiple paths for compatibility
        default_paths = [
            "/data/analytics.db",  # Docker
            os.path.expanduser("~/.mimo/analytics.db"),  # Local
        ]
        
        self.db_path = db_path or os.environ.get("MIMO_ANALYTICS_DB", "")
        
        if not self.db_path:
            for path in default_paths:
                try:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    # Test if we can write
                    test_conn = sqlite3.connect(path)
                    test_conn.close()
                    self.db_path = path
                    break
                except (sqlite3.OperationalError, PermissionError):
                    continue
        
        if not self.db_path:
            # Fallback to temp directory
            import tempfile
            self.db_path = os.path.join(tempfile.gettempdir(), "mimo_analytics.db")
        
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                device_id TEXT,
                connected_at REAL NOT NULL,
                disconnected_at REAL,
                ip_address TEXT,
                user_agent TEXT,
                tier TEXT DEFAULT 'free'
            );
            
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                event_data TEXT,
                timestamp REAL NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT NOT NULL,
                metric TEXT NOT NULL,
                value REAL NOT NULL,
                PRIMARY KEY (date, metric)
            );
            
            CREATE INDEX IF NOT EXISTS idx_connections_user ON connections(user_id);
            CREATE INDEX IF NOT EXISTS idx_connections_date ON connections(connected_at);
            CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
        """)
        conn.commit()

    def close(self):
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


class Analytics:
    """Analytics tracker for MiMo Server."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled and os.environ.get("MIMO_ANALYTICS_ENABLED", "true").lower() == "true"
        self.db = AnalyticsDB() if self.enabled else None
        self._flush_interval = 60  # seconds
        self._event_buffer = []
        self._buffer_lock = threading.Lock()
        
        if self.enabled:
            self._start_flush_thread()

    def _start_flush_thread(self):
        def flush_loop():
            while True:
                time.sleep(self._flush_interval)
                self._flush_buffer()
        
        t = threading.Thread(target=flush_loop, daemon=True)
        t.start()

    def _flush_buffer(self):
        with self._buffer_lock:
            if not self._event_buffer:
                return
            events = self._event_buffer[:]
            self._event_buffer.clear()

        if self.db and events:
            conn = self.db._get_conn()
            conn.executemany(
                "INSERT INTO events (user_id, event_type, event_data, timestamp) VALUES (?, ?, ?, ?)",
                [(e["user_id"], e["event_type"], json.dumps(e.get("event_data")), e["timestamp"]) for e in events]
            )
            conn.commit()

    # ─── Connection Tracking ──────────────────────────────────────────

    def track_connection(self, user_id: str, device_id: str = None, 
                         ip_address: str = None, user_agent: str = None,
                         tier: str = "free") -> int:
        """Track a new connection. Returns connection ID."""
        if not self.enabled:
            return 0

        conn = self.db._get_conn()
        cursor = conn.execute(
            """INSERT INTO connections (user_id, device_id, connected_at, ip_address, user_agent, tier)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, device_id, time.time(), ip_address, user_agent, tier)
        )
        conn.commit()
        
        # Update daily unique users
        today = datetime.now().strftime("%Y-%m-%d")
        self._update_daily_stat(today, "unique_users", user_id)
        
        return cursor.lastrowid

    def track_disconnection(self, user_id: str):
        """Track disconnection."""
        if not self.enabled:
            return

        conn = self.db._get_conn()
        conn.execute(
            """UPDATE connections SET disconnected_at = ? 
               WHERE user_id = ? AND disconnected_at IS NULL""",
            (time.time(), user_id)
        )
        conn.commit()

    # ─── Event Tracking ───────────────────────────────────────────────

    def track_event(self, user_id: str, event_type: str, event_data: dict = None):
        """Track a user event (buffered for performance)."""
        if not self.enabled:
            return

        event = {
            "user_id": user_id,
            "event_type": event_type,
            "event_data": event_data,
            "timestamp": time.time()
        }

        with self._buffer_lock:
            self._event_buffer.append(event)
            
            # Flush if buffer is large
            if len(self._event_buffer) >= 100:
                events = self._event_buffer[:]
                self._event_buffer.clear()
                
                conn = self.db._get_conn()
                conn.executemany(
                    "INSERT INTO events (user_id, event_type, event_data, timestamp) VALUES (?, ?, ?, ?)",
                    [(e["user_id"], e["event_type"], json.dumps(e.get("event_data")), e["timestamp"]) for e in events]
                )
                conn.commit()

    # ─── Convenience Methods ──────────────────────────────────────────

    def track_chat(self, user_id: str, message_length: int):
        self.track_event(user_id, "chat", {"length": message_length})

    def track_file_operation(self, user_id: str, operation: str, path: str):
        self.track_event(user_id, "file_op", {"op": operation, "path": path})

    def track_terminal_command(self, user_id: str, command: str):
        self.track_event(user_id, "terminal", {"command": command[:100]})

    def track_screen_stream(self, user_id: str, duration: float):
        self.track_event(user_id, "screen_stream", {"duration": duration})

    def track_adb_command(self, user_id: str, device: str, action: str):
        self.track_event(user_id, "adb", {"device": device, "action": action})

    # ─── Daily Stats ──────────────────────────────────────────────────

    def _update_daily_stat(self, date: str, metric: str, unique_key: str):
        """Update daily unique count."""
        conn = self.db._get_conn()
        
        # Check if already counted
        existing = conn.execute(
            "SELECT value FROM daily_stats WHERE date = ? AND metric = ?",
            (date, f"{metric}:{unique_key}")
        ).fetchone()
        
        if not existing:
            conn.execute(
                "INSERT OR REPLACE INTO daily_stats (date, metric, value) VALUES (?, ?, 1)",
                (date, f"{metric}:{unique_key}")
            )
            conn.commit()

    # ─── Queries ──────────────────────────────────────────────────────

    def get_daily_active_users(self, days: int = 30) -> List[Dict]:
        """Get daily active users for the last N days."""
        if not self.enabled:
            return []

        conn = self.db._get_conn()
        since = time.time() - (days * 86400)
        
        rows = conn.execute("""
            SELECT DATE(connected_at, 'unixepoch') as date, COUNT(DISTINCT user_id) as users
            FROM connections
            WHERE connected_at > ?
            GROUP BY date
            ORDER BY date
        """, (since,)).fetchall()
        
        return [{"date": r["date"], "users": r["users"]} for r in rows]

    def get_retention(self, days: int = 30) -> List[Dict]:
        """Get user retention (users who returned after first visit)."""
        if not self.enabled:
            return []

        conn = self.db._get_conn()
        since = time.time() - (days * 86400)
        
        # First visit per user
        first_visits = conn.execute("""
            SELECT user_id, MIN(connected_at) as first_visit
            FROM connections
            WHERE connected_at > ?
            GROUP BY user_id
        """, (since,)).fetchall()
        
        # Return visits
        result = []
        for fv in first_visits:
            returns = conn.execute("""
                SELECT COUNT(*) as return_count
                FROM connections
                WHERE user_id = ? AND connected_at > ?
            """, (fv["user_id"], fv["first_visit"] + 86400)).fetchone()
            
            result.append({
                "user_id": fv["user_id"],
                "first_visit": datetime.fromtimestamp(fv["first_visit"]).strftime("%Y-%m-%d"),
                "return_count": returns["return_count"]
            })
        
        return result

    def get_feature_usage(self, days: int = 7) -> Dict[str, int]:
        """Get feature usage counts."""
        if not self.enabled:
            return {}

        conn = self.db._get_conn()
        since = time.time() - (days * 86400)
        
        rows = conn.execute("""
            SELECT event_type, COUNT(*) as count
            FROM events
            WHERE timestamp > ?
            GROUP BY event_type
        """, (since,)).fetchall()
        
        return {r["event_type"]: r["count"] for r in rows}

    def get_connection_stats(self) -> Dict:
        """Get current connection statistics."""
        if not self.enabled:
            return {}

        conn = self.db._get_conn()
        
        # Active connections
        active = conn.execute(
            "SELECT COUNT(*) as count FROM connections WHERE disconnected_at IS NULL"
        ).fetchone()["count"]
        
        # Today's connections
        today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
        today = conn.execute(
            "SELECT COUNT(DISTINCT user_id) as users FROM connections WHERE connected_at > ?",
            (today_start,)
        ).fetchone()["users"]
        
        # Total users
        total = conn.execute(
            "SELECT COUNT(DISTINCT user_id) as count FROM connections"
        ).fetchone()["count"]
        
        return {
            "active_connections": active,
            "today_unique_users": today,
            "total_users": total
        }

    def export_report(self, days: int = 7) -> Dict:
        """Export a comprehensive analytics report."""
        return {
            "period": f"Last {days} days",
            "daily_active_users": self.get_daily_active_users(days),
            "feature_usage": self.get_feature_usage(days),
            "connection_stats": self.get_connection_stats(),
            "retention": self.get_retention(days)[:100]  # Limit to 100 users
        }


# Singleton
_analytics = None

def get_analytics() -> Analytics:
    global _analytics
    if _analytics is None:
        _analytics = Analytics()
    return _analytics
