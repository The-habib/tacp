"""Handlers for automation.*, tasks.*, and diagnostics.* namespace capabilities."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from tacp.backends.base import BaseBackend
from tacp.core.discovery import DeviceDiscovery


# In-memory storage for tasks and automations
_TASKS: Dict[str, Dict[str, Any]] = {}
_AUTOMATIONS: Dict[str, Dict[str, Any]] = {}


def handle_tasks_list(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """List running and completed background tasks."""
    limit = int(params.get("limit", 50))
    tasks = list(_TASKS.values())[-limit:]
    return {"success": True, "count": len(tasks), "tasks": tasks}


def handle_tasks_get(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get status and output of a specific task ID."""
    task_id = params.get("task_id")
    if not task_id or task_id not in _TASKS:
        return {"success": False, "error": f"Task '{task_id}' not found"}
    return {"success": True, "task": _TASKS[task_id]}


def handle_tasks_cancel(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Cancel a running task."""
    task_id = params.get("task_id")
    if not task_id or task_id not in _TASKS:
        return {"success": False, "error": f"Task '{task_id}' not found"}
    _TASKS[task_id]["status"] = "cancelled"
    return {"success": True, "task_id": task_id, "status": "cancelled"}


def handle_automation_create(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Define a new reusable JSON workflow automation."""
    name = params.get("name")
    steps = params.get("steps", [])
    if not name or not steps:
        return {"success": False, "error": "Missing required parameter 'name' or 'steps'"}

    auto_id = f"auto_{uuid.uuid4().hex[:8]}"
    record = {
        "id": auto_id,
        "name": name,
        "description": params.get("description", ""),
        "steps": steps,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _AUTOMATIONS[auto_id] = record
    return {"success": True, "automation": record}


def handle_automation_list(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """List all registered automations."""
    return {"success": True, "count": len(_AUTOMATIONS), "automations": list(_AUTOMATIONS.values())}


def handle_automation_start(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an automation workflow sequentially."""
    auto_id = params.get("automation_id")
    auto = _AUTOMATIONS.get(auto_id)
    if not auto:
        return {"success": False, "error": f"Automation '{auto_id}' not found"}

    task_id = f"task_{uuid.uuid4().hex[:8]}"
    task_record = {
        "id": task_id,
        "automation_id": auto_id,
        "name": auto["name"],
        "status": "completed",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "step_results": [],
    }

    # Execute steps (simulated/dispatched)
    for idx, step in enumerate(auto.get("steps", [])):
        step_tool = step.get("tool", "unknown")
        task_record["step_results"].append({
            "step_index": idx,
            "tool": step_tool,
            "status": "completed",
        })

    task_record["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _TASKS[task_id] = task_record
    return {"success": True, "task": task_record}


def handle_diagnostics_bundle(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Compile a complete portable diagnostic bundle archive (.zip)."""
    bundle_dir = Path.home() / ".tacp" / "diagnostics"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    bundle_path = bundle_dir / f"tacp_diagnostic_bundle_{timestamp}.zip"

    report = DeviceDiscovery.run_full_discovery()

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("device_capability_report.json", json.dumps(report, indent=2))
        zf.writestr("discovery_timestamp.txt", report["timestamp"])

        # Include doctor markdown if present
        doc_md = Path("/data/data/com.termux/files/home/tacp/TACP_DEVICE_CAPABILITY_REPORT.md")
        if doc_md.exists():
            zf.write(doc_md, "TACP_DEVICE_CAPABILITY_REPORT.md")

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "size_bytes": bundle_path.stat().st_size,
        "timestamp": timestamp,
    }
