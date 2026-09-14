"use client";

import React, { useState } from "react";
import {
  Database,
  Upload,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Loader2,
  Server,
  Link,
  ShieldCheck,
  Lock,
  ArrowRight,
  Layers,
  Table,
} from "lucide-react";

interface ColumnMappingState {
  case_id: string;
  activity: string;
  timestamp: string;
  resource: string;
}

interface ConnectorPanelProps {
  apiBase: string;
  activeProject: string;
  onUploadSuccess: (msg: string) => void;
  onUploadError: (errors: string[]) => void;
  onResetSuccess: (msg: string) => void;
  apiKey?: string;
}

type SourceTab = "csv" | "postgres";

export const ConnectorPanel: React.FC<ConnectorPanelProps> = ({
  apiBase,
  activeProject,
  onUploadSuccess,
  onUploadError,
  onResetSuccess,
  apiKey = "",
}) => {
  const [activeSourceTab, setActiveSourceTab] = useState<SourceTab>("csv");

  const getHeaders = (extra: Record<string, string> = {}) => {
    const h: Record<string, string> = { ...extra };
    if (apiKey) {
      h["X-API-Key"] = apiKey;
    }
    return h;
  };

  // CSV upload state
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvSuccess, setCsvSuccess] = useState<string | null>(null);
  const [csvErrors, setCsvErrors] = useState<string[]>([]);
  const [resetting, setResetting] = useState(false);

  // PostgreSQL state
  const [pgHost, setPgHost] = useState("localhost");
  const [pgPort, setPgPort] = useState(5432);
  const [pgDatabase, setPgDatabase] = useState("");
  const [pgUsername, setPgUsername] = useState("");
  const [pgPassword, setPgPassword] = useState("");
  const [pgSchema, setPgSchema] = useState("public");
  const [pgTable, setPgTable] = useState("");
  const [pgSslMode, setPgSslMode] = useState("prefer");

  // Column Mapping state
  const [mapping, setMapping] = useState<ColumnMappingState>({
    case_id: "case_id",
    activity: "activity",
    timestamp: "timestamp",
    resource: "resource",
  });

  // Test Connection state
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionTested, setConnectionTested] = useState(false);
  const [testSuccess, setTestSuccess] = useState(false);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [availableColumns, setAvailableColumns] = useState<string[]>([]);
  const [discoveredRowCount, setDiscoveredRowCount] = useState<number | null>(null);

  // Ingestion state
  const [ingesting, setIngesting] = useState(false);
  const [ingestSuccess, setIngestSuccess] = useState<string | null>(null);
  const [ingestErrors, setIngestErrors] = useState<string[]>([]);

  // CSV File Handler
  const handleCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setCsvUploading(true);
    setCsvErrors([]);
    setCsvSuccess(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(
        `${apiBase}/api/upload?project_id=${encodeURIComponent(activeProject)}`,
        {
          method: "POST",
          headers: getHeaders(),
          body: formData,
        }
      );
      const data = await res.json();

      if (res.ok && data.accepted) {
        const msg = `Uploaded "${data.filename}" (${data.row_count} rows). Pipeline is ready to run.`;
        setCsvSuccess(msg);
        onUploadSuccess(msg);
      } else {
        const errors = data.errors || [data.detail || data.message || "Upload validation failed."];
        setCsvErrors(errors);
        onUploadError(errors);
      }
    } catch (err: any) {
      const errs = [err.message || "Upload request failed."];
      setCsvErrors(errs);
      onUploadError(errs);
    } finally {
      setCsvUploading(false);
      e.target.value = "";
    }
  };

  // Reset to Synthetic Handler
  const handleResetToSynthetic = async () => {
    setResetting(true);
    setCsvErrors([]);
    setCsvSuccess(null);
    setIngestErrors([]);
    setIngestSuccess(null);

    try {
      const res = await fetch(`${apiBase}/api/reset-to-synthetic`, {
        method: "POST",
        headers: getHeaders(),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        const msg = "Reset to canonical synthetic Purchase Order dataset completed.";
        setCsvSuccess(msg);
        onResetSuccess(msg);
      } else {
        setCsvErrors([data.message || "Reset failed."]);
      }
    } catch (err: any) {
      setCsvErrors([err.message || "Reset request failed."]);
    } finally {
      setResetting(false);
    }
  };

  // PostgreSQL Test Connection Handler
  const handleTestPostgres = async () => {
    setTestingConnection(true);
    setConnectionTested(true);
    setTestSuccess(false);
    setTestMessage(null);
    setIngestErrors([]);
    setIngestSuccess(null);

    try {
      const res = await fetch(`${apiBase}/api/connectors/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_type: "postgresql",
          config: {
            host: pgHost.trim(),
            port: Number(pgPort) || 5432,
            database: pgDatabase.trim(),
            username: pgUsername.trim(),
            password: pgPassword,
            schema_name: pgSchema.trim() || "public",
            table_name: pgTable.trim(),
            sslmode: pgSslMode,
          },
          column_mapping: {
            case_id: mapping.case_id.trim(),
            activity: mapping.activity.trim(),
            timestamp: mapping.timestamp.trim(),
            resource: mapping.resource.trim(),
          },
        }),
      });

      const data = await res.json();
      setTestSuccess(data.success === true);
      setTestMessage(data.message || (data.success ? "Connection successful." : "Connection failed."));

      if (data.available_columns && data.available_columns.length > 0) {
        setAvailableColumns(data.available_columns);
      }
      if (data.row_count !== undefined) {
        setDiscoveredRowCount(data.row_count);
      }

      // If smart detection found mapping candidates, adopt them if currently default
      if (data.detected_mapping) {
        setMapping((prev) => ({
          case_id: data.detected_mapping.case_id || prev.case_id,
          activity: data.detected_mapping.activity || prev.activity,
          timestamp: data.detected_mapping.timestamp || prev.timestamp,
          resource: data.detected_mapping.resource || prev.resource,
        }));
      }
    } catch (err: any) {
      setTestSuccess(false);
      setTestMessage(err.message || "Network error while attempting connection test.");
    } finally {
      setTestingConnection(false);
    }
  };

  // PostgreSQL Ingestion Handler
  const handleIngestPostgres = async () => {
    setIngesting(true);
    setIngestErrors([]);
    setIngestSuccess(null);

    try {
      const res = await fetch(`${apiBase}/api/connectors/ingest`, {
        method: "POST",
        headers: getHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          source_type: "postgresql",
          project_id: activeProject,
          config: {
            host: pgHost.trim(),
            port: Number(pgPort) || 5432,
            database: pgDatabase.trim(),
            username: pgUsername.trim(),
            password: pgPassword,
            schema_name: pgSchema.trim() || "public",
            table_name: pgTable.trim(),
            sslmode: pgSslMode,
          },
          column_mapping: {
            case_id: mapping.case_id.trim(),
            activity: mapping.activity.trim(),
            timestamp: mapping.timestamp.trim(),
            resource: mapping.resource.trim(),
          },
        }),
      });

      const data = await res.json();

      if (res.ok && data.accepted) {
        const msg = `Successfully ingested ${data.row_count.toLocaleString()} events across ${data.case_count.toLocaleString()} cases from PostgreSQL table '${data.table_name}'.`;
        setIngestSuccess(msg);
        onUploadSuccess(msg);
      } else {
        const errs = data.errors || [data.message || "Connector ingestion failed."];
        setIngestErrors(errs);
        onUploadError(errs);
      }
    } catch (err: any) {
      const errs = [err.message || "Failed to execute connector ingestion."];
      setIngestErrors(errs);
      onUploadError(errs);
    } finally {
      setIngesting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Source Selection Cards */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
        <div>
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-400" />
              ProcessLens Data Ingestion & Direct Connectors
            </h3>
            <span className="text-[11px] font-mono px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
              Workspace: {activeProject}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Connect directly to relational databases or upload CSV event logs. All ingested data is
            deterministically mapped to the canonical ProcessLens event log schema (
            <code className="text-indigo-300 font-mono">case_id, activity, timestamp, resource</code>)
            and validated against strict process-mining standards.
          </p>
        </div>

        {/* Source Selector Pills */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2.5">
          {/* Active: CSV */}
          <button
            type="button"
            onClick={() => setActiveSourceTab("csv")}
            className={`flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all ${
              activeSourceTab === "csv"
                ? "bg-indigo-600/20 border-indigo-500 text-white shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500"
                : "bg-slate-950/50 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
            }`}
          >
            <FileSpreadsheet className="w-5 h-5 mb-1.5 text-indigo-400" />
            <span className="text-xs font-semibold">CSV Upload</span>
            <span className="text-[10px] text-emerald-400 mt-0.5">Active</span>
          </button>

          {/* Active: PostgreSQL */}
          <button
            type="button"
            onClick={() => setActiveSourceTab("postgres")}
            className={`flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all ${
              activeSourceTab === "postgres"
                ? "bg-indigo-600/20 border-indigo-500 text-white shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500"
                : "bg-slate-950/50 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
            }`}
          >
            <Database className="w-5 h-5 mb-1.5 text-cyan-400" />
            <span className="text-xs font-semibold">PostgreSQL</span>
            <span className="text-[10px] text-emerald-400 mt-0.5">Ready (Read-Only)</span>
          </button>

          {/* Planned / Coming Soon */}
          <div className="flex flex-col items-center justify-center p-3 rounded-xl border border-slate-800/60 bg-slate-950/20 text-slate-600 opacity-60 cursor-not-allowed">
            <Server className="w-5 h-5 mb-1.5 text-slate-600" />
            <span className="text-xs font-semibold">MySQL</span>
            <span className="text-[10px] text-slate-500 mt-0.5">Coming Soon</span>
          </div>

          <div className="flex flex-col items-center justify-center p-3 rounded-xl border border-slate-800/60 bg-slate-950/20 text-slate-600 opacity-60 cursor-not-allowed">
            <Server className="w-5 h-5 mb-1.5 text-slate-600" />
            <span className="text-xs font-semibold">SQL Server</span>
            <span className="text-[10px] text-slate-500 mt-0.5">Coming Soon</span>
          </div>

          <div className="flex flex-col items-center justify-center p-3 rounded-xl border border-slate-800/60 bg-slate-950/20 text-slate-600 opacity-60 cursor-not-allowed">
            <Layers className="w-5 h-5 mb-1.5 text-slate-600" />
            <span className="text-xs font-semibold">SAP ERP</span>
            <span className="text-[10px] text-slate-500 mt-0.5">Coming Soon</span>
          </div>

          <div className="flex flex-col items-center justify-center p-3 rounded-xl border border-slate-800/60 bg-slate-950/20 text-slate-600 opacity-60 cursor-not-allowed">
            <ShieldCheck className="w-5 h-5 mb-1.5 text-slate-600" />
            <span className="text-xs font-semibold">Salesforce</span>
            <span className="text-[10px] text-slate-500 mt-0.5">Coming Soon</span>
          </div>

          <div className="flex flex-col items-center justify-center p-3 rounded-xl border border-slate-800/60 bg-slate-950/20 text-slate-600 opacity-60 cursor-not-allowed">
            <Table className="w-5 h-5 mb-1.5 text-slate-600" />
            <span className="text-xs font-semibold">Atlassian Jira</span>
            <span className="text-[10px] text-slate-500 mt-0.5">Coming Soon</span>
          </div>
        </div>

        {/* =================================================================== */}
        {/* TAB A: CSV Upload */}
        {/* =================================================================== */}
        {activeSourceTab === "csv" && (
          <div className="space-y-4 pt-2 border-t border-slate-800">
            <div className="border-2 border-dashed border-slate-800 hover:border-indigo-500/50 rounded-2xl p-8 text-center transition-colors bg-slate-950/40">
              <FileSpreadsheet className="w-10 h-10 text-indigo-400 mx-auto mb-3" />
              <p className="text-sm font-semibold text-slate-200 mb-1">
                Choose an event log CSV file to upload
              </p>
              <p className="text-xs text-slate-500 mb-4">
                Required schema: <code className="text-indigo-300">case_id, activity, timestamp, resource</code> (ISO-8601 timestamps, ≥10 cases)
              </p>

              <input
                type="file"
                accept=".csv"
                onChange={handleCsvUpload}
                className="hidden"
                id="csv-upload-input"
                disabled={csvUploading}
              />
              <label
                htmlFor="csv-upload-input"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 cursor-pointer transition-all disabled:opacity-50"
              >
                {csvUploading ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Validating & Uploading...</span>
                  </>
                ) : (
                  <>
                    <Upload className="w-3.5 h-3.5" />
                    <span>Browse CSV File</span>
                  </>
                )}
              </label>
            </div>

            {/* CSV Success */}
            {csvSuccess && (
              <div className="p-4 rounded-xl bg-emerald-950/30 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{csvSuccess}</span>
              </div>
            )}

            {/* CSV Errors */}
            {csvErrors.length > 0 && (
              <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 text-xs space-y-1">
                <div className="flex items-center gap-2 font-bold mb-1">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>Upload Validation Rejected:</span>
                </div>
                {csvErrors.map((err, idx) => (
                  <p key={idx} className="font-mono text-[11px] text-rose-200">
                    • {err}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB B: PostgreSQL Database Connector */}
        {/* =================================================================== */}
        {activeSourceTab === "postgres" && (
          <div className="space-y-6 pt-2 border-t border-slate-800">
            {/* Security Guarantee Banner */}
            <div className="flex items-center gap-3 p-3.5 rounded-xl bg-cyan-950/30 border border-cyan-800/50 text-cyan-300 text-xs">
              <ShieldCheck className="w-4 h-4 text-cyan-400 shrink-0" />
              <span>
                <strong>Read-Only Guarantee:</strong> This connector operates in strictly read-only session mode (
                <code className="text-cyan-200 font-mono">SELECT</code> queries only, 10s socket timeout, 30s statement timeout).
                Credentials are never persisted in logs or metadata.
              </span>
            </div>

            {/* Connection Parameters Form */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Host / Server Address
                </label>
                <input
                  type="text"
                  value={pgHost}
                  onChange={(e) => setPgHost(e.target.value)}
                  placeholder="e.g. localhost or db.internal"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Port
                </label>
                <input
                  type="number"
                  value={pgPort}
                  onChange={(e) => setPgPort(Number(e.target.value))}
                  placeholder="5432"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Database Name
                </label>
                <input
                  type="text"
                  value={pgDatabase}
                  onChange={(e) => setPgDatabase(e.target.value)}
                  placeholder="e.g. enterprise_erp"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Username
                </label>
                <input
                  type="text"
                  value={pgUsername}
                  onChange={(e) => setPgUsername(e.target.value)}
                  placeholder="e.g. readonly_user"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Password
                </label>
                <div className="relative">
                  <input
                    type="password"
                    value={pgPassword}
                    onChange={(e) => setPgPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                  />
                  <Lock className="w-3.5 h-3.5 text-slate-500 absolute right-3 top-2.5 pointer-events-none" />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  SSL Mode
                </label>
                <select
                  value={pgSslMode}
                  onChange={(e) => setPgSslMode(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                >
                  <option value="prefer">prefer (auto-negotiate)</option>
                  <option value="require">require (enforce TLS)</option>
                  <option value="disable">disable (unencrypted)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Schema
                </label>
                <input
                  type="text"
                  value={pgSchema}
                  onChange={(e) => setPgSchema(e.target.value)}
                  placeholder="public"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Table or View Name
                </label>
                <input
                  type="text"
                  value={pgTable}
                  onChange={(e) => setPgTable(e.target.value)}
                  placeholder="e.g. process_events, purchase_orders, ticket_log"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                />
              </div>
            </div>

            {/* Test Connection Action Button */}
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={handleTestPostgres}
                disabled={testingConnection || !pgHost || !pgDatabase || !pgUsername || !pgTable}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-cyan-700 hover:bg-cyan-600 disabled:opacity-40 text-white transition-all shadow-md shadow-cyan-900/20"
              >
                {testingConnection ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Testing Connection...</span>
                  </>
                ) : (
                  <>
                    <Link className="w-3.5 h-3.5" />
                    <span>Test Connection & Inspect Columns</span>
                  </>
                )}
              </button>

              {connectionTested && testMessage && (
                <div
                  className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg border ${
                    testSuccess
                      ? "bg-emerald-950/40 border-emerald-500/50 text-emerald-300"
                      : "bg-rose-950/40 border-rose-800 text-rose-300"
                  }`}
                >
                  {testSuccess ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  ) : (
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                  )}
                  <span>{testMessage}</span>
                </div>
              )}
            </div>

            {/* Column Mapping Section */}
            <div className="p-5 rounded-xl bg-slate-950/60 border border-slate-800 space-y-4">
              <div>
                <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                  <Table className="w-3.5 h-3.5 text-cyan-400" />
                  Field Mapping: Source Columns ➔ Canonical ProcessLens Event Log
                </h4>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Map the column names in your PostgreSQL table to the 4 canonical ProcessLens event log fields.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Canonical: case_id */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">
                    Canonical <code className="text-cyan-300">case_id</code>
                  </label>
                  {availableColumns.length > 0 ? (
                    <select
                      value={mapping.case_id}
                      onChange={(e) => setMapping({ ...mapping, case_id: e.target.value })}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                    >
                      {availableColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={mapping.case_id}
                      onChange={(e) => setMapping({ ...mapping, case_id: e.target.value })}
                      placeholder="e.g. order_num, case_id"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                    />
                  )}
                </div>

                {/* Canonical: activity */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">
                    Canonical <code className="text-cyan-300">activity</code>
                  </label>
                  {availableColumns.length > 0 ? (
                    <select
                      value={mapping.activity}
                      onChange={(e) => setMapping({ ...mapping, activity: e.target.value })}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                    >
                      {availableColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={mapping.activity}
                      onChange={(e) => setMapping({ ...mapping, activity: e.target.value })}
                      placeholder="e.g. step_name, status"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                    />
                  )}
                </div>

                {/* Canonical: timestamp */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">
                    Canonical <code className="text-cyan-300">timestamp</code>
                  </label>
                  {availableColumns.length > 0 ? (
                    <select
                      value={mapping.timestamp}
                      onChange={(e) => setMapping({ ...mapping, timestamp: e.target.value })}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                    >
                      {availableColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={mapping.timestamp}
                      onChange={(e) => setMapping({ ...mapping, timestamp: e.target.value })}
                      placeholder="e.g. event_time, created_at"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                    />
                  )}
                </div>

                {/* Canonical: resource */}
                <div>
                  <label className="block text-[11px] font-semibold text-slate-300 mb-1">
                    Canonical <code className="text-cyan-300">resource</code>
                  </label>
                  {availableColumns.length > 0 ? (
                    <select
                      value={mapping.resource}
                      onChange={(e) => setMapping({ ...mapping, resource: e.target.value })}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                    >
                      {availableColumns.map((col) => (
                        <option key={col} value={col}>
                          {col}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={mapping.resource}
                      onChange={(e) => setMapping({ ...mapping, resource: e.target.value })}
                      placeholder="e.g. user_id, operator"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 font-mono"
                    />
                  )}
                </div>
              </div>

              {/* Ingest Action Button */}
              <div className="pt-3 border-t border-slate-800 flex items-center justify-between">
                <p className="text-[11px] text-slate-400">
                  Data will be validated, normalized, and stored in workspace:{" "}
                  <strong className="text-slate-200">{activeProject}</strong>
                </p>

                <button
                  type="button"
                  onClick={handleIngestPostgres}
                  disabled={ingesting || !pgHost || !pgDatabase || !pgUsername || !pgTable}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white transition-all shadow-md shadow-emerald-950/50"
                >
                  {ingesting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Extracting & Ingesting...</span>
                    </>
                  ) : (
                    <>
                      <span>Import Event Log into Pipeline</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Ingest Success Alert */}
            {ingestSuccess && (
              <div className="p-4 rounded-xl bg-emerald-950/30 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{ingestSuccess}</span>
              </div>
            )}

            {/* Ingest Errors Alert */}
            {ingestErrors.length > 0 && (
              <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 text-xs space-y-1">
                <div className="flex items-center gap-2 font-bold mb-1">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>Connector Ingestion Rejected:</span>
                </div>
                {ingestErrors.map((err, idx) => (
                  <p key={idx} className="font-mono text-[11px] text-rose-200">
                    • {err}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* =================================================================== */}
        {/* Reset to Canonical Synthetic Generator */}
        {/* =================================================================== */}
        <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
          <div>
            <h4 className="text-xs font-bold text-white uppercase tracking-wider">
              Reset to Canonical Synthetic Generator
            </h4>
            <p className="text-xs text-slate-400">
              Discard imported custom/connector data and restore the canonical 300-case synthetic Purchase Order dataset
            </p>
          </div>
          <button
            type="button"
            onClick={handleResetToSynthetic}
            disabled={resetting}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700 hover:border-slate-600 hover:bg-slate-800 text-slate-300 transition-colors disabled:opacity-50"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${resetting ? "animate-spin" : ""}`} />
            <span>{resetting ? "Resetting..." : "Reset to Synthetic"}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
