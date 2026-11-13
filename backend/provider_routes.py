"""Curated provider cancellation routes from first-party help sources.

Route labels are hints only. The active DOM element is selected on each page
and must still pass the navigation policy before Observe can dispatch it.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse


PROVIDER_ROUTES = {
    "apple_music": {
        "provider": "apple_music",
        "hosts": ("music.apple.com",),
        "help_url": "https://support.apple.com/en-us/118399",
        "steps": {
            "account_menu": ("My Account",),
            "settings": ("Settings",),
            "manage_subscription": ("Manage", "Manage Subscriptions"),
            "final": ("Cancel Subscription", "Cancel Membership"),
        },
    },
    "spotify": {
        "provider": "spotify",
        "hosts": ("spotify.com",),
        "help_url": "https://support.spotify.com/us/article/cancel-premium/",
        "steps": {
            "manage_plan": ("Manage your plan", "Manage plan"),
            "final": ("Cancel subscription", "Cancel Premium"),
        },
    },
    "amazon_prime_india": {
        "provider": "amazon_prime_india",
        "hosts": ("amazon.in",),
        "help_url": "https://in.amazonforum.com/s/question/0D5at000010LpWDCA0/i-want-refund-and-i-want-to-cancel-my-subsciptions",
        "steps": {
            "your_prime": ("Your Prime Membership", "Prime Membership"),
            "manage_membership": ("Manage membership", "Manage Prime Membership", "Update, cancel and more"),
            "final": ("End membership", "End membership and benefits"),
        },
    },
}

CANCELLATION_GOAL = re.compile(
    r"\b(cancel|cancellation|unsubscribe|end\s+(?:my\s+)?(?:membership|subscription|plan)|"
    r"turn\s+off.{0,30}renew|stop.{0,30}renew)\b", re.I)
PARTNER = re.compile(
    r"(?:billed|billing|managed|paid)\s+(?:through|by|via)\s+"
    r"(google play|apple|a mobile provider|your provider|a partner|a third.party)", re.I)


def _label(element: dict) -> str:
    value = " ".join(str(element.get("accessible_name") or element.get("text") or "").split())
    value = re.sub(r"^(?:settings|manage_membership|manage_accounts|cancel_presentation|subscriptions)\s+", "", value, flags=re.I)
    return value.strip(" .…!:")[:100]


def get_provider_route(url: str, instruction: str) -> dict | None:
    """Return route hints only for supported providers and cancellation tasks."""
    if not CANCELLATION_GOAL.search(instruction or ""):
        return None
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    for route in PROVIDER_ROUTES.values():
        if any(host == domain or host.endswith("." + domain) for domain in route["hosts"]):
            return route
    return None


def _find(snapshot: dict, labels: tuple[str, ...], *, menu_only: bool = False,
          subscription_context: bool = False) -> dict | None:
    wanted = {label.casefold() for label in labels}
    for element in snapshot.get("elements", []):
        if not element.get("visible", True) or not element.get("enabled", True):
            continue
        # Route labels can also occur in headings and page copy. Only select a
        # current control the extension can actually activate.
        if element.get("tag") not in {"a", "button"} and element.get("role") not in {
                "button", "menuitem", "tab"}:
            continue
        label = _label(element)
        if label.casefold() not in wanted:
            continue
        if menu_only and not (element.get("has_popup") or element.get("controls")
                              or element.get("expanded") is not None):
            continue
        if subscription_context and not re.search(r"subscription|membership|plan", " ".join((
                str(element.get("surrounding_heading") or ""),
                str(element.get("context_label") or ""),
                str(snapshot.get("page_text") or ""))), re.I):
            continue
        return element
    return None


def match_provider_action(route: dict | None, snapshot: dict) -> dict | None:
    """Match official route intents to visible controls on this exact DOM snapshot."""
    if not route:
        return None
    text = str(snapshot.get("page_text") or "")
    partner = PARTNER.search(text)
    if partner:
        return {"provider": route["provider"], "help_url": route["help_url"],
                "route_step": "partner_handoff", "handoff": partner.group(1), "action": None}

    steps = route["steps"]
    element = None
    step_name = ""
    if route["provider"] == "apple_music":
        # The menu item wins over the opener whenever it is already visible.
        element = _find(snapshot, steps["settings"])
        if element:
            step_name = "settings"
        if not element:
            element = _find(snapshot, steps["manage_subscription"], subscription_context=True)
            if element:
                step_name = "manage_subscription"
        if not element:
            element = _find(snapshot, steps["final"])
            if element:
                step_name = "final"
        if not element:
            element = _find(snapshot, steps["account_menu"], menu_only=True)
            if element:
                step_name = "account_menu"
    elif route["provider"] == "spotify":
        element = _find(snapshot, steps["final"])
        if element:
            step_name = "final"
        if not element:
            element = _find(snapshot, steps["manage_plan"])
            if element:
                step_name = "manage_plan"
    else:
        element = _find(snapshot, steps["final"])
        if element:
            step_name = "final"
        if not element:
            element = _find(snapshot, steps["manage_membership"])
            if element:
                step_name = "manage_membership"
        if not element:
            element = _find(snapshot, steps["your_prime"])
            if element:
                step_name = "your_prime"

    if not element:
        return None
    label = _label(element) or "This control"
    return {
        "provider": route["provider"], "help_url": route["help_url"],
        "route_step": step_name,
        "action": {"action": "click", "element_id": element.get("shadow_id") or element.get("data-shadow-id"),
                   "value": "", "reason": f"Official route: {step_name}", "confidence": 1.0},
        "final": step_name == "final",
        "stalled_guidance": "Open Settings to continue." if step_name == "account_menu"
            else f"Open {label} to continue.",
    }
