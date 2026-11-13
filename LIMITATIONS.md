# SHADOW — Limitations, Ethical Boundaries & Future Roadmap

**Project:** SHADOW — The Dark Pattern Detection Agent  
**DevHack 2026** — *The Agent That Fights Dark Patterns*

---

## 1. Current Technical Limitations

### 1.1 Held-Out Evaluation Sample Size
- **Current State:** Our held-out evaluation suite contains **30 carefully curated samples (14 deceptive, 16 clean)** with 0% overlap with the training set.
- **Limitation:** While it yields statistically meaningful comparative metrics (Hybrid F1: 0.8462 vs Rule F1: 0.7273), 30 samples is a compact validation benchmark.
- **Mitigation:** Future milestones will incorporate the full Kaggle/Princeton Dark Pattern dataset (~1,800 eCommerce crawl samples) for expanded benchmark validation.

### 1.2 Deep Shadow DOM & Cross-Origin Iframes
- **Current State:** SHADOW inspects the top-level window DOM and standard light DOM elements.
- **Limitation:** Iframes hosted on cross-origin third-party domains (e.g., embedded Stripe payment elements or external checkout widgets) are isolated by the browser Same-Origin Policy.
- **Mitigation:** SHADOW uses Manifest V3 `all_frames: true` where permitted, but strictly adheres to browser sandbox rules without attempting origin bypass.

### 1.3 Canvas and WebGL Interactive Controls
- **Current State:** Detection relies on semantic DOM nodes (`<button>`, `<a>`, `<input>`, `<dialog>`).
- **Limitation:** Web applications that render interactive controls exclusively using `<canvas>` or WebGL (e.g., interactive 3D configurators or custom graphical forms) lack inspectable text nodes.
- **Mitigation:** Integration of vision-language models (e.g., Qwen-2.5-VL / Moondream) as an image-based fallback tier.

---

## 2. Ethical Safety Boundaries & Non-Negotiables

SHADOW was designed from the ground up to protect consumers ethically. We enforce strict behavioral constraints:

| Boundary | Enforcement | Rationale |
| :--- | :--- | :--- |
| **No CAPTCHA / Bot Bypass** | Agent pauses immediately and hands off control to human. | Defeating proof-of-work checks or human verification gates violates platform Terms of Service and cybersecurity ethics. |
| **No Auto-Purchase** | Actions involving financial charges are blocked unconditionally. | An AI agent should never spend consumer money without explicit, real-time human authorization. |
| **No Password / CVV Scraping** | Fields are replaced with `[REDACTED_SENSITIVE]` client-side. | Prevents exposure of sensitive credentials to cloud LLMs or persistent database logs. |
| **No Unauthorized Clicks on Real Web** | Observe and Guide modes use passive visual badges only. | Prevents unintended state mutations or data corruption on public websites. |

---

## 3. Legal and Regulatory Disclaimers

1. **Evidentiary Support vs Legal Counsel:**  
   ShadowTrail reports provide structured client-side telemetry and cryptographic records of observed DOM manipulations. However, they represent technical evidence rather than formal legal advice.
2. **Platform Terms of Service:**  
   SHADOW operates solely as a client-side consumer agent assisting the user with their own accounts. It does not perform distributed scraping, account cracking, or automated spamming.

---

## 4. Engineering Roadmap

1. **Phase 7 (Post-Hackathon): Multi-Modal Vision Model**  
   - Run a lightweight, on-device quantized model (Moondream2 / Qwen2-VL) to detect visual contrast deceptions (e.g., `#fafafa` cancel button on a `#ffffff` card).
2. **Phase 8: Decentralized Pattern Registry**  
   - Enable an optional, privacy-preserving telemetry feed where verified dark patterns from major eCommerce platforms are published to an open-source consumer defense database.
3. **Phase 9: Automated Regulatory Auto-Filing**  
   - Allow users to export their signed ShadowTrail PDF report directly to the FTC ReportFraud portal, the European Consumer Centres Network (ECC-Net), or India's National Consumer Helpline with one click.
