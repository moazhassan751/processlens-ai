"""
Script to generate ProcessLens_Live_Demo_Guide.docx and ProcessLens_Live_Demo_Guide.pdf.
"""

import os
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
import fitz  # PyMuPDF

def set_cell_background(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def create_docx(filename):
    doc = Document()
    
    # Page setup - 0.75 inch margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.75)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)
        
    # Styles
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)
    font.color.rgb = RGBColor(0x1e, 0x29, 0x3b) # Slate 800

    # Document Header
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = p_title.add_run("ProcessLens — Live Demo Guide & Presenter Script")
    run_title.font.name = 'Arial'
    run_title.font.size = Pt(24)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(0x38, 0x43, 0xd0) # Indigo

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = p_sub.add_run("Step-by-Step Presenter Cheatsheet: Exactly What to Click, What to Do & What to Say")
    run_sub.font.size = Pt(13)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(0x64, 0x74, 0x8b) # Slate 500

    doc.add_paragraph() # Spacer

    # -------------------------------------------------------------
    # Callout Box: 30-Second Elevator Pitch
    # -------------------------------------------------------------
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    set_cell_background(cell, "F1F5F9") # Slate 100
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)
    
    p = cell.paragraphs[0]
    r = p.add_run("🎙️ The 30-Second Elevator Pitch (Memorize This!)\n")
    r.bold = True
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(0x1e, 0x1b, 0x4b) # Indigo dark
    
    r_body = p.add_run(
        "\"ProcessLens is an Enterprise Process Intelligence platform. In simple terms, it takes messy company spreadsheets "
        "and does 3 things:\n"
        "1. It automatically draws a visual roadmap of how work actually moves, highlighting where orders get stuck.\n"
        "2. It acts as a weather forecast for delays, predicting which active orders will be late before customers complain.\n"
        "3. It gives managers a prescription, telling them the exact action to take right now to prevent the delay.\""
    )
    r_body.font.size = Pt(10.5)
    r_body.font.italic = True

    doc.add_paragraph()

    # -------------------------------------------------------------
    # Section 1: The Jargon Decoder
    # -------------------------------------------------------------
    h1 = doc.add_heading("1. Jargon Decoder: Hard Words ➔ Plain English", level=1)
    h1.runs[0].font.color.rgb = RGBColor(0x0f, 0x17, 0x2a)
    
    doc.add_paragraph("Keep this cheat-table in mind whenever you look at the screen:")

    t_jargon = doc.add_table(rows=1, cols=2)
    t_jargon.style = 'Table Grid'
    t_jargon.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_cells = t_jargon.rows[0].cells
    hdr_cells[0].text = "Difficult Term on Screen"
    hdr_cells[1].text = "What You Should Say (Plain English)"
    set_cell_background(hdr_cells[0], "1E293B")
    set_cell_background(hdr_cells[1], "1E293B")
    for cell in hdr_cells:
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.bold = True
                r.font.color.rgb = RGBColor(0xff, 0xff, 0xff)

    jargon_items = [
        ("Process Discovery", "Drawing the visual roadmap of our business orders from raw timestamps."),
        ("Bottleneck", "The biggest traffic jam in the process where cases wait the longest."),
        ("Process Conformance", "Rule-checking to see whether employees followed company policy or took detours."),
        ("Rework Loop", "Bouncing back: an order had an error, was rejected, and had to be reviewed twice."),
        ("Trace Fitness", "The compliance score (0.97 means 97% of steps followed the clean rule)."),
        ("What-If Simulation", "A time-machine calculator: 'If approvals are 30% faster, how much company time is saved?'"),
        ("In-Flight Open Cases", "Active orders currently being worked on today that haven't finished yet."),
        ("Predictive Late Risk", "The AI weather forecast warning which active orders will miss their deadline."),
        ("SHAP Feature Drivers", "The exact reasons why an order is delayed (e.g. waiting in the queue for 5 hours)."),
        ("Prescriptive Next Action", "The doctor's prescription telling the manager exactly how to fix the delay right now.")
    ]

    for term, plain in jargon_items:
        row_cells = t_jargon.add_row().cells
        row_cells[0].text = term
        row_cells[0].paragraphs[0].runs[0].font.bold = True
        row_cells[1].text = plain
        set_cell_background(row_cells[0], "F8FAFC")
        set_cell_background(row_cells[1], "FFFFFF")

    doc.add_paragraph()

    # -------------------------------------------------------------
    # Section 2: Step-by-Step Live Demo Walkthrough
    # -------------------------------------------------------------
    h2 = doc.add_heading("2. The 5-Minute Step-by-Step Live Demo Script", level=1)
    h2.runs[0].font.color.rgb = RGBColor(0x0f, 0x17, 0x2a)

    demo_steps = [
        {
            "num": "STEP 1",
            "title": "Process Discovery & The Bottleneck",
            "tab": "Tab: PROCESS DISCOVERY (Default Tab)",
            "do": [
                "Make sure you are on http://localhost:3100 on the 'PROCESS DISCOVERY' tab.",
                "Point your mouse to the central interactive flowchart (the boxes and arrows).",
                "Scroll down slightly to point out the 'Bottleneck Analysis' table at the bottom."
            ],
            "say": (
                "\"Welcome to ProcessLens. Right here on the Discovery tab, our platform automatically mined 300 real "
                "Purchase Order records and generated this visual flowchart.\n\n"
                "Instead of guessing how work gets done, we can see the exact journey from 'Submitted' to 'Completed'.\n\n"
                "Notice the red highlight pointing to 'Approved': ProcessLens instantly exposes that orders wait at this step "
                "for an average of 30.26 hours! That is our primary operational traffic jam.\""
            ),
            "tip": "Explain that this isn't a manual drawing; it is calculated directly from raw event timestamps."
        },
        {
            "num": "STEP 2",
            "title": "Interactive Event Log Filtering (Phase H8)",
            "tab": "Tab: PROCESS DISCOVERY (Filter Bar Above Map)",
            "do": [
                "Click the button 'Alice Johnson' in the resource filter bar above the graph.",
                "Point to the live badge: 'Showing 147 of 300 cases (49.0%)'.",
                "Point to the graph updating live with her specific cycle times.",
                "Click 'Clear filters' to reset back to all 300 cases."
            ],
            "say": (
                "\"In traditional tools, filtering requires running slow database scripts. Here, ProcessLens does it in real-time.\n\n"
                "Watch as I click 'Alice Johnson' — the graph instantly narrows to the 147 orders she touched, recalculating "
                "transition times and bottleneck stats completely in-memory.\n\n"
                "I click 'Clear filters', and we immediately return to the full 300-case company view.\""
            ),
            "tip": "Audience will love that there is no page reload and no lag."
        },
        {
            "num": "STEP 3",
            "title": "Rule Conformance & Rework Loops",
            "tab": "Tab: PROCESS CONFORMANCE (Click 2nd Tab)",
            "do": [
                "Click the 'PROCESS CONFORMANCE' tab.",
                "Point to the '82.0% Conformance Rate' card.",
                "Point to the '54 Deviating Cases' card.",
                "Show the bottom table detailing the 'Sent Back for Correction' rework loop."
            ],
            "say": (
                "\"Now let's check policy compliance. Our company rule is simple: Submitted ➔ Reviewed ➔ Approved ➔ Completed.\n\n"
                "ProcessLens runs token-based replay and reveals that 82% of orders followed the clean rule.\n\n"
                "However, 18% of orders broke policy by going through a rework loop: they were rejected and sent back for correction. "
                "ProcessLens proves that each rework loop added 5.5 hours of wasted delay to those orders.\""
            ),
            "tip": "Emphasize that this catches waste and policy violations that spreadsheets hide."
        },
        {
            "num": "STEP 4",
            "title": "What-If Simulation (ROI Calculator)",
            "tab": "Tab: WHAT-IF SIMULATION (Click 3rd Tab)",
            "do": [
                "Click the 'WHAT-IF SIMULATION' tab.",
                "Ensure Target Activity is set to 'Approved' and Duration Reduction is set to '30%'.",
                "Click the purple button: 'Run What-If Simulation'.",
                "Point to the before/after results: 37.95h ➔ 28.87h (-9.08h savings)."
            ],
            "say": (
                "\"Before investing money into hiring or software, executives ask: 'What will we actually gain if we fix this bottleneck?'\n\n"
                "In the What-If Simulator, we test reducing the Approved bottleneck by 30%.\n\n"
                "With one click, ProcessLens calculates that total company cycle time drops from 37.95 hours down to 28.87 hours — "
                "saving 9.08 hours per order, or a 23.9% total efficiency gain!\""
            ),
            "tip": "Managers love this because it gives them mathematical justification for team investments."
        },
        {
            "num": "STEP 5",
            "title": "Predictive Risk & The Case Intelligence Drawer",
            "tab": "Tab: PREDICTIVE RISK & OPEN CASES (Click 4th Tab)",
            "do": [
                "Click the 'PREDICTIVE RISK & OPEN CASES' tab.",
                "Show the Model Benchmark card (0.826 ROC-AUC accuracy).",
                "Scroll down to the 'In-Flight Open Cases' table.",
                "Find row 'OPEN-0004' (marked with a red Late Risk badge).",
                "Click the 'Explain Case' button on row 'OPEN-0004' to open the slide-out drawer.",
                "Show the Risk Gauge (64%), the SHAP Driver chart, and the Prescriptive Action card."
            ],
            "say": (
                "\"Historical analysis is great, but what about orders in progress today?\n\n"
                "Our machine learning model monitors active orders and flags delays in advance.\n\n"
                "Look at case OPEN-0004: it is flagged in red with a 64.3% risk of missing its deadline.\n\n"
                "When I click 'Explain Case', the AI drawer slides out and explains why: the order has been waiting in the queue for over 5 hours.\n\n"
                "Best of all, ProcessLens prescribes the solution: 'Expedite Approval Step'. It mathematically calculates that doing this "
                "will reduce risk from 64.3% down to 42.1% (-22% reduction)!\""
            ),
            "tip": "Close the drawer by clicking 'Done' at the bottom to transition smoothly."
        },
        {
            "num": "STEP 6",
            "title": "Enterprise Pipeline & Data Connectors",
            "tab": "Tab: DATA MANAGEMENT & AUDIT HISTORY",
            "do": [
                "Click the 'DATA MANAGEMENT' tab.",
                "Show the CSV Upload area, the PostgreSQL database connector tab, and the 'Reset to Synthetic Data' button.",
                "Point out the top-right 'Run Pipeline (Async)' button."
            ],
            "say": (
                "\"Finally, ProcessLens is enterprise-ready:\n"
                "• It connects directly to enterprise databases like PostgreSQL.\n"
                "• It sanitizes CSV uploads against malicious formula injection attacks.\n"
                "• It features asynchronous background pipeline execution with full audit history.\n\n"
                "That is ProcessLens: Discover bottlenecks, enforce compliance, simulate fixes, predict active delays, and prescribe solutions!\""
            ),
            "tip": "Finish with confidence and ask for their questions."
        }
    ]

    for step in demo_steps:
        p_step = doc.add_paragraph()
        r_step = p_step.add_run(f"▶ {step['num']}: {step['title']}")
        r_step.font.size = Pt(14)
        r_step.font.bold = True
        r_step.font.color.rgb = RGBColor(0x38, 0x43, 0xd0)

        p_tab = doc.add_paragraph()
        r_tab = p_tab.add_run(f"📍 Location: {step['tab']}")
        r_tab.font.bold = True
        r_tab.font.color.rgb = RGBColor(0x47, 0x55, 0x69)

        t_click = doc.add_table(rows=1, cols=1)
        t_click.alignment = WD_TABLE_ALIGNMENT.CENTER
        c_click = t_click.cell(0, 0)
        set_cell_background(c_click, "EFF6FF")
        set_cell_margins(c_click, top=100, bottom=100, left=150, right=150)
        p_c = c_click.paragraphs[0]
        r_c_hdr = p_c.add_run("🖱️ WHAT TO DO / WHAT TO CLICK:\n")
        r_c_hdr.bold = True
        r_c_hdr.font.color.rgb = RGBColor(0x1d, 0x4e, 0xd8)
        for d in step['do']:
            r_c_item = p_c.add_run(f"• {d}\n")
            r_c_item.font.size = Pt(10)

        doc.add_paragraph()

        t_say = doc.add_table(rows=1, cols=1)
        t_say.alignment = WD_TABLE_ALIGNMENT.CENTER
        c_say = t_say.cell(0, 0)
        set_cell_background(c_say, "F0FDF4")
        set_cell_margins(c_say, top=100, bottom=100, left=150, right=150)
        p_s = c_say.paragraphs[0]
        r_s_hdr = p_s.add_run("🗣️ WHAT TO SAY (Word-for-Word Talking Points):\n")
        r_s_hdr.bold = True
        r_s_hdr.font.color.rgb = RGBColor(0x15, 0x80, 0x3d)
        r_s_body = p_s.add_run(step['say'])
        r_s_body.font.size = Pt(10.5)
        r_s_body.font.italic = True

        p_tip = doc.add_paragraph()
        r_tip = p_tip.add_run(f"💡 Pro-Tip: {step['tip']}")
        r_tip.font.size = Pt(9.5)
        r_tip.font.color.rgb = RGBColor(0x64, 0x74, 0x8b)

        doc.add_paragraph()

    # -------------------------------------------------------------
    # Section 3: Tough Q&A Cheat Sheet
    # -------------------------------------------------------------
    h3 = doc.add_heading("3. Anticipated Questions & Winning Answers", level=1)
    h3.runs[0].font.color.rgb = RGBColor(0x0f, 0x17, 0x2a)

    qa_list = [
        (
            "Q: Can ProcessLens work with our company's real data?",
            "A: Yes! It supports any standard process log containing 4 columns: Case ID, Activity, Timestamp, and Resource. "
            "You can upload CSVs directly or connect to an existing database like PostgreSQL."
        ),
        (
            "Q: How is the delay prediction calculated?",
            "A: We train a tuned Random Forest and LightGBM model on past completed cases. It looks at how long steps took, "
            "who handled them, and how congested the overall system was to predict delay probabilities."
        ),
        (
            "Q: How does the AI explain its recommendations?",
            "A: It uses exact SHAP TreeExplainer math. Instead of guessing, it calculates the exact mathematical contribution "
            "of each factor (like queue waiting time) and tests the risk reduction of fixing that bottleneck."
        ),
        (
            "Q: Why does the approval step take 30 hours in the demo?",
            "A: Because our 300-order sample data reflects real-world operations where managers only review batches once or twice a week, "
            "creating an approval bottleneck that ProcessLens easily catches."
        )
    ]

    for q, a in qa_list:
        p_qa = doc.add_paragraph()
        rq = p_qa.add_run(f"{q}\n")
        rq.bold = True
        rq.font.size = Pt(11)
        rq.font.color.rgb = RGBColor(0x0f, 0x17, 0x2a)
        ra = p_qa.add_run(a)
        ra.font.size = Pt(10.5)
        ra.font.color.rgb = RGBColor(0x33, 0x41, 0x55)
        doc.add_paragraph()

    doc.save(filename)
    print(f"Successfully generated: {filename}")

def create_pdf(docx_path, pdf_path):
    import win32com.client
    word = win32com.client.Dispatch('Word.Application')
    word.Visible = False
    try:
        doc = word.Documents.Open(os.path.abspath(docx_path))
        doc.SaveAs(os.path.abspath(pdf_path), FileFormat=17) # 17 = wdFormatPDF
        doc.Close()
        print(f"Successfully generated native PDF: {pdf_path}")
    finally:
        word.Quit()

if __name__ == "__main__":
    docx_file = r"d:\Process Lens\ProcessLens_Live_Demo_Guide.docx"
    pdf_file = r"d:\Process Lens\ProcessLens_Live_Demo_Guide.pdf"
    create_docx(docx_file)
    create_pdf(docx_file, pdf_file)
