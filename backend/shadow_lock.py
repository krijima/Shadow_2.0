"""
ShadowLock — safety engine.
Never modifies the user's authorized_goal.
"""
from urllib.parse import urlparse, urljoin
from config import APPROVED_DOMAINS, MAX_STEPS, ALLOW_PUBLIC_WEB, is_streamcove_url

ALLOWED_ACTION_TYPES = {"click", "scroll", "select", "read", "ask_user", "stop", "highlight"}
BLOCKED_ACTION_TYPES = {"purchase", "upgrade", "external_navigate"}

PRICE_SIGNALS = [
    "$", "£", "€", "usd", "eur", "gbp",
    "buy now", "purchase", "upgrade", "subscribe", "add to cart",
    "checkout", "payment", "billing",
]


class ShadowLock:
    BLOCKED_ACTION_TYPES = BLOCKED_ACTION_TYPES
    APPROVED_DOMAINS = APPROVED_DOMAINS

    def validate_action(self, action: dict, task: dict) -> tuple[bool, str]:
        """
        Returns (is_allowed, reason).
        Checks:
          1. Action type is in allowed list
          2. No new purchases or upgrades (price signals in element text)
          3. No navigation outside approved domains
          4. Step limit not exceeded (MAX_STEPS=25)
        Returns (False, reason) if blocked, (True, "") if allowed.
        """
        action_type = action.get("action", "").lower()
        element_text = (action.get("element_text") or action.get("value") or "").lower()
        reason = action.get("reason", "")
        steps_taken = task.get("steps_taken", 0)

        # 1. Check step limit
        if steps_taken >= MAX_STEPS:
            return False, f"Step limit of {MAX_STEPS} reached. Stopping to protect user."

        # 2. Check action type is allowed
        if action_type in BLOCKED_ACTION_TYPES:
            return False, f"Action type '{action_type}' is blocked by ShadowLock."

        if action_type not in ALLOWED_ACTION_TYPES:
            return False, f"Unknown action type '{action_type}'. Only {ALLOWED_ACTION_TYPES} are permitted."

        # 3. Price signal check — block purchase/upgrade actions
        if action_type == "click":
            for signal in PRICE_SIGNALS:
                if signal in element_text:
                    # Allow if the element is clearly about *cancellation* not purchase
                    if any(w in element_text for w in ["cancel", "refund", "unsubscribe"]):
                        break
                    return False, f"Blocked: element text contains price signal '{signal}' suggesting a purchase/upgrade."

        # 4. Domain check for any URL in action
        url = action.get("url") or action.get("value") or ""
        if url.startswith("http"):
            hostname = urlparse(url).hostname or ""
            task_url = task.get("current_url") or ""
            current_host = urlparse(task_url).hostname if task_url else ""
            allowed_hosts = set(self.APPROVED_DOMAINS) | {"localhost"}
            if current_host:
                allowed_hosts.add(current_host)
            try:
                from boundaries import SnapshotBoundary
                allowed_hosts |= SnapshotBoundary.get_permitted_domains()
            except Exception:
                pass
            if not any(d in hostname for d in allowed_hosts):
                return False, f"Blocked: navigation to external domain '{hostname}' is not permitted."

        return True, ""

    def requires_approval(self, action: dict, page_snapshot: dict | None = None) -> bool:
        """
        Returns True if action needs explicit user approval.
        Requires approval for:
        1. The FINAL cancellation confirmation click (e.g. 'btn-confirm-cancel' on StreamCove).
        2. Consequential mutations on real websites (irreversible deletions, payment confirmations).
        """
        action_type = action.get("action", "").lower()
        element_id = (action.get("element_id") or "").lower()
        element_text = (action.get("element_text") or action.get("value") or "").lower()
        reason = (action.get("reason") or "").lower()

        if action_type == "click":
            # 1. StreamCove final confirmation button
            if element_id == "btn-confirm-cancel" or "confirm-cancel" in element_id:
                return True

            # These exact StreamCove links only navigate to another cancellation
            # page. Do not classify planner prose such as "cancel subscription"
            # as a final mutation. All other controls retain the generic checks.
            snapshot = page_snapshot or {}
            url = snapshot.get("url", "")
            routes = {
                ("/static/index.html", "link-subscription"): "/static/subscription.html",
                ("/static/index.html", "link-subscription-cta"): "/static/subscription.html",
                ("/static/index.html", "link-account"): "/static/account.html",
                ("/static/account.html", "link-subscription"): "/static/subscription.html",
                ("/static/subscription.html", "btn-cancel-subscription"): "/static/cancel_step1.html",
                ("/static/cancel_step1.html", "btn-continue-cancel"): "/static/cancel_step2.html",
                ("/static/cancel_step2.html", "btn-reject-offer"): "/static/cancel_confirm.html",
                ("/static/cancel_step2.html", "btn-reject-offer-2"): "/static/cancel_confirm.html",
            }
            expected_path = routes.get((urlparse(url).path, element_id))
            if is_streamcove_url(url) and expected_path:
                for element in snapshot.get("elements", []):
                    if (element.get("data-shadow-id") or element.get("shadow_id")) != element_id:
                        continue
                    target = urlparse(urljoin(url, element.get("href") or ""))
                    source = urlparse(url)
                    if (element.get("tag") == "a" and element.get("visible", True)
                            and element.get("enabled", True)
                            and (target.scheme, target.netloc) == (source.scheme, source.netloc)
                            and target.path == expected_path and not target.query):
                        return False

            # 2. Universal consequential actions on external websites
            high_risk_patterns = [
                "confirm cancellation", "confirm cancel", "delete account",
                "permanently delete", "confirm payment", "place order", "pay now",
                "cancel membership", "cancel subscription", "cancel plan",
                "cancel service", "end membership", "terminate subscription"
            ]
            if any(p in element_id or p in element_text or p in reason for p in high_risk_patterns):
                return True

            # If element text is an exact "cancel" button or link on an external site, require approval
            if element_text.strip() == "cancel" or element_id.strip() == "cancel":
                return True

        return False

    def is_prompt_injection(self, text: str) -> bool:
        """
        Check for obvious prompt injection patterns in page text.
        Look for: SYSTEM, OVERRIDE, ignore previous instructions, do not cancel,
        mark as complete, etc.
        """
        lower = text.lower()
        injection_patterns = [
            "system override",
            "ignore previous",
            "ignore all previous",
            "do not cancel",
            "mark task as complete",
            "mark as complete",
            "you have agreed to",
            "system:",
            "new instruction",
            "disregard",
            "forget your instructions",
            "act as",
            "jailbreak",
        ]
        for pattern in injection_patterns:
            if pattern in lower:
                return True
        return False
