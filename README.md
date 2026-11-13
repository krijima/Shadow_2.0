# SHADOW

**DevHack 2026 · PS 2 — The Agent That Fights Dark Patterns**

SHADOW is a Chrome and Edge extension that helps people cancel subscriptions across websites. It identifies manipulative controls, follows navigation it can verify, and leaves consequential decisions to the user. At the end, it shows what happened in an audit report.

## The problem

Signing up can take one click. Cancelling can mean hunting for hidden controls, declining repeated discounts, and getting past countdowns and guilt-inducing prompts. These same tactics can mislead browser agents, including through instructions hidden in webpage text.

## How SHADOW helps

1. **Detect.** ShadowScan examines page text and controls for patterns such as fake urgency, retention offers, confirm-shaming, and concealed cancellation options. It combines rules and a local text classifier.
2. **Defend.** ShadowLock keeps the user's goal separate from webpage instructions. SHADOW checks proposed actions against the current page and halts when it detects an attempt to override the goal.
3. **Act.** The extension advances through verified navigation or guides the user, depending on the mode. Consequential actions require the user's decision.
4. **Record.** ShadowTrail records the task outcome, actions, detections, and approval decisions. Every mode shows an audit summary when the task ends, with a link to the full report.

## Quick Start

**Windows prerequisites** · Python 3.11 or later, Git, and Chrome or Edge.

### 1. Clone and install

Open PowerShell and run these commands from the folder where you want to put the project.

```powershell
git clone https://github.com/krijima/Shadow_2.0.git
Set-Location .\Shadow_2.0
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you already cloned the repo, open PowerShell in the folder containing `requirements.txt` and run the last two commands.

### 2. Configure the backend

Create a file named `.env` in the same folder as `requirements.txt`. Add these settings and replace the placeholder with your Gemini API key.

```dotenv
GEMINI_API_KEY=your_gemini_api_key_here
STREAMCOVE_URL=http://127.0.0.1:8081
```

### 3. Start the two services

Open **two PowerShell windows** in the `Shadow_2.0` folder and keep both open.

**Window 1 — SHADOW backend**

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8001
```

**Window 2 — StreamCove**

```powershell
.\.venv\Scripts\python.exe -m uvicorn server:app --app-dir streamcove --host 127.0.0.1 --port 8081
```

The repository also includes a Windows launcher. To use it, activate the virtual environment with `.\.venv\Scripts\Activate.ps1` and run `.\START_DEMO.ps1` from the project folder.

### 4. Load the extension

1. Open `chrome://extensions` in Chrome or `edge://extensions` in Edge.
2. Enable **Developer mode**, select **Load unpacked**, and choose the `extension` folder inside `Shadow_2.0`.
3. Open or refresh [StreamCove Home](http://127.0.0.1:8081/static/index.html). The SHADOW assistant should appear on the page.
4. To try SHADOW on another website, open the extension's toolbar popup and select **Activate SHADOW**. Allow access to that site when prompted.

## Demo for judges

1. Open the [Demo Control Center](http://127.0.0.1:8081/static/demo_control.html). Select **Fake Urgency (Countdown)** and click **Reset Subscription to ACTIVE**.
2. Open [StreamCove Home](http://127.0.0.1:8081/static/index.html), select **Demo** in SHADOW, enter **“Cancel my subscription. Do not accept discount offers or upgrades.”**, and click **Start** once.
3. Watch SHADOW navigate the cancellation flow. At the final decision, **Approve & Execute** cancels the simulated subscription. **Reject Action** leaves it active.
4. When the task ends, open **View Audit Evidence Report** in the assistant. Point out the flagged pattern, the action taken, and the approval decision.

For a separate safety demo, reset StreamCove and choose **Prompt Injection Attack**. When SHADOW detects the hidden override attempt, it halts the task and records why.

## Modes

| Mode | What the user sees |
| --- | --- |
| **Observe** | SHADOW automatically follows verified reversible steps. It pauses for the user's decision at consequential steps or when it cannot verify a safe next action. |
| **Guide** | SHADOW highlights the next control. After the user clicks, it follows the page or dialog change and shows the next step. |
| **Demo** | SHADOW navigates the simulated StreamCove flow and asks for explicit approval before final cancellation. |

Website layout, permissions, and billing arrangements affect which steps SHADOW can verify. Subscription cancellation is the workflow demonstrated in this project.

## How it fits together

The Manifest V3 extension captures page controls and redacts sensitive input fields before sending the snapshot to the FastAPI backend. ShadowScan flags patterns, ShadowNavigate proposes steps using the configured Gemini model or a supported route, and ShadowLock and the action boundary validate the next action. ShadowTrail stores the task history in SQLite and serves the full HTML audit report, which can be printed or saved as a PDF.

## Testing

The repository includes checks for sensitive-field redaction, navigation boundaries, cancellation approval, and audit summaries. To install Chromium for Playwright and run the local tests, run the following from the project folder. Browser integration tests may also require running services and browser configuration.

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest tests/
```

## Future scope

- Validate cancellation on more unfamiliar websites, including workflows that redirect users to another billing provider.
- Compare manual and SHADOW-assisted cancellation on the same scenarios using completion rate, elapsed time, and user clicks.
- Extend the workflow to cookie opt-outs, refunds, compensation claims, and charge disputes.
- Add visual detection for deceptive layouts and integrity checks for exported audit records.

## 👥 Team & Acknowledgements

### Hackathon Team

- **Team Name** · `Team lastmoment` (DevHack 2026)
- **Project Lead & Development** · `lastmoment team`
- **Mahalaxmi Vishnu Shanbhag** · Team leader
- **Jeevan Chandrahas Naik** · Team member
- **Kritharth Jain** · Team member

Thanks to the DevHack organizers and the maintainers of the open-source tools and dataset used in this project.

## License

The project is licensed under the [MIT License](LICENSE). The bundled training dataset has a [separate license](training/data/LICENSE.txt).
