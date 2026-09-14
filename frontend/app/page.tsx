"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Header } from "./components/Header";
import { SnapshotSelector } from "./components/SnapshotSelector";
import { LiveLogPanel } from "./components/LiveLogPanel";
import { ProcessGraph } from "./components/ProcessGraph";
import { CaseExplainDrawer, PrescriptiveAction } from "./components/CaseExplainDrawer";
import { ConformancePanel } from "./components/ConformancePanel";
import { SimulationPanel } from "./components/SimulationPanel";
import { ConnectorPanel } from "./components/ConnectorPanel";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  Database,
  FileSpreadsheet,
  GitCommit,
  History,
  Info,
  Layers,
  Lightbulb,
  Play,
  RotateCcw,
  ShieldAlert,
  Sliders,
  Sparkles,
  TrendingUp,
  Upload,
  Zap,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Config & Types
// ---------------------------------------------------------------------------
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

function getAuthHeaders(additionalHeaders: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...additionalHeaders };
  if (API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }
  return headers;
}

type PhaseStatus = { phase1: boolean; phase2: boolean; phase3: boolean };
type StaleFlags = { discovery: boolean; prediction: boolean; recommendation: boolean };

type DataQuality = {
  available: boolean;
  case_count: number;
  event_count: number;
  date_range: { start: string; end: string; formatted: string; duration_days: number } | null;
  activity_count: number;
  activities: string[];
  rework_case_count: number;
  rework_case_pct: number;
  avg_events_per_case: number;
  missing_values_count: number;
  is_valid: boolean;
  error?: string;
};

type StatusResponse = {
  files: Record<string, boolean>;
  phases: PhaseStatus;
  data_source?: "synthetic" | "uploaded";
  upload_meta?: { filename: string | null; row_count: number | null } | null;
  stale?: StaleFlags;
  data_quality?: DataQuality | null;
};

type Bottleneck = {
  activity: string;
  avg_wait_hours: number;
  times_repeated: number;
  delay_contribution: "High" | "Medium" | "Low";
};

type DiscoveryData = {
  available: boolean;
  process_map_exists: boolean;
  bottlenecks: Bottleneck[];
  fallback?: boolean;
  warning?: string;
};

type PathsData = {
  available: boolean;
  paths: string[];
  fallback?: boolean;
  warning?: string;
};

type MetricVariation = {
  mean: number;
  std: number;
  min: number;
  max: number;
  range_str: string;
};

type FoldMetric = {
  fold: number;
  val_samples?: number;
  late_cases?: number;
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  roc_auc: number;
};

type ModelMetrics = {
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  roc_auc: number;
  risk_threshold?: number;
  threshold?: number;
  threshold_method?: string;
  cv_strategy?: string;
  n_splits?: number;
  strategy_note?: string;
  variation?: {
    roc_auc?: MetricVariation;
    f1?: MetricVariation;
    accuracy?: MetricVariation;
    precision?: MetricVariation;
    recall?: MetricVariation;
  };
  fold_metrics?: FoldMetric[];
  error?: string;
};

type FeatureImportance = { feature: string; importance: number };

type FeatureContribution = {
  feature: string;
  contribution: number;
};

type OpenCase = {
  case_id: string;
  current_step: string;
  late_risk_probability: number | null;
  predicted_label: string;
  risk_label?: string;
  risk_threshold?: number;
  anomaly_flag: boolean;
  elapsed_hours_so_far: number;
  risk_drivers?: string[];
  feature_contributions?: FeatureContribution[];
  base_value?: number | null;
  explanation?: string;
  prescriptive_action?: PrescriptiveAction;
};

type PredictionsData = {
  available: boolean;
  risk_threshold?: number;
  threshold?: number;
  threshold_method?: string;
  summary: {
    late_risk_count: number;
    on_track_count: number;
    insufficient_data_count: number;
    anomaly_count: number;
    total_cases: number;
  };
  model_metrics: ModelMetrics;
  enterprise_benchmark?: any;
  feature_importances: FeatureImportance[];
  open_cases: OpenCase[];
  fallback?: boolean;
  warning?: string;
};

type ExplanationData = {
  available: boolean;
  investigator_findings?: string;
  draft_recommendation?: string;
  verification_result?: string;
  timestamp?: string;
  approved?: boolean;
  fallback?: boolean;
  warning?: string;
};

type PastRun = {
  id: string;
  created_at: string;
  data_source: "synthetic" | "uploaded";
  source_filename: string | null;
  row_count: number | null;
  status: "running" | "completed" | "failed";
  failed_at_phase: string | null;
};

type RunDetail = {
  run: PastRun;
  discovery: DiscoveryData;
  paths: PathsData;
  predictions: PredictionsData;
  explanation: ExplanationData;
};

type Tab = "discovery" | "conformance" | "simulation" | "prediction" | "recommendation" | "history" | "upload";

export default function Home() {
  // Navigation & Workspace State
  const [activeTab, setActiveTab] = useState<Tab>("discovery");
  const [simulationPreselectedActivity, setSimulationPreselectedActivity] = useState<string | null>(null);
  const [projects, setProjects] = useState<string[]>(["default"]);
  const [activeProject, setActiveProject] = useState<string>("default");
  const [status, setStatus] = useState<StatusResponse | null>(null);

  // Dynamic Snapshot Milestone State (Phase 7 Feature 3)
  const [snapshotActivity, setSnapshotActivity] = useState<string>("Reviewed");

  // Asynchronous Execution & Live Logs (Phase 7 Feature 1)
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [showLogPanel, setShowLogPanel] = useState<boolean>(false);
  const [isRunning, setIsRunning] = useState<boolean>(false);

  // Case Explanation Drawer State (Phase 7 Feature 5)
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [showExplainDrawer, setShowExplainDrawer] = useState<boolean>(false);

  // Analytical Data States
  const [liveDiscovery, setLiveDiscovery] = useState<DiscoveryData | null>(null);
  const [livePaths, setLivePaths] = useState<PathsData | null>(null);
  const [livePredictions, setLivePredictions] = useState<PredictionsData | null>(null);
  const [liveExplanation, setLiveExplanation] = useState<ExplanationData | null>(null);

  // Polish: Loading & Global Error States
  const [loadingOutputs, setLoadingOutputs] = useState<boolean>(true);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [showFoldBreakdown, setShowFoldBreakdown] = useState<boolean>(false);

  // History & Upload states
  const [pastRuns, setPastRuns] = useState<PastRun[]>([]);
  const [selectedPastRunId, setSelectedPastRunId] = useState<string | null>(null);
  const [historicalData, setHistoricalData] = useState<RunDetail | null>(null);
  const [loadingRun, setLoadingRun] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  // --------------------------------------------------------------------------
  // Dynamic Page Title (Phase B)
  // --------------------------------------------------------------------------
  const activeScenarioLabel = status?.data_source === "synthetic"
    ? "Synthetic Log"
    : (status?.upload_meta?.filename || "Uploaded Log");

  useEffect(() => {
    const titleLabel = activeProject !== "default"
      ? `${activeScenarioLabel} (${activeProject})`
      : activeScenarioLabel;
    document.title = `ProcessLens — ${titleLabel}`;
  }, [activeScenarioLabel, activeProject]);

  // --------------------------------------------------------------------------
  // Data Fetching
  // --------------------------------------------------------------------------
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/status`);
      if (res.ok) {
        const data: StatusResponse = await res.json();
        setStatus(data);
        return data;
      }
    } catch (err: any) {
      console.warn("Could not fetch status:", err);
      setGlobalError("Unable to connect to ProcessLens backend. Please ensure the server is running on port 8000.");
    }
    return null;
  }, []);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects`);
      if (res.ok) {
        const data = await res.json();
        if (data.projects && Array.isArray(data.projects)) {
          const ids = data.projects.map((p: any) => p.project_id || p);
          if (ids.length > 0) {
            setProjects(ids);
          }
        }
      }
    } catch (err) {
      console.warn("Could not load projects:", err);
    }
  }, []);

  const fetchPastRuns = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/runs?limit=25`);
      if (res.ok) {
        const data = await res.json();
        setPastRuns(data.runs || []);
      }
    } catch {
      // Supabase not ready or offline
    }
  }, []);

  const fetchAllOutputs = useCallback(async (st: StatusResponse) => {
    const projQuery = `project_id=${encodeURIComponent(activeProject)}`;
    if (st.phases.phase1) {
      try {
        const [dRes, pRes] = await Promise.all([
          fetch(`${API_BASE}/api/discovery?${projQuery}`),
          fetch(`${API_BASE}/api/discovery/paths?${projQuery}`),
        ]);
        if (dRes.ok) setLiveDiscovery(await dRes.json());
        if (pRes.ok) setLivePaths(await pRes.json());
      } catch (err) {
        console.warn("Failed fetching discovery outputs:", err);
      }
    } else {
      setLiveDiscovery(null);
      setLivePaths(null);
    }

    if (st.phases.phase2) {
      try {
        const predRes = await fetch(`${API_BASE}/api/predictions?${projQuery}`);
        if (predRes.ok) setLivePredictions(await predRes.json());
      } catch (err) {
        console.warn("Failed fetching prediction outputs:", err);
      }
    } else {
      setLivePredictions(null);
    }

    if (st.phases.phase3) {
      try {
        const expRes = await fetch(`${API_BASE}/api/explanation?${projQuery}`);
        if (expRes.ok) setLiveExplanation(await expRes.json());
      } catch (err) {
        console.warn("Failed fetching explanation outputs:", err);
      }
    } else {
      setLiveExplanation(null);
    }
  }, [activeProject]);

  const reloadAll = useCallback(async () => {
    setLoadingOutputs(true);
    setGlobalError(null);
    try {
      const st = await fetchStatus();
      if (st) {
        await fetchAllOutputs(st);
      }
      await Promise.allSettled([fetchPastRuns(), fetchProjects()]);
    } catch (err: any) {
      setGlobalError(err.message || "Failed to load process data.");
    } finally {
      setLoadingOutputs(false);
    }
  }, [fetchStatus, fetchAllOutputs, fetchPastRuns, fetchProjects]);

  useEffect(() => {
    reloadAll();
  }, [reloadAll]);

  // --------------------------------------------------------------------------
  // Workspace / Project Handlers (Phase 7 Feature 4)
  // --------------------------------------------------------------------------
  const handleCreateProject = async (newProjectId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/projects`, {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ project_id: newProjectId }),
      });
      if (res.ok) {
        if (!projects.includes(newProjectId)) {
          setProjects([...projects, newProjectId]);
        }
        setActiveProject(newProjectId);
      }
    } catch (err) {
      console.error("Failed to create project:", err);
    }
  };

  // --------------------------------------------------------------------------
  // Async Pipeline Trigger Handlers (Phase 7 Feature 1)
  // --------------------------------------------------------------------------
  const triggerRunAll = async () => {
    setIsRunning(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/run/all?snapshot_activity=${encodeURIComponent(
          snapshotActivity
        )}&project_id=${encodeURIComponent(activeProject)}`,
        {
          method: "POST",
          headers: getAuthHeaders(),
        }
      );
      if (res.ok) {
        const data = await res.json();
        if (data.run_id) {
          setActiveRunId(data.run_id);
          setShowLogPanel(true);
        }
      } else {
        const errData = await res.json().catch(() => ({}));
        const errMsg = errData.detail || errData.error || `Failed to start run (HTTP ${res.status})`;
        setGlobalError(errMsg);
        setIsRunning(false);
      }
    } catch (err) {
      console.error("Run all failed:", err);
      setGlobalError("Failed to connect to backend to start run.");
      setIsRunning(false);
    }
  };

  const triggerSinglePhase = async (phaseName: "phase1" | "phase2" | "phase3") => {
    setIsRunning(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/run/${phaseName}?project_id=${encodeURIComponent(activeProject)}`,
        {
          method: "POST",
          headers: getAuthHeaders(),
        }
      );
      if (res.ok) {
        const data = await res.json();
        if (data.run_id) {
          setActiveRunId(data.run_id);
          setShowLogPanel(true);
        }
      } else {
        const errData = await res.json().catch(() => ({}));
        const errMsg = errData.detail || errData.error || `Failed to start ${phaseName} (HTTP ${res.status})`;
        setGlobalError(errMsg);
        setIsRunning(false);
      }
    } catch (err) {
      console.error(`Run ${phaseName} failed:`, err);
      setGlobalError(`Failed to connect to backend to start ${phaseName}.`);
      setIsRunning(false);
    }
  };

  const handleRunComplete = (completionStatus: string) => {
    setIsRunning(false);
    reloadAll();
  };

  // --------------------------------------------------------------------------
  // Case Explanation Trigger (Phase 7 Feature 5)
  // --------------------------------------------------------------------------
  const handleExplainCase = (caseId: string) => {
    setSelectedCaseId(caseId);
    setShowExplainDrawer(true);
  };

  // --------------------------------------------------------------------------
  // History Selection
  // --------------------------------------------------------------------------
  const selectPastRun = async (runId: string) => {
    setLoadingRun(true);
    try {
      const res = await fetch(`${API_BASE}/api/runs/${runId}`);
      if (res.ok) {
        const data: RunDetail = await res.json();
        setSelectedPastRunId(runId);
        setHistoricalData(data);
      }
    } catch (err) {
      console.error("Failed to load run:", err);
    } finally {
      setLoadingRun(false);
    }
  };

  // --------------------------------------------------------------------------
  // Upload & Reset
  // --------------------------------------------------------------------------
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadErrors([]);
    setUploadSuccess(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        headers: getAuthHeaders(),
        body: formData,
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setUploadSuccess(`Uploaded "${data.filename}" (${data.row_count} rows). Pipeline is ready to run.`);
        reloadAll();
      } else {
        const errors = data.errors || [data.detail || data.message || "Upload validation failed."];
        setUploadErrors(errors);
      }
    } catch (err: any) {
      setUploadErrors([err.message || "Upload request failed."]);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleResetToSynthetic = async () => {
    setResetting(true);
    try {
      const res = await fetch(`${API_BASE}/api/reset-to-synthetic`, {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        setUploadSuccess("Reset to synthetic event log dataset.");
        setUploadErrors([]);
        reloadAll();
      }
    } catch (err) {
      console.error("Reset failed:", err);
    } finally {
      setResetting(false);
    }
  };

  // Display data selection (live vs historical)
  const isViewingHistorical = Boolean(selectedPastRunId && historicalData);
  const discovery = isViewingHistorical ? historicalData!.discovery : liveDiscovery;
  const paths = isViewingHistorical ? historicalData!.paths : livePaths;
  const predictions = isViewingHistorical ? historicalData!.predictions : livePredictions;
  const explanation = isViewingHistorical ? historicalData!.explanation : liveExplanation;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-indigo-600 selection:text-white pb-20">
      {/* Top Header with Workspace Isolation & Pipeline Trigger */}
      <Header
        projects={projects}
        activeProject={activeProject}
        onSelectProject={setActiveProject}
        onCreateProject={handleCreateProject}
        dataSource={status?.data_source || "synthetic"}
        sourceFilename={status?.upload_meta?.filename}
        rowCount={status?.upload_meta?.row_count}
        isStale={Boolean(status?.stale?.discovery || status?.stale?.prediction || status?.stale?.recommendation)}
        onRefresh={reloadAll}
        onRunPipeline={triggerRunAll}
        isRunning={isRunning}
      />

      <main className="max-w-7xl mx-auto px-6 py-6 w-full flex-1 space-y-6">
        {/* Global Error Banner */}
        {globalError && (
          <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 text-xs flex items-center justify-between gap-4 shadow-lg animate-in fade-in duration-200">
            <div className="flex items-center gap-2.5">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
              <span className="font-medium text-rose-200">{globalError}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={reloadAll}
                className="px-2.5 py-1 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 font-semibold border border-rose-500/30 transition-colors"
              >
                Retry
              </button>
              <button
                type="button"
                onClick={() => setGlobalError(null)}
                className="p-1 text-slate-400 hover:text-white transition-colors"
                title="Dismiss"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {/* Dynamic Snapshot Selector (Feature 3) & Individual Phase Runner Controls */}
        <div className="space-y-3">
          <SnapshotSelector
            selectedActivity={snapshotActivity}
            onSelectActivity={setSnapshotActivity}
            apiBaseUrl={API_BASE}
            disabled={isRunning}
          />

          {/* Quick Sub-actions bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 px-1 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 font-medium">Individual Phase Execution:</span>
              <button
                onClick={() => triggerSinglePhase("phase1")}
                disabled={isRunning}
                className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-indigo-500/50 hover:bg-slate-850 text-slate-300 font-semibold transition-all disabled:opacity-50"
              >
                1. Discovery
              </button>
              <button
                onClick={() => triggerSinglePhase("phase2")}
                disabled={isRunning}
                className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-indigo-500/50 hover:bg-slate-850 text-slate-300 font-semibold transition-all disabled:opacity-50"
              >
                2. ML Predict
              </button>
              <button
                onClick={() => triggerSinglePhase("phase3")}
                disabled={isRunning}
                className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-indigo-500/50 hover:bg-slate-850 text-slate-300 font-semibold transition-all disabled:opacity-50"
              >
                3. AI Explain Agents
              </button>
            </div>

            {/* Live Logs Drawer Toggle Button */}
            {activeRunId && (
              <button
                onClick={() => setShowLogPanel(!showLogPanel)}
                className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 font-semibold bg-indigo-500/10 border border-indigo-500/20 px-3 py-1.5 rounded-lg transition-colors"
              >
                <Activity className="w-3.5 h-3.5" />
                <span>{showLogPanel ? "Hide Live Terminal" : "View Live Execution Terminal"}</span>
              </button>
            )}
          </div>
        </div>

        {/* Historical Run Banner if inspecting past run */}
        {isViewingHistorical && (
          <div className="p-4 rounded-xl bg-amber-950/30 border border-amber-500/40 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-amber-200 text-xs">
              <History className="w-5 h-5 text-amber-400 shrink-0" />
              <div>
                <span className="font-bold">Viewing Historical Run:</span>{" "}
                <span className="font-mono">{selectedPastRunId}</span> (
                {new Date(historicalData!.run.created_at).toLocaleString()})
              </div>
            </div>
            <button
              onClick={() => {
                setSelectedPastRunId(null);
                setHistoricalData(null);
              }}
              className="px-3 py-1 rounded-lg text-xs font-semibold bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 transition-colors"
            >
              Return to Current Live Output
            </button>
          </div>
        )}

        {/* Data Quality & Dataset Health Telemetry Banner (Phase C Feature 3) */}
        {status?.data_quality && status.data_quality.available && (
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-xl backdrop-blur-md flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                <Database className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    Dataset Quality & Telemetry
                  </span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                    {status.data_quality.is_valid ? "Schema Validated" : "Validation Warning"}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400">
                  Defensible metrics computed directly from currently loaded event log
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-6 text-xs">
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Case Count</span>
                <span className="font-mono font-bold text-white text-sm">
                  {status.data_quality.case_count.toLocaleString()} <span className="text-slate-500 font-sans text-xs">cases</span>
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Total Events</span>
                <span className="font-mono font-bold text-white text-sm">
                  {status.data_quality.event_count.toLocaleString()} <span className="text-slate-500 font-sans text-xs">events</span>
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Date Range</span>
                <span className="font-mono text-cyan-300 text-xs">
                  {status.data_quality.date_range?.formatted || "N/A"}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Activities</span>
                <span className="font-mono font-bold text-white text-sm">
                  {status.data_quality.activity_count} <span className="text-slate-500 font-sans text-xs">distinct</span>
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Rework Frequency</span>
                <span className={`font-mono font-bold text-sm ${status.data_quality.rework_case_pct > 15 ? "text-amber-400" : "text-emerald-400"}`}>
                  {status.data_quality.rework_case_pct}% <span className="text-slate-500 font-sans text-xs">({status.data_quality.rework_case_count} cases)</span>
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Main Tab Navigation */}
        <div className="border-b border-slate-800 flex items-center gap-1">
          <button
            onClick={() => setActiveTab("discovery")}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-all ${
              activeTab === "discovery"
                ? "border-indigo-500 text-indigo-400 bg-indigo-500/5"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <GitCommit className="w-4 h-4" />
            <span>Process Discovery</span>
          </button>

          <button
            onClick={() => setActiveTab("conformance")}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-all ${
              activeTab === "conformance"
                ? "border-indigo-500 text-indigo-400 bg-indigo-500/5"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <ShieldAlert className="w-4 h-4" />
            <span>Process Conformance</span>
          </button>

          <button
            onClick={() => setActiveTab("simulation")}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-all ${
              activeTab === "simulation"
                ? "border-indigo-500 text-indigo-400 bg-indigo-500/5"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Sliders className="w-4 h-4" />
            <span>What-If Simulation</span>
          </button>

          <button
            onClick={() => setActiveTab("prediction")}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-all ${
              activeTab === "prediction"
                ? "border-indigo-500 text-indigo-400 bg-indigo-500/5"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            <span>Predictive Risk & Open Cases</span>
          </button>

          <button
            onClick={() => setActiveTab("recommendation")}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-all ${
              activeTab === "recommendation"
                ? "border-indigo-500 text-indigo-400 bg-indigo-500/5"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Lightbulb className="w-4 h-4" />
            <span>AI Recommendations</span>
          </button>

          <button
            onClick={() => setActiveTab("history")}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-all ${
              activeTab === "history"
                ? "border-indigo-500 text-indigo-400 bg-indigo-500/5"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <History className="w-4 h-4" />
            <span>Audit History</span>
            {pastRuns.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-800 text-slate-300">
                {pastRuns.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab("upload")}
            className={`flex items-center gap-2 px-4 py-3 text-xs font-bold uppercase tracking-wider border-b-2 transition-all ${
              activeTab === "upload"
                ? "border-indigo-500 text-indigo-400 bg-indigo-500/5"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Upload className="w-4 h-4" />
            <span>Data Management</span>
          </button>
        </div>

        {/* =================================================================== */}
        {/* TAB 1: Process Discovery (Feature 2) */}
        {/* =================================================================== */}
        {activeTab === "discovery" && (
          <div className="space-y-6">
            {/* Fallback Warning Banner */}
            {Boolean(discovery?.fallback || paths?.fallback) && (
              <div
                id="discovery-fallback-warning"
                data-testid="fallback-warning-banner"
                className="p-4 rounded-xl bg-amber-950/40 border border-amber-500/50 text-amber-200 text-xs flex items-center justify-between gap-3 shadow-lg animate-in fade-in duration-200"
              >
                <div className="flex items-center gap-2.5">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <div>
                    <span className="font-bold text-amber-100">Showing fallback data, not this run's own output.</span>
                    <span className="text-amber-300/80 ml-2">
                      {discovery?.warning || paths?.warning || "The requested run-specific artifact was unavailable and the system is displaying legacy fallback data."}
                    </span>
                  </div>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  Fallback Active
                </span>
              </div>
            )}

            {/* Interactive Process Map Canvas */}
            <ProcessGraph
              apiBaseUrl={API_BASE}
              staticMapUrl={`${API_BASE}/api/discovery/process-map-image`}
              onRunPhase1={() => triggerSinglePhase("phase1")}
            />

            {/* Bottlenecks Table */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Clock className="w-4 h-4 text-indigo-400" />
                    Activity Wait Times & Rework Loops
                  </h3>
                  <p className="text-xs text-slate-400">
                    Handover latency and repetition counts ranked by process impact
                  </p>
                </div>
              </div>

              {loadingOutputs && !discovery ? (
                <div className="space-y-3 py-2 animate-pulse">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="h-11 rounded-xl bg-slate-950/60 border border-slate-800/80 flex items-center justify-between px-4">
                      <div className="w-32 h-3 bg-slate-800 rounded" />
                      <div className="w-16 h-3 bg-slate-800 rounded" />
                      <div className="w-20 h-3 bg-slate-800 rounded" />
                      <div className="w-16 h-5 bg-slate-800 rounded-full" />
                    </div>
                  ))}
                </div>
              ) : discovery?.bottlenecks && discovery.bottlenecks.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs text-slate-300 border-collapse">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
                        <th className="py-3 px-4">Activity Name</th>
                        <th className="py-3 px-4">Avg Wait Time</th>
                        <th className="py-3 px-4">Cases with Rework</th>
                        <th className="py-3 px-4 text-right">Delay Contribution</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono">
                      {discovery.bottlenecks.map((bn, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                          <td className="py-3 px-4 font-sans font-semibold text-slate-200 truncate max-w-[200px]" title={bn.activity}>
                            {bn.activity}
                          </td>
                          <td className="py-3 px-4 font-bold text-white">
                            {bn.avg_wait_hours.toFixed(2)}h
                          </td>
                          <td className="py-3 px-4 text-slate-300">
                            {bn.times_repeated} cases
                          </td>
                          <td className="py-3 px-4 text-right font-sans">
                            <div className="flex items-center justify-end gap-2">
                              <span
                                className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                                  bn.delay_contribution === "High"
                                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                    : bn.delay_contribution === "Medium"
                                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                    : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                }`}
                              >
                                {bn.delay_contribution}
                              </span>
                              <button
                                type="button"
                                onClick={() => {
                                  setSimulationPreselectedActivity(bn.activity);
                                  setActiveTab("simulation");
                                }}
                                className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-indigo-950 border border-indigo-800 hover:border-indigo-600 text-indigo-300 transition-colors flex items-center gap-1"
                                title={`Simulate operational interventions on ${bn.activity}`}
                              >
                                <Sliders className="w-2.5 h-2.5" />
                                <span>Simulate</span>
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-12 text-center text-slate-400 text-xs max-w-sm mx-auto space-y-3">
                  <div className="w-10 h-10 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-center text-slate-500 mx-auto">
                    <Clock className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="font-semibold text-slate-200 mb-0.5">No Bottleneck Data Discovered Yet</p>
                    <p className="text-slate-500 text-[11px] leading-relaxed">
                      Run Phase 1 (Discovery) to analyze timestamp gaps between sequential activities and identify rework loops.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => triggerSinglePhase("phase1")}
                    disabled={isRunning}
                    className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 transition-all"
                  >
                    Run Phase 1 (Discovery)
                  </button>
                </div>
              )}
            </div>

            {/* Process Paths */}
            {paths?.paths && paths.paths.length > 0 && (
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md space-y-3">
                <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <GitCommit className="w-4 h-4 text-indigo-400" />
                  Discovered Process Variants & Execution Pathways
                </h3>
                <div className="space-y-2">
                  {paths.paths.map((p, idx) => (
                    <div
                      key={idx}
                      className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 font-mono text-xs text-indigo-300"
                    >
                      {p}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Conformance Quick Link Banner */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-xl backdrop-blur-md flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 shrink-0">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                    Process Conformance & Trace Alignments
                  </h4>
                  <p className="text-[11px] text-slate-400">
                    Verify compliance against the normative reference model, detect skips and rework loops, and audit case-level fitness.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setActiveTab("conformance")}
                className="px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 flex items-center gap-1.5 transition-all"
              >
                <span>View Conformance Report</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 2: Process Conformance Checking (Phase E) */}
        {/* =================================================================== */}
        {activeTab === "conformance" && (
          <ConformancePanel
            apiBaseUrl={API_BASE}
            projectId={activeProject}
            onRunPhase1={() => triggerSinglePhase("phase1")}
          />
        )}

        {/* =================================================================== */}
        {/* TAB 3: What-If Simulation (Phase F) */}
        {/* =================================================================== */}
        {activeTab === "simulation" && (
          <SimulationPanel
            apiBaseUrl={API_BASE}
            projectId={activeProject}
            onRunPhase1={() => triggerSinglePhase("phase1")}
            preselectedActivity={simulationPreselectedActivity}
          />
        )}

        {/* =================================================================== */}
        {/* TAB 2: Predictive Risk & Open Cases with AI Explain (Feature 5) */}
        {/* =================================================================== */}
        {activeTab === "prediction" && (
          <div className="space-y-6">
            {/* Fallback Warning Banner */}
            {Boolean(predictions?.fallback) && (
              <div
                id="prediction-fallback-warning"
                data-testid="fallback-warning-banner"
                className="p-4 rounded-xl bg-amber-950/40 border border-amber-500/50 text-amber-200 text-xs flex items-center justify-between gap-3 shadow-lg animate-in fade-in duration-200"
              >
                <div className="flex items-center gap-2.5">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <div>
                    <span className="font-bold text-amber-100">Showing fallback data, not this run's own output.</span>
                    <span className="text-amber-300/80 ml-2">
                      {predictions?.warning || "The requested run-specific artifact was unavailable and the system is displaying legacy fallback data."}
                    </span>
                  </div>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  Fallback Active
                </span>
              </div>
            )}

            {loadingOutputs && !predictions ? (
              <div className="space-y-6 animate-pulse">
                {/* Skeleton Metric Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 h-24 space-y-2">
                      <div className="w-24 h-3 bg-slate-800 rounded" />
                      <div className="w-16 h-6 bg-slate-700 rounded" />
                      <div className="w-20 h-2.5 bg-slate-800/80 rounded" />
                    </div>
                  ))}
                </div>
                {/* Skeleton Chart */}
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 h-48 space-y-4">
                  <div className="w-48 h-4 bg-slate-800 rounded" />
                  <div className="space-y-3 pt-2">
                    {[1, 2, 3].map((i) => (
                      <div key={i} className="flex items-center gap-3">
                        <div className="w-32 h-3 bg-slate-800 rounded" />
                        <div className="flex-1 h-3 bg-slate-800 rounded-full" />
                        <div className="w-12 h-3 bg-slate-800 rounded" />
                      </div>
                    ))}
                  </div>
                </div>
                {/* Skeleton Table */}
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 h-64 space-y-4">
                  <div className="w-56 h-4 bg-slate-800 rounded" />
                  <div className="space-y-3 pt-2">
                    {[1, 2, 3, 4].map((i) => (
                      <div key={i} className="h-10 rounded-xl bg-slate-950/60 border border-slate-800/80" />
                    ))}
                  </div>
                </div>
              </div>
            ) : predictions?.available ? (
              <>
                {/* Metric Cards Banner */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-slate-400 text-xs block font-medium">Model Accuracy</span>
                      {predictions.model_metrics.cv_strategy && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-mono font-semibold">
                          {predictions.model_metrics.n_splits || 5}-Fold CV
                        </span>
                      )}
                    </div>
                    <span className="text-2xl font-bold font-mono text-emerald-400">
                      {predictions.model_metrics.accuracy
                        ? `${(predictions.model_metrics.accuracy * 100).toFixed(1)}%`
                        : "N/A"}
                    </span>
                    {predictions.model_metrics.variation?.accuracy ? (
                      <div className="text-[11px] text-slate-400 mt-1 font-mono">
                        <span>Range: {predictions.model_metrics.variation.accuracy.range_str}</span>
                        <span className="text-slate-500 ml-1">(±{(predictions.model_metrics.variation.accuracy.std * 100).toFixed(1)}%)</span>
                      </div>
                    ) : (
                      <span className="text-[11px] text-slate-500 block mt-1">
                        F1: {predictions.model_metrics.f1?.toFixed(3) || "N/A"}
                      </span>
                    )}
                  </div>

                  <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-slate-400 text-xs block font-medium">ROC-AUC Score</span>
                      {predictions.model_metrics.cv_strategy && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 font-mono font-semibold">
                          Stratified
                        </span>
                      )}
                    </div>
                    <span className="text-2xl font-bold font-mono text-cyan-400">
                      {predictions.model_metrics.roc_auc?.toFixed(3) || "N/A"}
                    </span>
                    {predictions.model_metrics.variation?.roc_auc ? (
                      <div className="text-[11px] text-slate-400 mt-1 font-mono">
                        <span>Range: {predictions.model_metrics.variation.roc_auc.range_str}</span>
                        <span className="text-slate-500 ml-1">(±{predictions.model_metrics.variation.roc_auc.std.toFixed(3)})</span>
                      </div>
                    ) : (
                      <span className="text-[11px] text-slate-500 block mt-1">
                        Precision: {predictions.model_metrics.precision?.toFixed(3) || "N/A"}
                      </span>
                    )}
                  </div>

                  <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
                    <span className="text-slate-400 text-xs block font-medium">Active Open Cases</span>
                    <span className="text-2xl font-bold font-mono text-white">
                      {predictions.summary?.total_cases ?? predictions.open_cases.length}
                    </span>
                    <span className="text-[11px] text-slate-500 block mt-1">
                      {predictions.summary?.late_risk_count ?? 0} flagged at late risk
                    </span>
                  </div>

                  <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
                    <span className="text-slate-400 text-xs block font-medium">Anomalies Detected</span>
                    <span className="text-2xl font-bold font-mono text-purple-400">
                      {predictions.summary?.anomaly_count ?? 0}
                    </span>
                    <span className="text-[11px] text-slate-500 block mt-1">
                      Isolation Forest filter
                    </span>
                  </div>
                </div>

                {/* Cross-Validation Fold Breakdown Banner (Phase C) */}
                {predictions.model_metrics.fold_metrics && predictions.model_metrics.fold_metrics.length > 0 && (
                  <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-3.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                        <span className="text-xs font-semibold text-slate-200">
                          Stratified {predictions.model_metrics.n_splits || 5}-Fold Cross-Validation Metrics
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono hidden sm:inline">
                          (Observed fold variation without asymptotic fabrication)
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setShowFoldBreakdown(!showFoldBreakdown)}
                        className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold transition-colors"
                      >
                        {showFoldBreakdown ? "Hide Folds ▲" : "Show Fold Breakdown ▼"}
                      </button>
                    </div>

                    {showFoldBreakdown && (
                      <div className="mt-3 overflow-x-auto border-t border-slate-800/80 pt-3">
                        <table className="w-full text-left text-xs font-mono text-slate-300">
                          <thead>
                            <tr className="text-slate-500 text-[10px] uppercase border-b border-slate-800">
                              <th className="py-1.5 px-2">Fold</th>
                              <th className="py-1.5 px-2">Val Samples</th>
                              <th className="py-1.5 px-2">Late Cases</th>
                              <th className="py-1.5 px-2">Accuracy</th>
                              <th className="py-1.5 px-2">ROC-AUC</th>
                              <th className="py-1.5 px-2">F1 Score</th>
                              <th className="py-1.5 px-2">Precision</th>
                              <th className="py-1.5 px-2">Recall</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/50">
                            {predictions.model_metrics.fold_metrics.map((fold) => (
                              <tr key={fold.fold} className="hover:bg-slate-800/30">
                                <td className="py-1.5 px-2 font-bold text-white">Fold #{fold.fold}</td>
                                <td className="py-1.5 px-2 text-slate-400">{fold.val_samples ?? "-"}</td>
                                <td className="py-1.5 px-2 text-slate-400">{fold.late_cases ?? "-"}</td>
                                <td className="py-1.5 px-2 text-emerald-400 font-semibold">{(fold.accuracy * 100).toFixed(1)}%</td>
                                <td className="py-1.5 px-2 text-cyan-400 font-semibold">{fold.roc_auc.toFixed(3)}</td>
                                <td className="py-1.5 px-2 text-slate-300">{fold.f1.toFixed(3)}</td>
                                <td className="py-1.5 px-2 text-slate-300">{fold.precision.toFixed(3)}</td>
                                <td className="py-1.5 px-2 text-slate-300">{fold.recall.toFixed(3)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                {/* Enterprise Multi-Prefix & Gradient Boosting Benchmark Card */}
                {predictions.enterprise_benchmark && (
                  <div className="bg-gradient-to-r from-indigo-950/50 via-slate-900 to-slate-900/90 border border-indigo-500/40 rounded-2xl p-5 shadow-xl">
                    <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                      <div className="flex items-center gap-2.5">
                        <div className="p-2 rounded-xl bg-gradient-to-tr from-amber-500/20 to-indigo-500/20 text-amber-300 border border-amber-500/30">
                          <Zap className="w-4 h-4 text-amber-400" />
                        </div>
                        <div>
                          <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                            Enterprise Benchmark: Multi-Prefix & Gradient Boosting
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold normal-case">
                              {predictions.enterprise_benchmark.dataset.total_prefix_rows} Multi-Prefix Snapshots
                            </span>
                          </h4>
                          <p className="text-[11px] text-slate-400">
                            5-Fold Stratified Group CV (zero cross-prefix leakage) with real-time WIP system queue congestion.
                          </p>
                        </div>
                      </div>
                      <span className="text-[11px] font-mono font-semibold text-emerald-300 bg-emerald-500/10 px-3 py-1 rounded-lg border border-emerald-500/30">
                        Top Performer: {predictions.enterprise_benchmark.winning_model} (Test AUC: {predictions.enterprise_benchmark.models.random_forest.test_roc_auc.toFixed(3)})
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-800/80 font-mono text-xs">
                      <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex items-center justify-between">
                        <div>
                          <span className="text-[10px] text-slate-400 uppercase block font-sans font-semibold">Tuned Random Forest</span>
                          <span className="text-emerald-400 font-bold text-base">
                            {predictions.enterprise_benchmark.models.random_forest.cv_roc_auc_mean.toFixed(3)} CV AUC
                          </span>
                          <span className="text-[10px] text-slate-500 ml-1.5">
                            (±{predictions.enterprise_benchmark.models.random_forest.cv_roc_auc_std.toFixed(3)})
                          </span>
                        </div>
                        <div className="text-right">
                          <span className="text-[10px] text-slate-400 uppercase block font-sans">Holdout Test</span>
                          <span className="text-emerald-400 font-bold text-base">
                            {predictions.enterprise_benchmark.models.random_forest.test_roc_auc.toFixed(3)} AUC
                          </span>
                        </div>
                      </div>

                      <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex items-center justify-between">
                        <div>
                          <span className="text-[10px] text-slate-400 uppercase block font-sans font-semibold">LightGBM Gradient Boosting</span>
                          <span className="text-cyan-400 font-bold text-base">
                            {predictions.enterprise_benchmark.models.lightgbm.cv_roc_auc_mean.toFixed(3)} CV AUC
                          </span>
                          <span className="text-[10px] text-slate-500 ml-1.5">
                            (±{predictions.enterprise_benchmark.models.lightgbm.cv_roc_auc_std.toFixed(3)})
                          </span>
                        </div>
                        <div className="text-right">
                          <span className="text-[10px] text-slate-400 uppercase block font-sans">Holdout Test</span>
                          <span className="text-cyan-400 font-bold text-base">
                            {predictions.enterprise_benchmark.models.lightgbm.test_roc_auc.toFixed(3)} AUC
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Feature Importance Bar Chart */}
                {predictions.feature_importances && predictions.feature_importances.length > 0 && (
                  <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl">
                    <h3 className="text-sm font-bold text-white uppercase tracking-wider mb-4 flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-indigo-400" />
                      Top Predictive Features (Random Forest)
                    </h3>
                    <div className="space-y-2">
                      {predictions.feature_importances.slice(0, 6).map((item) => {
                        const maxVal = Math.max(...predictions.feature_importances.map((i) => i.importance), 0.001);
                        const pct = Math.round((item.importance / maxVal) * 100);
                        return (
                          <div key={item.feature} className="flex items-center gap-3 text-xs">
                            <span className="text-slate-400 w-48 text-right shrink-0 font-mono truncate" title={item.feature}>
                              {item.feature}
                            </span>
                            <div className="flex-1 bg-slate-950 rounded-full h-3 border border-slate-800 overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 rounded-full"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                            <span className="text-slate-300 w-14 font-mono text-right">
                              {item.importance.toFixed(4)}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Open Cases Table with Explain Case Button */}
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                    <div>
                      <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                        <ShieldAlert className="w-4 h-4 text-rose-400" />
                        In-Flight Open Cases Risk Telemetry
                        <span className="ml-2 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 normal-case">
                          Risk threshold: {(predictions.risk_threshold ?? predictions.model_metrics?.risk_threshold ?? 0.19).toFixed(2)}
                        </span>
                      </h3>
                      <p className="text-xs text-slate-400">
                        Live cases undergoing process completion with model-derived risk drivers. Click <strong>Explain Case</strong> for token-efficient root cause synthesis.
                      </p>
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs text-slate-300 border-collapse">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
                          <th className="py-3 px-4">Case & Risk Drivers</th>
                          <th className="py-3 px-4">Current Step</th>
                          <th className="py-3 px-4">Elapsed Hours</th>
                          <th className="py-3 px-4">Risk Probability</th>
                          <th className="py-3 px-4">Status</th>
                          <th className="py-3 px-4">Prescriptive Next Action</th>
                          <th className="py-3 px-4 text-right">Diagnostic Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono">
                        {predictions.open_cases.length > 0 ? (
                          predictions.open_cases.map((c) => (
                            <tr key={c.case_id} className="hover:bg-slate-800/40 transition-colors">
                              <td className="py-3 px-4 max-w-[280px]">
                                <div className="font-bold text-white font-mono">{c.case_id}</div>
                                {c.explanation && (
                                  <div className="text-[11px] text-slate-400 font-sans mt-1 leading-snug line-clamp-2" title={c.explanation}>
                                    {c.explanation}
                                  </div>
                                )}
                                {c.risk_drivers && c.risk_drivers.length > 0 && (
                                  <div className="flex flex-wrap gap-1 mt-1.5">
                                    {c.risk_drivers.map((d) => (
                                      <span key={d} className="px-1.5 py-0.5 rounded text-[9px] bg-slate-800 border border-slate-700/60 text-indigo-300 font-mono">
                                        {d}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </td>
                              <td className="py-3 px-4 font-sans text-slate-300 truncate max-w-[150px]" title={c.current_step}>
                                {c.current_step}
                              </td>
                              <td className="py-3 px-4 text-slate-300">
                                {c.elapsed_hours_so_far.toFixed(1)}h
                              </td>
                              <td className="py-3 px-4 font-bold">
                                {c.late_risk_probability !== null ? (
                                  <span
                                    className={
                                      c.late_risk_probability >= (c.risk_threshold ?? predictions.risk_threshold ?? 0.19)
                                        ? "text-rose-400"
                                        : c.late_risk_probability >= (c.risk_threshold ?? predictions.risk_threshold ?? 0.19) * 0.7
                                        ? "text-amber-400"
                                        : "text-emerald-400"
                                    }
                                  >
                                    {(c.late_risk_probability * 100).toFixed(1)}%
                                  </span>
                                ) : (
                                  "N/A"
                                )}
                              </td>
                              <td className="py-3 px-4 font-sans">
                                <span
                                  className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                                    c.predicted_label === "Late Risk"
                                      ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                      : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                  }`}
                                >
                                  {c.predicted_label}
                                </span>
                                {c.anomaly_flag && (
                                  <span className="ml-1.5 px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider bg-purple-500/20 text-purple-300 border border-purple-500/30">
                                    Anomaly
                                  </span>
                                )}
                              </td>
                              <td className="py-3 px-4 font-sans max-w-[230px]">
                                {c.prescriptive_action && c.prescriptive_action.action_title !== "Awaiting Milestone" ? (
                                  <button
                                    type="button"
                                    onClick={() => handleExplainCase(c.case_id)}
                                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 transition-all text-left group"
                                    title={c.prescriptive_action.guidance}
                                  >
                                    <Zap className="w-3.5 h-3.5 text-amber-400 shrink-0 group-hover:scale-110 transition-transform" />
                                    <div className="truncate">
                                      <span className="font-semibold">{c.prescriptive_action.action_title}</span>
                                      {c.prescriptive_action.risk_reduction_pct > 0 && (
                                        <span className="ml-1.5 text-[10px] text-emerald-400 font-mono font-bold">
                                          -{c.prescriptive_action.risk_reduction_pct}%
                                        </span>
                                      )}
                                    </div>
                                  </button>
                                ) : (
                                  <span className="text-slate-500 text-[11px] font-mono">Standard Routing</span>
                                )}
                              </td>
                              <td className="py-3 px-4 text-right font-sans">
                                <button
                                  type="button"
                                  onClick={() => handleExplainCase(c.case_id)}
                                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/20 transition-all active:scale-95"
                                >
                                  <Sparkles className="w-3 h-3 text-cyan-200" />
                                  <span>Explain Case</span>
                                </button>
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={7} className="py-8 text-center text-slate-500 font-sans text-xs">
                              No open in-flight cases found matching the current snapshot milestone.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            ) : (
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-12 text-center shadow-xl max-w-lg mx-auto space-y-4">
                <div className="w-12 h-12 rounded-2xl bg-slate-950 border border-slate-800 flex items-center justify-center text-indigo-400 mx-auto shadow-inner">
                  <ShieldAlert className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white mb-1">
                    Predictive Model Not Yet Trained
                  </h3>
                  <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                    Execute Phase 2 to freeze case states at milestone cutoffs, extract feature matrices, and train the Random Forest delay classifier.
                  </p>
                </div>
                <div className="flex items-center justify-center gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => triggerSinglePhase("phase2")}
                    disabled={isRunning}
                    className="px-5 py-2.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 transition-all"
                  >
                    Train Model & Predict Delays
                  </button>
                  <button
                    type="button"
                    onClick={() => setActiveTab("upload")}
                    className="px-4 py-2.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                  >
                    Upload Custom Log
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 3: AI Recommendations */}
        {/* =================================================================== */}
        {activeTab === "recommendation" && (
          <div className="space-y-6">
            {/* Fallback Warning Banner */}
            {Boolean(explanation?.fallback) && (
              <div
                id="explanation-fallback-warning"
                data-testid="fallback-warning-banner"
                className="p-4 rounded-xl bg-amber-950/40 border border-amber-500/50 text-amber-200 text-xs flex items-center justify-between gap-3 shadow-lg animate-in fade-in duration-200"
              >
                <div className="flex items-center gap-2.5">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <div>
                    <span className="font-bold text-amber-100">Showing fallback data, not this run's own output.</span>
                    <span className="text-amber-300/80 ml-2">
                      {explanation?.warning || "The requested run-specific artifact was unavailable and the system is displaying legacy fallback data."}
                    </span>
                  </div>
                </div>
                <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  Fallback Active
                </span>
              </div>
            )}

            {loadingOutputs && !explanation ? (
              <div className="space-y-6 animate-pulse">
                <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex items-center justify-between">
                  <div className="h-4 w-48 bg-slate-800 rounded"></div>
                  <div className="h-4 w-32 bg-slate-800 rounded"></div>
                </div>
                {[1, 2, 3].map((i) => (
                  <div key={i} className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 space-y-4">
                    <div className="h-4 w-44 bg-slate-800 rounded"></div>
                    <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
                      <div className="h-3 w-full bg-slate-800/80 rounded"></div>
                      <div className="h-3 w-5/6 bg-slate-800/80 rounded"></div>
                      <div className="h-3 w-4/6 bg-slate-800/80 rounded"></div>
                    </div>
                  </div>
                ))}
              </div>
            ) : explanation?.available ? (
              <div className="space-y-6">
                {/* Status Bar */}
                <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                    <span className="text-slate-400">Agent Multi-Stage Consensus:</span>
                    <span
                      className={`px-2.5 py-0.5 rounded-full font-bold uppercase text-[10px] ${
                        explanation.approved
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                      }`}
                    >
                      {explanation.approved ? "Approved by Verifier" : "Pending Verification"}
                    </span>
                  </div>
                  {explanation.timestamp && (
                    <span className="text-slate-500 font-mono">
                      Generated {new Date(explanation.timestamp).toLocaleString()}
                    </span>
                  )}
                </div>

                {/* Investigator Findings */}
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Activity className="w-4 h-4 text-cyan-400" />
                    Investigator Root Cause Findings
                  </h3>
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-200 leading-relaxed whitespace-pre-wrap font-mono break-words">
                    {explanation.investigator_findings || "No findings recorded."}
                  </div>
                </div>

                {/* Draft Recommendation */}
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-amber-400" />
                    Intervention Recommendation
                  </h3>
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-200 leading-relaxed whitespace-pre-wrap font-mono break-words">
                    {explanation.draft_recommendation || "No recommendation drafted."}
                  </div>
                </div>

                {/* Verifier Score & Review */}
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    Verifier Evaluation & Mathematical Grounding
                  </h3>
                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-200 leading-relaxed whitespace-pre-wrap font-mono break-words">
                    {explanation.verification_result || "No verification review recorded."}
                  </div>
                </div>
              </div>
            ) : (
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-12 text-center shadow-xl max-w-lg mx-auto space-y-4">
                <div className="w-12 h-12 rounded-2xl bg-slate-950 border border-slate-800 flex items-center justify-center text-amber-400 mx-auto shadow-inner">
                  <Lightbulb className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white mb-1">
                    AI Recommendations Not Yet Generated
                  </h3>
                  <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
                    Run Phase 3 to dispatch the Investigator and Verifier CrewAI agents to formulate macro process interventions based on discovered bottlenecks.
                  </p>
                </div>
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={() => triggerSinglePhase("phase3")}
                    disabled={isRunning}
                    className="px-5 py-2.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 transition-all"
                  >
                    Run AI Recommendation Agents
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 4: Audit History (Supabase Persistence) */}
        {/* =================================================================== */}
        {activeTab === "history" && (
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <History className="w-4 h-4 text-indigo-400" />
                  Supabase Run History & Persistence
                </h3>
                <p className="text-xs text-slate-400">
                  Every pipeline execution is committed to PostgreSQL with full snapshot telemetry
                </p>
              </div>
            </div>

            {loadingOutputs && pastRuns.length === 0 ? (
              <div className="space-y-3 py-4 animate-pulse">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 bg-slate-800/40 rounded-lg w-full"></div>
                ))}
              </div>
            ) : pastRuns.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-300 border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
                      <th className="py-3 px-4">Run Identifier</th>
                      <th className="py-3 px-4">Execution Date</th>
                      <th className="py-3 px-4">Data Source</th>
                      <th className="py-3 px-4">Row Count</th>
                      <th className="py-3 px-4">Outcome</th>
                      <th className="py-3 px-4 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    {pastRuns.map((r) => (
                      <tr key={r.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3 px-4 font-bold text-white truncate max-w-xs" title={r.id}>
                          {r.id}
                        </td>
                        <td className="py-3 px-4 text-slate-400">
                          {new Date(r.created_at).toLocaleString()}
                        </td>
                        <td className="py-3 px-4 capitalize font-sans">
                          {r.data_source} {r.source_filename ? `(${r.source_filename})` : ""}
                        </td>
                        <td className="py-3 px-4 text-slate-300">
                          {r.row_count?.toLocaleString() || "N/A"}
                        </td>
                        <td className="py-3 px-4 font-sans">
                          <span
                            className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                              r.status === "completed"
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                : r.status === "failed"
                                ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                : "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                            }`}
                          >
                            {r.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right font-sans">
                          <button
                            type="button"
                            onClick={() => selectPastRun(r.id)}
                            disabled={loadingRun}
                            className="px-3 py-1 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
                          >
                            {loadingRun && selectedPastRunId === r.id ? "Loading..." : "Inspect Run"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-12 text-center max-w-md mx-auto space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-slate-950 border border-slate-800 flex items-center justify-center text-slate-500 mx-auto shadow-inner">
                  <History className="w-6 h-6" />
                </div>
                <h4 className="text-sm font-semibold text-slate-300">No Past Executions Stored</h4>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Execute the pipeline in this workspace to record automated performance audits, transition models, and risk projections in Supabase PostgreSQL.
                </p>
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={() => triggerRunAll()}
                    disabled={isRunning}
                    className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 transition-all disabled:opacity-50"
                  >
                    Run Full Pipeline Now
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 5: Data Management & Direct Connectors (Phase G) */}
        {/* =================================================================== */}
        {activeTab === "upload" && (
          <ConnectorPanel
            apiBase={API_BASE}
            activeProject={activeProject}
            apiKey={API_KEY}
            onUploadSuccess={(msg) => {
              setUploadSuccess(msg);
              reloadAll();
            }}
            onUploadError={(errs) => {
              setUploadErrors(errs);
            }}
            onResetSuccess={(msg) => {
              setUploadSuccess(msg);
              setUploadErrors([]);
              reloadAll();
            }}
          />
        )}
      </main>

      {/* Real-time Streaming Logs Bottom Console (Feature 1) */}
      <LiveLogPanel
        runId={activeRunId}
        isOpen={showLogPanel}
        onClose={() => setShowLogPanel(false)}
        onRunComplete={handleRunComplete}
        apiBaseUrl={API_BASE}
      />

      {/* Case Intelligence AI Explanation Slide-over Drawer (Feature 5) */}
      <CaseExplainDrawer
        caseId={selectedCaseId}
        isOpen={showExplainDrawer}
        onClose={() => setShowExplainDrawer(false)}
        apiBaseUrl={API_BASE}
      />
    </div>
  );
}
