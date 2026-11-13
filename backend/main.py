"""
SHADOW Backend — FastAPI application.
Port: 8001
"""
import uuid
import sys
import os
import re

# Allow running from project root with: python -c "import sys; sys.path.insert(0,'backend'); import main"
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime
from pathlib import Path
import sqlite3
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from typing import Optional

from config import GEMINI_API_KEY, SCREENSHOT_DIR, STREAMCOVE_URL, is_streamcove_url, MAX_STEPS
from loop_detector import LoopDetector
from navigation_policy import classify_navigation, preferred_membership_link
from provider_routes import get_provider_route, match_provider_action
from database import (
    init_db,
    create_task,
    get_task,
    update_task_status,
    increment_steps,
    log_action,
    get_pending_approval,
    create_approval,
    resolve_approval,
    get_db,
)
from shadow_scan import ShadowScan
from shadow_lock import ShadowLock
from shadow_navigate import ShadowNavigate, optimizer
from shadow_trail import ShadowTrail
from boundaries import SnapshotBoundary, ActionBoundary

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="SHADOW Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scanner = ShadowScan()
locker = ShadowLock()
navigator = ShadowNavigate()
trail = ShadowTrail()
action_boundary = ActionBoundary()
loop_detector = LoopDetector()


def verify_streamcove_cancellation(user_id: str = "demo") -> bool:
    """Verify that the subscription was genuinely cancelled in StreamCove."""
    try:
        import urllib.request
        import json
        req = urllib.request.Request(f"{STREAMCOVE_URL}/api/subscription?user_id={user_id}")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode())
            return data.get("status") == "cancelled"
    except Exception:
        pass
    return False


@app.on_event("startup")
async def on_startup():
    init_db()


# ── Request / Response models ─────────────────────────────────────────────────

class CreateTaskRequest(BaseModel):
    instruction: str
    user_id: str = "default"
    mode: str = "observe"  # "observe", "guide", "demo"
    url: Optional[str] = None


class UpdateTaskStatusRequest(BaseModel):
    status: str


class NavigateRequest(BaseModel):
    task_id: str
    page_snapshot: dict  # {url, elements[], page_text}


class ApproveRequest(BaseModel):
    approved: bool


class ScreenshotRequest(BaseModel):
    task_id: str
    screenshot_b64: str
    label: str = "screenshot"


class PermitDomainRequest(BaseModel):
    domain: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "gemini_configured": bool(GEMINI_API_KEY)}


@app.post("/api/demo/reset")
async def demo_reset(request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    if client_ip not in ("127.0.0.1", "localhost", "::1", "testclient"):
        raise HTTPException(status_code=403, detail="Demo reset is restricted to localhost demo environment")
    conn = get_db()
    conn.execute(
        "UPDATE tasks SET status='cancelled', updated_at=? WHERE status='active'",
        (datetime.utcnow().isoformat(),),
    )
    conn.commit()
    conn.close()
    return {
        "success": True,
        "message": "Demo active tasks reset to cancelled safely. Audit trail and evidence preserved.",
    }


@app.post("/api/permissions/permit")
async def permit_domain_endpoint(body: PermitDomainRequest):
    domain = body.domain.lower().strip()
    SnapshotBoundary.permit_domain(domain)
    return {"permitted": True, "domain": domain}


@app.post("/api/task")
async def create_task_endpoint(body: CreateTaskRequest):
    task_id = str(uuid.uuid4())
    req_mode = body.mode
    if req_mode == "demo" and body.url and not is_streamcove_url(body.url):
        req_mode = "guide"

    # authorized_goal mirrors instruction — the LLM never modifies it
    task = create_task(
        task_id=task_id,
        user_instruction=body.instruction,
        authorized_goal=body.instruction,
        mode=req_mode,
    )
    if body.url:
        try:
            from urllib.parse import urlparse
            p_host = (urlparse(body.url).hostname or "").lower()
            if p_host and not (p_host.startswith("169.254.") or p_host.startswith("10.") or p_host.startswith("192.168.") or p_host == "0.0.0.0"):
                SnapshotBoundary.permit_domain(p_host)
        except Exception:
            pass
        update_task_status(task_id, task["status"], current_url=body.url)
    return {"task_id": task_id, "status": task["status"], "mode": task.get("mode", req_mode)}


@app.get("/api/task/{task_id}")
async def get_task_endpoint(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.patch("/api/task/{task_id}/status")
async def update_status_endpoint(task_id: str, body: UpdateTaskStatusRequest):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    allowed_transitions = {"pause", "resume", "cancel", "halt", "paused", "active", "cancelled", "completed", "failed", "halted"}
    status_map = {
        "pause": "paused",
        "resume": "active",
        "cancel": "cancelled",
        "halt": "halted",
    }
    new_status = status_map.get(body.status, body.status)

    if new_status not in {"active", "paused", "completed", "failed", "cancelled", "halted"}:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")

    current_status = task.get("status")
    if current_status in {"completed", "cancelled", "halted"} and new_status in {"paused", "active"}:
        return {"task_id": task_id, "status": current_status, "ok": False,
                "error": f"Task is {current_status}. Start New Task to continue."}

    update_task_status(task_id, new_status)
    return {"task_id": task_id, "status": new_status, "ok": True}


@app.post("/api/navigate")
async def navigate_endpoint(body: NavigateRequest):
    task_id = body.task_id

    # 1. Phase 4 Input Boundary: Validate and sanitize untrusted page snapshot
    try:
        validated_snapshot = SnapshotBoundary.sanitize_snapshot(body.page_snapshot)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid page snapshot: {str(e)}")

    page_snapshot = validated_snapshot.model_dump()

    # 2. Verify task exists and is active
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] not in ("active",):
        raise HTTPException(
            status_code=409,
            detail=f"Task is not active (status: {task['status']}). Resume it first."
        )

    # Update current URL
    url = page_snapshot.get("url", "")
    if url:
        update_task_status(task_id, task["status"], current_url=url)

    # 3. Run Context-Aware ShadowScan (Phase 3 Hybrid Detector)
    detections = scanner.scan_all(page_snapshot, task_id)

    # Boundary: Enforce Demo Mode origin — strictly restricted to StreamCove
    task_mode = task.get("mode", "demo" if is_streamcove_url(url) else "observe")
    if task_mode == "demo" and not is_streamcove_url(url):
        halt_msg = f"Demo Mode is restricted to StreamCove demonstration environment ({url} is external). Task halted."
        update_task_status(task_id, "halted", current_url=url)
        log_action(
            task_id=task_id,
            step_number=task.get("steps_taken", 0),
            action_type="blocked",
            element_id="",
            element_text="",
            reason=halt_msg,
            result="blocked",
        )
        return {
            "action": {
                "action": "stop",
                "element_id": "",
                "value": "",
                "reason": halt_msg,
                "confidence": 1.0,
            },
            "detections": detections,
            "requires_approval": False,
            "approval_id": None,
            "blocked": True,
            "block_reason": "demo_mode_restricted_to_streamcove",
            "status": "halted",
        }

    # 4. If scan finds prompt_injection → block immediately
    prompt_injection_detected = (
        any(d["category"] == "prompt_injection" for d in detections)
        or "contains_suspicious_override_payload" in validated_snapshot.untrusted_flags
    )
    if prompt_injection_detected:
        blocked_action = {
            "action": "stop",
            "element_id": "",
            "value": "",
            "reason": "PROMPT INJECTION DETECTED: The page attempted to override your instructions. Task halted for safety.",
            "confidence": 1.0,
        }
        log_action(
            task_id=task_id,
            step_number=task.get("steps_taken", 0),
            action_type="blocked",
            element_id="",
            element_text="",
            reason="Prompt injection detected on page",
            result="blocked",
        )
        return {
            "action": blocked_action,
            "detections": detections,
            "requires_approval": False,
            "approval_id": None,
            "blocked": True,
            "block_reason": "prompt_injection",
        }

    provider_route = None
    route_step = None
    if task.get("mode") in {"observe", "guide"}:
        provider_route = get_provider_route(
            url, task.get("authorized_goal", task.get("user_instruction", "")))
        if provider_route:
            route_step = match_provider_action(provider_route, validated_snapshot.model_dump())

    if route_step and route_step.get("handoff"):
        reason = f"This subscription is billed through {route_step['handoff']}. Manage it there."
        update_task_status(task_id, "paused")
        increment_steps(task_id)
        log_action(task_id=task_id, step_number=(task.get("steps_taken") or 0) + 1,
                   action_type="ask_user", element_id="", element_text=route_step["handoff"],
                   reason=reason, result="provider_handoff")
        return {"action": {"action": "ask_user", "element_id": "", "value": "",
                            "reason": reason, "confidence": 1.0},
                "detections": detections, "requires_approval": False, "approval_id": None,
                "blocked": False, "mode": task.get("mode"), "status": "paused",
                "route_provider": route_step["provider"], "route_help_url": route_step["help_url"],
                "route_step": "partner_handoff", "route_handoff": route_step["handoff"]}

    if route_step and route_step.get("action"):
        # First-party documentation supplies the step order; the selected DOM
        # control still has to pass ActionBoundary, ShadowLock and nav policy.
        action = {**route_step["action"], "planner": "provider_route"}
    else:
        # 5. Check GEMINI key before calling planner
        if not GEMINI_API_KEY:
            raise HTTPException(
                status_code=503,
                detail="GEMINI_API_KEY is not configured. Please add it to your .env file or use a supported provider route."
            )

        # 6. Get action history for context
        conn = get_db()
        history_rows = conn.execute(
            "SELECT * FROM actions WHERE task_id = ? ORDER BY step_number, id",
            (task_id,)
        ).fetchall()
        history = [dict(r) for r in history_rows]
        conn.close()

        # 7. Call ShadowNavigate with Cost Optimization (Phase 6)
        try:
            action = navigator.plan_next_action(page_snapshot, task, history)
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI planning error: {str(e)}")

    # 8. Phase 5 Output Boundary: Validate proposed action against DOM and safety rules
    is_valid, boundary_err, validated_action = action_boundary.validate_action(
        action, validated_snapshot, task
    )
    if not is_valid:
        is_step_budget = "Maximum navigation step budget reached" in str(boundary_err)
        if is_step_budget:
            update_task_status(task_id, "halted")

        log_action(
            task_id=task_id,
            step_number=task.get("steps_taken", 0),
            action_type="blocked",
            element_id=action.get("element_id", ""),
            element_text=action.get("element_text", ""),
            reason=boundary_err or "Action rejected by ActionBoundary",
            result="blocked",
        )
        return {
            "action": {
                "action": "stop",
                "element_id": "",
                "value": "",
                "reason": f"Action blocked: {boundary_err}",
                "confidence": 1.0,
            },
            "detections": detections,
            "requires_approval": False,
            "approval_id": None,
            "blocked": True,
            "block_reason": boundary_err,
            "status": "halted" if is_step_budget else None,
        }

    # 9. Validate returned action with ShadowLock
    is_allowed, block_reason = locker.validate_action(action, task)
    if not is_allowed:
        log_action(
            task_id=task_id,
            step_number=task.get("steps_taken", 0),
            action_type="blocked",
            element_id=action.get("element_id", ""),
            element_text=action.get("element_text", ""),
            reason=block_reason,
            result="blocked",
        )
        return {
            "action": {
                "action": "stop",
                "element_id": "",
                "value": "",
                "reason": f"Action blocked by ShadowLock: {block_reason}",
                "confidence": 1.0,
            },
            "detections": detections,
            "requires_approval": False,
            "approval_id": None,
            "blocked": True,
            "block_reason": block_reason,
        }

    # 10. Check operating mode & approval requirements (Phase 5 & 7)
    task_mode = task.get("mode", "demo" if "localhost" in url or "127.0.0.1" in url else "observe")
    
    if task_mode in {"observe", "guide"} and action.get("action") not in {"stop"}:
        if (task_mode == "observe" and action.get("action") == "click"
                and action.get("confidence", 0) >= 0.85
                and re.search(r"\b(cancel|cancellation|subscription|membership)\b",
                              task.get("authorized_goal", task.get("user_instruction", "")), re.I)):
            # Provider route matching already selected and verified the next
            # official step. Do not let this generic heuristic replace a
            # consequential final control with a nearby menu opener.
            preferred = None if route_step else preferred_membership_link(page_snapshot)
            if preferred and preferred["element_id"] != action.get("element_id"):
                preferred = {**action, "element_id": preferred["element_id"],
                             "reason": "Use the verified same-origin membership navigation link."}
                candidate_valid, _, candidate_action = action_boundary.validate_action(
                    preferred, validated_snapshot, task)
                if candidate_valid:
                    candidate_allowed, _ = locker.validate_action(candidate_action.model_dump(), task)
                    if candidate_allowed:
                        action = candidate_action.model_dump()
        policy = classify_navigation(action, page_snapshot)
        waiting = task_mode == "guide" or not policy["reversible"]
        action = {**action, "element_text": policy["label"],
                  "action": "highlight" if waiting else "click"}
        # Observe returns early below, so it must still use the semantic loop
        # detector. Guide remains user-driven and deliberately bypasses this.
        if task_mode == "observe" and not waiting:
            is_stalled, _, stall_reason = loop_detector.record_step(
                task_id, page_snapshot, action, semantic_only=True)
            if is_stalled:
                update_task_status(task_id, "halted")
                log_action(task_id=task_id, step_number=task.get("steps_taken", 0),
                           action_type="blocked", element_id=action.get("element_id", ""),
                           element_text=policy["label"], reason=stall_reason or "Navigation stalled.",
                           result="blocked")
                return {"action": {"action": "stop", "element_id": "", "value": "",
                                    "reason": stall_reason or "Navigation stalled.", "confidence": 1.0},
                        "detections": detections, "requires_approval": False, "approval_id": None,
                        "blocked": True, "block_reason": "loop_stalled", "mode": task_mode,
                        "status": "halted"}
        if waiting:
            update_task_status(task_id, "paused")
        increment_steps(task_id)
        log_action(task_id=task_id, step_number=(task.get("steps_taken") or 0) + 1,
                   action_type=action["action"], element_id=action.get("element_id", ""),
                   element_text=policy["label"], reason=action.get("reason", ""),
                   result="waiting_on_page" if waiting else "reversible_navigation")
        return {"action": action, "detections": detections, "requires_approval": False,
                "approval_id": None, "blocked": False, "block_reason": None,
                "mode": task_mode, "status": "paused" if waiting else "active",
                "waiting_for_user": waiting, "reversible": policy["reversible"],
                "navigation_target": policy["target"],
                "policy_decision": "auto_navigate" if policy["reversible"] and not waiting else "review_on_page",
                "guidance": policy["guidance"],
                "stalled_guidance": route_step.get("stalled_guidance") if route_step else None,
                "route_provider": route_step.get("provider") if route_step else None,
                "route_help_url": route_step.get("help_url") if route_step else None,
                "route_step": route_step.get("route_step") if route_step else None,
                "planner": action.get("planner", "gemini")}

    # Mode C: Demo / Standard Consequential Check
    needs_approval = locker.requires_approval(action, page_snapshot)
    approval_id = None

    if needs_approval:
        approval_id = create_approval(
            task_id=task_id,
            action_description=action.get("reason", f"{action['action']} on {action.get('element_id', '')}"),
            target_url=url,
            element_id=action.get("element_id", ""),
        )
        return {
            "action": action,
            "detections": detections,
            "requires_approval": True,
            "approval_id": approval_id,
            "blocked": False,
            "block_reason": None,
            "mode": task_mode,
        }

    # Loop and stall detection: monitor state changes and repeated actions
    is_stalled, change_desc, stall_reason = loop_detector.record_step(task_id, page_snapshot, action)
    if is_stalled:
        update_task_status(task_id, "halted")
        log_action(
            task_id=task_id,
            step_number=task.get("steps_taken", 0),
            action_type="blocked",
            element_id=action.get("element_id", ""),
            element_text=action.get("element_text", ""),
            reason=f"Navigation stalled: {stall_reason}",
            result="blocked",
        )
        return {
            "action": {
                "action": "stop",
                "element_id": "",
                "value": "",
                "reason": f"Navigation stalled: {stall_reason}",
                "confidence": 1.0,
            },
            "detections": detections,
            "requires_approval": False,
            "approval_id": None,
            "blocked": True,
            "block_reason": "loop_stalled",
            "status": "halted",
        }

    # 11. Log action and increment step counter
    increment_steps(task_id)
    dispatch_result = f"dispatched ({change_desc})" if change_desc else "dispatched"
    log_action(
        task_id=task_id,
        step_number=task.get("steps_taken", 0) + 1,
        action_type=action.get("action", ""),
        element_id=action.get("element_id", ""),
        element_text=action.get("element_text", ""),
        reason=action.get("reason", ""),
        result=dispatch_result,
    )

    # Mark completed or halted if stop action
    final_status = "active"
    if action.get("action") == "stop":
        if is_streamcove_url(url):
            is_cancelled = verify_streamcove_cancellation()
            final_status = "completed" if is_cancelled else "halted"
        else:
            final_status = "completed"
        update_task_status(task_id, final_status)

    return {
        "action": action,
        "detections": detections,
        "requires_approval": False,
        "approval_id": None,
        "blocked": False,
        "block_reason": None,
        "mode": task_mode,
        "status": final_status,
        "planner": action.get("planner", "gemini"),
    }


@app.post("/api/approve/{approval_id}")
async def approve_endpoint(approval_id: int, body: ApproveRequest):
    approval = get_pending_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Approval already resolved: {approval['status']}")

    # Phase 5 Output Boundary: Enforce single-use token lock
    if not action_boundary.verify_single_use_approval(approval_id):
        raise HTTPException(status_code=409, detail="Approval token has already been consumed.")

    resolve_approval(approval_id, body.approved)

    # Log the approval resolution
    task_id = approval["task_id"]
    task = get_task(task_id)
    if task and body.approved:
        update_task_status(task_id, "active")
        increment_steps(task_id)
        log_action(
            task_id=task_id,
            step_number=(task.get("steps_taken") or 0) + 1,
            action_type="click",
            element_id=approval.get("element_id", ""),
            element_text=approval.get("action_description", ""),
            reason=f"User approved: {approval.get('action_description', '')}",
            result="approved_and_dispatched",
        )

    return {
        "approval_id": approval_id,
        "status": "approved" if body.approved else "rejected",
        "task_id": task_id,
        "element_id": approval.get("element_id", ""),
        "action": {
            "action": "click",
            "element_id": approval.get("element_id", ""),
            "reason": "User approved consequential action"
        }
    }


@app.get("/api/metrics/{task_id}")
async def metrics_endpoint(task_id: str):
    """Phase 6: Cost optimization metrics endpoint."""
    return optimizer.get_task_metrics(task_id)


@app.get("/api/evidence/{task_id}")
async def evidence_endpoint(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return trail.generate_report(task_id)


@app.get("/api/evidence/{task_id}/html", response_class=HTMLResponse)
async def evidence_html_endpoint(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return trail.generate_html_report(task_id)


@app.get("/api/evidence/{task_id}/screenshot/{filename}")
async def evidence_screenshot_endpoint(task_id: str, filename: str):
    screenshot_path = Path(SCREENSHOT_DIR) / task_id / filename
    if not screenshot_path.exists():
        alt_path = Path("artifacts/screenshots") / filename
        if alt_path.exists():
            return FileResponse(alt_path)
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(screenshot_path)


@app.post("/api/screenshot")
async def screenshot_endpoint(body: ScreenshotRequest):
    """Save a base64 screenshot. Returns the saved file path."""
    task = get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        path = trail.record_screenshot(body.task_id, body.screenshot_b64, body.label)
        return {"path": path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Screenshot save error: {str(e)}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
