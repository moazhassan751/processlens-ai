# ProcessLens — Live Demo Guide & Presenter Script

> **Step-by-Step Presenter Cheatsheet**: Exactly What to Click, What to Do, and What to Say.

---

## 🎙️ The 30-Second Elevator Pitch (Memorize This!)

> *"ProcessLens is an Enterprise Process Intelligence platform. In simple terms, it takes messy company spreadsheets and does 3 things:*
> 1. ***Draws a visual roadmap*** *of how work actually moves, highlighting where orders get stuck.*
> 2. ***Acts as a weather forecast for delays***, *predicting which active orders will be late before customers complain.*
> 3. ***Prescribes the exact action*** *to take right now to prevent the delay."*

---

## 1. Jargon Decoder: Difficult Words ➔ Plain English

| Difficult Term on Screen | What You Should Say (Plain English) |
| :--- | :--- |
| **Process Discovery** | Drawing the visual roadmap of our business orders from raw timestamps. |
| **Bottleneck** | The biggest traffic jam in the process where cases wait the longest. |
| **Process Conformance** | Rule-checking to see whether employees followed company policy or took detours. |
| **Rework Loop** | Bouncing back: an order had an error, was rejected, and had to be reviewed twice. |
| **Trace Fitness** | The compliance score (0.97 means 97% of steps followed the clean rule). |
| **What-If Simulation** | A time-machine calculator: *"If approvals are 30% faster, how much company time is saved?"* |
| **In-Flight Open Cases** | Active orders currently being worked on today that haven't finished yet. |
| **Predictive Late Risk** | The AI weather forecast warning which active orders will miss their deadline. |
| **SHAP Feature Drivers** | The exact reasons why an order is delayed (e.g. waiting in the queue for 5 hours). |
| **Prescriptive Next Action** | The doctor's prescription telling the manager exactly how to fix the delay right now. |

---

## 2. The 5-Minute Step-by-Step Live Demo Script

Open your browser at **[http://localhost:3100](http://localhost:3100)**.

---

### ▶ STEP 1: Process Discovery & The Bottleneck
* **📍 Location:** Tab: `PROCESS DISCOVERY` (Default Tab)
* **🖱️ WHAT TO DO / WHAT TO CLICK:**
  * Point your mouse to the central interactive flowchart (the boxes and arrows).
  * Scroll down slightly to point out the **Bottleneck Analysis** table at the bottom.
* **🗣️ WHAT TO SAY (Talking Points):**
  > *"Welcome to ProcessLens. Right here on the Discovery tab, our platform automatically mined 300 real Purchase Order records and generated this visual flowchart.*
  >
  > *Instead of guessing how work gets done, we can see the exact journey from 'Submitted' to 'Completed'.*
  >
  > *Notice the red highlight pointing to 'Approved': ProcessLens instantly exposes that orders wait at this step for an average of 30.26 hours! That is our primary operational traffic jam."*
* **💡 Pro-Tip:** Explain that this isn't a manual drawing; it is calculated directly from raw event timestamps.

---

### ▶ STEP 2: Interactive Event Log Filtering (Phase H8)
* **📍 Location:** Tab: `PROCESS DISCOVERY` (Filter Bar Above Map)
* **🖱️ WHAT TO DO / WHAT TO CLICK:**
  * Click the button **`Alice Johnson`** in the resource filter bar above the graph.
  * Point to the live badge: `Showing 147 of 300 cases (49.0%)`.
  * Point to the graph updating live with her specific cycle times.
  * Click **`Clear filters`** to reset back to all 300 cases.
* **🗣️ WHAT TO SAY (Talking Points):**
  > *"In traditional tools, filtering requires running slow database scripts. Here, ProcessLens does it in real-time.*
  >
  > *Watch as I click 'Alice Johnson' — the graph instantly narrows to the 147 orders she touched, recalculating transition times and bottleneck stats completely in-memory.*
  >
  > *I click 'Clear filters', and we immediately return to the full 300-case company view."*
* **💡 Pro-Tip:** The audience will love that there is no page reload and zero lag.

---

### ▶ STEP 3: Rule Conformance & Rework Loops
* **📍 Location:** Tab: `PROCESS CONFORMANCE` (Click 2nd Tab)
* **🖱️ WHAT TO DO / WHAT TO CLICK:**
  * Click the **`PROCESS CONFORMANCE`** tab.
  * Point to the **`82.0% Conformance Rate`** card.
  * Point to the **`54 Deviating Cases`** card.
  * Show the bottom table detailing the `Sent Back for Correction` rework loop.
* **🗣️ WHAT TO SAY (Talking Points):**
  > *"Now let's check policy compliance. Our company rule is simple: Submitted ➔ Reviewed ➔ Approved ➔ Completed.*
  >
  > *ProcessLens runs token-based replay and reveals that 82% of orders followed the clean rule.*
  >
  > *However, 18% of orders broke policy by going through a rework loop: they were rejected and sent back for correction. ProcessLens proves that each rework loop added 5.5 hours of wasted delay to those orders."*
* **💡 Pro-Tip:** Emphasize that this catches waste and policy violations that spreadsheets hide.

---

### ▶ STEP 4: What-If Simulation (ROI Calculator)
* **📍 Location:** Tab: `WHAT-IF SIMULATION` (Click 3rd Tab)
* **🖱️ WHAT TO DO / WHAT TO CLICK:**
  * Click the **`WHAT-IF SIMULATION`** tab.
  * Ensure Target Activity is set to **`Approved`** and Duration Reduction is set to **`30%`**.
  * Click the purple button: **`Run What-If Simulation`**.
  * Point to the before/after results: `37.95h ➔ 28.87h (-9.08h savings)`.
* **🗣️ WHAT TO SAY (Talking Points):**
  > *"Before investing money into hiring or software, executives ask: 'What will we actually gain if we fix this bottleneck?'*
  >
  > *In the What-If Simulator, we test reducing the Approved bottleneck by 30%.*
  >
  > *With one click, ProcessLens calculates that total company cycle time drops from 37.95 hours down to 28.87 hours — saving 9.08 hours per order, or a 23.9% total efficiency gain!"*
* **💡 Pro-Tip:** Managers love this because it gives mathematical justification for team investments.

---

### ▶ STEP 5: Predictive Risk & The Case Intelligence Drawer
* **📍 Location:** Tab: `PREDICTIVE RISK & OPEN CASES` (Click 4th Tab)
* **🖱️ WHAT TO DO / WHAT TO CLICK:**
  * Click the **`PREDICTIVE RISK & OPEN CASES`** tab.
  * Show the Model Benchmark card (0.826 ROC-AUC accuracy).
  * Scroll down to the **In-Flight Open Cases** table.
  * Find row **`OPEN-0004`** (marked with a red Late Risk badge).
  * Click the **`Explain Case`** button on row **`OPEN-0004`** to open the slide-out drawer.
  * Show the Risk Gauge (64%), the SHAP Driver chart, and the Prescriptive Action card.
* **🗣️ WHAT TO SAY (Talking Points):**
  > *"Historical analysis is great, but what about orders in progress today?*
  >
  > *Our machine learning model monitors active orders and flags delays in advance.*
  >
  > *Look at case OPEN-0004: it is flagged in red with a 64.3% risk of missing its deadline.*
  >
  > *When I click 'Explain Case', the AI drawer slides out and explains why: the order has been waiting in the queue for over 5 hours.*
  >
  > *Best of all, ProcessLens prescribes the solution: 'Expedite Approval Step'. It mathematically calculates that doing this will reduce risk from 64.3% down to 42.1% (-22% reduction)!"*
* **💡 Pro-Tip:** Close the drawer by clicking **`Done`** at the bottom to transition smoothly.

---

### ▶ STEP 6: Enterprise Pipeline & Data Connectors
* **📍 Location:** Tab: `DATA MANAGEMENT` & `AUDIT HISTORY`
* **🖱️ WHAT TO DO / WHAT TO CLICK:**
  * Click the **`DATA MANAGEMENT`** tab.
  * Show the CSV Upload area, the PostgreSQL database connector tab, and the **`Reset to Synthetic Data`** button.
  * Point out the top-right **`Run Pipeline (Async)`** button.
* **🗣️ WHAT TO SAY (Talking Points):**
  > *"Finally, ProcessLens is enterprise-ready:*
  > • *It connects directly to enterprise databases like PostgreSQL.*
  > • *It sanitizes CSV uploads against malicious formula injection attacks.*
  > • *It features asynchronous background pipeline execution with full audit history.*
  >
  > *That is ProcessLens: Discover bottlenecks, enforce compliance, simulate fixes, predict active delays, and prescribe solutions!"*
* **💡 Pro-Tip:** Finish with confidence and ask for their questions.

---

## 3. Anticipated Questions & Winning Answers

* **Q: Can ProcessLens work with our company's real data?**
  * **A:** Yes! It supports any standard process log containing 4 columns: Case ID, Activity, Timestamp, and Resource. You can upload CSVs directly or connect to an existing database like PostgreSQL.
* **Q: How is the delay prediction calculated?**
  * **A:** We train a tuned Random Forest and LightGBM model on past completed cases. It looks at how long steps took, who handled them, and how congested the overall system was to predict delay probabilities.
* **Q: How does the AI explain its recommendations?**
  * **A:** It uses exact SHAP TreeExplainer math. Instead of guessing, it calculates the exact mathematical contribution of each factor (like queue waiting time) and tests the risk reduction of fixing that bottleneck.
* **Q: Why does the approval step take 30 hours in the demo?**
  * **A:** Because our 300-order sample data reflects real-world operations where managers only review batches once or twice a week, creating an approval bottleneck that ProcessLens easily catches.
