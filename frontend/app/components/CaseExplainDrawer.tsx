"use client";

import React, { useState, useEffect } from "react";
import { 
  Sparkles, 
  X, 
  AlertTriangle, 
  CheckCircle2, 
  Clock, 
  ShieldAlert, 
  Cpu, 
  Database, 
  ArrowRight,
  Loader2,
  HelpCircle,
  Lightbulb,
  Zap,
} from "lucide-react";
import { MarkdownRenderer } from "./MarkdownRenderer";

export interface PrescriptiveAction {
  action_title: string;
  action_category: string;
  current_risk: number;
  projected_risk: number;
  risk_reduction_pct: number;
  feasibility: string;
  guidance: string;
}

interface CaseExplanationResponse {
  case_id: string;
  risk_level: string;
  risk_score: number;
  anomaly: boolean;
  explanation: {
    summary: string;
    evidence: string[];
    what_to_do?: string;
    how_to_prevent?: string;
    recommendation: string;
  };
  prescriptive_action?: PrescriptiveAction;
  source: string;
  cached: boolean;
}

interface CaseExplainDrawerProps {
  caseId: string | null;
  isOpen: boolean;
  onClose: () => void;
  apiBaseUrl?: string;
}

export const CaseExplainDrawer: React.FC<CaseExplainDrawerProps> = ({
  caseId,
  isOpen,
  onClose,
  apiBaseUrl = "http://localhost:8000",
}) => {
  const [data, setData] = useState<CaseExplanationResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!caseId || !isOpen) {
      setData(null);
      setError(null);
      return;
    }

    const fetchExplanation = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${apiBaseUrl}/api/explain/case/${encodeURIComponent(caseId)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.error || `HTTP ${res.status}: Failed to explain case`);
        }

        const result: CaseExplanationResponse = await res.json();
        setData(result);
      } catch (err: any) {
        setError(err.message || "Failed to generate explanation");
      } finally {
        setLoading(false);
      }
    };

    fetchExplanation();
  }, [caseId, isOpen, apiBaseUrl]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div 
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-lg bg-slate-950 border-l border-slate-800 shadow-2xl flex flex-col">
          {/* Header */}
          <div className="p-6 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 text-white shadow-lg shadow-indigo-600/30">
                <Sparkles className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-white tracking-tight">
                    Case Intelligence
                  </h2>
                  {caseId && (
                    <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                      {caseId}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400">
                  Targeted Root-Cause Diagnosis & Action Recommendation
                </p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content Area */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {loading ? (
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 animate-pulse flex items-center justify-between">
                  <div className="space-y-2">
                    <div className="w-24 h-3 rounded bg-slate-800" />
                    <div className="w-36 h-6 rounded bg-slate-700" />
                  </div>
                  <div className="w-16 h-8 rounded bg-slate-800" />
                </div>

                <div className="space-y-2">
                  <div className="w-28 h-3 rounded bg-slate-800 animate-pulse" />
                  <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-2 animate-pulse">
                    <div className="w-full h-3 rounded bg-slate-800" />
                    <div className="w-5/6 h-3 rounded bg-slate-800" />
                    <div className="w-2/3 h-3 rounded bg-slate-800" />
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="w-32 h-3 rounded bg-slate-800 animate-pulse" />
                  <div className="space-y-2">
                    <div className="p-3 rounded-xl bg-slate-900/50 border border-slate-800/80 animate-pulse h-11" />
                    <div className="p-3 rounded-xl bg-slate-900/50 border border-slate-800/80 animate-pulse h-11" />
                    <div className="p-3 rounded-xl bg-slate-900/50 border border-slate-800/80 animate-pulse h-11" />
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800 animate-pulse h-20" />
              </div>
            ) : error ? (
              <div className="p-5 rounded-2xl bg-rose-950/30 border border-rose-800/60 text-rose-300 text-xs space-y-3">
                <div className="flex items-center gap-2 font-bold text-sm text-rose-200">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                  Unable to Generate Case Explanation
                </div>
                <p className="text-xs text-rose-200/90 leading-relaxed break-words">{error}</p>
                <button
                  type="button"
                  onClick={() => {
                    // re-trigger fetch
                    if (caseId) {
                      setLoading(true);
                      setError(null);
                      fetch(`${apiBaseUrl}/api/explain/case/${encodeURIComponent(caseId)}`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                      })
                        .then((res) => {
                          if (!res.ok) throw new Error(`HTTP ${res.status}`);
                          return res.json();
                        })
                        .then(setData)
                        .catch((err) => setError(err.message || "Failed to load explanation"))
                        .finally(() => setLoading(false));
                    }
                  }}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 border border-rose-500/30 transition-colors"
                >
                  Retry Analysis
                </button>
              </div>
            ) : data ? (
              <>
                {/* Risk Level Banner */}
                <div
                  className={`p-4 rounded-xl border flex items-center justify-between gap-4 ${
                    data.risk_level === "HIGH"
                      ? "bg-rose-950/30 border-rose-500/40 text-rose-300"
                      : data.risk_level === "MEDIUM"
                      ? "bg-amber-950/30 border-amber-500/40 text-amber-300"
                      : "bg-emerald-950/30 border-emerald-500/40 text-emerald-300"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    {data.risk_level === "HIGH" ? (
                      <ShieldAlert className="w-6 h-6 text-rose-400 shrink-0" />
                    ) : (
                      <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" />
                    )}
                    <div>
                      <span className="text-xs font-semibold uppercase tracking-wider block">
                        Assessed Risk Classification
                      </span>
                      <span className="text-lg font-bold text-white">
                        {data.risk_level} RISK
                      </span>
                    </div>
                  </div>

                  <div className="text-right">
                    <span className="text-xs text-slate-400 block">Delay Probability</span>
                    <span className="text-lg font-bold font-mono text-white">
                      {(data.risk_score * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Engine Source & Cache Badge */}
                <div className="flex flex-wrap items-center justify-between gap-2 p-3 rounded-lg bg-slate-900 border border-slate-800 text-xs">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-indigo-400" />
                    <span className="text-slate-400">Diagnosis Provider:</span>
                    <span className="font-semibold text-slate-200 uppercase text-[11px] px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/30 text-indigo-300">
                      {data.source === "llm" ? "AI Model (Groq / Gemini)" : "Deterministic Rule Engine"}
                    </span>
                  </div>

                  {data.cached && (
                    <div className="flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30">
                      <Database className="w-3 h-3" />
                      <span>Cached Response</span>
                    </div>
                  )}
                </div>

                {/* Anomaly Callout if applicable */}
                {data.anomaly && (
                  <div className="p-3 rounded-lg bg-purple-950/30 border border-purple-500/30 text-purple-300 text-xs flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-purple-400 shrink-0" />
                    <span>
                      <strong>Isolation Forest Anomaly:</strong> This case exhibits unusual sequence duration or irregular resource patterns.
                    </span>
                  </div>
                )}

                {/* Executive Summary */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                    Executive Summary
                  </h3>
                  <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 text-xs text-slate-200 leading-relaxed shadow-md">
                    <MarkdownRenderer content={data.explanation.summary} />
                  </div>
                </div>

                {/* Structured Evidence Points */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-cyan-400" />
                    Diagnostic Evidence
                  </h3>
                  <div className="space-y-2">
                    {data.explanation.evidence.map((point, index) => (
                      <div
                        key={index}
                        className="p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 flex items-start gap-2.5 text-xs text-slate-300"
                      >
                        <ArrowRight className="w-3.5 h-3.5 text-indigo-400 shrink-0 mt-0.5" />
                        <span>{point}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Prescriptive Next-Best-Action (Simulated Counterfactual) */}
                {data.prescriptive_action && data.prescriptive_action.action_title !== "Awaiting Milestone" && (
                  <div className="space-y-2">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                      <Zap className="w-3.5 h-3.5 text-amber-400" />
                      Prescriptive Next-Best-Action (Simulated Counterfactual)
                    </h3>
                    <div className="p-4 rounded-xl bg-gradient-to-br from-indigo-950/60 to-slate-900 border border-indigo-500/40 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-amber-500/20 text-amber-300 border border-amber-500/30">
                            {data.prescriptive_action.action_category}
                          </span>
                          <span className="font-bold text-sm text-white">
                            {data.prescriptive_action.action_title}
                          </span>
                        </div>
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                          Feasibility: {data.prescriptive_action.feasibility}
                        </span>
                      </div>

                      {data.prescriptive_action.risk_reduction_pct > 0 && (
                        <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 flex items-center justify-between">
                          <div className="text-center">
                            <span className="text-[10px] uppercase text-slate-400 block font-mono">Current Risk</span>
                            <span className="text-base font-bold font-mono text-rose-400">
                              {(data.prescriptive_action.current_risk * 100).toFixed(1)}%
                            </span>
                          </div>
                          <div className="flex flex-col items-center">
                            <span className="text-[10px] font-mono text-emerald-400 font-bold">
                              -{data.prescriptive_action.risk_reduction_pct}% Risk
                            </span>
                            <ArrowRight className="w-4 h-4 text-emerald-400 my-0.5" />
                          </div>
                          <div className="text-center">
                            <span className="text-[10px] uppercase text-slate-400 block font-mono">Projected Risk</span>
                            <span className="text-base font-bold font-mono text-emerald-400">
                              {(data.prescriptive_action.projected_risk * 100).toFixed(1)}%
                            </span>
                          </div>
                        </div>
                      )}

                      <p className="text-xs text-indigo-200/90 leading-relaxed font-sans">
                        {data.prescriptive_action.guidance}
                      </p>
                    </div>
                  </div>
                )}

                {/* What To Do: Immediate Remediation */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                    <Zap className="w-3.5 h-3.5 text-amber-400" />
                    What To Do (Immediate Tactical Remediation)
                  </h3>
                  <div className="p-4 rounded-xl bg-gradient-to-br from-amber-950/20 to-slate-900/90 border border-amber-500/30 text-xs text-amber-100/90 leading-relaxed shadow-lg">
                    <MarkdownRenderer
                      content={
                        data.explanation.what_to_do ||
                        data.explanation.recommendation ||
                        "Prioritize this case for immediate review."
                      }
                      accentColor="amber"
                    />
                  </div>
                </div>

                {/* How To Prevent: Root-Cause Prevention & Controls */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    How To Prevent (Systemic Process Controls)
                  </h3>
                  <div className="p-4 rounded-xl bg-gradient-to-br from-emerald-950/20 to-slate-900/90 border border-emerald-500/30 text-xs text-emerald-100/90 leading-relaxed shadow-lg">
                    <MarkdownRenderer
                      content={
                        data.explanation.how_to_prevent ||
                        "Establish automated SLA thresholds at handoff and enforce mandatory intake validation to prevent rework cycles."
                      }
                      accentColor="emerald"
                    />
                  </div>
                </div>
              </>
            ) : null}
          </div>

          {/* Footer */}
          <div className="p-4 bg-slate-900/90 border-t border-slate-800 flex items-center justify-between text-xs text-slate-500">
            <span>ProcessLens Case Engine</span>
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
