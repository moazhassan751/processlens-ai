"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  MarkerType,
  Handle,
  Position,
  Node,
  Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { 
  GitCommit, 
  Clock, 
  Flame, 
  Activity, 
  Maximize2, 
  Info, 
  ArrowRight,
  Sliders,
  CheckCircle2,
  ShieldAlert,
  Image as ImageIcon
} from "lucide-react";

interface GraphNodeData {
  [key: string]: any;
  id: string;
  label: string;
  frequency: number;
  avg_duration_hours: number;
  median_duration_hours: number;
  is_bottleneck: boolean;
}

interface GraphEdgeData {
  [key: string]: any;
  source: string;
  target: string;
  frequency: number;
  avg_duration_hours: number;
  median_duration_hours: number;
  is_bottleneck: boolean;
  is_conforming?: boolean;
  is_deviating?: boolean;
}

// Custom Node Component
const CustomActivityNode = ({ data }: { data: GraphNodeData }) => {
  return (
    <div
      className={`px-4 py-3 rounded-xl min-w-[180px] shadow-xl border backdrop-blur-md transition-all duration-200 ${
        data.is_bottleneck
          ? "bg-rose-950/90 border-rose-500 shadow-rose-950/50 ring-2 ring-rose-500/30"
          : "bg-slate-900/95 border-slate-700 hover:border-indigo-500 shadow-slate-950/50"
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="w-2.5 h-2.5 !bg-indigo-400 border border-slate-900"
      />
      
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-1.5">
          <Activity className={`w-3.5 h-3.5 ${data.is_bottleneck ? "text-rose-400" : "text-indigo-400"}`} />
          <span className="text-xs font-bold text-white tracking-wide truncate max-w-[130px]">
            {data.label}
          </span>
        </div>
        {data.is_bottleneck && (
          <span className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse">
            <Flame className="w-2.5 h-2.5 text-rose-400" />
            Bottleneck
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 text-[10px] pt-1.5 border-t border-slate-800">
        <div>
          <span className="text-slate-400 block text-[9px]">Cases</span>
          <span className="font-semibold text-slate-200 font-mono">
            {data.frequency.toLocaleString()}
          </span>
        </div>
        <div>
          <span className="text-slate-400 block text-[9px]">Avg Duration</span>
          <span className="font-semibold text-slate-200 font-mono">
            {data.avg_duration_hours}h
          </span>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2.5 h-2.5 !bg-indigo-400 border border-slate-900"
      />
    </div>
  );
};

const nodeTypes = {
  activityNode: CustomActivityNode,
};

interface ProcessGraphProps {
  apiBaseUrl?: string;
  staticMapUrl?: string | null;
  onRunPhase1?: () => void;
}

export const ProcessGraph: React.FC<ProcessGraphProps> = ({
  apiBaseUrl = "http://localhost:8000",
  staticMapUrl,
  onRunPhase1,
}) => {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedElement, setSelectedElement] = useState<GraphNodeData | GraphEdgeData | null>(null);
  const [viewMode, setViewMode] = useState<"interactive" | "static">("interactive");
  const [minFrequency, setMinFrequency] = useState<number>(1);
  const [maxFreq, setMaxFreq] = useState<number>(100);
  const [showConformanceOverlay, setShowConformanceOverlay] = useState<boolean>(false);
  const [rawData, setRawData] = useState<{ nodes: GraphNodeData[]; edges: GraphEdgeData[] } | null>(null);

  // Layout algorithm: topologically order activities by flow direction
  const computeAutoLayout = (rawNodes: GraphNodeData[], rawEdges: GraphEdgeData[], conformanceMode: boolean = false) => {
    // Determine ranks by traversing edges
    const incoming: Record<string, string[]> = {};
    const outgoing: Record<string, string[]> = {};
    rawNodes.forEach((n) => {
      incoming[n.id] = [];
      outgoing[n.id] = [];
    });
    rawEdges.forEach((e) => {
      if (outgoing[e.source]) outgoing[e.source].push(e.target);
      if (incoming[e.target]) incoming[e.target].push(e.source);
    });

    // Simple layered DAG rank assignment
    const ranks: Record<string, number> = {};
    const visited = new Set<string>();

    const assignRank = (nodeId: string, currentRank: number) => {
      if (ranks[nodeId] === undefined || currentRank > ranks[nodeId]) {
        ranks[nodeId] = currentRank;
      }
      if (visited.has(nodeId)) return;
      visited.add(nodeId);
      (outgoing[nodeId] || []).forEach((nxt) => assignRank(nxt, currentRank + 1));
    };

    // Start with root nodes (no incoming edges)
    const roots = rawNodes.filter((n) => incoming[n.id].length === 0);
    if (roots.length === 0 && rawNodes.length > 0) {
      roots.push(rawNodes[0]);
    }
    roots.forEach((r) => assignRank(r.id, 0));

    // Fill in any unranked nodes
    rawNodes.forEach((n, idx) => {
      if (ranks[n.id] === undefined) ranks[n.id] = idx;
    });

    // Group nodes by rank
    const rankGroups: Record<number, GraphNodeData[]> = {};
    rawNodes.forEach((n) => {
      const r = ranks[n.id] || 0;
      if (!rankGroups[r]) rankGroups[r] = [];
      rankGroups[r].push(n);
    });

    // Position nodes vertically and horizontally
    const flowNodes: Node[] = [];
    Object.keys(rankGroups).forEach((rankKey) => {
      const rank = parseInt(rankKey, 10);
      const group = rankGroups[rank];
      const y = 80 + rank * 140;
      const spacing = 220;
      const startX = Math.max(100, 450 - ((group.length - 1) * spacing) / 2);

      group.forEach((nodeData, idx) => {
        flowNodes.push({
          id: nodeData.id,
          type: "activityNode",
          position: { x: startX + idx * spacing, y },
          data: nodeData,
        });
      });
    });

    // Flow edges
    const flowEdges: Edge[] = rawEdges.map((e, idx) => {
      let strokeColor = e.is_bottleneck ? "#f43f5e" : "#6366f1";
      let strokeDash: string | undefined = undefined;
      let strokeWidth = e.is_bottleneck ? 3 : Math.max(1.5, Math.min(4, Math.log10(e.frequency + 1) * 2));
      let labelFill = e.is_bottleneck ? "#fda4af" : "#cbd5e1";

      if (conformanceMode) {
        if (e.is_conforming) {
          strokeColor = "#10b981";
          strokeWidth = 2.5;
          labelFill = "#6ee7b7";
        } else if (e.is_deviating) {
          strokeColor = "#f59e0b";
          strokeDash = "5,5";
          strokeWidth = 2;
          labelFill = "#fcd34d";
        }
      }

      return {
        id: `e-${e.source}-${e.target}-${idx}`,
        source: e.source,
        target: e.target,
        animated: conformanceMode ? Boolean(e.is_deviating) : Boolean(e.is_bottleneck),
        label: `${e.frequency}x (${e.avg_duration_hours}h)`,
        style: {
          stroke: strokeColor,
          strokeWidth: strokeWidth,
          strokeDasharray: strokeDash,
        },
        labelStyle: {
          fill: labelFill,
          fontSize: 10,
          fontWeight: 600,
          backgroundColor: "#0f172a",
          padding: "2px 4px",
          borderRadius: "4px",
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: strokeColor,
        },
        data: e,
      };
    });

    return { flowNodes, flowEdges };
  };

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl}/api/process-graph`);
      if (res.status === 202) {
        setError("Event log not available yet. Please run the pipeline first.");
        return;
      }
      if (!res.ok) {
        throw new Error(`Failed to load process graph (HTTP ${res.status})`);
      }
      const data = await res.json();
      if (!data.nodes || data.nodes.length === 0) {
        setError("No process nodes discovered. Run Phase 1 to mine the graph.");
        return;
      }

      setRawData({ nodes: data.nodes, edges: data.edges });
      const highestFreq = Math.max(...data.edges.map((e: GraphEdgeData) => e.frequency), 10);
      setMaxFreq(highestFreq);

      const { flowNodes, flowEdges } = computeAutoLayout(data.nodes, data.edges, showConformanceOverlay);
      setNodes(flowNodes);
      setEdges(flowEdges);
    } catch (err: any) {
      setError(err.message || "Failed to load process graph");
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, setNodes, setEdges, showConformanceOverlay]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  useEffect(() => {
    if (!rawData) return;
    const { flowNodes, flowEdges } = computeAutoLayout(rawData.nodes, rawData.edges, showConformanceOverlay);
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [showConformanceOverlay]);

  const onNodeClick = (_: any, node: Node) => {
    setSelectedElement(node.data as unknown as GraphNodeData);
  };

  const onEdgeClick = (_: any, edge: Edge) => {
    setSelectedElement(edge.data as unknown as GraphEdgeData);
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl backdrop-blur-md">
      {/* Top Controls Toolbar */}
      <div className="px-6 py-3.5 bg-slate-950/80 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <GitCommit className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white tracking-tight flex items-center gap-2">
              Interactive Process Map
              <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                Live Directed Graph
              </span>
            </h2>
            <p className="text-xs text-slate-400">
              Interactive Directly-Follows Graph • Click activities or transitions for duration insights
            </p>
          </div>
        </div>

        {/* View Mode Toggle & Actions */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowConformanceOverlay((prev) => !prev)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all border ${
              showConformanceOverlay
                ? "bg-amber-500/20 border-amber-500/50 text-amber-300 shadow-sm"
                : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
            title="Toggle Conformance Paths overlay (Green: Conforming, Amber Dashed: Deviating)"
          >
            <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
            <span>Conformance Overlay</span>
            {showConformanceOverlay && (
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
            )}
          </button>

          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs font-semibold">
            <button
              onClick={() => setViewMode("interactive")}
              className={`px-3 py-1.5 rounded-md transition-all ${
                viewMode === "interactive"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Interactive Canvas
            </button>
            <button
              onClick={() => setViewMode("static")}
              className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition-all ${
                viewMode === "static"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <ImageIcon className="w-3.5 h-3.5" />
              Graphviz Static
            </button>
          </div>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div className="relative h-[550px] w-full bg-slate-950">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-400 p-8 space-y-4">
            <div className="relative w-16 h-16 flex items-center justify-center">
              <div className="absolute inset-0 rounded-full border-2 border-indigo-500/20 border-t-indigo-500 animate-spin" />
              <Activity className="w-7 h-7 text-indigo-400 animate-pulse" />
            </div>
            <div className="text-center">
              <p className="text-sm font-semibold text-slate-200">Mining Directed Process Graph...</p>
              <p className="text-xs text-slate-500 mt-1">
                Computing activity transitions, execution frequencies, and cycle time latencies
              </p>
            </div>
            {/* Subtle mock node skeletons */}
            <div className="flex items-center gap-6 pt-4 opacity-40">
              <div className="w-28 h-10 rounded-xl bg-slate-800 border border-slate-700 animate-pulse" />
              <div className="w-8 border-t border-dashed border-slate-600" />
              <div className="w-28 h-10 rounded-xl bg-slate-800 border border-slate-700 animate-pulse" />
              <div className="w-8 border-t border-dashed border-slate-600" />
              <div className="w-28 h-10 rounded-xl bg-slate-800 border border-slate-700 animate-pulse" />
            </div>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-400 p-8 text-center max-w-lg mx-auto">
            <div className="w-12 h-12 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-indigo-400 mb-3 shadow-inner">
              <GitCommit className="w-6 h-6" />
            </div>
            <h4 className="text-sm font-bold text-white mb-1.5">Process Map Not Yet Available</h4>
            <p className="text-xs text-slate-400 leading-relaxed mb-6">
              {error.includes("202") || error.includes("not available")
                ? "The event log has not been mined into a directed process topology yet. Execute Phase 1 (Discovery) to generate activity nodes, handover latencies, and bottleneck heatmaps."
                : error}
            </p>
            <div className="flex items-center gap-3">
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
                onClick={loadGraph}
                className="px-4 py-2 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-800 hover:bg-slate-850 text-slate-300 transition-colors"
              >
                Retry Loading
              </button>
            </div>
          </div>
        ) : viewMode === "static" ? (
          <div className="flex items-center justify-center h-full p-6 overflow-auto">
            {staticMapUrl ? (
              <img
                src={staticMapUrl}
                alt="Static Process Map"
                className="max-h-full max-w-full rounded-xl border border-slate-800 shadow-2xl object-contain"
              />
            ) : (
              <div className="text-slate-500 text-sm">Static process map image not available.</div>
            )}
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            nodeTypes={nodeTypes}
            fitView
            attributionPosition="bottom-left"
            className="bg-slate-950"
          >
            <Background color="#334155" gap={20} size={1} />
            <Controls className="!bg-slate-900 !border-slate-800 !text-slate-300 !fill-slate-300" />
            <MiniMap
              nodeColor={(n: any) => (n.data?.is_bottleneck ? "#f43f5e" : "#6366f1")}
              className="!bg-slate-900/90 !border-slate-800 !rounded-xl overflow-hidden"
              maskColor="rgba(15, 23, 42, 0.7)"
            />
          </ReactFlow>
        )}

        {/* Element Inspector Overlay */}
        {selectedElement && (
          <div className="absolute top-4 right-4 z-20 w-72 bg-slate-900/95 border border-slate-700 rounded-xl p-4 shadow-2xl backdrop-blur-md animate-in fade-in slide-in-from-top-2 duration-150">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                {"source" in selectedElement ? (
                  <ArrowRight className="w-4 h-4 text-cyan-400" />
                ) : (
                  <Activity className="w-4 h-4 text-indigo-400" />
                )}
                <span className="text-xs font-bold text-white uppercase tracking-wider">
                  {"source" in selectedElement ? "Transition Details" : "Activity Metrics"}
                </span>
              </div>
              <button
                onClick={() => setSelectedElement(null)}
                className="text-slate-400 hover:text-white text-xs font-mono"
              >
                ✕
              </button>
            </div>

            {"source" in selectedElement ? (
              // Edge Details
              <div className="space-y-2 text-xs">
                <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 block text-[10px]">Pathway</span>
                  <span className="font-semibold text-slate-200">
                    {selectedElement.source} → {selectedElement.target}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Transition Count</span>
                    <span className="font-bold text-white font-mono">
                      {selectedElement.frequency.toLocaleString()}
                    </span>
                  </div>
                  <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Avg Transition Time</span>
                    <span className="font-bold text-white font-mono">
                      {selectedElement.avg_duration_hours}h
                    </span>
                  </div>
                </div>
                {selectedElement.is_bottleneck && (
                  <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[11px] flex items-center gap-1.5">
                    <Flame className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                    <span>Critical handover delay identified in 75th percentile.</span>
                  </div>
                )}
                {selectedElement.is_conforming !== undefined && (
                  <div className={`p-2 rounded-lg text-[11px] flex items-center gap-1.5 ${
                    selectedElement.is_conforming
                      ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-300"
                      : "bg-amber-500/10 border border-amber-500/30 text-amber-300"
                  }`}>
                    <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
                    <span>{selectedElement.is_conforming ? "Normative Reference Transition" : "Observed Deviation / Non-Conforming Flow"}</span>
                  </div>
                )}
              </div>
            ) : (
              // Node Details
              <div className="space-y-2 text-xs">
                <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 block text-[10px]">Activity Name</span>
                  <span className="font-bold text-white">{selectedElement.label}</span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Unique Cases</span>
                    <span className="font-bold text-white font-mono">
                      {selectedElement.frequency.toLocaleString()}
                    </span>
                  </div>
                  <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-slate-400 block text-[10px]">Avg Duration</span>
                    <span className="font-bold text-white font-mono">
                      {selectedElement.avg_duration_hours}h
                    </span>
                  </div>
                </div>
                <div className="p-2 rounded-lg bg-slate-950 border border-slate-800">
                  <span className="text-slate-400 block text-[10px]">Median Wait Duration</span>
                  <span className="font-bold text-white font-mono">
                    {selectedElement.median_duration_hours}h
                  </span>
                </div>
                {selectedElement.is_bottleneck && (
                  <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[11px] flex items-center gap-1.5">
                    <Flame className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                    <span>Flagged as major process bottleneck.</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
