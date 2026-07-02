"""Session state management — memory and Redis backends."""

import json
import time
import threading
from typing import Any


class SessionStore:
    """Interface for session state storage."""

    def __init__(self):
        self.authorized_devices = set()
        self.connected_clients = set()
        self.processes = {}
        self.active_streams = {}

    def authorize(self, addr):
        self.authorized_devices.add(addr)

    def deauthorize(self, addr):
        self.authorized_devices.discard(addr)

    def is_authorized(self, addr):
        return addr in self.authorized_devices

    def add_client(self, client):
        self.connected_clients.add(client)

    def remove_client(self, client):
        self.connected_clients.discard(client)

    def client_count(self):
        return len(self.connected_clients)

    def register_process(self, msg_id, process):
        self.processes[msg_id] = process

    def unregister_process(self, msg_id):
        self.processes.pop(msg_id, None)

    def register_stream(self, msg_id, stream):
        self.active_streams[msg_id] = stream

    def stop_stream(self, msg_id):
        if msg_id in self.active_streams:
            self.active_streams[msg_id]["active"] = False
            del self.active_streams[msg_id]


class RedisSessionStore(SessionStore):
    """Redis-backed session store for multi-worker deployments."""

    def __init__(self, redis_url):
        import redis
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self._lock = threading.Lock()
        self._local_authorized = set()
        self._local_clients = set()
        super().__init__()
        print(f"[STATE] Redis session store connected: {redis_url}", flush=True)

    def authorize(self, addr):
        key = f"mimo:auth:{addr}"
        self.redis.set(key, "1", ex=3600)
        with self._lock:
            self._local_authorized.add(addr)

    def deauthorize(self, addr):
        key = f"mimo:auth:{addr}"
        self.redis.delete(key)
        with self._lock:
            self._local_authorized.discard(addr)

    def is_authorized(self, addr):
        if addr in self._local_authorized:
            return True
        key = f"mimo:auth:{addr}"
        return self.redis.exists(key)

    def add_client(self, client):
        addr = str(client.addr)
        self.redis.hset("mimo:clients", addr, json.dumps({
            "addr": addr,
            "connected_at": time.time()
        }))
        with self._lock:
            self._local_clients.add(client)

    def remove_client(self, client):
        addr = str(client.addr)
        self.redis.hdel("mimo:clients", addr)
        with self._lock:
            self._local_clients.discard(client)

    def client_count(self):
        return self.redis.hlen("mimo:clients")
