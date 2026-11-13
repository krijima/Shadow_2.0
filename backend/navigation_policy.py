"""Conservative navigation policy for ordinary-site Observe and Guide modes.

The planner chooses a target; observed DOM semantics decide whether SHADOW may
click it. Ambiguity is a website review, never permission to submit a form.
"""
import re
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from pocketfm_route import is_pocketfm, match_pocketfm

MUTATION = re.compile(r"\b(cancel|confirm|delete|remove|terminate|unsubscribe|purchase|buy|pay|upgrade|downgrade|accept|agree|save|submit|apply|renew|renewal|send|sign|end membership|close account|leave|disconnect|disable|deactivate|log ?out|sign ?out|turn off|switch plan|change plan)\b", re.I)
NAVIGATION = re.compile(
    r"^(?:(?:open|view|manage|go to)\s+)?(?:my\s+|your\s+)?"
    r"(?:account(?:\s+settings)?|settings|membership(?:\s+(?:details|settings))?|"
    r"subscription(?:s|\s+(?:details|settings))?|plan|your plan|prime membership|"
    r"profile|billing(?:\s+details)?|payment methods|preferences|security|privacy)"
    r"(?:\s*[.…!])?$", re.I)
ICON_LIGATURE = re.compile(
    r"^(?:settings|manage_membership|manage_accounts|cancel_presentation|subscriptions|account_circle|"
    r"arrow_forward|arrow_back|close|more_vert|menu|check_circle|warning|help|info|edit|delete|"
    r"credit_card|person|search|open_in_new)\s+", re.I)


def _control_label(element: dict) -> str:
    label = " ".join(str(element.get("accessible_name") or element.get("text") or "").split())
    return ICON_LIGATURE.sub("", label).strip()[:80]


def classify_navigation(action: dict, snapshot: dict) -> dict:
    element_id = action.get("element_id")
    element = next((e for e in snapshot.get("elements", [])
                    if (e.get("shadow_id") or e.get("data-shadow-id")) == element_id), {})
    label = _control_label(element)
    navigation_label = label.strip(" ⚙️›→.…!")
    risk_text = " ".join(str(element.get(key) or "") for key in ("text", "accessible_name", "value"))
    manage_in_subscription_context = (navigation_label.casefold() == "manage" and
        bool(re.search(r"subscription|membership|plan", str(snapshot.get("page_text") or "") + " " +
                       str(element.get("surrounding_heading") or "") + " " +
                       str(element.get("context_label") or ""), re.I)))
    # GitHub's settings sidebar uses these labels for read-only billing pages.
    # This grants navigation only; the usual origin, URL, form, and mutation
    # checks below still decide whether the actual control is reversible.
    github_billing_navigation = (
        urlparse(snapshot.get("url", "")).hostname == "github.com"
        and urlparse(snapshot.get("url", "")).path.startswith("/settings/")
        and navigation_label.casefold() in {"billing and licensing", "overview", "licensing"})
    reversible = False
    pocket_step = match_pocketfm(snapshot) if is_pocketfm(snapshot.get('url', '')) else None
    pocket_navigation = bool(pocket_step and pocket_step.get('reversible')
        and pocket_step.get('action', {}).get('element_id') == element_id)
    if (element and action.get("action") == "click" and action.get("confidence", 0) >= 0.85
            and element.get("visible", True) and element.get("enabled", True)
            and (NAVIGATION.fullmatch(navigation_label) or manage_in_subscription_context
                 or github_billing_navigation or pocket_navigation)
            and not MUTATION.search(risk_text)):
        tag = element.get("tag")
        if pocket_navigation and tag != 'a' and not element.get('in_form', False) and element.get('type') != 'submit':
            reversible = True
        elif tag == "a" and element.get("href"):
            source = urlparse(snapshot.get("url", ""))
            target = urlparse(urljoin(snapshot.get("url", ""), element["href"]))
            query = parse_qs(target.query)
            reversible = (target.scheme in {"http", "https"}
                          and (source.scheme, source.netloc) == (target.scheme, target.netloc)
                          and not element.get("in_form", False)
                          and "/api/" not in target.path.lower()
                          and not MUTATION.search(re.sub(r"[-_/]", " ", unquote(target.path + " " + target.query)))
                          and not set(query).intersection({"action", "do", "confirm", "execute", "operation", "csrf", "token"}))
        elif tag == "summary":
            reversible = (element.get("expanded") is not None
                          and not element.get("in_form", False))
        elif tag == "button":
            # A label or a non-submit type alone does not prove this button
            # only opens reversible UI. Require explicit disclosure semantics.
            reversible = (bool(element.get("controls") or element.get("has_popup")
                               or element.get("expanded") is not None or element.get("menu_context"))
                          and not element.get("in_form", False)
                          and element.get("type") != "submit")
        elif element.get("role") in {"button", "menuitem", "tab"}:
            reversible = (bool(element.get("controls") or element.get("has_popup")
                               or element.get("expanded") is not None or element.get("menu_context"))
                          and not element.get("in_form", False))
    visible_label = label or "This control"
    if not reversible and re.search(r"\b(cancel|cancellation|unsubscribe|end membership)\b", risk_text, re.I):
        guidance = "Review cancellation."
    else:
        guidance = f"Open {visible_label}." if reversible else f"{visible_label}? Review on page."
    return {"reversible": bool(reversible), "label": visible_label,
            "target": {key: element.get(key) for key in
                       ("tag", "type", "text", "accessible_name", "href", "in_form", "role", "controls", "expanded", "has_popup", "menu_context", "provider_control")},
            "guidance": guidance}


def preferred_membership_link(snapshot: dict) -> dict | None:
    """Find a structurally verified same-origin membership link for cancellation goals."""
    for element in snapshot.get("elements", []):
        label = _control_label(element)
        if not re.fullmatch(r"(?:manage|view|open)\s+(?:my\s+|your\s+)?(?:membership|subscription)(?:\s+details)?", label, re.I):
            continue
        candidate = {"action": "click", "element_id": element.get("shadow_id") or element.get("data-shadow-id"),
                     "confidence": 1.0}
        if candidate["element_id"] and classify_navigation(candidate, snapshot)["reversible"]:
            return candidate
    return None
