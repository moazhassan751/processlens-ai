"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ArrowRight,
  Search,
  Filter,
  Layers,
  Sparkles,
  RefreshCw,
  X,
  HelpCircle,
  TrendingDown,
  Activity,
  ChevronRight,
  GitBranch,
} from "lucide-react";

export interface AlignmentMove {
  log: string;
  model: string;
  type: "sync" | "log_move" | "model_move";
  category?: string;
}

export interface CaseDeviation {
  case_id: string;
  is_conforming: boolean;
  fitness: number;
  observed_path: string[];
  expected_path: string[];
  mismatch_count: number;
  deviation_types: string[];
  affected_activities: string[];
  affected_transitions: string[];
  alignment_moves: AlignmentMove[];
  explanation: string;
}

export interface TopDeviation {
  pattern: string;
  deviation_type: string;
  affected_cases: number;
  affected_pct: number;
  affected_activities: string[];
  affected_transitions: string[];
  description: string;
}

export interface VariantInfo {
  variant_id: string;
  activities: string[];
  activity_sequence: string;
  case_count: number;
  percentage: number;
  rank: number;
  is_default: boolean;
}

export interface ConformanceData {
  available: boolean;
  error?: string;
  fallback?: boolean;
  warning?: string;
  reference_process: string[];
  reference_variant_id?: string;
  summary: {
    total_cases: number;
    conforming_cases: number;
    deviating_cases: number;
    conformance_rate_pct: number;
    average_trace_fitness: number;
    log_fitness: number;
  };
  top_deviations: TopDeviation[];
  case_deviations: CaseDeviation[];
  transition_deviations: Record<string, number>;
}

interface ConformancePanelProps {
  apiBaseUrl?: string;
  activeProject?: string;
  projectId?: string;
  onRefresh?: () => void;
  onRunPhase1?: () => void;
}

export const ConformancePanel: React.FC<ConformancePanelProps> = ({
  apiBaseUrl = "http://localhost:8000",
  activeProject = "default",
  projectId,
  onRefresh,
  onRunPhase1,
}) => {
  const currentProject = projectId || activeProject;
  const [data, setData] = useState<ConformanceData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Variant Selection State (Phase H7)
  const [variants, setVariants] = useState<VariantInfo[]>([]);
  const [selectedVariantId, setSelectedVariantId] = useState<string>("");
  const [loadingVariants, setLoadingVariants] = useState<boolean>(false);

  // Filter & Search
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [filterType, setFilterType] = useState<"all" | "deviating" | "conforming">("deviating");

  // Case Inspection Modal
  const [inspectedCase, setInspectedCase] = useState<CaseDeviation | null>(null);
  const [showHelp, setShowHelp] = useState<boolean>(false);

  const fetchVariants = useCallback(async () => {
    setLoadingVariants(true);
    try {
      const res = await fetch(`${apiBaseUrl}/api/conformance/variants?project_id=${encodeURIComponent(currentProject)}`);
      if (res.ok) {
        const json = await res.json();
        if (json.available && Array.isArray(json.variants)) {
          setVariants(json.variants);
          if (json.default_variant_id && !selectedVariantId) {
            setSelectedVariantId(json.default_variant_id);
          }
        }
      }
    } catch (err) {
      console.error("Failed to load variants:", err);
    } finally {
      setLoadingVariants(false);
    }
  }, [apiBaseUrl, currentProject]);

  const fetchConformance = useCallback(async (customVariantId?: string) => {
    setLoading(true);
    setError(null);
    try {
      const activeVar = customVariantId !== undefined ? customVariantId : selectedVariantId;
      const varQuery = activeVar ? `&reference_variant=${encodeURIComponent(activeVar)}` : "";
      const res = await fetch(`${apiBaseUrl}/api/conformance?project_id=${encodeURIComponent(currentProject)}${varQuery}`);
      if (res.status === 202) {
        const body = await res.json();
        setData(body);
        setLoading(false);
        return;
      }

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || errBody.error || `HTTP ${res.status}: Failed to load conformance`);
      }

      const json = await res.json();
      setData(json);
      if (json.reference_variant_id && !selectedVariantId) {
        setSelectedVariantId(json.reference_variant_id);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load conformance results.");
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, currentProject, selectedVariantId]);

  useEffect(() => {
    fetchVariants();
    fetchConformance();
  }, [fetchVariants, fetchConformance]);

  const handleVariantChange = (newVarId: string) => {
    setSelectedVariantId(newVarId);
    fetchConformance(newVarId);
  };

  // Filtered cases
  const filteredCases = useMemo(() => {
    if (!data?.case_deviations) return [];
    return data.case_deviations.filter((c) => {
      // Type filter
      if (filterType === "deviating" && c.is_conforming) return false;
      if (filterType === "conforming" && !c.is_conforming) return false;

      // Search term
      if (!searchTerm) return true;
      const lower = searchTerm.toLowerCase();
      if (c.case_id.toLowerCase().includes(lower)) return true;
      if (c.observed_path.some((a) => a.toLowerCase().includes(lower))) return true;
      if (c.deviation_types.some((d) => d.toLowerCase().includes(lower))) return true;
      return false;
    });
  }, [data, filterType, searchTerm]);

  // Loading Skeleton
  if (loading && !data) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 h-24 space-y-2">
              <div className="w-20 h-3 bg-slate-800 rounded" />
              <div className="w-16 h-6 bg-slate-700 rounded" />
              <div className="w-24 h-2.5 bg-slate-800/80 rounded" />
            </div>
          ))}
        </div>
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 h-48 space-y-4">
          <div className="w-48 h-4 bg-slate-800 rounded" />
          <div className="space-y-3 pt-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 rounded-xl bg-slate-950/60 border border-slate-800/80" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Not available / Empty state
  if (!data?.available) {
    return (
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-12 text-center shadow-xl max-w-lg mx-auto space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-slate-950 border border-slate-800 flex items-center justify-center text-indigo-400 mx-auto shadow-inner">
          <ShieldAlert className="w-6 h-6" />
        </div>
        <div>
          <h3 className="text-base font-bold text-white mb-1">
            Conformance Analysis Not Yet Available
          </h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto leading-relaxed">
            Run Phase 1 (Process Discovery) to reconstruct the normative reference model and evaluate observed cases for deviations.
          </p>
        </div>
        {error && (
          <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-xs text-left font-mono">
            {error}
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
            onClick={() => fetchConformance()}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300 transition-colors"
          >
            Retry Loading
          </button>
        </div>
      </div>
    );
  }

  const { summary, reference_process, top_deviations } = data;

  return (
    <div className="space-y-6">
      {/* Fallback Warning Banner */}
      {data.fallback && (
        <div
          id="conformance-fallback-warning"
          data-testid="fallback-warning-banner"
          className="p-4 rounded-xl bg-amber-950/40 border border-amber-500/50 text-amber-200 text-xs flex items-center justify-between gap-3 shadow-lg animate-in fade-in duration-200"
        >
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <div>
              <span className="font-bold text-amber-100">Showing fallback data, not this run's own output.</span>
              <span className="text-amber-300/80 ml-2">
                {data.warning || "The requested run-specific artifact was unavailable and the system is displaying legacy fallback data."}
              </span>
            </div>
          </div>
          <span className="px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/30">
            Fallback Active
          </span>
        </div>
      )}

      {/* KPI Cards Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <div className="flex items-center justify-between mb-1">
            <span className="text-slate-400 text-xs block font-medium">Conformance Rate</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-mono font-semibold">
              Alignments
            </span>
          </div>
          <span className={`text-2xl font-bold font-mono ${
            summary.conformance_rate_pct >= 80 ? "text-emerald-400" : summary.conformance_rate_pct >= 60 ? "text-amber-400" : "text-rose-400"
          }`}>
            {summary.conformance_rate_pct.toFixed(1)}%
          </span>
          <span className="text-[11px] text-slate-500 block mt-1">
            {summary.conforming_cases} of {summary.total_cases} cases compliant
          </span>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <span className="text-slate-400 text-xs block font-medium">Cases Evaluated</span>
          <span className="text-2xl font-bold font-mono text-white">
            {summary.total_cases.toLocaleString()}
          </span>
          <span className="text-[11px] text-slate-500 block mt-1">
            Deterministic token replay
          </span>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <span className="text-slate-400 text-xs block font-medium">Conforming Cases</span>
          <span className="text-2xl font-bold font-mono text-emerald-400">
            {summary.conforming_cases.toLocaleString()}
          </span>
          <span className="text-[11px] text-slate-500 block mt-1">
            Exact match to reference
          </span>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <span className="text-slate-400 text-xs block font-medium">Deviating Cases</span>
          <span className="text-2xl font-bold font-mono text-rose-400">
            {summary.deviating_cases.toLocaleString()}
          </span>
          <span className="text-[11px] text-slate-500 block mt-1">
            {((summary.deviating_cases / Math.max(summary.total_cases, 1)) * 100).toFixed(1)}% deviation rate
          </span>
        </div>

        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-lg">
          <span className="text-slate-400 text-xs block font-medium">Average Trace Fitness</span>
          <span className="text-2xl font-bold font-mono text-cyan-400">
            {summary.average_trace_fitness.toFixed(3)}
          </span>
          <span className="text-[11px] text-slate-500 block mt-1">
            Log Fitness: {summary.log_fitness.toFixed(3)}
          </span>
        </div>
      </div>

      {/* Normative Reference Model Banner */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl backdrop-blur-md">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                  Normative Reference Model (Benchmark Happy Path)
                </h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-emerald-500/10 border border-emerald-500/30 text-emerald-300">
                  Standard Procedure
                </span>
                <button
                  type="button"
                  onClick={() => setShowHelp(!showHelp)}
                  className="text-slate-400 hover:text-indigo-300 transition-colors"
                  title="Explain Process Conformance Checking"
                >
                  <HelpCircle className="w-3.5 h-3.5" />
                </button>
              </div>
              <p className="text-[11px] text-slate-400">
                All cases are deterministically compared against this intended sequence to detect skips, insertions, and rework loops
              </p>
            </div>
          </div>
        </div>

        {/* User-Selectable Reference Variant Dropdown (Phase H7) */}
        {variants.length > 0 && (
          <div className="mb-4 p-3 bg-slate-950/60 rounded-xl border border-slate-800 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-indigo-400 shrink-0" />
              <span className="text-xs font-semibold text-slate-200">Reference Process Variant:</span>
              <span className="text-[11px] text-slate-400 font-mono">({variants.length} discovered)</span>
            </div>
            <div className="flex items-center gap-2">
              <select
                id="conformance-reference-variant-select"
                value={selectedVariantId}
                onChange={(e) => handleVariantChange(e.target.value)}
                disabled={loading}
                className="bg-slate-900 border border-slate-700 text-xs text-slate-100 rounded-lg px-3 py-1.5 focus:ring-1 focus:ring-indigo-500 font-medium cursor-pointer"
              >
                {variants.map((v) => (
                  <option key={v.variant_id} value={v.variant_id}>
                    Variant #{v.rank}: {v.activity_sequence} ({v.case_count} cases · {v.percentage}%){v.is_default ? " ★ Default" : ""}
                  </option>
                ))}
              </select>
              {loading && <RefreshCw className="w-3.5 h-3.5 text-indigo-400 animate-spin shrink-0" />}
            </div>
          </div>
        )}

        {showHelp && (
          <div className="mb-4 p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 space-y-1.5 leading-relaxed animate-in fade-in duration-200">
            <p className="font-semibold text-white">How ProcessLens Measures Conformance:</p>
            <p>
              1. <strong>Normative Reference:</strong> Automatically identified as the clean dominant variant ({reference_process.join(" → ")}).
            </p>
            <p>
              2. <strong>Mathematical Alignments:</strong> Uses PM4Py A* optimal trace alignment to find the minimal edit distance between what actually happened in each case and the expected model.
            </p>
            <p>
              3. <strong>Classification:</strong> Every mismatch is categorized as a <em>Rework Loop</em> (activity repeated), <em>Unplanned Activity</em> (unauthorized insertion), or <em>Skipped Activity</em> (omission). Zero hallucination.
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 p-3 bg-slate-950/80 rounded-xl border border-slate-800">
          {reference_process.map((activity, idx) => (
            <React.Fragment key={idx}>
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs font-semibold text-slate-200 shadow-inner">
                <span className="w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px] flex items-center justify-center font-mono">
                  {idx + 1}
                </span>
                <span>{activity}</span>
              </div>
              {idx < reference_process.length - 1 && (
                <ArrowRight className="w-3.5 h-3.5 text-slate-600 shrink-0" />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Top Deviations Table */}
      {top_deviations && top_deviations.length > 0 && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Discovered Process Deviations & Patterns
              </h3>
              <p className="text-xs text-slate-400">
                Most frequent structural deviations and rework transitions observed in the dataset
              </p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300 border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Deviation Pattern / Transition</th>
                  <th className="py-3 px-4">Classification</th>
                  <th className="py-3 px-4">Affected Activities</th>
                  <th className="py-3 px-4 text-right">Case Volume & Share</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {top_deviations.map((td, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-sans font-semibold text-white max-w-md">
                      <div className="font-mono text-xs text-amber-300 break-words">
                        {td.pattern}
                      </div>
                      <div className="text-[11px] text-slate-400 font-sans mt-0.5">
                        {td.description}
                      </div>
                    </td>
                    <td className="py-3 px-4 font-sans">
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                        td.deviation_type === "Rework Loop"
                          ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                          : td.deviation_type === "Skipped Activity"
                          ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                          : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                      }`}>
                        {td.deviation_type}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-sans text-slate-300">
                      <div className="flex flex-wrap gap-1">
                        {td.affected_activities.map((a, i) => (
                          <span key={i} className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] text-slate-300 font-mono">
                            {a}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right font-sans">
                      <span className="font-bold text-white font-mono text-sm">
                        {td.affected_cases} cases
                      </span>
                      <span className="text-slate-500 text-xs ml-1.5 font-mono">
                        ({td.affected_pct}%)
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Case-by-Case Conformance & Deviation Inspection Table */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-indigo-400" />
              Trace-Level Case Conformance Audit
            </h3>
            <p className="text-xs text-slate-400">
              Deterministic case compliance scores and alignment traces. Click <strong>Inspect Alignment</strong> for move-by-move verification.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search Case ID or activity..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="bg-slate-950 border border-slate-700 text-xs text-slate-200 pl-8 pr-3 py-1.5 rounded-lg focus:outline-none focus:border-indigo-500 w-52 shadow-inner"
              />
            </div>

            {/* Filter Buttons */}
            <div className="flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5 text-xs">
              <button
                onClick={() => setFilterType("deviating")}
                className={`px-3 py-1 rounded-md font-semibold transition-all ${
                  filterType === "deviating"
                    ? "bg-rose-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Deviating ({summary.deviating_cases})
              </button>
              <button
                onClick={() => setFilterType("conforming")}
                className={`px-3 py-1 rounded-md font-semibold transition-all ${
                  filterType === "conforming"
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Conforming ({summary.conforming_cases})
              </button>
              <button
                onClick={() => setFilterType("all")}
                className={`px-3 py-1 rounded-md font-semibold transition-all ${
                  filterType === "all"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                All ({summary.total_cases})
              </button>
            </div>
          </div>
        </div>

        {/* Cases Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-300 border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 text-[11px] font-semibold uppercase tracking-wider">
                <th className="py-3 px-4">Case ID</th>
                <th className="py-3 px-4">Trace Fitness</th>
                <th className="py-3 px-4">Observed Execution Sequence</th>
                <th className="py-3 px-4">Detected Deviations</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Alignment Analysis</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {filteredCases.length > 0 ? (
                filteredCases.slice(0, 50).map((c) => (
                  <tr key={c.case_id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-bold text-white">
                      {c.case_id}
                    </td>
                    <td className="py-3 px-4 font-bold">
                      <span className={c.fitness >= 0.999 ? "text-emerald-400" : c.fitness >= 0.7 ? "text-amber-400" : "text-rose-400"}>
                        {(c.fitness * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-3 px-4 font-sans max-w-sm">
                      <div className="font-mono text-[11px] text-slate-300 truncate" title={c.observed_path.join(" → ")}>
                        {c.observed_path.join(" → ")}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">
                        {c.observed_path.length} steps executed
                      </div>
                    </td>
                    <td className="py-3 px-4 font-sans">
                      {c.deviation_types.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {c.deviation_types.map((t, idx) => (
                            <span
                              key={idx}
                              className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                                t === "Rework Loop"
                                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                  : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                              }`}
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-slate-500 text-[11px]">None (Zero Mismatches)</span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-sans">
                      <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                        c.is_conforming
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                      }`}>
                        {c.is_conforming ? "Conforming" : "Deviating"}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-sans">
                      <button
                        type="button"
                        onClick={() => setInspectedCase(c)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-indigo-600 hover:text-white text-slate-200 transition-colors"
                      >
                        <span>Inspect Alignment</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-500 font-sans text-xs">
                    No cases match the selected filter or search term.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {filteredCases.length > 50 && (
          <div className="text-center text-slate-500 text-xs py-2">
            Showing first 50 of {filteredCases.length} filtered cases.
          </div>
        )}
      </div>

      {/* Case Alignment Inspection Modal */}
      {inspectedCase && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 w-full max-w-2xl shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-xl text-white ${
                  inspectedCase.is_conforming ? "bg-emerald-600" : "bg-rose-600"
                }`}>
                  {inspectedCase.is_conforming ? (
                    <CheckCircle2 className="w-5 h-5" />
                  ) : (
                    <AlertTriangle className="w-5 h-5" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-white tracking-tight">
                      Trace Alignment: {inspectedCase.case_id}
                    </h3>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                      inspectedCase.is_conforming
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                        : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                    }`}>
                      Fitness: {(inspectedCase.fitness * 100).toFixed(1)}%
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">
                    Step-by-step mathematical alignment between observed log and expected model
                  </p>
                </div>
              </div>

              <button
                onClick={() => setInspectedCase(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Explanation Synthesis */}
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-200 leading-relaxed font-sans">
              <span className="font-semibold text-indigo-400 block mb-1">Deterministic Assessment:</span>
              {inspectedCase.explanation}
            </div>

            {/* Step-by-Step Alignment Matrix */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-indigo-400" />
                A* Alignment Move Sequence
              </h4>

              <div className="border border-slate-800 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 text-[10px] uppercase tracking-wider">
                      <th className="py-2.5 px-3">Step #</th>
                      <th className="py-2.5 px-3">Observed Event (Log)</th>
                      <th className="py-2.5 px-3">Expected Event (Model)</th>
                      <th className="py-2.5 px-3 text-right">Move Evaluation</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 bg-slate-900/60">
                    {inspectedCase.alignment_moves.map((m, idx) => (
                      <tr key={idx} className={m.type !== "sync" ? "bg-rose-950/20" : ""}>
                        <td className="py-2 px-3 text-slate-500">#{idx + 1}</td>
                        <td className="py-2 px-3">
                          {m.log !== ">>" ? (
                            <span className="text-slate-200 font-semibold">{m.log}</span>
                          ) : (
                            <span className="text-rose-400 font-bold italic">&gt;&gt; (Skipped)</span>
                          )}
                        </td>
                        <td className="py-2 px-3">
                          {m.model !== ">>" ? (
                            <span className="text-slate-200">{m.model}</span>
                          ) : (
                            <span className="text-amber-400 font-bold italic">&gt;&gt; (Unplanned)</span>
                          )}
                        </td>
                        <td className="py-2 px-3 text-right font-sans">
                          {m.type === "sync" ? (
                            <span className="inline-flex items-center gap-1 text-emerald-400 text-[11px] font-semibold">
                              <CheckCircle2 className="w-3.5 h-3.5" />
                              <span>Synchronous</span>
                            </span>
                          ) : m.type === "log_move" ? (
                            <span className="inline-flex items-center gap-1 text-amber-400 text-[11px] font-bold uppercase">
                              <AlertTriangle className="w-3.5 h-3.5" />
                              <span>{m.category || "Log Insertion"}</span>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-rose-400 text-[11px] font-bold uppercase">
                              <X className="w-3.5 h-3.5" />
                              <span>Model Omission</span>
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Close Button */}
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setInspectedCase(null)}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
              >
                Close Inspection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
