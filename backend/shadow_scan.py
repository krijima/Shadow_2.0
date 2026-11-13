"""
ShadowScan — Context-Aware Hybrid Dark Pattern Detector (Phase 3).
Combines:
1. DOM Geometry & Layout Analysis (visibility, computed opacity, bounding boxes).
2. Rule-Based Pattern Matcher (confirm-shaming, countdown urgency, retention deals).
3. Local Machine-Learning Text Classifier (TF-IDF + Logistic Regression, Apache-2.0).
4. Context-aware False-Positive Filtering (distinguishes legitimate discounts from manipulative traps).
"""
from database import log_detection
from ml_detector import MLDetector

# Legitimate informational phrases that must NEVER be misclassified as dark patterns
LEGITIMATE_CONTEXT_PATTERNS = [
    "cancel anytime",
    "cancel at any time",
    "annual plans save",
    "save 15% compared to monthly",
    "yes, cancel my subscription",
    "subscription overview",
    "manage plan",
    "my subscription",
    "want to make changes to your subscription",
    "paid through",
    "next billing date",
    "payment method",
    "terms of service",
    "privacy policy",
    "account settings",
    "security settings",
    "notification preferences",
    "feedback survey",
]

DARK_PATTERN_RULES = [
    {
        "category": "confirm_shaming",
        "patterns": [
            "i don't want to save money",
            "no thanks, i love paying more",
            "i prefer to stay confused",
            "i want to miss out",
        ],
        "reason": "Button or link uses guilt-inducing language to discourage cancellation",
    },
    {
        "category": "retention_offer",
        "patterns": [
            "special offer just for you",
            "exclusive deal",
            "50% off for your next",
            "60% off for your next",
            "one last offer",
            "stay and save",
            "don't want to lose you",
            "accept offer",
        ],
        "reason": "Aggressive retention offer injected during cancellation flow to prevent user exit",
    },
    {
        "category": "fake_urgency",
        "patterns": [
            "expires in",
            "offer expires in",
            "countdown",
            "only 1 left in stock",
            "only 2 left in stock",
        ],
        "reason": "Artificial time countdown or scarcity pressure deployed to suppress consumer deliberation",
        "threat_type": "consumer_pattern",
        "confidence": 0.94,
    },
    {
        "category": "suspicious_urgency",
        "patterns": [
            "offer expires",
            "limited time",
            "only today",
            "hurry",
            "act fast",
            "sale ends soon",
        ],
        "reason": "Time pressure claim creates psychological urgency. Unverified without server-side inventory verification.",
        "threat_type": "consumer_pattern",
        "confidence": 0.70,
    },
    {
        "category": "misleading_cancellation",
        "patterns": [
            "pause instead",
            "you'll lose everything",
            "all your data will be deleted",
            "you will immediately lose access",
            "cannot be undone",
        ],
        "reason": "Misleads or intimidates user about consequences of cancellation",
    },
    {
        "category": "hidden_cancellation",
        "patterns": [],  # detected by element visibility/style analysis
        "reason": "Cancellation option is visually obscured or hidden",
    },
    {
        "category": "repeated_retention",
        "patterns": [],  # detected by step count + same page revisit
        "reason": "Multiple retention offers blocking cancellation path",
    },
    {
        "category": "forced_continuity",
        "patterns": [
            "you will be charged",
            "billing continues",
            "subscription renews automatically",
        ],
        "reason": "Implies continued billing without clear opt-out",
    },
    {
        "category": "prompt_injection",
        "patterns": [
            "system override",
            "ignore previous",
            "do not cancel",
            "mark task as complete",
            "system:",
            "you have agreed to",
        ],
        "reason": "Webpage attempting to inject instructions into AI agent",
    },
]


class ShadowScan:
    def __init__(self):
        self.ml = MLDetector()

    def _get_rules_for_eval(self):
        """Helper for evaluation benchmarks to test pure rule matching."""
        return [r for r in DARK_PATTERN_RULES if r["category"] != "prompt_injection"]

    def is_informational_article(self, url: str) -> bool:
        """Domain prior for encyclopedia, documentation, or educational websites."""
        if not url:
            return False
        lower_url = url.lower()
        INFORMATIONAL_DOMAINS = [
            "wikipedia.org", "wikimedia.org", "w3.org", "arxiv.org",
            "docs.python.org", "docs.github.com", "developer.mozilla.org"
        ]
        return any(d in lower_url for d in INFORMATIONAL_DOMAINS)

    def is_educational_or_quoted_context(self, text: str, element: dict = None) -> bool:
        """
        Context-aware detection to prevent false positives when text discusses or quotes dark patterns
        (e.g. Wikipedia articles, research papers, news, documentation), while ensuring actual
        interactive elements (buttons, inputs) remain subject to analysis regardless of domain.
        """
        if not text:
            return False
        lower = text.lower()

        # If it is an active interactive control (e.g. button, input, actionable link),
        # it is a real interactive UI element, NOT passive academic prose!
        if element:
            tag = (element.get("tag") or "").lower()
            role = (element.get("role") or "").lower()
            if tag in ["button", "input", "select", "textarea"]:
                return False
            if tag == "a" and element.get("href"):
                return False
            if role in ["button", "link", "checkbox", "menuitem"]:
                return False

        # Educational & analytical framing phrases
        EDUCATIONAL_FRAMING = [
            "is an example of", "is a dark pattern", "known as confirmshaming",
            "technique called", "manipulative design pattern", "researchers define",
            "deceptive design where", "practice of using", "coined by",
            "according to the study", "criticized for using", "the term refers to",
            "often seen on", "illustrated by", "scholarly article", "ftc report",
            "in this article, we examine", "dark patterns are tricks",
            "categorized as", "study on dark patterns", "encyclopedic",
            "defined as", "user interface designed to trick", "confirmshaming is a",
            "roach motel refers to", "dark pattern practice", "academic paper",
        ]
        if any(f in lower for f in EDUCATIONAL_FRAMING):
            return True

        # Quotation analysis: A dark pattern phrase enclosed in quotes within descriptive prose
        has_quotes = ('"' in text) or ("'" in text) or ("“" in text) or ("”" in text)
        if has_quotes and len(text) > 60:
            return True

        return False

    def is_legitimate_context(self, text: str) -> bool:
        """Filter out legitimate, transparent pricing or normal cancellation controls."""
        lower = text.lower()
        return any(p in lower for p in LEGITIMATE_CONTEXT_PATTERNS)

    def _match_patterns(self, text: str, rule: dict) -> bool:
        """Check if text matches any pattern in a rule (case-insensitive)."""
        lower = text.lower()
        return any(p.lower() in lower for p in rule["patterns"] if p)

    def _make_detection(
        self,
        category: str,
        reason: str,
        visible_text: str,
        url: str,
        element_context: str,
        evidence: str,
        task_id: str,
        element_id: str = "",
        method: str = "rule",
        confidence: float = 0.95,
    ) -> dict:
        threat_type = "security_threat" if category == "prompt_injection" else "consumer_pattern"
        uncertainty = round(max(0.0, 1.0 - float(confidence)), 2)
        detection = {
            "category": category,
            "visible_text": visible_text[:500],
            "url": url,
            "element_id": element_id,
            "element_context": element_context[:300],
            "reason": reason,
            "evidence": evidence[:300],
            "task_id": task_id,
            "method": method,
            "confidence": round(float(confidence), 2),
            "threat_type": threat_type,
            "uncertainty": uncertainty,
        }
        log_detection(
            task_id=task_id,
            category=category,
            visible_text=visible_text[:500],
            url=url,
            element_context=element_context[:300],
            reason=reason,
            evidence=evidence[:300],
        )
        return detection

    def scan_page_text(self, text: str, url: str, task_id: str) -> list[dict]:
        """Scan visible page text using rules and local ML classifier."""
        detections = []
        is_educational = self.is_educational_or_quoted_context(text) or (self.is_informational_article(url) and not any(tag in text.lower() for tag in ["<button", "<input"]))

        # 1. Check deterministic rules
        for rule in DARK_PATTERN_RULES:
            if not rule["patterns"]:
                continue
            # When text is educational/quoted analysis, ONLY check security threats (prompt injection)
            if is_educational and rule["category"] != "prompt_injection":
                continue

            if self._match_patterns(text, rule):
                lower = text.lower()
                evidence = ""
                for p in rule["patterns"]:
                    idx = lower.find(p.lower())
                    if idx != -1:
                        start = max(0, idx - 20)
                        end = min(len(text), idx + len(p) + 40)
                        evidence = text[start:end]
                        break
                
                rule_conf = rule.get("confidence", 0.98 if rule["category"] == "prompt_injection" else 0.92)
                detections.append(
                    self._make_detection(
                        category=rule["category"],
                        reason=rule["reason"],
                        visible_text=evidence,
                        url=url,
                        element_context="page_text",
                        evidence=evidence,
                        task_id=task_id,
                        element_id="",
                        method="rule",
                        confidence=rule_conf,
                    )
                )

        # 2. Local ML Classifier check on paragraphs (suppressed on educational/quoted text)
        if not is_educational and self.ml.is_available and not self.is_legitimate_context(text):
            ml_res = self.ml.predict(text[:600])
            if ml_res.get("is_dark_pattern") and ml_res.get("confidence", 0.0) >= 0.65:
                cat = ml_res.get("category", "general_dark_pattern")
                if not any(d["category"] == cat for d in detections):
                    detections.append(
                        self._make_detection(
                            category=cat,
                            reason=f"Potential manipulation identified by local ML model ({cat.replace('_', ' ')})",
                            visible_text=text[:150],
                            url=url,
                            element_context="page_text",
                            evidence=text[:150],
                            task_id=task_id,
                            element_id="",
                            method="ml_classifier",
                            confidence=ml_res["confidence"],
                        )
                    )

        return detections

    def scan_element(self, element: dict, url: str, task_id: str) -> list[dict]:
        """Scan a single DOM element using rules, DOM geometry, and local ML classifier."""
        detections = []
        text = element.get("text") or element.get("label") or element.get("value") or ""
        element_id = (
            element.get("data-shadow-id")
            or element.get("shadow_id")
            or element.get("id")
            or ""
        )

        # Skip scanning if this is transparent pricing or legitimate user controls
        if self.is_legitimate_context(text):
            return detections

        # Check if this element is passive educational/quoted text
        if self.is_educational_or_quoted_context(text, element):
            # Only check for prompt injection in educational elements
            for rule in DARK_PATTERN_RULES:
                if rule["category"] == "prompt_injection" and self._match_patterns(text, rule):
                    detections.append(
                        self._make_detection(
                            category="prompt_injection",
                            reason=rule["reason"],
                            visible_text=text[:200],
                            url=url,
                            element_context=f"element:{element_id}",
                            evidence=text[:200],
                            task_id=task_id,
                            element_id=element_id,
                            method="rule",
                            confidence=0.98,
                        )
                    )
            return detections
        text = element.get("text") or element.get("label") or element.get("value") or ""
        element_id = (
            element.get("data-shadow-id")
            or element.get("shadow_id")
            or element.get("id")
            or ""
        )

        # Skip scanning if this is transparent pricing or legitimate user controls
        if self.is_legitimate_context(text):
            return detections

        # 1. Rule-based element scanning
        for rule in DARK_PATTERN_RULES:
            if not rule["patterns"]:
                continue
            if self._match_patterns(text, rule):
                lower = text.lower()
                evidence = ""
                for p in rule["patterns"]:
                    idx = lower.find(p.lower())
                    if idx != -1:
                        start = max(0, idx - 20)
                        end = min(len(text), idx + len(p) + 40)
                        evidence = text[start:end]
                        break
                detections.append(
                    self._make_detection(
                        category=rule["category"],
                        reason=rule["reason"],
                        visible_text=text[:200],
                        url=url,
                        element_context=f"element:{element_id}",
                        evidence=evidence,
                        task_id=task_id,
                        element_id=element_id,
                        method="rule",
                        confidence=0.98 if rule["category"] == "prompt_injection" else 0.95,
                    )
                )

        # 2. DOM Geometry & Visibility Analysis (Hidden Cancellation detection)
        # Check computed styles, bounding box, and hidden containers
        computed_style = element.get("computed_style") or {}
        opacity = float(computed_style.get("opacity", 1.0))
        bounding_rect = element.get("bounding_rect") or {}
        rect_width = bounding_rect.get("width", 100)
        rect_height = bounding_rect.get("height", 50)
        is_visible_flag = element.get("visible", True)

        is_cancel_action = any(w in text.lower() for w in ["cancel", "unsubscribe", "end subscription", "other options"])
        if is_cancel_action:
            is_hidden = (
                not is_visible_flag
                or opacity < 0.25
                or rect_width <= 1
                or rect_height <= 1
                or "other options" in text.lower()
            )
            if is_hidden:
                evidence_desc = (
                    f"Element '{element_id}' contains cancellation option but is obscured "
                    f"(visible={is_visible_flag}, opacity={opacity}, dimensions={rect_width}x{rect_height})"
                )
                detections.append(
                    self._make_detection(
                        category="hidden_cancellation",
                        reason="Cancellation option is obscured or buried behind non-standard controls",
                        visible_text=text[:200],
                        url=url,
                        element_context=f"element:{element_id} (hidden_or_obscured)",
                        evidence=evidence_desc,
                        task_id=task_id,
                        element_id=element_id,
                        method="dom_geometry",
                        confidence=0.96,
                    )
                )

        # 3. Local ML text classifier check on element text (if no rule matched)
        if not detections and self.ml.is_available and len(text.strip()) > 10:
            ml_pred = self.ml.predict(text)
            if ml_pred.get("is_dark_pattern") and ml_pred.get("confidence", 0.0) >= 0.78:
                cat = ml_pred.get("category", "general_dark_pattern")
                detections.append(
                    self._make_detection(
                        category=cat,
                        reason=f"Potential deceptive element text identified by local ML model ({cat.replace('_', ' ')})",
                        visible_text=text[:200],
                        url=url,
                        element_context=f"element:{element_id}",
                        evidence=text[:200],
                        task_id=task_id,
                        element_id=element_id,
                        method="ml_classifier",
                        confidence=ml_pred["confidence"],
                    )
                )

        return detections

    def scan_hierarchy(self, elements: list[dict], url: str, task_id: str) -> list[dict]:
        """
        Analyze visual hierarchy asymmetry between retention vs exit/opt-out options.
        Detects cases where a retention action is rendered with high visual prominence
        (primary CTA, large font) while cancellation or opt-out is hidden, low-contrast,
        or rendered as an inconspicuous ghost button.
        """
        detections = []
        if self.is_informational_article(url):
            return detections

        cancel_elements = []
        retention_elements = []

        for el in elements:
            text = (el.get("text") or el.get("label") or "").strip().lower()
            if not text:
                continue
            prominence = el.get("visual_prominence") or {}
            is_ghost = prominence.get("is_ghost", False)
            is_primary = prominence.get("is_primary", False)
            computed_style = el.get("computed_style") or {}
            opacity = float(computed_style.get("opacity", 1.0))

            if any(w in text for w in ["cancel", "unsubscribe", "opt out", "reject optional", "end membership"]):
                cancel_elements.append((el, text, is_ghost, is_primary, opacity))
            elif any(w in text for w in ["keep", "stay", "continue membership", "accept all", "claim offer", "keep subscription"]):
                retention_elements.append((el, text, is_ghost, is_primary, opacity))

        # If retention option is visually dominant (primary) while cancellation is suppressed (ghost or low opacity)
        if retention_elements and cancel_elements:
            for c_el, c_text, c_ghost, c_prim, c_opacity in cancel_elements:
                for r_el, r_text, r_ghost, r_prim, r_opacity in retention_elements:
                    if (r_prim and (c_ghost or c_opacity < 0.6)) or (c_ghost and not r_ghost):
                        c_id = c_el.get("data-shadow-id") or c_el.get("shadow_id") or c_el.get("id") or ""
                        r_id = r_el.get("data-shadow-id") or r_el.get("shadow_id") or r_el.get("id") or ""
                        evidence = (
                            f"Visual hierarchy asymmetry: Retention option '{r_text}' (# {r_id}) has primary prominence "
                            f"while cancellation option '{c_text}' (# {c_id}) is subdued (ghost={c_ghost}, opacity={c_opacity})"
                        )
                        detections.append(
                            self._make_detection(
                                category="misleading_cancellation",
                                reason="Visual hierarchy heavily favors retention while suppressing cancellation controls",
                                visible_text=f"{c_text} vs {r_text}",
                                url=url,
                                element_context=f"elements:{c_id}_vs_{r_id}",
                                evidence=evidence,
                                task_id=task_id,
                                element_id=c_id,
                                method="visual_hierarchy",
                                confidence=0.88,
                            )
                        )
                        break
        return detections

    def scan_preselected_options(self, elements: list[dict], url: str, task_id: str) -> list[dict]:
        """
        Detect pre-selected optional checkboxes/radios that opt the user into marketing,
        recurring add-ons, or non-essential data monetization.
        Explicitly distinguishes legitimate terms-of-service, login preferences, and accessibility settings.
        """
        detections = []

        BENIGN_CHECKBOX_PATTERNS = [
            "agree to terms", "terms of service", "terms and conditions",
            "privacy policy", "accept all terms", "i agree to the",
            "remember me", "stay signed in", "save login", "keep me logged in",
            "high contrast", "screen reader", "enable subtitles", "cookies",
            "accessible", "dark mode", "required",
        ]

        DECEPTIVE_OPT_IN_PATTERNS = [
            "send me marketing",
            "receive promotional",
            "partner offers",
            "newsletter",
            "auto-renew",
            "add insurance",
            "share browsing data",
            "optional protection",
            "third-party partners",
            "commercial partners",
            "paid protection",
            "trial converts to paid",
            "recurring add-on",
        ]

        for el in elements:
            tag = (el.get("tag") or "").lower()
            el_type = (el.get("type") or "").lower()
            if tag == "input" and el_type in ["checkbox", "radio"]:
                is_checked = el.get("checked", False)
                text = (el.get("label") or el.get("text") or el.get("value") or "").strip().lower()
                el_id = el.get("data-shadow-id") or el.get("shadow_id") or el.get("id") or ""

                if not is_checked:
                    continue

                # Ensure standard terms of service or remember me are NEVER flagged as forced continuity
                if any(benign in text for benign in BENIGN_CHECKBOX_PATTERNS):
                    continue

                if any(pat in text for pat in DECEPTIVE_OPT_IN_PATTERNS):
                    evidence = f"Option '{text}' is pre-checked by default without explicit user selection."
                    detections.append(
                        self._make_detection(
                            category="forced_continuity",
                            reason="Pre-selected option opts user into non-essential recurring commitment or data sharing",
                            visible_text=text[:200],
                            url=url,
                            element_context=f"element:{el_id} (pre-selected)",
                            evidence=evidence,
                            task_id=task_id,
                            element_id=el_id,
                            method="dom_attributes",
                            confidence=0.92,
                        )
                    )
        return detections

    def scan_all(self, page_snapshot: dict, task_id: str) -> list[dict]:
        """
        Full page scan combining:
        1. Individual element geometry, styling, and text rules.
        2. Visual hierarchy asymmetry (prominent retention vs ghost cancellation).
        3. Pre-selected opt-in checkboxes/radios.
        4. Repeated retention obstacles across sequential task steps.
        5. Page text rules and ML classification (with context-aware educational suppression).
        """
        url = page_snapshot.get("url", "")
        page_text = page_snapshot.get("page_text", "")
        elements = page_snapshot.get("elements", [])

        # 1. Scan individual elements first to bind exact element_ids
        element_detections = []
        element_seen = set()
        for element in elements:
            el_detections = self.scan_element(element, url, task_id)
            for d in el_detections:
                key = (d["category"], d["element_id"])
                if key not in element_seen:
                    element_seen.add(key)
                    element_detections.append(d)

        # 2. Visual hierarchy asymmetry check
        hierarchy_detections = self.scan_hierarchy(elements, url, task_id)
        for hd in hierarchy_detections:
            key = (hd["category"], hd["element_id"])
            if key not in element_seen:
                element_seen.add(key)
                element_detections.append(hd)

        # 3. Pre-selected opt-in check (with benign terms exclusion)
        preselected_detections = self.scan_preselected_options(elements, url, task_id)
        for pd in preselected_detections:
            key = (pd["category"], pd["element_id"])
            if key not in element_seen:
                element_seen.add(key)
                element_detections.append(pd)

        # 4. Check for repeated retention obstacles across journey steps
        if task_id:
            try:
                from database import get_detections_for_task
                past_detections = get_detections_for_task(task_id)
                past_retentions = [d for d in past_detections if d.get("category") in ("retention_offer", "repeated_retention")]
                curr_retentions = [d for d in element_detections if d.get("category") == "retention_offer"]
                if past_retentions and curr_retentions:
                    for cr in curr_retentions:
                        evidence = f"Repeated retention obstacles encountered across multiple sequential steps ({len(past_retentions) + 1} offers)."
                        key = ("repeated_retention", cr.get("element_id", ""))
                        if key not in element_seen:
                            element_seen.add(key)
                            element_detections.append(
                                self._make_detection(
                                    category="repeated_retention",
                                    reason="Multiple retention offers blocking cancellation path across repeated steps",
                                    visible_text=cr.get("visible_text", "")[:200],
                                    url=url,
                                    element_context=cr.get("element_context", ""),
                                    evidence=evidence,
                                    task_id=task_id,
                                    element_id=cr.get("element_id", ""),
                                    method="sequential_history",
                                    confidence=0.96,
                                )
                            )
                        break
            except Exception:
                pass

        # 5. Scan full page text (with educational context check)
        text_detections = self.scan_page_text(page_text, url, task_id)

        # 6. Combine without duplicating already element-identified categories
        detections = list(element_detections)
        covered_categories = {d["category"] for d in element_detections if d.get("element_id")}
        for td in text_detections:
            if td["category"] not in covered_categories:
                detections.append(td)

        return detections
