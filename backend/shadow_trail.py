"""
ShadowTrail — evidence collector.
"""
import base64
from datetime import datetime
from pathlib import Path
from database import get_db, log_action, log_detection
from config import SCREENSHOT_DIR


class ShadowTrail:
    def record_action(self, task_id: str, action: dict, result: str):
        """Log action to DB."""
        task = self._get_task(task_id)
        step_number = (task.get("steps_taken") or 0) if task else 0
        log_action(
            task_id=task_id,
            step_number=step_number,
            action_type=action.get("action", "unknown"),
            element_id=action.get("element_id", ""),
            element_text=action.get("element_text", ""),
            reason=action.get("reason", ""),
            result=result,
        )

    def record_detection(self, task_id: str, detection: dict):
        """Log dark pattern to DB."""
        log_detection(
            task_id=task_id,
            category=detection.get("category", "unknown"),
            visible_text=detection.get("visible_text", ""),
            url=detection.get("url", ""),
            element_context=detection.get("element_context", ""),
            reason=detection.get("reason", ""),
            evidence=detection.get("evidence", ""),
        )

    def record_screenshot(self, task_id: str, screenshot_b64: str, label: str) -> str:
        """Save screenshot PNG, return file path."""
        screenshot_dir = Path(SCREENSHOT_DIR) / task_id
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
        filename = f"{timestamp}_{safe_label}.png"
        filepath = screenshot_dir / filename

        # Decode and save
        image_data = base64.b64decode(screenshot_b64)
        filepath.write_bytes(image_data)
        return str(filepath)

    def generate_report(self, task_id: str) -> dict:
        """Return full evidence report as dict with: task, actions, detections, screenshots."""
        conn = get_db()

        task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        task = dict(task_row) if task_row else {}

        action_rows = conn.execute(
            "SELECT * FROM actions WHERE task_id = ? ORDER BY step_number, id", (task_id,)
        ).fetchall()
        actions = [dict(r) for r in action_rows]

        detection_rows = conn.execute(
            "SELECT * FROM detections WHERE task_id = ? ORDER BY id", (task_id,)
        ).fetchall()
        detections = [dict(r) for r in detection_rows]

        # List screenshot files if any
        screenshots = []
        screenshot_dir = Path(SCREENSHOT_DIR) / task_id
        if screenshot_dir.exists():
            for f in sorted(screenshot_dir.iterdir()):
                if f.suffix.lower() == ".png":
                    screenshots.append(str(f))

        conn.close()

        return {
            "task": task,
            "actions": actions,
            "detections": detections,
            "screenshots": screenshots,
        }

    def generate_html_report(self, task_id: str) -> str:
        """Return a polished, judge-ready evidence and decision report."""
        report = self.generate_report(task_id)
        task = report.get("task", {})
        actions = report.get("actions", [])
        detections = report.get("detections", [])

        # Fetch approvals from database
        from database import get_approvals_for_task
        approvals = get_approvals_for_task(task_id)

        # Fetch AI optimizer and latency metrics
        try:
            from shadow_navigate import optimizer
            model_metrics = optimizer.get_task_metrics(task_id)
        except Exception:
            model_metrics = {
                "api_calls": 0,
                "cached_hits": 0,
                "total_latency_ms": 0.0,
                "estimated_prompt_tokens": 0,
                "estimated_completion_tokens": 0,
                "models_used": ["gemini-2.5-flash"],
            }

        total_tokens = model_metrics.get("estimated_prompt_tokens", 0) + model_metrics.get("estimated_completion_tokens", 0)
        est_cost_usd = (model_metrics.get("estimated_prompt_tokens", 0) * 0.075 / 1_000_000) + (model_metrics.get("estimated_completion_tokens", 0) * 0.30 / 1_000_000)
        models_display = ", ".join(model_metrics.get("models_used") or ["gemini-2.5-flash"])

        def esc(s):
            return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

        status_color = {
            "active": "#38bdf8",
            "paused": "#fbbf24",
            "completed": "#34d399",
            "failed": "#f87171",
            "cancelled": "#94a3b8",
            "halted": "#f97316",
        }.get(task.get("status", ""), "#94a3b8")

        # Halt explanation if task was halted
        halt_reason = None
        if task.get("status") == "halted":
            for a in reversed(actions):
                if a.get("result") == "blocked" or "halted" in str(a.get("reason", "")).lower() or "stalled" in str(a.get("reason", "")).lower():
                    halt_reason = a.get("reason", "")
                    break
            if not halt_reason and actions:
                halt_reason = actions[-1].get("reason", "")

        halt_html = ""
        if halt_reason:
            halt_html = f"""
            <div class="meta-item" style="margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border);">
              <div class="meta-label" style="color: #f97316;">Halt Explanation</div>
              <div class="meta-val" style="color: #fed7aa; font-size: 0.85rem; font-weight: 600;">{esc(halt_reason)}</div>
            </div>"""

        # Duration calculation
        duration_str = "N/A"
        if task.get("created_at") and task.get("updated_at"):
            try:
                t0 = datetime.fromisoformat(task["created_at"])
                t1 = datetime.fromisoformat(task["updated_at"])
                diff = int((t1 - t0).total_seconds())
                duration_str = f"{diff // 60}m {diff % 60}s" if diff >= 60 else f"{diff}s"
            except Exception:
                duration_str = "Under 1 min"

        # Actions rows
        actions_html = ""
        for a in actions:
            res_str = a.get("result", "")
            is_blocked = "blocked" in res_str.lower()
            badge_class = "action-blocked" if is_blocked else "action-executed"
            actions_html += f"""
            <tr>
              <td><span class="step-badge">#{esc(a.get('step_number', ''))}</span></td>
              <td><code>{esc(a.get('action_type', ''))}</code></td>
              <td><code>{esc(a.get('element_id', '')) or 'N/A'}</code></td>
              <td>{esc(a.get('reason', ''))}</td>
              <td><span class="{badge_class}">{esc(res_str)}</span></td>
              <td class="time-col">{esc(a.get('timestamp', ''))}</td>
            </tr>"""

        # Detections rows
        detections_html = ""
        for d in detections:
            cat = d.get("category", "")
            threat_type = "Security Threat" if cat == "prompt_injection" else "Consumer Pattern"
            threat_class = "threat-security" if cat == "prompt_injection" else "threat-consumer"
            detections_html += f"""
            <tr>
              <td><span class="{threat_class}">{threat_type}</span></td>
              <td><strong>{esc(cat.replace('_', ' ').title())}</strong></td>
              <td><code>{esc(d.get('element_id', '')) or 'page_text'}</code></td>
              <td>{esc(d.get('reason', ''))}</td>
              <td class="evidence-box">{esc(d.get('evidence', '') or d.get('visible_text', ''))}</td>
              <td class="time-col">{esc(d.get('url', ''))}</td>
            </tr>"""

        # Approvals rows
        approvals_html = ""
        for app in approvals:
            app_status = app.get("status", "pending")
            status_cls = "app-approved" if app_status == "approved" else ("app-rejected" if app_status == "rejected" else "app-pending")
            approvals_html += f"""
            <tr>
              <td>#{esc(app.get('id', ''))}</td>
              <td>{esc(app.get('action_description', ''))}</td>
              <td><code>{esc(app.get('element_id', '')) or 'N/A'}</code></td>
              <td><span class="{status_cls}">{esc(app_status.upper())}</span></td>
              <td class="time-col">{esc(app.get('requested_at', ''))}</td>
              <td class="time-col">{esc(app.get('resolved_at', '') or 'Pending')}</td>
            </tr>"""

        # Screenshots gallery
        screenshots = report.get("screenshots", [])
        screenshots_html = ""
        if screenshots:
            for s in screenshots:
                s_name = Path(s).name
                screenshots_html += f"""
                <div class="screenshot-card">
                  <div class="screenshot-title">{esc(s_name)}</div>
                  <img src="/api/evidence/{task_id}/screenshot/{esc(s_name)}" alt="{esc(s_name)}" onerror="this.style.display='none'" />
                </div>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SHADOW Evidence & Decision Report — {esc(task_id)}</title>
<style>
  :root {{
    --bg-dark: #0a0d18;
    --card-bg: #12172b;
    --border: #232d4b;
    --accent-violet: #8b5cf6;
    --accent-cyan: #06b6d4;
    --accent-green: #10b981;
    --accent-amber: #f59e0b;
    --accent-red: #ef4444;
    --text-primary: #f1f5f9;
    --text-muted: #94a3b8;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg-dark);
    color: var(--text-primary);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 2.5rem 2rem;
    line-height: 1.5;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  
  /* Header & Controls */
  .header-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: 1.5rem;
    margin-bottom: 2rem;
  }}
  .brand-group {{ display: flex; align-items: center; gap: 12px; }}
  .brand-title {{ font-size: 1.6rem; font-weight: 800; letter-spacing: 0.5px; }}
  .brand-title span {{ color: var(--accent-violet); }}
  .tagline {{ font-size: 0.85rem; color: var(--text-muted); }}
  .btn-group {{ display: flex; gap: 10px; }}
  .btn {{
    background: var(--card-bg);
    color: var(--text-primary);
    border: 1px solid var(--border);
    padding: 0.5rem 1rem;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    transition: all 0.2s ease;
  }}
  .btn:hover {{ background: var(--border); border-color: var(--accent-violet); }}
  .btn-primary {{ background: var(--accent-violet); border-color: var(--accent-violet); }}
  .btn-primary:hover {{ background: #7c3aed; }}

  /* Metadata Cards */
  .meta-grid {{
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 1.5rem;
    margin-bottom: 2rem;
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.5rem;
  }}
  .card-title {{
    font-size: 0.9rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--accent-violet);
    margin-bottom: 1rem;
  }}
  .meta-item {{ margin-bottom: 0.6rem; }}
  .meta-label {{ font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }}
  .meta-val {{ font-size: 0.95rem; font-weight: 500; margin-top: 2px; }}
  .badge-status {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
  }}
  .badge-mode {{
    background: rgba(139, 92, 246, 0.2);
    color: #c4b5fd;
    border: 1px solid var(--accent-violet);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 700;
  }}

  /* Metrics Summary */
  .metrics-row {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 2.5rem;
  }}
  .metric-box {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.2rem;
    text-align: center;
  }}
  .metric-num {{ font-size: 2.2rem; font-weight: 800; color: var(--text-primary); }}
  .metric-label {{ font-size: 0.8rem; color: var(--text-muted); font-weight: 600; margin-top: 4px; }}

  /* Tables */
  .section-title {{
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--text-primary);
    margin: 2rem 0 1rem;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 2rem;
  }}
  th {{
    background: #18203c;
    color: #cbd5e1;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 0.85rem 1rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }}
  td {{
    padding: 0.85rem 1rem;
    border-bottom: 1px solid var(--border);
    font-size: 0.88rem;
    vertical-align: top;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}
  code {{
    background: #1e293b;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.82rem;
    color: #38bdf8;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }}
  .time-col {{ font-size: 0.78rem; color: var(--text-muted); font-family: ui-monospace, monospace; }}
  .evidence-box {{
    font-family: ui-monospace, monospace;
    font-size: 0.82rem;
    background: #0d1222;
    padding: 6px 10px;
    border-radius: 4px;
    border-left: 3px solid var(--accent-violet);
    max-width: 320px;
  }}
  .step-badge {{
    background: var(--border);
    color: var(--text-primary);
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.75rem;
  }}
  .threat-security {{
    background: rgba(239, 68, 68, 0.2);
    color: #fca5a5;
    border: 1px solid rgba(239, 68, 68, 0.4);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 700;
  }}
  .threat-consumer {{
    background: rgba(245, 158, 11, 0.2);
    color: #fde68a;
    border: 1px solid rgba(245, 158, 11, 0.4);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 700;
  }}
  .action-executed {{ color: var(--accent-green); font-weight: 600; font-size: 0.8rem; }}
  .action-blocked {{ color: var(--accent-red); font-weight: 600; font-size: 0.8rem; }}
  .app-approved {{ color: var(--accent-green); font-weight: 700; }}
  .app-rejected {{ color: var(--accent-red); font-weight: 700; }}
  .app-pending {{ color: var(--accent-amber); font-weight: 700; }}
  .empty-msg {{ padding: 1.5rem; text-align: center; color: var(--text-muted); font-style: italic; }}

  /* Disclaimer Footer */
  .audit-disclaimer {{
    margin-top: 3rem;
    padding: 1.2rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: rgba(30, 41, 59, 0.5);
    font-size: 0.78rem;
    color: var(--text-muted);
    text-align: center;
  }}

  /* Print Stylesheet */
  @media print {{
    body {{ background: #fff !important; color: #000 !important; padding: 1rem; }}
    .btn-group {{ display: none !important; }}
    .header-row {{ border-bottom: 2px solid #333 !important; }}
    .card, table, .metric-box {{ background: #fff !important; border: 1px solid #ccc !important; color: #000 !important; page-break-inside: avoid; }}
    th {{ background: #f0f0f0 !important; color: #000 !important; font-weight: 700; }}
    td {{ color: #000 !important; }}
    code {{ background: #f5f5f5 !important; color: #111 !important; }}
    .evidence-box {{ background: #f9f9f9 !important; border-left-color: #666 !important; color: #000 !important; }}
  }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header-row">
    <div class="brand-group">
      <div style="font-size: 2rem;">🛡️</div>
      <div>
        <div class="brand-title">SHADOW <span>TRAIL</span></div>
        <div class="tagline">Audit-Ready Evidence &amp; Decision Record — DevHack 2026</div>
      </div>
    </div>
    <div class="btn-group">
      <button class="btn" onclick="window.print()">🖨️ Print / Save as PDF</button>
      <a class="btn btn-primary" href="/api/evidence/{esc(task_id)}" download="shadow_audit_{esc(task_id)}.json">📥 Export JSON</a>
    </div>
  </div>

  <!-- Meta Cards -->
  <div class="meta-grid">
    <div class="card">
      <div class="card-title">User Objective &amp; Authorization</div>
      <div class="meta-item">
        <div class="meta-label">Original User Instruction</div>
        <div class="meta-val">"{esc(task.get('user_instruction', 'N/A'))}"</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">ShadowLock Authorized Goal</div>
        <div class="meta-val" style="color: var(--accent-violet);">"{esc(task.get('authorized_goal', 'N/A'))}"</div>
      </div>
      <div class="meta-item" style="margin-top: 10px;">
        <div class="meta-label">Target Website</div>
        <div class="meta-val" style="font-family: monospace; font-size: 0.85rem;">{esc(task.get('current_url', 'N/A'))}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Execution Context</div>
      <div class="meta-item">
        <div class="meta-label">Task Status</div>
        <div class="meta-val"><span class="badge-status" style="background:{status_color};color:#0a0d18">{esc(task.get('status', 'unknown')).upper()}</span></div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Operating Mode</div>
        <div class="meta-val"><span class="badge-mode">{esc(task.get('mode', 'observe').upper())} MODE</span></div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Total Execution Duration</div>
        <div class="meta-val">{esc(duration_str)}</div>
      </div>
      {halt_html}
    </div>
  </div>

  <!-- Key Metrics -->
  <div class="metrics-row">
    <div class="metric-box">
      <div class="metric-num">{len(actions)}</div>
      <div class="metric-label">Observed Navigation Steps</div>
    </div>
    <div class="metric-box">
      <div class="metric-num" style="color: {'var(--accent-red)' if detections else 'var(--accent-green)'}">{len(detections)}</div>
      <div class="metric-label">Dark Patterns Flagged</div>
    </div>
    <div class="metric-box">
      <div class="metric-num" style="color: var(--accent-cyan);">{len(approvals)}</div>
      <div class="metric-label">ShadowLock Approvals</div>
    </div>
    <div class="metric-box">
      <div class="metric-num" style="color: var(--accent-violet);">{task.get('steps_taken', 0)}</div>
      <div class="metric-label">Total DOM Steps</div>
    </div>
  </div>

  <!-- AI Inference & Cost Telemetry Strip -->
  <div class="card" style="margin-bottom: 2rem; border-left: 4px solid var(--accent-cyan);">
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:1rem;">
      <div>
        <div style="font-size:0.8rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">AI Engine &amp; Cost Efficiency Telemetry</div>
        <div style="font-size:0.95rem; font-weight:600; margin-top:2px;">
          Active Model: <code style="color:var(--accent-cyan);">{esc(models_display)}</code>
        </div>
      </div>
      <div style="display:flex; gap:1.5rem; flex-wrap:wrap; font-size:0.85rem;">
        <div><span style="color:var(--text-muted);">API Calls / Cached:</span> <strong>{model_metrics.get('api_calls', 0)} / {model_metrics.get('cached_hits', 0)}</strong></div>
        <div><span style="color:var(--text-muted);">Est. Tokens:</span> <strong>~{total_tokens}</strong></div>
        <div><span style="color:var(--text-muted);">Cumulative Latency:</span> <strong>{model_metrics.get('total_latency_ms', 0):.1f} ms</strong></div>
        <div><span style="color:var(--text-muted);">Estimated Cost:</span> <strong style="color:var(--accent-green);">${est_cost_usd:.5f}</strong></div>
      </div>
    </div>
  </div>

  <!-- Approvals & Consequential Decisions -->
  <div class="section-title">⚖️ Human-in-the-Loop Decisions &amp; ShadowLock Interceptions</div>
  {'<table><thead><tr><th>ID</th><th>Action Intercepted</th><th>Element Target</th><th>Decision</th><th>Requested</th><th>Resolved</th></tr></thead><tbody>' + approvals_html + '</tbody></table>' if approvals else '<div class="card empty-msg">No consequential actions required explicit confirmation.</div>'}

  <!-- Dark Patterns Detected -->
  <div class="section-title">🚨 Detected Dark Patterns &amp; Visual Deceptions</div>
  {'<table><thead><tr><th>Threat Type</th><th>Pattern Category</th><th>Element ID</th><th>Reasoning</th><th>Supporting Evidence</th><th>URL Context</th></tr></thead><tbody>' + detections_html + '</tbody></table>' if detections else '<div class="card empty-msg" style="color: var(--accent-green);">✓ Zero deceptive patterns detected on current navigation trajectory.</div>'}

  <!-- Navigation Action Timeline -->
  <div class="section-title">🧭 Navigation Journey &amp; AI Action Log</div>
  {'<table><thead><tr><th>Step</th><th>Action</th><th>Target Element</th><th>Agent Reasoning</th><th>ShadowLock Status</th><th>Timestamp</th></tr></thead><tbody>' + actions_html + '</tbody></table>' if actions else '<div class="card empty-msg">No navigation actions logged yet.</div>'}

  <!-- Screenshot Evidence (if available) -->
  {('<div class="section-title">📸 Visual Evidence Captures</div><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1rem;margin-bottom:2rem;">' + screenshots_html + '</div>') if screenshots_html else ''}

  <!-- Final Disclaimer -->
  <div class="audit-disclaimer">
    <strong>SHADOW Audit Notice:</strong> This report documents observed client-side DOM events, AI planner decisions, and human verification checkpoints. It represents recorded browser telemetry for consumer-protection analysis. It does not constitute formal legal counsel.
  </div>

</div>
</body>
</html>"""

    def _get_task(self, task_id: str) -> dict | None:
        conn = get_db()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        conn.close()
        return dict(row) if row else None
