"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Sliders,
  Clock,
  ArrowRight,
  TrendingDown,
  RotateCcw,
  Sparkles,
  Flame,
  Activity,
  AlertCircle,
  CheckCircle2,
  HelpCircle,
  Zap,
  Info,
  Layers,
  ChevronRight,
  ShieldAlert,
  AlertTriangle,
} from "lucide-react";

export interface ActivityBaseline {
  activity: string;
  avg_wait_hours: number;
  median_wait_hours: number;
  occurrence_count: number;
  avg_duration_hours: number;
  median_duration_hours: number;
  rework_cases: number;
}

export interface BottleneckItem {
  activity: string;
  avg_wait_hours: number;
  times_repeated: number;
  delay_contribution: "High" | "Medium" | "Low";
}

export interface SimulationBaseline {
  available: boolean;
  message?: string;
  fallback?: boolean;
  warning?: string;
  case_count: number;
  event_count: number;
  avg_cycle_time_hours: number;
  median_cycle_time_hours: number;
  p75_cycle_time_hours: number;
  rework_case_count: number;
  rework_case_pct: number;
  primary_bottleneck?: BottleneckItem | null;
  bottlenecks: BottleneckItem[];
  activities: ActivityBaseline[];
  resources: { resource: string; event_count: number; case_count: number }[];
}

export interface SimulationResult {
  available: boolean;
  fallback?: boolean;
  warning?: string;
  scenario: {
    type: string;
    title: string;
    target_activity?: string;
    target_resource?: string;
    reduction_pct: number;
    capacity_increase_pct?: number;
    assumptions: string;
    calculation_basis: string[];
  };
  baseline: {
    case_count: number;
    avg_cycle_time_hours: number;
    median_cycle_time_hours: number;
    component_name: string;
    component_value: number;
  };
  simulated: {
    avg_cycle_time_hours: number;
    median_cycle_time_hours: number;
    component_value: number;
    affected_cases_count: number;
    affected_cases_pct: number;
  };
  impact: {
    absolute_reduction_hours: number;
    cycle_time_improvement_pct: number;
    component_reduction_hours: number;
    component_reduction_pct: number;
  };
  explanation: string;
}

export interface ScenarioHistoryItem {
  id: string;
  title: string;
  scenario_type: string;
  target: string;
  adjustment_pct: number;
  simulated_cycle_time: number;
  improvement_pct: number;
  hours_saved: number;
  timestamp: string;
}

interface SimulationPanelProps {
  apiBaseUrl?: string;
  projectId?: string;
  onRunPhase1?: () => void;
  preselectedActivity?: string | null;
}

export const SimulationPanel: React.FC<SimulationPanelProps> = ({
  apiBaseUrl = "http://localhost:8000",
  projectId = "default",
  onRunPhase1,
  preselectedActivity,
}) => {
  const [baseline, setBaseline] = useState<SimulationBaseline | null>(null);
  const [loadingBaseline, setLoadingBaseline] = useState<boolean>(true);
  const [baselineError, setBaselineError] = useState<string | null>(null);

  // Scenario Configuration State
  const [scenarioType, setScenarioType] = useState<
    "bottleneck_wait_reduction" | "rework_reduction" | "activity_duration_reduction" | "resource_capacity"
  >("bottleneck_wait_reduction");
  const [targetActivity, setTargetActivity] = useState<string>("");
  const [targetResource, setTargetResource] = useState<string>("");
  const [reductionPct, setReductionPct] = useState<number>(30);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [simulationError, setSimulationError] = useState<string | null>(null);

  // Active Simulation Result & History
  const [activeResult, setActiveResult] = useState<SimulationResult | null>(null);
  const [history, setHistory] = useState<ScenarioHistoryItem[]>([]);
  const [showBasisDetails, setShowBasisDetails] = useState<boolean>(false);

  // Load Baseline Metrics
  const fetchBaseline = useCallback(async () => {
    setLoadingBaseline(true);
    setBaselineError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/api/simulation/baseline?project_id=${encodeURIComponent(projectId)}`);
      if (res.status === 202) {
        const body = await res.json();
        setBaseline(body);
        setLoadingBaseline(false);
        return;
      }
      if (!res.ok) {
        throw new Error(`Failed to load simulation baseline (HTTP ${res.status})`);
      }
      const data: SimulationBaseline = await res.json();
      setBaseline(data);

      // Set initial target activity
      if (data.available && data.activities && data.activities.length > 0) {
        if (preselectedActivity && data.activities.some((a) => a.activity === preselectedActivity)) {
          setTargetActivity(preselectedActivity);
        } else if (data.primary_bottleneck) {
          setTargetActivity(data.primary_bottleneck.activity);
        } else {
          setTargetActivity(data.activities[0].activity);
        }
      }
      if (data.resources && data.resources.length > 0) {
        setTargetResource(data.resources[0].resource);
      }
    } catch (err: any) {
      setBaselineError(err.message || "Could not fetch simulation baseline.");
    } finally {
      setLoadingBaseline(false);
    }
  }, [apiBaseUrl, projectId, preselectedActivity]);

  useEffect(() => {
    fetchBaseline();
  }, [fetchBaseline]);

  // Execute Simulation Scenario
  const handleRunSimulation = async (
    customType?: "bottleneck_wait_reduction" | "rework_reduction" | "activity_duration_reduction" | "resource_capacity",
    customActivity?: string,
    customPct?: number
  ) => {
    setIsSimulating(true);
    setSimulationError(null);

    const type = customType || scenarioType;
    const act = customActivity !== undefined ? customActivity : targetActivity;
    const pct = customPct !== undefined ? customPct : reductionPct;

    try {
      const payload: Record<string, any> = {
        project_id: projectId,
        scenario_type: type,
        reduction_pct: pct,
      };

      if (type === "resource_capacity") {
        payload.target_resource = targetResource;
        payload.capacity_increase_pct = pct;
      } else {
        payload.target_activity = act;
      }

      const res = await fetch(`${apiBaseUrl}/api/simulation/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const body = await res.json();
      if (!res.ok || res.status === 422 || !body.available) {
        throw new Error(body.error || body.message || `Simulation failed with HTTP ${res.status}`);
      }

      setActiveResult(body);

      // Add to multi-scenario comparison history
      const historyEntry: ScenarioHistoryItem = {
        id: `sim-${Date.now()}-${Math.random().toString(36).substring(2, 5)}`,
        title: body.scenario.title,
        scenario_type: type,
        target: type === "resource_capacity" ? (targetResource || "All Resources") : act,
        adjustment_pct: pct,
        simulated_cycle_time: body.simulated.avg_cycle_time_hours,
        improvement_pct: body.impact.cycle_time_improvement_pct,
        hours_saved: body.impact.absolute_reduction_hours,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      };

      setHistory((prev) => [historyEntry, ...prev.filter((h) => h.title !== historyEntry.title).slice(0, 6)]);
    } catch (err: any) {
      setSimulationError(err.message || "Failed to execute simulation scenario.");
    } finally {
      setIsSimulating(false);
    }
  };

  // Quick Preset Handlers
  const handleApplyPreset = (type: any, act: string, pct: number) => {
    setScenarioType(type);
    setTargetActivity(act);
    setReductionPct(pct);
    handleRunSimulation(type, act, pct);
  };

  // Loading Skeleton
  if (loadingBaseline && !baseline) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 h-24 space-y-2">
              <div className="w-20 h-3 bg-slate-800 rounded" />
              <div className="w-24 h-6 bg-slate-700 rounded" />
              <div className="w-28 h-2.5 bg-slate-800/80 rounded" />
            </div>
          ))}
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 h-64" />
      </div>
    );
  }

  // Empty State: Pipeline Not Yet Executed
  if (!baseline?.available) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-12 text-center shadow-xl max-w-lg mx-auto space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-slate-950 border border-slate-800 flex items-center justify-center text-indigo-400 mx-auto shadow-inner">
          <Sliders className="w-6 h-6" />
        </div>
        <div>
          <h3 className="text-base font-bold text-white mb-1">
            What-If Simulation Requires Analysis
          </h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
            Execute Phase 1 (Process Discovery) to establish the observed operational baseline before creating simulation scenarios.
          </p>
        </div>
        {baselineError && (
          <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-xs text-left font-mono">
            {baselineError}
          </div>
        )}
        <div className="flex items-center justify-center gap-3 pt-2">
          {onRunPhase1 && (
            <button
              type="button"
              onClick={onRunPhase1}
              className="px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 transition-all"
            >
              Run Phase 1 (Discovery)
            </button>
          )}
          <button
            type="button"
            onClick={fetchBaseline}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 transition-colors"
          >
            Retry Loading
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Fallback Warning Banner */}
      {(baseline.fallback || activeResult?.fallback) && (
        <div
          id="simulation-fallback-warning"
          data-testid="fallback-warning-banner"
          className="p-4 rounded-xl bg-amber-950/40 border border-amber-500/50 text-amber-200 text-xs flex items-center justify-between gap-3 shadow-lg animate-in fade-in duration-200"
        >
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <div>
              <span className="font-bold text-amber-100">Showing fallback data, not this run's own output.</span>
              <span className="text-amber-300/80 ml-2">
                {baseline.warning || activeResult?.warning || "The requested run-specific artifact was unavailable and the system is displaying legacy fallback data."}
              </span>
            </div>
          </div>
          <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/30">
            Fallback Active
          </span>
        </div>
      )}

      {/* Disclaimer Banner */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 rounded-xl bg-indigo-950/30 border border-indigo-500/20 text-indigo-300 text-xs backdrop-blur-md">
        <div className="flex items-center gap-2">
          <Info className="w-4 h-4 text-indigo-400 shrink-0" />
          <span>
            <strong>Deterministic Scenario Modeling:</strong> All calculations represent estimated operational impact under selected assumptions derived from the active event log. Not a guaranteed forecast.
          </span>
        </div>
        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-indigo-500/20 border border-indigo-500/30 text-indigo-200">
          Zero LLM Computation
        </span>
      </div>

      {/* Baseline KPI Telemetry Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <div className="flex items-center justify-between mb-1">
            <span className="text-slate-400 text-xs block font-medium">Observed Cases</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">
              Active Log
            </span>
          </div>
          <span className="text-2xl font-bold font-mono text-white">
            {baseline.case_count.toLocaleString()}
          </span>
          <span className="text-[11px] text-slate-500 block mt-1">
            {baseline.event_count.toLocaleString()} total event logs
          </span>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <span className="text-slate-400 text-xs block font-medium">Baseline Avg Cycle Time</span>
          <span className="text-2xl font-bold font-mono text-white">
            {baseline.avg_cycle_time_hours.toFixed(2)}h
          </span>
          <span className="text-[11px] text-slate-500 block mt-1">
            From first to last activity
          </span>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <span className="text-slate-400 text-xs block font-medium">Baseline Median Cycle Time</span>
          <span className="text-2xl font-bold font-mono text-cyan-400">
            {baseline.median_cycle_time_hours.toFixed(2)}h
          </span>
          <span className="text-[11px] text-slate-500 block mt-1">
            75th percentile: {baseline.p75_cycle_time_hours.toFixed(2)}h
          </span>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <div className="flex items-center justify-between mb-1">
            <span className="text-slate-400 text-xs block font-medium">Primary Bottleneck</span>
            {baseline.primary_bottleneck && (
              <span className="text-[9px] px-1.5 py-0.2 rounded font-bold uppercase tracking-wider bg-rose-500/20 text-rose-300 border border-rose-500/40">
                {baseline.primary_bottleneck.delay_contribution} Impact
              </span>
            )}
          </div>
          <span className="text-base font-bold font-sans text-rose-400 truncate block" title={baseline.primary_bottleneck?.activity}>
            {baseline.primary_bottleneck?.activity || "None"}
          </span>
          <span className="text-[11px] text-slate-400 font-mono block mt-1">
            {baseline.primary_bottleneck ? `${baseline.primary_bottleneck.avg_wait_hours.toFixed(2)}h avg wait` : "No bottleneck"}
          </span>
        </div>
      </div>

      {/* Scenario Builder Card */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <Sliders className="w-4 h-4 text-indigo-400" />
              Scenario Configuration
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Select an operational lever and adjust the intervention intensity to simulate cycle-time impact
            </p>
          </div>

          {/* Quick Presets */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-500 text-[11px]">Quick Levers:</span>
            {baseline.primary_bottleneck && (
              <button
                type="button"
                onClick={() => handleApplyPreset("bottleneck_wait_reduction", baseline.primary_bottleneck!.activity, 30)}
                className="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-indigo-950 border border-indigo-800 hover:border-indigo-600 text-indigo-300 transition-colors"
              >
                -30% Bottleneck ({baseline.primary_bottleneck.activity})
              </button>
            )}
            <button
              type="button"
              onClick={() => handleApplyPreset("rework_reduction", "all", 50)}
              className="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-indigo-950 border border-indigo-800 hover:border-indigo-600 text-indigo-300 transition-colors"
            >
              -50% Process Rework
            </button>
            {baseline.activities[0] && (
              <button
                type="button"
                onClick={() => handleApplyPreset("activity_duration_reduction", baseline.activities[0].activity, 25)}
                className="px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-indigo-950 border border-indigo-800 hover:border-indigo-600 text-indigo-300 transition-colors"
              >
                -25% Processing Time
              </button>
            )}
          </div>
        </div>

        {/* Intervention Mode Tabs */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <button
            type="button"
            onClick={() => setScenarioType("bottleneck_wait_reduction")}
            className={`p-3 rounded-xl border text-left transition-all ${
              scenarioType === "bottleneck_wait_reduction"
                ? "bg-indigo-600/10 border-indigo-500 shadow-sm shadow-indigo-500/10 text-white"
                : "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-bold">1. Bottleneck Wait</span>
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
            </div>
            <p className="text-[11px] text-slate-500 leading-tight">
              Reduce handover queue time leading into an activity
            </p>
          </button>

          <button
            type="button"
            onClick={() => setScenarioType("rework_reduction")}
            className={`p-3 rounded-xl border text-left transition-all ${
              scenarioType === "rework_reduction"
                ? "bg-indigo-600/10 border-indigo-500 shadow-sm shadow-indigo-500/10 text-white"
                : "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-bold">2. Rework Loops</span>
              <RotateCcw className="w-3.5 h-3.5 text-indigo-400" />
            </div>
            <p className="text-[11px] text-slate-500 leading-tight">
              Eliminate delays from repeated step re-executions
            </p>
          </button>

          <button
            type="button"
            onClick={() => setScenarioType("activity_duration_reduction")}
            className={`p-3 rounded-xl border text-left transition-all ${
              scenarioType === "activity_duration_reduction"
                ? "bg-indigo-600/10 border-indigo-500 shadow-sm shadow-indigo-500/10 text-white"
                : "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-bold">3. Step Duration</span>
              <Activity className="w-3.5 h-3.5 text-indigo-400" />
            </div>
            <p className="text-[11px] text-slate-500 leading-tight">
              Streamline execution and task processing time
            </p>
          </button>

          <button
            type="button"
            onClick={() => setScenarioType("resource_capacity")}
            className={`p-3 rounded-xl border text-left transition-all ${
              scenarioType === "resource_capacity"
                ? "bg-indigo-600/10 border-indigo-500 shadow-sm shadow-indigo-500/10 text-white"
                : "bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-bold">4. Resource Bandwidth</span>
              <Zap className="w-3.5 h-3.5 text-indigo-400" />
            </div>
            <p className="text-[11px] text-slate-500 leading-tight">
              Expand reviewer/worker staffing capacity
            </p>
          </button>
        </div>

        {/* Target and Slider Inputs */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
          {/* Target Activity or Resource Selection */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-300 block">
              {scenarioType === "resource_capacity" ? "Target Resource Pool" : "Target Process Activity"}
            </label>
            {scenarioType === "resource_capacity" ? (
              <select
                value={targetResource}
                onChange={(e) => setTargetResource(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-indigo-500 transition-colors"
              >
                <option value="all resources">All Resources (Process-Wide Bandwidth)</option>
                {baseline.resources.map((r) => (
                  <option key={r.resource} value={r.resource}>
                    {r.resource} ({r.event_count} events across {r.case_count} cases)
                  </option>
                ))}
              </select>
            ) : scenarioType === "rework_reduction" ? (
              <select
                value={targetActivity}
                onChange={(e) => setTargetActivity(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-indigo-500 transition-colors"
              >
                <option value="all">All Process Activities (Global Rework Elimination)</option>
                {baseline.activities.map((a) => (
                  <option key={a.activity} value={a.activity}>
                    {a.activity} ({a.rework_cases} cases with rework)
                  </option>
                ))}
              </select>
            ) : (
              <select
                value={targetActivity}
                onChange={(e) => setTargetActivity(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-white focus:outline-none focus:border-indigo-500 transition-colors"
              >
                {baseline.activities.map((a) => {
                  const isBn = baseline.primary_bottleneck?.activity === a.activity;
                  return (
                    <option key={a.activity} value={a.activity}>
                      {a.activity} {isBn ? "★ [Primary Bottleneck]" : ""} ({scenarioType === "bottleneck_wait_reduction" ? `${a.avg_wait_hours}h wait` : `${a.avg_duration_hours}h duration`})
                    </option>
                  );
                })}
              </select>
            )}
            <p className="text-[11px] text-slate-500">
              {scenarioType === "bottleneck_wait_reduction" && "Reduces the wait time leading directly into this activity."}
              {scenarioType === "rework_reduction" && "Reduces cycle time lost to repeated loops of this activity."}
              {scenarioType === "activity_duration_reduction" && "Reduces execution duration spent processing this step."}
              {scenarioType === "resource_capacity" && "Scales wait time inversely proportional to added capacity."}
            </p>
          </div>

          {/* Adjustment Slider */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300">
                {scenarioType === "resource_capacity" ? "Capacity Addition Percentage" : "Target Reduction Percentage"}
              </label>
              <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-indigo-400 bg-indigo-950/60 border border-indigo-800/80 px-2 py-0.5 rounded-lg">
                <span>{scenarioType === "resource_capacity" ? `+${reductionPct}%` : `-${reductionPct}%`}</span>
              </div>
            </div>

            <div className="flex items-center gap-4 pt-1">
              <input
                type="range"
                min="5"
                max="90"
                step="5"
                value={reductionPct}
                onChange={(e) => setReductionPct(parseInt(e.target.value, 10))}
                className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />
              <input
                type="number"
                min="1"
                max="100"
                value={reductionPct}
                onChange={(e) => {
                  const val = parseInt(e.target.value, 10);
                  if (!isNaN(val)) setReductionPct(Math.min(100, Math.max(1, val)));
                }}
                className="w-16 bg-slate-950 border border-slate-800 rounded-xl px-2 py-1.5 text-xs text-center font-mono text-white focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex justify-between text-[10px] text-slate-500 font-mono">
              <span>5% (Conservative)</span>
              <span>30% (Standard)</span>
              <span>50% (Substantial)</span>
              <span>90% (Radical)</span>
            </div>
          </div>
        </div>

        {/* Error message */}
        {simulationError && (
          <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-800/80 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{simulationError}</span>
          </div>
        )}

        {/* Run Button */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={() => handleRunSimulation()}
            disabled={isSimulating}
            className="px-5 py-2.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/25 flex items-center gap-2 transition-all disabled:opacity-50"
          >
            {isSimulating ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Simulating Scenario...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5 text-indigo-200" />
                <span>Run What-If Simulation</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      </div>

      {/* Active Simulation Result Banner */}
      {activeResult && (
        <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-2xl backdrop-blur-md space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-200">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                <CheckCircle2 className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
                  {activeResult.scenario.title}
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-mono font-semibold">
                    Simulated Result
                  </span>
                </h4>
                <p className="text-xs text-slate-400">{activeResult.scenario.assumptions}</p>
              </div>
            </div>
          </div>

          {/* 3 Hero Comparison Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Current Baseline */}
            <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4">
              <span className="text-slate-400 text-xs block font-medium">Observed Baseline</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-3xl font-bold font-mono text-white">
                  {activeResult.baseline.avg_cycle_time_hours.toFixed(2)}h
                </span>
                <span className="text-xs text-slate-500 font-mono">avg cycle</span>
              </div>
              <span className="text-[11px] text-slate-500 block mt-1">
                Median: {activeResult.baseline.median_cycle_time_hours.toFixed(2)}h
              </span>
            </div>

            {/* Simulated Outcome */}
            <div className="bg-slate-950/80 border border-indigo-500/40 rounded-xl p-4 shadow-sm shadow-indigo-500/10">
              <span className="text-indigo-400 text-xs block font-medium">Simulated Outcome</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-3xl font-bold font-mono text-indigo-200">
                  {activeResult.simulated.avg_cycle_time_hours.toFixed(2)}h
                </span>
                <span className="text-xs text-indigo-400/80 font-mono">avg cycle</span>
              </div>
              <span className="text-[11px] text-slate-400 block mt-1">
                Simulated Median: {activeResult.simulated.median_cycle_time_hours.toFixed(2)}h
              </span>
            </div>

            {/* Estimated Improvement */}
            <div className="bg-slate-950/80 border border-emerald-500/40 rounded-xl p-4 shadow-sm shadow-emerald-500/10">
              <span className="text-emerald-400 text-xs block font-medium">Estimated Improvement</span>
              <div className="flex items-baseline gap-2 mt-1">
                <span className="text-3xl font-bold font-mono text-emerald-400">
                  {activeResult.impact.cycle_time_improvement_pct.toFixed(1)}%
                </span>
                <span className="text-xs text-emerald-300/80 font-mono">faster</span>
              </div>
              <span className="text-[11px] text-emerald-400/80 block mt-1">
                -{activeResult.impact.absolute_reduction_hours.toFixed(2)} hours saved per case
              </span>
            </div>
          </div>

          {/* Component Change Summary */}
          <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
            <div>
              <span className="text-slate-400 block text-[10px] uppercase tracking-wider font-sans font-semibold mb-0.5">
                Targeted Metric ({activeResult.baseline.component_name})
              </span>
              <div className="flex items-center gap-2 font-bold text-white">
                <span>{activeResult.baseline.component_value.toFixed(2)}h</span>
                <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
                <span className="text-emerald-400">{activeResult.simulated.component_value.toFixed(2)}h</span>
                <span className="text-[11px] px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 font-sans">
                  -{activeResult.impact.component_reduction_hours.toFixed(2)}h (-{activeResult.impact.component_reduction_pct.toFixed(1)}%)
                </span>
              </div>
            </div>

            <div>
              <span className="text-slate-400 block text-[10px] uppercase tracking-wider font-sans font-semibold mb-0.5">
                Process Coverage
              </span>
              <span className="text-slate-200">
                {activeResult.simulated.affected_cases_count} of {activeResult.baseline.case_count} cases affected ({activeResult.simulated.affected_cases_pct.toFixed(1)}%)
              </span>
            </div>
          </div>

          {/* Plain English Synthesis */}
          <div className="p-4 rounded-xl bg-indigo-950/20 border border-indigo-500/20 text-xs text-slate-300 leading-relaxed space-y-2">
            <div className="flex items-center gap-1.5 font-bold text-white text-[11px] uppercase tracking-wider">
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              <span>Operational Interpretation</span>
            </div>
            <p>{activeResult.explanation}</p>
          </div>

          {/* Calculation Basis Accordion */}
          <div>
            <button
              type="button"
              onClick={() => setShowBasisDetails((prev) => !prev)}
              className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1.5 font-semibold transition-colors"
            >
              <ChevronRight className={`w-3.5 h-3.5 transition-transform ${showBasisDetails ? "rotate-90" : ""}`} />
              <span>{showBasisDetails ? "Hide Mathematical Calculation Basis" : "Show Mathematical Calculation Basis"}</span>
            </button>

            {showBasisDetails && (
              <div className="mt-3 p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-xs font-mono text-slate-300">
                <span className="text-[10px] text-slate-500 uppercase tracking-wider font-sans block mb-1">
                  Deterministic Step-by-Step Proof:
                </span>
                <ul className="space-y-1.5 list-disc list-inside text-[11px] text-slate-400">
                  {activeResult.scenario.calculation_basis.map((step, idx) => (
                    <li key={idx}>
                      <span className="text-slate-300">{step}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Multi-Scenario Stacking Comparison Table */}
      {history.length > 0 && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-400" />
                Scenario Comparison Matrix
              </h3>
              <p className="text-xs text-slate-400">
                Contrast simulated operational outcomes across different levers tested in this session
              </p>
            </div>
            <button
              type="button"
              onClick={() => setHistory([])}
              className="text-[11px] text-slate-400 hover:text-slate-200 transition-colors"
            >
              Clear Matrix
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300 border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Scenario Intervention</th>
                  <th className="py-3 px-4">Target Activity / Resource</th>
                  <th className="py-3 px-4">Adjustment</th>
                  <th className="py-3 px-4">Simulated Cycle Time</th>
                  <th className="py-3 px-4">Avg Hours Saved</th>
                  <th className="py-3 px-4 text-right">Estimated Improvement</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {/* Baseline Row */}
                <tr className="bg-slate-950/40 text-slate-400">
                  <td className="py-3 px-4 font-sans font-bold text-white">Baseline (Observed Reality)</td>
                  <td className="py-3 px-4 font-sans text-slate-400">—</td>
                  <td className="py-3 px-4">—</td>
                  <td className="py-3 px-4 font-bold text-white">{baseline.avg_cycle_time_hours.toFixed(2)}h</td>
                  <td className="py-3 px-4">—</td>
                  <td className="py-3 px-4 text-right font-sans">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-800 text-slate-400">
                      Baseline
                    </span>
                  </td>
                </tr>

                {/* Scenario Rows */}
                {history.map((h) => (
                  <tr key={h.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-sans font-semibold text-slate-200">{h.title}</td>
                    <td className="py-3 px-4 font-sans text-indigo-300">{h.target}</td>
                    <td className="py-3 px-4 font-bold text-indigo-400">
                      {h.scenario_type === "resource_capacity" ? `+${h.adjustment_pct}%` : `-${h.adjustment_pct}%`}
                    </td>
                    <td className="py-3 px-4 font-bold text-white">{h.simulated_cycle_time.toFixed(2)}h</td>
                    <td className="py-3 px-4 text-emerald-400">-{h.hours_saved.toFixed(2)}h</td>
                    <td className="py-3 px-4 text-right font-sans">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        +{h.improvement_pct.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
