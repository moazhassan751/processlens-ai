"use client";

import React, { useState } from "react";
import { 
  Activity, 
  FolderGit2, 
  Database, 
  Plus, 
  RefreshCw, 
  CheckCircle2, 
  AlertTriangle,
  Play,
  Layers
} from "lucide-react";

interface HeaderProps {
  projects: string[];
  activeProject: string;
  onSelectProject: (projectId: string) => void;
  onCreateProject: (projectId: string) => void;
  dataSource: "synthetic" | "uploaded" | string;
  sourceFilename?: string | null;
  rowCount?: number | null;
  isStale?: boolean;
  onRefresh: () => void;
  onRunPipeline: () => void;
  isRunning?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  projects,
  activeProject,
  onSelectProject,
  onCreateProject,
  dataSource,
  sourceFilename,
  rowCount,
  isStale,
  onRefresh,
  onRunPipeline,
  isRunning = false,
}) => {
  const [showNewProjectModal, setShowNewProjectModal] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (newProjectName.trim()) {
      onCreateProject(newProjectName.trim());
      setNewProjectName("");
      setShowNewProjectModal(false);
    }
  };

  return (
    <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-0 z-40 px-6 py-3.5">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        {/* Brand & Title */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 p-0.5 shadow-lg shadow-indigo-500/20">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <Activity className="w-5 h-5 text-indigo-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-white">
                Process<span className="text-indigo-400">Lens</span>
              </h1>
              <span className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-300">
                Enterprise AI
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Process Mining • Predictive Risk • Real-time AI Agent
            </p>
          </div>
        </div>

        {/* Center/Right Actions & Metadata */}
        <div className="flex items-center flex-wrap gap-3">
          {/* Workspace / Project Selector */}
          <div className="flex items-center gap-2 bg-slate-900/90 border border-slate-800 rounded-lg px-3 py-1.5 shadow-inner">
            <FolderGit2 className="w-4 h-4 text-indigo-400 shrink-0" />
            <span className="text-xs text-slate-400 font-medium">Workspace:</span>
            <select
              value={activeProject}
              onChange={(e) => onSelectProject(e.target.value)}
              className="bg-transparent text-xs text-slate-200 font-semibold focus:outline-none cursor-pointer pr-1 max-w-[140px] truncate"
            >
              {projects.map((p) => (
                <option key={p} value={p} className="bg-slate-900 text-slate-200">
                  {p}
                </option>
              ))}
            </select>
            <button
              onClick={() => setShowNewProjectModal(true)}
              title="Create new workspace"
              className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-indigo-300 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Data Source Badge */}
          <div className="flex items-center gap-2 bg-slate-900/90 border border-slate-800 rounded-lg px-3 py-1.5 text-xs max-w-[280px]">
            <Database className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            <span className="text-slate-400 shrink-0">Source:</span>
            <span className="font-medium text-slate-200 capitalize truncate" title={dataSource === "synthetic" ? "Synthetic Log" : sourceFilename || "Uploaded Log"}>
              {dataSource === "synthetic" ? "Synthetic Log" : sourceFilename || "Uploaded Log"}
            </span>
            {rowCount !== undefined && rowCount !== null && (
              <span className="text-slate-500 font-mono text-[11px] shrink-0">
                ({rowCount.toLocaleString()} rows)
              </span>
            )}
          </div>

          {/* Sync Status Badge */}
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium">
            {isStale ? (
              <div className="flex items-center gap-1.5 text-amber-400 bg-amber-500/10 border-amber-500/20 px-2 py-0.5 rounded">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Stale Data</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 text-emerald-400 bg-emerald-500/10 border-emerald-500/20 px-2 py-0.5 rounded">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Synced</span>
              </div>
            )}
          </div>

          {/* Refresh button */}
          <button
            onClick={onRefresh}
            title="Refresh current state"
            className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>

          {/* Run All Button */}
          <button
            onClick={onRunPipeline}
            disabled={isRunning}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-xs transition-all shadow-md ${
              isRunning
                ? "bg-indigo-950 text-indigo-300 border border-indigo-700/50 cursor-not-allowed animate-pulse"
                : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/25 active:scale-95"
            }`}
          >
            {isRunning ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                <span>Running Pipeline...</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Run Pipeline (Async)</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* New Project Modal */}
      {showNewProjectModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 w-full max-w-sm shadow-2xl">
            <h3 className="text-base font-semibold text-white mb-2 flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-400" />
              Create Project Workspace
            </h3>
            <p className="text-xs text-slate-400 mb-4">
              Isolate event logs, ML artifacts, and prediction outputs into a dedicated workspace.
            </p>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Project Name / ID
                </label>
                <input
                  type="text"
                  placeholder="e.g. claims-q3-audit"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowNewProjectModal(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newProjectName.trim()}
                  className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50"
                >
                  Create Workspace
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </header>
  );
};
