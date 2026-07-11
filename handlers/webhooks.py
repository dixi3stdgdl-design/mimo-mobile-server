#!/usr/bin/env python3
"""
MiMo Mobile Webhook Handler
Receives webhooks from external services (Devin AI, GitHub, etc.)
and pushes real-time updates to connected mobile clients.
"""

import asyncio
import json
import time
import hashlib
import hmac
from typing import Dict, Any, Optional
from datetime import datetime

# Webhook secret for signature verification
WEBHOOK_SECRET = ""  # Set via environment variable

# Store for webhook events
webhook_events: list = []


class WebhookEvent:
    """Represents a webhook event."""
    
    def __init__(self, source: str, event_type: str, payload: Dict[str, Any]):
        self.id = hashlib.md5(f"{source}:{event_type}:{time.time()}".encode()).hexdigest()[:12]
        self.source = source
        self.event_type = event_type
        self.payload = payload
        self.timestamp = datetime.now().isoformat()
        self.delivered = False
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "event_type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "delivered": self.delivered
        }


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook signature (HMAC-SHA256)."""
    if not secret:
        return True  # Skip verification if no secret configured
    
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


async def handle_webhook(source: str, headers: Dict[str, str], body: bytes) -> Dict[str, Any]:
    """Process incoming webhook and push to connected clients."""
    
    # Verify signature if configured
    signature = headers.get("X-Hub-Signature-256", headers.get("X-Webhook-Signature", ""))
    if WEBHOOK_SECRET and not verify_webhook_signature(body, signature, WEBHOOK_SECRET):
        return {"status": "error", "message": "Invalid signature"}
    
    # Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON"}
    
    # Determine event type based on source
    event_type = determine_event_type(source, payload)
    
    # Create event
    event = WebhookEvent(source, event_type, payload)
    webhook_events.append(event)
    
    # Keep only last 100 events
    if len(webhook_events) > 100:
        webhook_events.pop(0)
    
    # Push to connected clients via WebSocket
    await push_to_clients(event)
    
    return {
        "status": "accepted",
        "event_id": event.id,
        "event_type": event_type
    }


def determine_event_type(source: str, payload: Dict[str, Any]) -> str:
    """Determine event type based on source and payload."""
    
    if source == "devin":
        # Devin AI events
        status = payload.get("status", "")
        if status == "completed":
            return "devin.task.completed"
        elif status == "failed":
            return "devin.task.failed"
        elif status == "running":
            return "devin.task.running"
        return "devin.task.update"
    
    elif source == "github":
        # GitHub events
        action = payload.get("action", "")
        if "pull_request" in payload:
            return f"github.pull_request.{action}"
        elif "push" in payload:
            return "github.push"
        elif "workflow_run" in payload:
            return "github.workflow_run"
        return f"github.{action}"
    
    elif source == "build":
        # Build system events
        return f"build.{payload.get('status', 'update')}"
    
    return f"{source}.update"


async def push_to_clients(event: WebhookEvent):
    """Push webhook event to all connected mobile clients."""
    # This would integrate with the WebSocket handler
    # For now, we'll just log it
    print(f"[WEBHOOK] Pushing event: {event.event_type} from {event.source}", flush=True)
    
    # The actual implementation would use the WebSocket state to send to all connected clients
    # Example:
    # for client_id, transport in state.connected_clients.items():
    #     send_json(transport, {
    #         "type": "webhook",
    #         "event": event.to_dict()
    #     })


def get_recent_events(limit: int = 20) -> list:
    """Get recent webhook events."""
    return [e.to_dict() for e in webhook_events[-limit:]]


def get_event_by_id(event_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific webhook event by ID."""
    for event in webhook_events:
        if event.id == event_id:
            return event.to_dict()
    return None


# ─── Devin-specific webhook handlers ─────────────────────────

async def handle_devin_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle webhook from Devin AI."""
    session_id = payload.get("session_id", "")
    status = payload.get("status", "")
    output = payload.get("output", [])
    
    event = WebhookEvent("devin", f"devin.task.{status}", {
        "session_id": session_id,
        "status": status,
        "output": output,
        "message": payload.get("message", "")
    })
    
    webhook_events.append(event)
    await push_to_clients(event)
    
    return {"status": "accepted", "event_id": event.id}


# ─── GitHub webhook handlers ─────────────────────────────────

async def handle_github_webhook(headers: Dict[str, str], body: bytes) -> Dict[str, Any]:
    """Handle webhook from GitHub."""
    event_type = headers.get("X-GitHub-Event", "unknown")
    
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid JSON"}
    
    event = WebhookEvent("github", f"github.{event_type}", payload)
    webhook_events.append(event)
    await push_to_clients(event)
    
    return {"status": "accepted", "event_id": event.id}
