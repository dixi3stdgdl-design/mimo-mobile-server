#!/usr/bin/env python3
"""
Devin AI Integration Handler
Manages Devin CLI execution and real-time status updates.
"""

import asyncio
import json
import os
import subprocess
import time
import uuid
from typing import Optional, Dict, Any

# Devin configuration
DEVIN_API_KEY = os.environ.get("DEVIN_API_KEY", "")
DEVIN_CLI_PATH = os.environ.get("DEVIN_CLI_PATH", "devin")
WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", "/home/DexTer")

# In-memory store for active Devin sessions
devin_sessions: Dict[str, Dict[str, Any]] = {}


class DevinSession:
    """Manages a single Devin AI session."""
    
    def __init__(self, task: str, params: Dict[str, Any] = None):
        self.session_id = str(uuid.uuid4())[:8]
        self.task = task
        self.params = params or {}
        self.status = "pending"
        self.created_at = time.time()
        self.output = []
        self.error = None
        self.devin_session_id = None
        self.process = None
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task": self.task,
            "params": self.params,
            "status": self.status,
            "created_at": self.created_at,
            "output": self.output[-50:],  # Last 50 lines
            "error": self.error,
            "devin_session_id": self.devin_session_id
        }


async def execute_devin_task(task: str, params: Dict[str, Any] = None) -> DevinSession:
    """Execute a Devin AI task asynchronously."""
    session = DevinSession(task, params)
    devin_sessions[session.session_id] = session
    
    # Build the Devin command
    cmd = build_devin_command(task, params)
    
    session.status = "running"
    session.output.append(f"[{time.strftime('%H:%M:%S')}] Starting Devin task: {task}")
    
    try:
        # Execute in background
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=WORKSPACE_DIR
        )
        session.process = process
        session.output.append(f"[{time.strftime('%H:%M:%S')}] Process started with PID: {process.pid}")
        
        # Read output asynchronously
        asyncio.create_task(read_process_output(session, process))
        
    except Exception as e:
        session.status = "failed"
        session.error = str(e)
        session.output.append(f"[{time.strftime('%H:%M:%S')}] Error: {e}")
    
    return session


def build_devin_command(task: str, params: Dict[str, Any] = None) -> str:
    """Build the Devin CLI command."""
    # Parse task type and build appropriate command
    task_lower = task.lower()
    
    if "android" in task_lower and "build" in task_lower:
        # Android build task
        branch = params.get("branch", "main")
        return f'{DEVIN_CLI_PATH} run "Review the latest push to branch {branch} and fix Android compilation warnings"'
    
    elif "bug" in task_lower or "error" in task_lower:
        # Bug fix task
        description = params.get("description", task)
        return f'{DEVIN_CLI_PATH} run "{description}"'
    
    elif "review" in task_lower or "pr" in task_lower:
        # Code review task
        pr_url = params.get("pr_url", "")
        if pr_url:
            return f'{DEVIN_CLI_PATH} run "Review pull request {pr_url} and provide feedback"'
        return f'{DEVIN_CLI_PATH} run "Review the latest changes and suggest improvements"'
    
    elif "test" in task_lower:
        # Testing task
        return f'{DEVIN_CLI_PATH} run "Write and run tests for the recent changes"'
    
    elif "deploy" in task_lower:
        # Deployment task
        return f'{DEVIN_CLI_PATH} run "Prepare deployment for the latest changes"'
    
    else:
        # Generic task
        return f'{DEVIN_CLI_PATH} run "{task}"'


async def read_process_output(session: DevinSession, process: asyncio.subprocess.Process):
    """Read and store process output."""
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded = line.decode().strip()
            session.output.append(f"[{time.strftime('%H:%M:%S')}] {decoded}")
            
            # Try to extract Devin session ID
            if "Session ID:" in decoded or "session_id" in decoded:
                session.devin_session_id = decoded.split(":")[-1].strip()
            
            # Check for completion signals
            if "completed" in decoded.lower() or "finished" in decoded.lower():
                session.status = "completed"
            elif "error" in decoded.lower() or "failed" in decoded.lower():
                session.status = "failed"
        
        # Wait for process to complete
        await process.wait()
        
        if session.status == "running":
            session.status = "completed" if process.returncode == 0 else "failed"
        
        session.output.append(f"[{time.strftime('%H:%M:%S')}] Process completed with exit code: {process.returncode}")
        
    except Exception as e:
        session.status = "failed"
        session.error = str(e)
        session.output.append(f"[{time.strftime('%H:%M:%S')}] Error reading output: {e}")


async def get_session_status(session_id: str) -> Optional[Dict[str, Any]]:
    """Get the status of a Devin session."""
    session = devin_sessions.get(session_id)
    if session:
        return session.to_dict()
    return None


async def list_sessions() -> list:
    """List all active Devin sessions."""
    return [s.to_dict() for s in devin_sessions.values()]


async def cancel_session(session_id: str) -> bool:
    """Cancel a running Devin session."""
    session = devin_sessions.get(session_id)
    if session and session.process:
        session.process.terminate()
        session.status = "cancelled"
        session.output.append(f"[{time.strftime('%H:%M:%S')}] Task cancelled by user")
        return True
    return False


def handle_devin_webhook(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle incoming webhook from MiMo Mobile."""
    action = data.get("action", "")
    task = data.get("task", "")
    params = data.get("params", {})
    
    if action == "execute":
        # Schedule async execution
        asyncio.create_task(execute_devin_task(task, params))
        return {"status": "accepted", "message": "Task queued for execution"}
    
    elif action == "status":
        session_id = data.get("session_id", "")
        return asyncio.ensure_future(get_session_status(session_id))
    
    elif action == "list":
        return asyncio.ensure_future(list_sessions())
    
    elif action == "cancel":
        session_id = data.get("session_id", "")
        return asyncio.ensure_future(cancel_session(session_id))
    
    return {"status": "error", "message": "Unknown action"}
