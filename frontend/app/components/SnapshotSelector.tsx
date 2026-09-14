"use client";

import React, { useEffect, useState } from "react";
import { Clock, CheckCircle2, AlertTriangle, HelpCircle, ShieldCheck } from "lucide-react";

interface SnapshotValidation {
  valid: boolean;
  activity: string;
  case_coverage_pct: number;
  total_cases: number;
  cases_with_activity: number;
  warnings: string[];
  error?: string | null;
}

interface SnapshotSelectorProps {
  selectedActivity: string;
  onSelectActivity: (activity: string) => void;
  apiBaseUrl?: string;
  disabled?: boolean;
}

export const SnapshotSelector: React.FC<SnapshotSelectorProps> = ({
  selectedActivity,
  onSelectActivity,
  apiBaseUrl = "http://localhost:8000",
  disabled = false,
}) => {
  const [activities, setActivities] = useState<string[]>([]);
  const [validation, setValidation] = useState<SnapshotValidation | null>(null);
  const [loading, setLoading] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  useEffect(() => {
    // Fetch available activities
    const fetchActivities = async () => {
      try {
        const res = await fetch(`${apiBaseUrl}/api/snapshot/activities`);
        if (res.ok) {
          const data = await res.json();
          if (data.activities && Array.isArray(data.activities)) {
            const names: string[] = data.activities.map((a: any) =>
              typeof a === "string" ? a : a.activity
            );
            setActivities(names);
            if (!selectedActivity && names.includes("Reviewed")) {
              onSelectActivity("Reviewed");
            } else if (!selectedActivity && names.length > 0) {
              onSelectActivity(names[0]);
            }
          }
        }
      } catch (err) {
        console.warn("Could not load activities:", err);
      }
    };
    fetchActivities();
  }, [apiBaseUrl]);

  useEffect(() => {
    if (!selectedActivity) return;
    const validate = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${apiBaseUrl}/api/snapshot/validate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ activity: selectedActivity }),
        });
        if (res.ok) {
          const data = await res.json();
          setValidation(data);
        } else {
          setValidation(null);
        }
      } catch (err) {
        console.warn("Validation error:", err);
      } finally {
        setLoading(false);
      }
    };
    validate();
  }, [selectedActivity, apiBaseUrl]);

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg backdrop-blur-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Clock className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-white uppercase tracking-wider">
                Feature Engineering Milestone Cutoff
              </span>
              <button
                type="button"
                onClick={() => setShowHelp(!showHelp)}
                className="text-slate-400 hover:text-indigo-300 transition-colors"
                title="Explain dynamic snapshot selection"
              >
                <HelpCircle className="w-3.5 h-3.5" />
              </button>
            </div>
            <p className="text-[11px] text-slate-400">
              Select milestone to freeze process state before training & predicting delays
            </p>
          </div>
        </div>

          {/* Milestone Selector Dropdown & Coverage Badge */}
          <div className="flex items-center gap-3">
            <div className="relative">
              <select
                value={selectedActivity}
                onChange={(e) => onSelectActivity(e.target.value)}
                disabled={disabled || activities.length === 0}
                className="bg-slate-950 border border-slate-700 text-slate-200 text-xs font-semibold rounded-lg px-3 py-1.5 pr-8 focus:outline-none focus:border-indigo-500 cursor-pointer disabled:opacity-50 appearance-none shadow-inner"
              >
                {activities.map((act) => (
                  <option key={act} value={act}>
                    Milestone: {act}
                  </option>
                ))}
                {activities.length === 0 && (
                  <option value="Reviewed">Milestone: Reviewed (Default)</option>
                )}
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-slate-400">
                <svg className="w-3 h-3 fill-current" viewBox="0 0 20 20">
                  <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" />
                </svg>
              </div>
            </div>

            {/* Validation Coverage indicator */}
            {loading ? (
              <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium border border-slate-800 bg-slate-950/60 text-slate-400 animate-pulse">
                <div className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
                <span>Evaluating coverage...</span>
              </div>
            ) : validation ? (
              <div className="flex items-center gap-2">
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border ${
                    validation.case_coverage_pct >= 80
                      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                      : validation.case_coverage_pct >= 50
                      ? "bg-amber-500/10 border-amber-500/30 text-amber-300"
                      : "bg-rose-500/10 border-rose-500/30 text-rose-300"
                  }`}
                >
                  {validation.case_coverage_pct >= 80 ? (
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  ) : (
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                  )}
                  <span>
                    {validation.case_coverage_pct.toFixed(0)}% Coverage ({validation.cases_with_activity}/{validation.total_cases} cases)
                  </span>
                </div>
              </div>
            ) : null}
          </div>
        </div>

        {/* Help Explainer Box */}
      {showHelp && (
        <div className="mt-3 p-3 rounded-lg bg-slate-950/70 border border-slate-800 text-xs text-slate-300 leading-relaxed animate-in fade-in slide-in-from-top-1 duration-150">
          <p className="font-medium text-indigo-300 mb-1">
            Dynamic Snapshot Selection (Phase 7 Feature 3)
          </p>
          <p>
            Instead of hardcoding the cutoff at a fixed event, you can freeze case histories at any milestone (e.g. <em>Submitted</em>, <em>Reviewed</em>, or <em>Approved</em>). 
            ProcessLens recalculates cumulative elapsed time, resource handoffs, and rework up to that specific event so the machine learning model predicts outcomes strictly based on early process signals.
          </p>
          {validation?.warnings && validation.warnings.length > 0 && (
            <div className="mt-2 text-amber-300 font-mono text-[11px]">
              Warning: {validation.warnings.join(" ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
