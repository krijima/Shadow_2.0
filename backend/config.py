import os
from pathlib import Path


def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

from urllib.parse import urlparse

STREAMCOVE_URL = os.environ.get("STREAMCOVE_URL", "http://localhost:8080")
DB_PATH = os.environ.get("SHADOW_DB_PATH", str(Path(__file__).parent / "shadow.db"))
SCREENSHOT_DIR = os.environ.get("SCREENSHOT_DIR", str(Path(__file__).parent / "screenshots"))
APPROVED_DOMAINS = ["localhost", "127.0.0.1"]
ALLOW_PUBLIC_WEB = os.environ.get("SHADOW_ALLOW_PUBLIC_WEB", "true").lower() in ("true", "1", "yes")
MAX_STEPS = 25


def is_streamcove_url(url: str) -> bool:
    """Return True if url belongs to the configured StreamCove demonstration service."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
        if not host:
            return False

        # Match configured STREAMCOVE_URL
        sc_parsed = urlparse(STREAMCOVE_URL)
        sc_host = (sc_parsed.hostname or "").lower()
        sc_port = sc_parsed.port or (443 if sc_parsed.scheme == "https" else 80)

        # Allow matching host + port
        effective_port = port or (443 if parsed.scheme == "https" else 80)
        if host == sc_host and effective_port == sc_port:
            return True

        # Allow localhost / 127.0.0.1 on demo ports (8080 for live demo, 8081 for pytest)
        if host in ("localhost", "127.0.0.1") and port in (8080, 8081):
            return True

        return False
    except Exception:
        return False
