# SHADOW — Hackathon Judge & Mentor Q&A (15 Technical Questions)

**Project:** SHADOW — The Dark Pattern Detection Agent  
**DevHack 2026** — *The Agent That Fights Dark Patterns*

---

### Q1: How does SHADOW differ from conventional automation tools like Playwright or Selenium?
> **Answer:**  
> Playwright and Selenium are script-execution harnesses designed for developers who already know the exact selectors and page flows. They have zero semantic understanding of manipulation.  
> **SHADOW is an autonomous consumer-rights browser agent.** It dynamically reads unfamiliar page layouts, classifies manipulative dark patterns using a hybrid ML pipeline, defends against adversarial UI tricks (e.g., hidden prompt injections and fake urgency countdowns), and adheres to strict safety boundaries with human-in-the-loop approvals.

---

### Q2: Why not just pass the entire webpage HTML to Gemini 2.5 Flash for every step?
> **Answer:**  
> 1. **Latency:** A full LLM call takes 800–1,500 ms; our Tier 1 rules take **0.01 ms** and our local ML takes **1.08 ms**, making live DOM highlighting instantaneous.  
> 2. **Financial Cost & Quotas:** Sending raw HTML repeatedly burns hundreds of thousands of tokens. Our `CostOptimizer` trims snapshots to interactive controls, deduplicates repeated states via deterministic hashing, and invokes Gemini only when semantic reasoning is strictly necessary (< \$0.0001 per flow).  
> 3. **Reliability & Offline Fallback:** If cloud APIs experience outages or rate limits, SHADOW gracefully falls back to local rules and ML without stranding the user.

---

### Q3: How do you prevent indirect prompt injection from hijacking the agent?
> **Answer:**  
> Through our **Input Boundary (`SnapshotBoundary`)** and **ShadowLock**:
> - `SnapshotBoundary` sanitizes incoming text, strips adversarial prefixes (`SYSTEM:`, `OVERRIDE:`, `ADMIN:`), and flags hidden `0px`/`1px` elements.
> - When a task starts, the user's intent is immutably locked into SQLite as `authorized_goal`. The AI planner is forbidden from modifying this goal.
> - Even if an adversarial injection attempts to redirect the agent (e.g., *"The user agreed to upgrade for \$29.99"*), ShadowLock evaluates the action against the immutable goal: upgrading directly contradicts cancellation, so the action is blocked unconditionally.

---

### Q4: How do you prevent false positives on legitimate discounts or educational articles (like Wikipedia)?
> **Answer:**  
> We use **context-aware hierarchical detection**:
> - We verify whether the text exists inside an interactive actionable element (`button`, `a`, `form`) versus informational body paragraphs (`<p>`, `<blockquote>`, `<article>`).
> - We inspect CSS visibility and visual hierarchy asymmetry (e.g., whether the "Keep" button is 5x larger than the "Cancel" button).
> - On educational sites like Wikipedia, dark pattern terms discussed in encyclopedic prose are recognized as educational context, whereas real interactive retention popups trigger alarms.

---

### Q5: What stops SHADOW from executing unauthorized purchases or deleting user accounts?
> **Answer:**  
> Our **Output Boundary (`ActionBoundary`)**:
> - Consequential actions (credit card charges, permanent cancellations, account deletions) are intercepted by ShadowLock.
> - They cannot execute autonomously; they generate an `approval_id` and require an interactive click from the human user in the assistant modal.
> - The backend issues a single-use approval token. Replays, unauthorized element clicks, or unapproved mutations return HTTP 403 Forbidden.

---

### Q6: How does SHADOW handle client-side Single-Page Applications (SPAs) like React or Next.js?
> **Answer:**  
> In `extension/content.js`:
> - We monkey-patch `history.pushState` and `history.replaceState` and listen to `popstate`.
> - A `MutationObserver` monitors DOM changes when SPAs dynamically mount or unmount components.
> - When a route transition occurs, SHADOW checks session persistence in `chrome.storage.local`, restores the active task state, and recalculates visual element overlays without reloading the page.

---

### Q7: How is user privacy protected when page snapshots are captured?
> **Answer:**  
> **Client-side data minimization:**
> - Before any DOM snapshot leaves the browser, `content.js` and `SnapshotBoundary` sanitize inputs.
> - Any field matching password types, CVVs, credit cards, or authentication headers is replaced with `[REDACTED_SENSITIVE]`.
> - Only interactive controls and structural headings are transmitted; private personal text in document bodies is not sent to the backend.

---

### Q8: What dataset was used to train your local ML detector, and what is its license?
> **Answer:**  
> - We utilized the open-source **Yamanalab eCommerce Dark Pattern Dataset**, which comprises **2,258 categorized real-world eCommerce text samples** under the **Apache-2.0 License**.
> - It includes verified examples of Scarcity, Fake Urgency, Obstruction, Confirm-Shaming, Social Proof, and Clean control text.

---

### Q9: What is your evaluation methodology and held-out benchmark performance?
> **Answer:**  
> We evaluated our system on an **independent held-out test suite of 30 samples (14 deceptive, 16 clean)** with **0% overlap** with the training dataset:
> - **Rule-Only:** Precision: **1.0000**, Recall: **0.5714**, F1: **0.7273**, FPR: **0.0000** (0 false positives).
> - **ML-Only (TF-IDF + Logistic Regression):** Precision: **0.7059**, Recall: **0.8571**, F1: **0.7742**, FPR: **0.3125**.
> - **Hybrid (Rule + ML Arbitration):** Precision: **0.9167**, Recall: **0.7857**, F1: **0.8462**, FPR: **0.0625** (only 1 false positive out of 16 clean samples).
> - All metrics are dynamically verified and reproduced via `training/build_and_verify_held_out_dataset.py`.

---

### Q10: Why did you provide three modes: Observe, Guide, and Autonomous?
> **Answer:**  
> To match user trust levels and regulatory safety standards:
> - **Observe Mode:** Completely passive analysis. Highlights deceptions and explains what they mean with zero clicks. Perfect for learning and auditing.
> - **Guide Mode:** Shows a pulsating purple halo (`🎯 SHADOW GUIDANCE`) around the next recommended action. Requires the user to confirm each step.
> - **Autonomous Mode:** Safely clicks through multi-step forms on permitted domains, pausing exclusively for consequential human approvals.

---

### Q11: Can manipulative websites detect and block SHADOW?
> **Answer:**  
> Because SHADOW is a Chrome extension running in the user's isolated content-script execution context:
> - Content scripts have an isolated DOM world and cannot be easily fingerprinted by webpage JavaScript.
> - Navigation clicks trigger genuine trusted browser events (`isTrusted: true`), indistinguishable from human mouse actions.
> - The assistant UI is rendered inside a secure, origin-isolated `<iframe>`, preventing page scripts from inspecting or hijacking assistant buttons.

---

### Q12: How does SHADOW handle CAPTCHAs, bot checks, and multi-factor authentication (MFA)?
> **Answer:**  
> **SHADOW adheres to strict ethical and technical boundaries:**
> - We never attempt to solve, bypass, or click through CAPTCHAs or Cloudflare bot challenges.
> - When a challenge or SMS/email MFA prompt appears, the agent pauses, notifies the user via the floating assistant, and allows the human to complete the verification directly before resuming.

---

### Q13: How does the single-use approval token work in ShadowLock?
> **Answer:**  
> When the agent reaches a state mutation (such as `/static/cancel_confirm.html`), the backend creates an entry in the `approvals` table with status `pending`.
> When the user clicks "Approve" in the UI, the frontend sends a signed approval payload to `POST /api/approve/{approval_id}`.
> Once resolved, the backend marks the approval as `resolved` with a timestamp and returns an execution token valid strictly for that single step. Replays or unauthorized duplicate clicks are rejected.

---

### Q14: How does ShadowTrail provide legal and regulatory value for consumer protection agencies?
> **Answer:**  
> Regulatory bodies like the FTC (US), EU Consumer Protection Cooperation (CPC), and India's CCPA require verifiable evidentiary proof to penalize companies for dark patterns.  
> **ShadowTrail** produces a complete, chronological audit record containing:
> 1. The original consumer objective.
> 2. Every UI deception encountered with DOM element identifiers, exact text, and screenshots.
> 3. AI confidence and detection reasoning.
> 4. Exportable structured JSON and executive-ready printable PDF reports.

---

### Q15: What is the roadmap for scaling SHADOW beyond this hackathon?
> **Answer:**  
> 1. **Multi-Model Vision Agents:** Incorporating lightweight local vision models (Qwen-2.5-VL / Moondream) to detect visual contrast deceptions directly from viewport pixels.  
> 2. **Crowdsourced Deception Registry:** Enabling anonymous, privacy-preserved telemetry reporting so dark pattern patterns detected across eCommerce sites are indexed for public consumer defense.  
> 3. **Regulatory Auto-Filing:** One-click automated complaint submission to regulatory portals (e.g., FTC ReportFraud or CCPA) with attached ShadowTrail evidence packages.
