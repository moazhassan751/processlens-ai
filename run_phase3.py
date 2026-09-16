"""
Phase 3 -- Agentic explanation and recommendation layer.

Uses CrewAI with three sequential agents (Investigator -> Recommendation ->
Verifier) connected to the MCP tool server for data access.

Includes one-retry logic: if the Verifier rejects the recommendation, the
Recommendation agent gets one chance to fix it with the feedback.

Usage:  python run_phase3.py
Requires: GEMINI_API_KEY environment variable set.
"""

import json
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Load .env file from project directory
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

# ---- Environment setup -----------------------------------------------

def ensure_graphviz_on_path():
    graphviz_bin = r"C:\Program Files\Graphviz\bin"
    if os.path.isdir(graphviz_bin) and graphviz_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = graphviz_bin + os.pathsep + os.environ.get("PATH", "")

ensure_graphviz_on_path()

TOOLS_SERVER = os.path.join(SCRIPT_DIR, "tools_server.py")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "explanation_output.json")
PYTHON_EXE = os.path.join(SCRIPT_DIR, "venv", "Scripts", "python.exe")

# If running inside the venv, use sys.executable
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable

# Check for API keys
groq_api_key = os.environ.get("GROQ_API_KEY")
gemini_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

if not groq_api_key and not gemini_api_key:
    print("[ERROR] Neither GROQ_API_KEY nor GEMINI_API_KEY is set.")
    print("Please paste your key into .env")
    sys.exit(1)

# Ensure environment variables are populated for Google GenAI SDK if present
if gemini_api_key:
    os.environ["GEMINI_API_KEY"] = gemini_api_key
    os.environ["GOOGLE_API_KEY"] = gemini_api_key

# Disable CrewAI interactive tracing prompts & telemetry to prevent stdin deadlocks
os.environ["CREWAI_TRACING_ENABLED"] = "false"
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"
os.environ["OTEL_SDK_DISABLED"] = "true"

# ---- CrewAI setup ----------------------------------------------------

from crewai import Agent, Task, Crew, Process, LLM
from crewai_tools import MCPServerAdapter
from mcp import StdioServerParameters

import re
import time

try:
    from crewai.llms.providers.gemini.completion import GeminiCompletion
    orig_handle_completion = GeminiCompletion._handle_completion

    def resilient_handle_completion(self, *args, **kwargs):
        max_retries = 6
        for attempt in range(max_retries):
            try:
                return orig_handle_completion(self, *args, **kwargs)
            except Exception as e:
                err_str = str(e)
                if any(k in err_str for k in ["503", "429", "UNAVAILABLE", "high demand", "RESOURCE_EXHAUSTED"]) and attempt < max_retries - 1:
                    match = re.search(r"retry in (\d+)", err_str, re.IGNORECASE) or re.search(r"retryDelay':\s*'(\d+)", err_str)
                    wait_sec = int(match.group(1)) + 2 if match else (attempt + 1) * 4
                    print(f"\n  [Notice] Gemini API rate limit / busy ({err_str[:60]}...). Retrying in {wait_sec}s...", flush=True)
                    time.sleep(wait_sec)
                else:
                    raise
    GeminiCompletion._handle_completion = resilient_handle_completion
except Exception:
    pass

# Multi-Tier LLM Architecture:
# PRIMARY: Groq GPT-OSS 20B (Investigator & Recommendation)
# VERIFICATION UPGRADE: Groq GPT-OSS 120B (Accuracy Verifier)
# FALLBACK: Google Gemini
groq_base_url = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
primary_model_env = os.environ.get("PRIMARY_MODEL", "openai/gpt-oss-20b")
verifier_model_env = os.environ.get("VERIFIER_MODEL", "openai/gpt-oss-120b")
gemini_model_env = os.environ.get("GEMINI_MODEL", "gemini/gemini-3.5-flash")

if groq_api_key:
    # Use OpenAI-compatible endpoint with provider prefix
    p_name = f"openai/{primary_model_env}" if not primary_model_env.startswith("openai/openai/") else primary_model_env
    v_name = f"openai/{verifier_model_env}" if not verifier_model_env.startswith("openai/openai/") else verifier_model_env

    primary_llm = LLM(
        model=p_name,
        base_url=groq_base_url,
        api_key=groq_api_key,
    )
    verifier_llm = LLM(
        model=v_name,
        base_url=groq_base_url,
        api_key=groq_api_key,
    )
else:
    primary_llm = LLM(
        model=gemini_model_env,
        api_key=gemini_api_key,
    )
    verifier_llm = primary_llm

# MCP server parameters
server_params = StdioServerParameters(
    command=PYTHON_EXE,
    args=[TOOLS_SERVER],
    env={**os.environ},
)


def build_investigator(tools):
    """Build the Investigator agent."""
    return Agent(
        role="Process Mining Investigator",
        goal=(
            "Call ALL FOUR tools (get_step_stats, compare_by_resource, "
            "get_rework_cases, get_prediction_summary) and compile their "
            "results into a structured findings summary."
        ),
        backstory=(
            "You are a process mining analyst. Your job is to gather ALL "
            "facts from the available tools. You MUST call every single "
            "tool at least once. For compare_by_resource, use the activity "
            "with the highest avg_wait_hours from get_step_stats results. "
            "Do not skip any tool. Do not make up data."
        ),
        tools=tools,
        llm=primary_llm,
        verbose=True,
    )


def build_investigator_task(agent):
    """Build the investigation task."""
    return Task(
        description=(
            "You MUST call all four tools in this exact order:\n"
            "1. Call get_step_stats() to get the bottleneck table\n"
            "2. Call compare_by_resource(activity_name=X) where X is the "
            "   activity with the highest avg_wait_hours from step 1\n"
            "3. Call get_rework_cases() to get rework statistics\n"
            "4. Call get_prediction_summary() to get prediction counts\n\n"
            "Then compile ALL raw results into a structured findings summary "
            "with these sections:\n"
            "- BOTTLENECK: activity name, avg_wait_hours, delay_contribution\n"
            "- RESOURCE COMPARISON: for the bottleneck activity, each "
            "  resource's avg_wait_hours and case_count\n"
            "- REWORK: rework_rate_pct, most_common_rework_activity, "
            "  extra_hours_per_reworked_case, total_extra_hours_from_rework\n"
            "- PREDICTIONS: total_open_cases, late_risk_count, on_track_count, "
            "  insufficient_data_count, avg_late_risk_probability\n\n"
            "Include ALL numbers exactly as returned by the tools."
        ),
        expected_output=(
            "A structured findings summary with four labeled sections "
            "(BOTTLENECK, RESOURCE COMPARISON, REWORK, PREDICTIONS) "
            "containing exact numbers from each tool call."
        ),
        agent=agent,
    )


def build_recommendation_agent():
    """Build the Recommendation agent (no tools needed)."""
    return Agent(
        role="Process Improvement Advisor",
        goal=(
            "Write a concise plain-language explanation (2-4 sentences) of "
            "the key process issues, plus exactly one specific, measurable "
            "recommendation that references at least one real number from "
            "the findings."
        ),
        backstory=(
            "You are a business process consultant. You translate data into "
            "actionable advice. Every recommendation you make MUST reference "
            "a specific number from the investigator's findings. Be precise "
            "and concrete, not vague."
        ),
        llm=primary_llm,
        verbose=True,
    )


def build_recommendation_task(agent, context_tasks, extra_context=""):
    """Build the recommendation task."""
    desc = (
        "Based on the Investigator's structured findings, write:\n"
        "1. A plain-language explanation (2-4 sentences) of the key issues\n"
        "2. Exactly ONE specific, measurable recommendation that references "
        "   at least one real number from the findings\n\n"
        "Rules:\n"
        "- Every single number, metric, or quantity you cite MUST come directly from the findings\n"
        "- NEVER invent, assume, or introduce arbitrary numbers, quotas, timelines, or quantities (e.g. do NOT say '10 cases', '5 days', or '20%') that do not appear in the findings\n"
        "- NEVER predict or invent hypothetical future outcome numbers or calculated reduction claims (e.g. do NOT say 'will drop to X' or 'will save Y hours') unless that exact number appears explicitly in the findings\n"
        "- All claims must cite ONLY real, historical metrics from the findings\n"
        "- Do NOT round numbers differently from how they appear in the findings\n"
        "- The recommendation must be actionable and specific\n"
    )
    if extra_context:
        desc += f"\n\nIMPORTANT FEEDBACK FROM VERIFIER (fix these issues):\n{extra_context}\n"

    return Task(
        description=desc,
        expected_output=(
            "A short explanation (2-4 sentences) followed by one specific "
            "recommendation with at least one exact number from the findings."
        ),
        agent=agent,
        context=context_tasks,
    )


def build_verifier_agent():
    """Build the Verifier agent (no tools needed)."""
    return Agent(
        role="Accuracy Verifier",
        goal=(
            "Check every numeric claim in the recommendation against the "
            "Investigator's original findings. Reject if ANY number doesn't "
            "match or is unsupported."
        ),
        backstory=(
            "You are a strict fact-checker. You compare every number in the "
            "recommendation against the raw findings. If even one number is "
            "wrong, rounded differently, or unsupported by the findings, "
            "you MUST reject the recommendation and state exactly which "
            "claim failed and why. If all numbers match, explicitly approve."
        ),
        llm=verifier_llm,
        verbose=True,
    )


def build_verifier_task(agent, context_tasks):
    """Build the verification task."""
    return Task(
        description=(
            "Compare every numeric claim in the Recommendation against the "
            "Investigator's original findings.\n\n"
            "For each number cited in the recommendation:\n"
            "1. Find the corresponding number in the Investigator's findings\n"
            "2. Check if they match exactly\n\n"
            "Output one of:\n"
            "- APPROVED: All numeric claims verified. [list each verified claim]\n"
            "- REJECTED: [which claim failed] [expected value from findings] "
            "  [actual value stated in recommendation]\n\n"
            "Do NOT approve if any number is wrong, rounded differently, or "
            "not found in the original findings."
        ),
        expected_output=(
            "Either 'APPROVED: ...' with list of verified claims, or "
            "'REJECTED: ...' with specific details of which claim failed."
        ),
        agent=agent,
        context=context_tasks,
    )


def check_approval(verification_text):
    """Check if verification explicitly approved (and not rejected)."""
    text = str(verification_text).strip().upper()
    if text.startswith("REJECTED") or "\nREJECTED" in text:
        return False
    return "APPROVED" in text


def fetch_mcp_data(tools):
    """Directly execute all 4 MCP tools via the MCP adapter for fast, quota-saving execution."""
    t_map = {t.name: t for t in tools}
    print("  [MCP Adapter] Querying get_step_stats()...", flush=True)
    raw_steps = t_map["get_step_stats"].run()
    step_stats = json.loads(raw_steps) if isinstance(raw_steps, str) else raw_steps

    bottleneck = sorted(step_stats, key=lambda x: x["avg_wait_hours"], reverse=True)[0]["activity"]
    print(f"  [MCP Adapter] Querying compare_by_resource(activity_name='{bottleneck}')...", flush=True)
    raw_res = t_map["compare_by_resource"].run(activity_name=bottleneck)
    res_comp = json.loads(raw_res) if isinstance(raw_res, str) else raw_res

    print("  [MCP Adapter] Querying get_rework_cases()...", flush=True)
    raw_rework = t_map["get_rework_cases"].run()
    rework = json.loads(raw_rework) if isinstance(raw_rework, str) else raw_rework

    print("  [MCP Adapter] Querying get_prediction_summary()...", flush=True)
    raw_preds = t_map["get_prediction_summary"].run()
    preds = json.loads(raw_preds) if isinstance(raw_preds, str) else raw_preds

    return {
        "step_stats": step_stats,
        "bottleneck_activity": bottleneck,
        "resource_comparison": res_comp,
        "rework": rework,
        "predictions": preds,
    }


def run_crew_once(tools, inject_error=False, fast_mode=False):
    """Run the three-agent crew once. Returns (outputs_dict, is_approved)."""
    investigator = build_investigator(tools if not fast_mode else [])
    recommender = build_recommendation_agent()
    verifier = build_verifier_agent()

    if fast_mode:
        mcp_data = fetch_mcp_data(tools)
        investigate_task = Task(
            description=(
                "Here is the verified data gathered directly from all four MCP tools:\n\n"
                f"- STEP STATS (from get_step_stats):\n{json.dumps(mcp_data['step_stats'], indent=2)}\n\n"
                f"- RESOURCE COMPARISON (from compare_by_resource for '{mcp_data['bottleneck_activity']}'):\n{json.dumps(mcp_data['resource_comparison'], indent=2)}\n\n"
                f"- REWORK ANALYSIS (from get_rework_cases):\n{json.dumps(mcp_data['rework'], indent=2)}\n\n"
                f"- PREDICTION SUMMARY (from get_prediction_summary):\n{json.dumps(mcp_data['predictions'], indent=2)}\n\n"
                "Compile ALL raw results into a structured findings summary with these sections:\n"
                "- BOTTLENECK: activity name, avg_wait_hours, delay_contribution\n"
                "- RESOURCE COMPARISON: for the bottleneck activity, each resource's avg_wait_hours and case_count\n"
                "- REWORK: rework_rate_pct, most_common_rework_activity, extra_hours_per_reworked_case, total_extra_hours_from_rework\n"
                "- PREDICTIONS: total_open_cases, late_risk_count, on_track_count, insufficient_data_count, avg_late_risk_probability\n\n"
                "Include ALL numbers exactly as returned by the tools."
            ),
            expected_output=(
                "A structured findings summary with four labeled sections "
                "(BOTTLENECK, RESOURCE COMPARISON, REWORK, PREDICTIONS) "
                "containing exact numbers from each tool."
            ),
            agent=investigator,
        )
    else:
        investigate_task = build_investigator_task(investigator)

    if inject_error:
        # Deliberately inject an incorrect claim to test the Verifier's rejection capability
        fake_rec = (
            "The primary bottleneck in the process is the Approved stage, which generates an average wait time of 99.9 hours. "
            "We recommend cutting approval turnaround times to under 24 hours to eliminate this 99.9-hour delay."
        )
        investigate_crew = Crew(agents=[investigator], tasks=[investigate_task], verbose=True)
        investigate_crew.kickoff()
        findings = str(investigate_task.output)

        test_verify_task = Task(
            description=(
                f"Here are the Investigator's original structured findings:\n\n{findings}\n\n"
                f"Here is the Recommendation to verify:\n\n{fake_rec}\n\n"
                "Compare every numeric claim in the Recommendation against the Investigator's original findings.\n\n"
                "For each number cited in the recommendation:\n"
                "1. Find the corresponding number in the Investigator's findings\n"
                "2. Check if they match exactly\n\n"
                "Output one of:\n"
                "- APPROVED: All numeric claims verified. [list each verified claim]\n"
                "- REJECTED: [which claim failed] [expected value from findings] [actual value stated in recommendation]\n\n"
                "Do NOT approve if any number is wrong, rounded differently, or not found in the original findings."
            ),
            expected_output="Either 'APPROVED: ...' or 'REJECTED: ...' with specific details.",
            agent=verifier,
        )
        verify_crew = Crew(agents=[verifier], tasks=[test_verify_task], verbose=True)
        verify_crew.kickoff()

        outputs = {
            "investigator_findings": findings,
            "draft_recommendation": fake_rec,
            "verification_result": str(test_verify_task.output),
        }
        is_approved = check_approval(test_verify_task.output)
        return outputs, is_approved

    recommend_task = build_recommendation_task(recommender, [investigate_task])
    verify_task = build_verifier_task(verifier, [investigate_task, recommend_task])

    # Assemble crew
    crew = Crew(
        agents=[investigator, recommender, verifier],
        tasks=[investigate_task, recommend_task, verify_task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()

    # Extract outputs
    outputs = {
        "investigator_findings": str(investigate_task.output),
        "draft_recommendation": str(recommend_task.output),
        "verification_result": str(verify_task.output),
    }

    is_approved = check_approval(verify_task.output)
    return outputs, is_approved


def run_retry(tools, rejection_reason, first_run_outputs):
    """Retry: send rejection feedback to Recommendation agent."""
    recommender = build_recommendation_agent()
    verifier = build_verifier_agent()

    findings = first_run_outputs.get("investigator_findings", "")

    recommend_task = Task(
        description=(
            f"Here are the Investigator's original structured findings:\n\n{findings}\n\n"
            f"IMPORTANT FEEDBACK FROM VERIFIER (The previous recommendation was REJECTED):\n"
            f"{rejection_reason}\n\n"
            f"Please address the feedback and write:\n"
            f"1. A plain-language explanation (2-4 sentences) of the key issues\n"
            f"2. Exactly ONE specific, measurable recommendation that references "
            f"at least one real number from the findings\n\n"
            f"Rules:\n"
            f"- Every single number, metric, or quantity you cite MUST come directly from the findings above\n"
            f"- NEVER invent, assume, or introduce arbitrary numbers, quotas, timelines, or quantities (e.g. do NOT say '10 cases', '5 days', or '20%') that do not appear in the findings\n"
            f"- NEVER predict or invent hypothetical future outcome numbers or calculated reduction claims (e.g. do NOT say 'will drop to X' or 'will save Y hours') unless that exact number appears explicitly in the findings\n"
            f"- All claims must cite ONLY real, historical metrics from the findings\n"
            f"- Do NOT round numbers differently from how they appear in the findings\n"
            f"- The recommendation must be actionable and specific\n"
        ),
        expected_output=(
            "A short explanation (2-4 sentences) followed by one specific "
            "recommendation with at least one exact number from the findings."
        ),
        agent=recommender,
    )

    verify_task = Task(
        description=(
            f"Here are the Investigator's original structured findings:\n\n{findings}\n\n"
            f"Compare every numeric claim in the revised Recommendation against these findings.\n\n"
            f"For each number cited in the recommendation:\n"
            f"1. Find the corresponding number in the Investigator's findings\n"
            f"2. Check if they match exactly\n\n"
            f"Output one of:\n"
            f"- APPROVED: All numeric claims verified. [list each verified claim]\n"
            f"- REJECTED: [which claim failed] [expected value from findings] "
            f"[actual value stated in recommendation]\n\n"
            f"Do NOT approve if any number is wrong, rounded differently, or "
            f"not found in the original findings."
        ),
        expected_output=(
            "Either 'APPROVED: ...' with list of verified claims, or "
            "'REJECTED: ...' with specific details of which claim failed."
        ),
        agent=verifier,
        context=[recommend_task],
    )

    crew = Crew(
        agents=[recommender, verifier],
        tasks=[recommend_task, verify_task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()

    outputs = {
        "investigator_findings": findings,
        "retry_recommendation": str(recommend_task.output),
        "retry_verification": str(verify_task.output),
    }

    is_approved = check_approval(verify_task.output)
    return outputs, is_approved


def main():
    print(flush=True)
    print("+" + "=" * 60 + "+", flush=True)
    print("|   ProcessLens Phase 3 -- Agentic Explanation Layer       |", flush=True)
    print("+" + "=" * 60 + "+", flush=True)

    # Check prerequisites
    for f in ["event_log.csv", "predictions.json"]:
        path = os.path.join(SCRIPT_DIR, f)
        if not os.path.exists(path):
            print(f"\n[ERROR] {f} not found. Run Phase 1 and Phase 2 first.", flush=True)
            sys.exit(1)

    print("\n>> Starting MCP tool server and CrewAI agents...", flush=True)
    print("-" * 60, flush=True)

    with MCPServerAdapter(server_params) as tools:
        print(f"\n  MCP tools loaded: {len(tools)} tools available", flush=True)
        for t in tools:
            print(f"    - {t.name}", flush=True)
        print(flush=True)

        # ---- First run ----
        test_rejection = "--test-rejection" in sys.argv
        fast_mode = "--fast" in sys.argv
        if test_rejection:
            print("  [TEST MODE] Deliberate rejection test enabled (injecting incorrect number in Attempt 1)...", flush=True)
        if fast_mode:
            print("  [FAST MODE] Quota-saving 3-call execution enabled (direct MCP querying)...", flush=True)

        print("=" * 60, flush=True)
        print("  ATTEMPT 1: Running Investigator -> Recommendation -> Verifier",
              flush=True)
        print("=" * 60, flush=True)

        outputs_1, approved_1 = run_crew_once(tools, inject_error=test_rejection, fast_mode=fast_mode)

        print("\n" + "=" * 60, flush=True)
        print("  STAGE OUTPUTS (Attempt 1)", flush=True)
        print("=" * 60, flush=True)

        print("\n--- Investigator Findings ---", flush=True)
        print(outputs_1["investigator_findings"], flush=True)

        print("\n--- Draft Recommendation ---", flush=True)
        print(outputs_1["draft_recommendation"], flush=True)

        print("\n--- Verification Result ---", flush=True)
        print(outputs_1["verification_result"], flush=True)

        final_outputs = outputs_1

        if not approved_1:
            print("\n[!] Verifier REJECTED the recommendation.", flush=True)
            print("    Retrying with feedback...", flush=True)
            print("=" * 60, flush=True)
            print("  ATTEMPT 2: Retry with Verifier feedback", flush=True)
            print("=" * 60, flush=True)

            rejection_reason = outputs_1["verification_result"]
            outputs_2, approved_2 = run_retry(
                tools, rejection_reason, outputs_1
            )

            print("\n" + "=" * 60, flush=True)
            print("  STAGE OUTPUTS (Attempt 2 - Retry)", flush=True)
            print("=" * 60, flush=True)

            print("\n--- Investigator Findings ---", flush=True)
            print(outputs_2["investigator_findings"], flush=True)

            print("\n--- Revised Recommendation ---", flush=True)
            print(outputs_2["retry_recommendation"], flush=True)

            print("\n--- Verification Result ---", flush=True)
            print(outputs_2["retry_verification"], flush=True)

            final_outputs.update(outputs_2)

            if not approved_2:
                print(
                    "\n[!] Verification failed TWICE. Recommendation is NOT "
                    "accepted. Manual review required.",
                    flush=True,
                )
            else:
                print("\n[OK] Retry APPROVED by Verifier.", flush=True)
        else:
            print("\n[OK] Recommendation APPROVED by Verifier.", flush=True)

    # ---- Save output ----
    final_outputs["timestamp"] = datetime.now().isoformat()
    final_outputs["approved"] = approved_1 or (
        "retry_verification" in final_outputs
        and check_approval(final_outputs.get("retry_verification", ""))
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_outputs, f, indent=2)

    print(flush=True)
    print("+" + "=" * 60 + "+", flush=True)
    print("|   ProcessLens Phase 3 -- COMPLETE                       |", flush=True)
    print("+" + "=" * 60 + "+", flush=True)
    print(f"  [OK] Saved to: explanation_output.json", flush=True)
    print(flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
