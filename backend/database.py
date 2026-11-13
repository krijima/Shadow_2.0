import sqlite3
from datetime import datetime
from pathlib import Path
from config import DB_PATH


def get_db() -> sqlite3.Connection:
    """Return a sqlite3 connection with row_factory set and tables initialized."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            user_instruction TEXT NOT NULL,
            authorized_goal TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            mode TEXT DEFAULT 'observe',
            current_url TEXT,
            steps_taken INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            step_number INTEGER,
            action_type TEXT,
            element_id TEXT,
            element_text TEXT,
            reason TEXT,
            result TEXT,
            timestamp TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );

        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            category TEXT,
            visible_text TEXT,
            url TEXT,
            element_context TEXT,
            reason TEXT,
            evidence TEXT,
            timestamp TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            action_description TEXT,
            target_url TEXT,
            element_id TEXT,
            status TEXT DEFAULT 'pending',
            requested_at TEXT,
            resolved_at TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
    """)

    # Migration: ensure mode column exists in tasks
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN mode TEXT DEFAULT 'observe'")
        conn.commit()
    except Exception:
        pass

    conn.commit()
    conn.close()


# ── Task helpers ──────────────────────────────────────────────────────────────

def create_task(task_id: str, user_instruction: str, authorized_goal: str, mode: str = "observe") -> dict:
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        """INSERT INTO tasks (id, user_instruction, authorized_goal, status, mode, steps_taken, created_at, updated_at)
           VALUES (?, ?, ?, 'active', ?, 0, ?, ?)""",
        (task_id, user_instruction, authorized_goal, mode, now, now),
    )
    conn.commit()
    conn.close()
    return get_task(task_id)


def get_task(task_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_task_status(task_id: str, status: str, current_url: str | None = None):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    if current_url is not None:
        conn.execute(
            "UPDATE tasks SET status = ?, current_url = ?, updated_at = ? WHERE id = ?",
            (status, current_url, now, task_id),
        )
    else:
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, task_id),
        )
    conn.commit()
    conn.close()


def increment_steps(task_id: str):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE tasks SET steps_taken = steps_taken + 1, updated_at = ? WHERE id = ?",
        (now, task_id),
    )
    conn.commit()
    conn.close()


# ── Action helpers ────────────────────────────────────────────────────────────

def log_action(
    task_id: str,
    step_number: int,
    action_type: str,
    element_id: str = "",
    element_text: str = "",
    reason: str = "",
    result: str = "",
):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        """INSERT INTO actions (task_id, step_number, action_type, element_id, element_text, reason, result, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, step_number, action_type, element_id, element_text, reason, result, now),
    )
    conn.commit()
    conn.close()


# ── Detection helpers ─────────────────────────────────────────────────────────

def log_detection(
    task_id: str,
    category: str,
    visible_text: str = "",
    url: str = "",
    element_context: str = "",
    reason: str = "",
    evidence: str = "",
):
    now = datetime.utcnow().isoformat()
    conn = get_db()
    conn.execute(
        """INSERT INTO detections (task_id, category, visible_text, url, element_context, reason, evidence, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (task_id, category, visible_text, url, element_context, reason, evidence, now),
    )
    conn.commit()
    conn.close()


# ── Approval helpers ──────────────────────────────────────────────────────────

def create_approval(
    task_id: str,
    action_description: str,
    target_url: str = "",
    element_id: str = "",
) -> int:
    now = datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO approvals (task_id, action_description, target_url, element_id, status, requested_at)
           VALUES (?, ?, ?, ?, 'pending', ?)""",
        (task_id, action_description, target_url, element_id, now),
    )
    approval_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return approval_id


def get_pending_approval(approval_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_detections_for_task(task_id: str) -> list[dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM detections WHERE task_id = ? ORDER BY id ASC", (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_actions_for_task(task_id: str) -> list[dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM actions WHERE task_id = ? ORDER BY step_number ASC, id ASC", (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_approvals_for_task(task_id: str) -> list[dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM approvals WHERE task_id = ? ORDER BY id ASC", (task_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_approval(approval_id: int, approved: bool):
    now = datetime.utcnow().isoformat()
    status = "approved" if approved else "rejected"
    conn = get_db()
    conn.execute(
        "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ?",
        (status, now, approval_id),
    )
    conn.commit()
    conn.close()
