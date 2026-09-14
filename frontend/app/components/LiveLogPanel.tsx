"use client";

import React, { useEffect, useRef, useState } from "react";
import { 
  Terminal, 
  ChevronUp, 
  ChevronDown, 
  X, 
  CheckCircle2, 
  AlertCircle, 
  Loader2, 
  Copy, 
  Check, 
  Maximize2, 
  Minimize2 
} from "lucide-react";

interface LogEntry {
  timestamp: string;
  line: string;
  level: "info" | "warning" | "error";
}

interface LiveLogPanelProps {
  runId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onRunComplete?: (status: string) => void;
  apiBaseUrl?: string;
}

export const LiveLogPanel: React.FC<LiveLogPanelProps> = ({
  runId,
  isOpen,
  onClose,
  onRunComplete,
  apiBaseUrl = "http://localhost:8000",
}) => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [status, setStatus] = useState<string>("QUEUED");
  const [progress, setProgress] = useState<number>(0);
  const [currentStage, setCurrentStage] = useState<string>("");
  const [isMinimized, setIsMinimized] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Auto-scroll to bottom of logs
  useEffect(() => {
    if (logContainerRef.current && !isMinimized) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, isMinimized]);

  useEffect(() => {
    if (!runId || !isOpen) {
      return;
    }

    setLogs([]);
    setStatus("RUNNING");
    setProgress(5);
    setCurrentStage("Initializing pipeline run...");

    // Try EventSource (SSE)
    let es: EventSource | null = null;
    let pollInterval: NodeJS.Timeout | null = null;

    try {
      es = new EventSource(`${apiBaseUrl}/api/run/${runId}/stream`);
      eventSourceRef.current = es;

      es.addEventListener("log", (e) => {
        try {
          const entry: LogEntry = JSON.parse(e.data);
          setLogs((prev) => [...prev, entry]);
        } catch (err) {
          console.error("Error parsing log event:", err);
        }
      });

      es.addEventListener("progress", (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.progress !== undefined) setProgress(data.progress);
          if (data.stage) setCurrentStage(data.stage);
        } catch (err) {
          console.error("Error parsing progress event:", err);
        }
      });

      es.addEventListener("status", (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.status) {
            setStatus(data.status);
            if (data.status === "COMPLETED") {
              setProgress(100);
              if (onRunComplete) onRunComplete("COMPLETED");
            } else if (data.status === "FAILED") {
              if (onRunComplete) onRunComplete("FAILED");
            }
          }
          if (data.progress !== undefined) setProgress(data.progress);
          if (data.current_stage) setCurrentStage(data.current_stage);
        } catch (err) {
          console.error("Error parsing status event:", err);
        }
      });

      es.onerror = () => {
        // Fallback to polling if SSE encounters an error or ends
        if (es) {
          es.close();
        }
        startPolling();
      };
    } catch (err) {
      startPolling();
    }

    // Polling fallback mechanism
    function startPolling() {
      if (pollInterval) return;
      pollInterval = setInterval(async () => {
        try {
          const statusRes = await fetch(`${apiBaseUrl}/api/run/${runId}/status`);
          if (statusRes.ok) {
            const statusData = await statusRes.json();
            setStatus(statusData.status);
            setProgress(statusData.progress || 0);
            if (statusData.current_stage) setCurrentStage(statusData.current_stage);

            if (["COMPLETED", "FAILED", "CANCELLED"].includes(statusData.status)) {
              if (pollInterval) clearInterval(pollInterval);
              if (onRunComplete) onRunComplete(statusData.status);
            }
          }

          const logsRes = await fetch(`${apiBaseUrl}/api/run/${runId}/logs`);
          if (logsRes.ok) {
            const logsData = await logsRes.json();
            if (logsData.logs) {
              setLogs(logsData.logs);
            }
          }
        } catch (err) {
          console.warn("Log polling error:", err);
        }
      }, 1500);
    }

    return () => {
      if (es) es.close();
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [runId, isOpen, apiBaseUrl]);

  if (!isOpen || !runId) return null;

  const copyLogs = () => {
    const text = logs.map((l) => `[${l.timestamp}] ${l.line}`).join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={`fixed bottom-0 left-0 right-0 z-50 transition-all duration-300 ease-in-out ${
        isMinimized ? "translate-y-[calc(100%-48px)]" : "translate-y-0"
      }`}
    >
      <div className="max-w-7xl mx-auto px-4">
        <div className="bg-slate-950 border-t border-x border-slate-800 rounded-t-2xl shadow-2xl overflow-hidden backdrop-blur-xl">
          {/* Header Bar */}
          <div className="px-5 py-2.5 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-indigo-400" />
                <span className="text-xs font-bold uppercase tracking-wider text-slate-200">
                  Live Execution Logs
                </span>
                <span className="font-mono text-[11px] text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                  {runId}
                </span>
              </div>

              {/* Status Badge */}
              <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold">
                {status === "RUNNING" && (
                  <span className="flex items-center gap-1.5 text-indigo-400 bg-indigo-500/10 border border-indigo-500/30 px-2 py-0.5 rounded-full">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Running ({progress}%)
                  </span>
                )}
                {status === "COMPLETED" && (
                  <span className="flex items-center gap-1.5 text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                    <CheckCircle2 className="w-3 h-3" />
                    Completed
                  </span>
                )}
                {status === "FAILED" && (
                  <span className="flex items-center gap-1.5 text-rose-400 bg-rose-500/10 border border-rose-500/30 px-2 py-0.5 rounded-full">
                    <AlertCircle className="w-3 h-3" />
                    Failed
                  </span>
                )}
                {status === "QUEUED" && (
                  <span className="text-amber-400 bg-amber-500/10 border border-amber-500/30 px-2 py-0.5 rounded-full">
                    Queued
                  </span>
                )}
              </div>

              {currentStage && (
                <span className="text-xs text-slate-400 hidden sm:inline-block truncate max-w-xs">
                  • {currentStage}
                </span>
              )}
            </div>

            {/* Header Control Actions */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={copyLogs}
                title="Copy all logs"
                className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
              >
                {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
              </button>
              <button
                onClick={() => setIsMinimized(!isMinimized)}
                title={isMinimized ? "Expand console" : "Minimize console"}
                className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors"
              >
                {isMinimized ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
              <button
                onClick={onClose}
                title="Close console"
                className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-rose-400 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="w-full bg-slate-900 h-1">
            <div
              className={`h-full transition-all duration-300 ${
                status === "FAILED"
                  ? "bg-rose-500"
                  : status === "COMPLETED"
                  ? "bg-emerald-500"
                  : "bg-indigo-500"
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>

          {/* Terminal Console View */}
          <div
            ref={logContainerRef}
            className="h-64 overflow-y-auto p-4 font-mono text-xs space-y-1 bg-slate-950 text-slate-300 selection:bg-indigo-900 selection:text-white"
          >
            {logs.length === 0 ? (
              <div className="flex items-center justify-center h-full text-slate-500 italic">
                <Loader2 className="w-4 h-4 mr-2 animate-spin text-indigo-400" />
                Waiting for subprocess stream...
              </div>
            ) : (
              logs.map((log, index) => {
                const isDivider = log.line.includes("===") || log.line.includes("---");
                const isSuccess = log.line.toLowerCase().includes("success") || log.line.toLowerCase().includes("completed");
                const isError = log.level === "error" || log.line.toLowerCase().includes("error") || log.line.toLowerCase().includes("fail");

                return (
                  <div
                    key={index}
                    className={`flex items-start gap-2 leading-relaxed ${
                      isDivider
                        ? "text-cyan-400 font-bold"
                        : isError
                        ? "text-rose-400 bg-rose-950/20 px-1 rounded"
                        : isSuccess
                        ? "text-emerald-300 font-semibold"
                        : log.level === "warning"
                        ? "text-amber-300"
                        : "text-slate-300"
                    }`}
                  >
                    <span className="text-slate-600 select-none text-[11px] shrink-0">
                      [{log.timestamp}]
                    </span>
                    <span className="break-all whitespace-pre-wrap">{log.line}</span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
