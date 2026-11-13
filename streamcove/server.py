"""
StreamCove FastAPI server — port 8080.
Fictional streaming subscription service for the SHADOW hackathon demo.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "streamcove.db"
STATIC_DIR = BASE_DIR / "static"

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL UNIQUE,
                status      TEXT    NOT NULL DEFAULT 'active',
                plan        TEXT    NOT NULL DEFAULT 'Premium',
                created_at  TEXT    NOT NULL,
                cancelled_at TEXT
            )
            """
        )
        conn.commit()
        # Seed demo user (idempotent)
        existing = conn.execute(
            "SELECT id FROM subscriptions WHERE user_id='demo'"
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO subscriptions (user_id, status, plan, created_at)
                VALUES ('demo', 'active', 'Premium', ?)
                """,
                (datetime.now(timezone.utc).isoformat(),),
            )
            conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scenario state  (import scenarios module)
# ---------------------------------------------------------------------------
import sys
sys.path.insert(0, str(BASE_DIR))
import scenarios as _scenarios  # noqa: E402

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="StreamCove API")

# Initialise DB on startup
init_db()

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class CancelRequest(BaseModel):
    user_id: str
    confirmed: bool


class ScenarioRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/subscription")
def get_subscription(user_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=?", (user_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return dict(row)


@app.post("/api/subscription/cancel")
def cancel_subscription(req: CancelRequest):
    if not req.confirmed:
        raise HTTPException(status_code=400, detail="confirmed must be true")
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        result = conn.execute(
            """
            UPDATE subscriptions
               SET status='cancelled', cancelled_at=?
             WHERE user_id=?
            """,
            (now, req.user_id),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Subscription not found")
    return {"success": True, "status": "cancelled", "cancelled_at": now}


@app.post("/api/subscription/reset")
def reset_subscription(request: Request, user_id: str = "demo"):
    client_ip = request.client.host if request.client else "127.0.0.1"
    if client_ip not in ("127.0.0.1", "localhost", "::1", "testclient"):
        raise HTTPException(status_code=403, detail="Reset is restricted to localhost demo environment")
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE subscriptions
               SET status='active', cancelled_at=NULL
             WHERE user_id=?
            """,
            (user_id,),
        )
    return {"success": True, "status": "active"}


@app.get("/api/scenario")
def get_scenario():
    name = _scenarios.get_current_scenario()
    info = _scenarios.get_scenario_info(name)
    return {"scenario": name, "description": info["description"]}


@app.post("/api/scenario")
def set_scenario(req: ScenarioRequest):
    try:
        _scenarios.set_current_scenario(req.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"scenario": req.name, "ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8080, reload=True)
