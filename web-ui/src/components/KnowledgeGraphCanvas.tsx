import React, { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  Node,
  Edge,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  MarkerType,
  BaseEdge,
  EdgeProps,
  getBezierPath,
  ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from '@dagrejs/dagre';
import {
  Network,
  AlertTriangle,
  Download,
  GitFork,
  ExternalLink,
  ChevronDown,
  RefreshCw,
  FileText,
  BookMarked,
  Share2,
  Maximize2,
  Minimize2,
  Sparkles,
  ArrowRight,
  ArrowDown,
  Focus,
  GitMerge,
} from 'lucide-react';
import { SessionGraph, GraphNode, ContradictionPair } from '../lib/types';
import { getSessionContradictions, triggerExportDownload } from '../lib/api';

interface KnowledgeGraphCanvasProps {
  sessionId: string | null;
  graph: SessionGraph | null;
  onDivergeConcept: (concept: string) => void;
  onFindCounterEvidence: (claim: string) => void;
  onOpenEvidence: (query?: string) => void;
  width?: number;
  isEnlarged?: boolean;
  onToggleEnlarge?: () => void;
  onReconcileGraph?: () => Promise<void>;
}

// ── Smart Graph Edge (Anti-Overlap Curved Routing & Themed Labels) ───────────

export const SmartGraphEdge: React.FC<EdgeProps> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  label,
  labelStyle,
  data,
}) => {
  const offset = (data?.offset as number) || 0;
  const isContradiction = Boolean(data?.isContradiction);
  const relationType = (data?.relation_type as string) || '';

  let path = '';
  let labelX = 0;
  let labelY = 0;

  if (Math.abs(offset) > 1) {
    const dx = targetX - sourceX;
    const dy = targetY - sourceY;
    const dist = Math.hypot(dx, dy) || 1;
    const nx = -dy / dist;
    const ny = dx / dist;

    // Cubic bezier curve control points with perpendicular displacement
    const c1x = sourceX + dx * 0.25 + nx * offset;
    const c1y = sourceY + dy * 0.25 + ny * offset;
    const c2x = sourceX + dx * 0.75 + nx * offset;
    const c2y = sourceY + dy * 0.75 + ny * offset;

    path = `M ${sourceX} ${sourceY} C ${c1x} ${c1y} ${c2x} ${c2y} ${targetX} ${targetY}`;

    // Midpoint for label along cubic curve (t = 0.5)
    labelX = 0.125 * sourceX + 0.375 * c1x + 0.375 * c2x + 0.125 * targetX;
    labelY = 0.125 * sourceY + 0.375 * c1y + 0.375 * c2y + 0.125 * targetY;
  } else {
    const [bezierPath, bx, by] = getBezierPath({
      sourceX,
      sourceY,
      sourcePosition,
      targetX,
      targetY,
      targetPosition,
      curvature: 0.25,
    });
    path = bezierPath;
    labelX = bx;
    labelY = by;
  }

  // Label theme styling based on relation type
  let labelBgColor = '#141418';
  let labelBorderColor = '#3f3f46';
  let labelTextColor = '#d4d4d8';

  if (isContradiction || relationType === 'contradicts') {
    labelBgColor = '#200a0e';
    labelBorderColor = '#e11d48';
    labelTextColor = '#fda4af';
  } else if (relationType === 'supports') {
    labelBgColor = '#071b12';
    labelBorderColor = '#10b981';
    labelTextColor = '#6ee7b7';
  } else if (relationType === 'cited_by' || relationType === 'cites' || relationType === 'derived_from') {
    labelBgColor = '#081726';
    labelBorderColor = '#0284c7';
    labelTextColor = '#7dd3fc';
  } else if (relationType === 'causes' || relationType === 'leads_to' || relationType === 'implements') {
    labelBgColor = '#211707';
    labelBorderColor = '#d97706';
    labelTextColor = '#fcd34d';
  }

  return (
    <BaseEdge
      id={id}
      path={path}
      markerEnd={markerEnd}
      style={style}
      label={label}
      labelX={labelX}
      labelY={labelY}
      labelShowBg
      labelStyle={{
        fill: labelTextColor,
        fontSize: 9.5,
        fontFamily: 'JetBrains Mono, monospace',
        fontWeight: 600,
        ...labelStyle,
      }}
      labelBgStyle={{
        fill: labelBgColor,
        stroke: labelBorderColor,
        strokeWidth: 1,
      }}
      labelBgPadding={[7, 3.5]}
      labelBgBorderRadius={3}
    />
  );
};

// ── Custom Node Component (High Contrast, Spaced, Directional Handles) ────────

const CustomGraphNode: React.FC<{ data: any }> = ({ data }) => {
  const { label, node_type, description, confidence, isContradiction } = data;

  const typeConfig: Record<
    string,
    { tag: string; border: string; bg: string; badge: string; glow: string }
  > = {
    entity: {
      tag: 'ENT',
      border: 'border-emerald-700/50 hover:border-emerald-400',
      bg: 'bg-[#0f1713]',
      badge: 'text-emerald-400 bg-emerald-950/70 border-emerald-800/80',
      glow: 'shadow-[0_0_15px_rgba(16,185,129,0.08)]',
    },
    claim: {
      tag: 'CLAIM',
      border: 'border-sky-700/50 hover:border-sky-400',
      bg: 'bg-[#0e1622]',
      badge: 'text-sky-400 bg-sky-950/70 border-sky-800/80',
      glow: 'shadow-[0_0_15px_rgba(56,189,248,0.08)]',
    },
    source: {
      tag: 'SRC',
      border: 'border-purple-700/50 hover:border-purple-400',
      bg: 'bg-[#151020]',
      badge: 'text-purple-400 bg-purple-950/70 border-purple-800/80',
      glow: 'shadow-[0_0_15px_rgba(168,85,247,0.08)]',
    },
    hypothesis: {
      tag: 'HYP',
      border: 'border-amber-700/60 border-dashed hover:border-amber-400',
      bg: 'bg-[#19150d]',
      badge: 'text-amber-400 bg-amber-950/70 border-amber-800/80',
      glow: 'shadow-[0_0_15px_rgba(245,158,11,0.08)]',
    },
  };

  const cfg = typeConfig[node_type] || typeConfig.entity;
  const isConflict = Boolean(isContradiction);

  return (
    <div
      className={`p-3 rounded-[3px] border ${
        isConflict
          ? 'border-rose-600 bg-[#1c0c10] shadow-[0_0_20px_rgba(225,29,72,0.18)]'
          : `${cfg.border} ${cfg.bg} ${cfg.glow}`
      } text-zinc-100 min-w-[210px] max-w-[270px] text-xs font-sans transition-all select-none relative group`}
    >
      {/* ── Top Handles ──────────────────────── */}
      <Handle
        type="target"
        position={Position.Top}
        id="top-target"
        className="!w-2 !h-2 !bg-zinc-500 hover:!bg-zinc-200 !border !border-zinc-900 !rounded-[1px]"
      />
      <Handle
        type="source"
        position={Position.Top}
        id="top-source"
        className="!w-2 !h-2 !bg-zinc-500 hover:!bg-zinc-200 !border !border-zinc-900 !rounded-[1px] !opacity-0"
      />

      {/* ── Left Handles ─────────────────────── */}
      <Handle
        type="target"
        position={Position.Left}
        id="left-target"
        className="!w-2 !h-2 !bg-zinc-500 hover:!bg-zinc-200 !border !border-zinc-900 !rounded-[1px]"
      />
      <Handle
        type="source"
        position={Position.Left}
        id="left-source"
        className="!w-2 !h-2 !bg-zinc-500 hover:!bg-zinc-200 !border !border-zinc-900 !rounded-[1px] !opacity-0"
      />

      {/* ── Right Handles ────────────────────── */}
      <Handle
        type="source"
        position={Position.Right}
        id="right-source"
        className="!w-2 !h-2 !bg-zinc-500 hover:!bg-zinc-200 !border !border-zinc-900 !rounded-[1px]"
      />
      <Handle
        type="target"
        position={Position.Right}
        id="right-target"
        className="!w-2 !h-2 !bg-zinc-500 hover:!bg-zinc-200 !border !border-zinc-900 !rounded-[1px] !opacity-0"
      />

      {/* ── Bottom Handles ───────────────────── */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom-source"
        className="!w-2 !h-2 !bg-zinc-500 hover:!bg-zinc-200 !border !border-zinc-900 !rounded-[1px]"
      />
      <Handle
        type="target"
        position={Position.Bottom}
        id="bottom-target"
        className="!w-2 !h-2 !bg-zinc-500 hover:!bg-zinc-200 !border !border-zinc-900 !rounded-[1px] !opacity-0"
      />

      {/* Node Header Pill & Confidence */}
      <div className="flex items-center justify-between font-mono text-[9px] mb-1.5">
        <div className="flex items-center gap-1.5">
          <span className={`px-1.5 py-0.5 rounded-[2px] border font-semibold tracking-wider ${cfg.badge}`}>
            {cfg.tag}
          </span>
          {isConflict && (
            <span className="px-1 py-0.5 rounded-[2px] bg-rose-950/80 text-rose-400 border border-rose-800 font-semibold tracking-wider flex items-center gap-0.5">
              CONFLICT
            </span>
          )}
        </div>
        {confidence !== undefined && (
          <span className="text-zinc-400 bg-zinc-900/80 border border-zinc-800 px-1.5 py-0.5 rounded-[2px]">
            {Math.round(confidence * 100)}%
          </span>
        )}
      </div>

      {/* Node Main Title */}
      <div className="font-semibold text-xs text-zinc-100 leading-snug line-clamp-2">
        {label}
      </div>

      {/* Node Description */}
      {description && (
        <div className="text-[11px] text-zinc-300 mt-1.5 line-clamp-3 font-sans leading-relaxed border-t border-zinc-800/60 pt-1.5">
          {description}
        </div>
      )}
    </div>
  );
};

const nodeTypes = {
  custom: CustomGraphNode,
};

const edgeTypes = {
  smart: SmartGraphEdge,
};

// ── Dagre Auto-Layout Engine with Multi-Edge Curvature Calculation ───────────

function computeLayout(
  graph: SessionGraph | null,
  contradictionIds: Set<string>,
  direction: 'TB' | 'LR' = 'TB'
): { nodes: Node[]; edges: Edge[] } {
  if (!graph || !graph.nodes || graph.nodes.length === 0) {
    return { nodes: [], edges: [] };
  }

  const dagreGraph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({
    rankdir: direction,
    nodesep: direction === 'TB' ? 140 : 120,
    ranksep: direction === 'TB' ? 180 : 180,
    edgesep: 60,
    marginx: 80,
    marginy: 80,
  });

  const nodeMap = new Map<string, GraphNode>();
  graph.nodes.forEach((n) => {
    nodeMap.set(n.id, n);
    dagreGraph.setNode(n.id, { width: 260, height: 140 });
  });

  const validEdges = (graph.edges || []).filter(
    (e) => nodeMap.has(e.source_node_id) && nodeMap.has(e.target_node_id)
  );

  validEdges.forEach((e) => {
    dagreGraph.setEdge(e.source_node_id, e.target_node_id);
  });

  dagre.layout(dagreGraph);

  // Group edges by unordered node pair to detect multi-edges & bidirectional edges
  const pairKey = (s: string, t: string) => (s < t ? `${s}___${t}` : `${t}___${s}`);
  const groupMap = new Map<string, string[]>();
  validEdges.forEach((e) => {
    const key = pairKey(e.source_node_id, e.target_node_id);
    const list = groupMap.get(key) || [];
    list.push(e.id);
    groupMap.set(key, list);
  });

  // Build nodes with generous spacing
  const layoutNodes: Node[] = graph.nodes.map((n) => {
    const dNode = dagreGraph.node(n.id);
    const x = dNode ? dNode.x - 130 : 0;
    const y = dNode ? dNode.y - 70 : 0;

    return {
      id: n.id,
      type: 'custom',
      position: { x, y },
      data: {
        ...n,
        isContradiction: contradictionIds.has(n.id),
      },
    };
  });

  // Build edges with directional handles and anti-overlap curves
  const layoutEdges: Edge[] = validEdges.map((e) => {
    const sourceDNode = dagreGraph.node(e.source_node_id);
    const targetDNode = dagreGraph.node(e.target_node_id);

    const sx = sourceDNode ? sourceDNode.x : 0;
    const sy = sourceDNode ? sourceDNode.y : 0;
    const tx = targetDNode ? targetDNode.x : 0;
    const ty = targetDNode ? targetDNode.y : 0;

    const dx = tx - sx;
    const dy = ty - sy;

    // Pick handles based on relative geometry
    let sourceHandle = 'bottom-source';
    let targetHandle = 'top-target';

    if (direction === 'TB') {
      if (dy > 60) {
        if (Math.abs(dx) < 100) {
          sourceHandle = 'bottom-source';
          targetHandle = 'top-target';
        } else if (dx >= 100) {
          sourceHandle = 'bottom-source';
          targetHandle = 'left-target';
        } else {
          sourceHandle = 'bottom-source';
          targetHandle = 'right-target';
        }
      } else if (Math.abs(dy) <= 60) {
        if (dx >= 0) {
          sourceHandle = 'right-source';
          targetHandle = 'left-target';
        } else {
          sourceHandle = 'left-source';
          targetHandle = 'right-target';
        }
      } else {
        // dy < -60 (backward cycle)
        if (dx >= 0) {
          sourceHandle = 'right-source';
          targetHandle = 'right-target';
        } else {
          sourceHandle = 'left-source';
          targetHandle = 'left-target';
        }
      }
    } else {
      // LR mode
      if (dx > 60) {
        if (Math.abs(dy) < 80) {
          sourceHandle = 'right-source';
          targetHandle = 'left-target';
        } else if (dy >= 80) {
          sourceHandle = 'right-source';
          targetHandle = 'top-target';
        } else {
          sourceHandle = 'right-source';
          targetHandle = 'bottom-target';
        }
      } else if (Math.abs(dx) <= 60) {
        if (dy >= 0) {
          sourceHandle = 'bottom-source';
          targetHandle = 'top-target';
        } else {
          sourceHandle = 'top-source';
          targetHandle = 'bottom-target';
        }
      } else {
        if (dy >= 0) {
          sourceHandle = 'bottom-source';
          targetHandle = 'bottom-target';
        } else {
          sourceHandle = 'top-source';
          targetHandle = 'top-target';
        }
      }
    }

    // Offset calculation for multi-edges and bidirectional edges
    const pKey = pairKey(e.source_node_id, e.target_node_id);
    const edgeIdsInPair = groupMap.get(pKey) || [];
    let offset = 0;

    if (edgeIdsInPair.length > 1) {
      const idx = edgeIdsInPair.indexOf(e.id);
      const isOppositePair = validEdges.some(
        (other) =>
          edgeIdsInPair.includes(other.id) &&
          other.source_node_id === e.target_node_id &&
          other.target_node_id === e.source_node_id
      );

      if (isOppositePair && edgeIdsInPair.length === 2) {
        // Bidirectional pair: both curve outward to their relative right
        offset = 36;
      } else {
        // Multi-edge in same direction or 3+ edges
        const mid = (edgeIdsInPair.length - 1) / 2;
        offset = (idx - mid) * 36;
      }
    }

    const isContradiction = e.relation_type === 'contradicts';
    const isSupports = e.relation_type === 'supports';
    const isCites = e.relation_type === 'cited_by' || (e.relation_type as string) === 'cites';
    const isCauses =
      (e.relation_type as string) === 'causes' ||
      (e.relation_type as string) === 'leads_to' ||
      e.relation_type === 'implements';

    let strokeColor = '#52525b';
    let strokeWidth = 1.4;
    let strokeDasharray: string | undefined = undefined;

    if (isContradiction) {
      strokeColor = '#f43f5e';
      strokeWidth = 2.2;
      strokeDasharray = '5 3';
    } else if (isSupports) {
      strokeColor = '#10b981';
      strokeWidth = 1.8;
    } else if (isCites) {
      strokeColor = '#38bdf8';
      strokeWidth = 1.6;
    } else if (isCauses) {
      strokeColor = '#f59e0b';
      strokeWidth = 1.6;
    }

    return {
      id: e.id,
      source: e.source_node_id,
      target: e.target_node_id,
      sourceHandle,
      targetHandle,
      type: 'smart',
      label: e.relation_type,
      data: {
        offset,
        isContradiction,
        relation_type: e.relation_type,
      },
      style: {
        stroke: strokeColor,
        strokeWidth,
        strokeDasharray,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
        width: 14,
        height: 14,
      },
    };
  });

  return { nodes: layoutNodes, edges: layoutEdges };
}

// ── Main KnowledgeGraphCanvas Component ──────────────────────────────────────

export const KnowledgeGraphCanvas: React.FC<KnowledgeGraphCanvasProps> = ({
  sessionId,
  graph,
  onDivergeConcept,
  onFindCounterEvidence,
  onOpenEvidence,
  width,
  isEnlarged,
  onToggleEnlarge,
  onReconcileGraph,
}) => {
  const [activeTab, setActiveTab] = useState<'graph' | 'radar'>('graph');
  const [contradictions, setContradictions] = useState<ContradictionPair[]>([]);
  const [isLoadingContradictions, setIsLoadingContradictions] = useState(false);
  const [isReconciling, setIsReconciling] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [exportModalContent, setExportModalContent] = useState<{ title: string; text: string } | null>(null);
  const [layoutDirection, setLayoutDirection] = useState<'TB' | 'LR'>('TB');

  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);

  // Collect contradiction node IDs
  const contradictionIds = useMemo(() => {
    const set = new Set<string>();
    contradictions.forEach((c) => {
      if (c.source_node?.id) set.add(c.source_node.id);
      if (c.target_node?.id) set.add(c.target_node.id);
    });
    return set;
  }, [contradictions]);

  // Compute Dagre auto-layout
  const { nodes: computedNodes, edges: computedEdges } = useMemo(() => {
    return computeLayout(graph, contradictionIds, layoutDirection);
  }, [graph, contradictionIds, layoutDirection]);

  const [nodes, setNodes, onNodesChange] = useNodesState(computedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(computedEdges);

  // Sync state when computed elements change
  useEffect(() => {
    setNodes(computedNodes);
    setEdges(computedEdges);
  }, [computedNodes, computedEdges, setNodes, setEdges]);

  // Fit view when width changes
  const prevWidthRef = useRef(width);
  useEffect(() => {
    if (rfInstance && width && width !== prevWidthRef.current) {
      prevWidthRef.current = width;
      const timeout = setTimeout(() => {
        rfInstance.fitView({ padding: 0.25, duration: 300 });
      }, 50);
      return () => clearTimeout(timeout);
    }
  }, [width, rfInstance]);

  // Load contradictions whenever sessionId or graph updates
  const loadContradictions = useCallback(async () => {
    if (!sessionId) {
      setContradictions([]);
      return;
    }
    setIsLoadingContradictions(true);
    try {
      const data = await getSessionContradictions(sessionId);
      setContradictions(data);
    } catch (err) {
      console.error('Failed to load contradictions:', err);
    } finally {
      setIsLoadingContradictions(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadContradictions();
  }, [sessionId, graph, loadContradictions]);

  const onNodeClick = useCallback((_: any, node: Node) => {
    setSelectedNode((node.data as unknown) as GraphNode);
  }, []);

  const handleTidyLayout = () => {
    const layout = computeLayout(graph, contradictionIds, layoutDirection);
    setNodes(layout.nodes);
    setEdges(layout.edges);
    setTimeout(() => {
      rfInstance?.fitView({ padding: 0.25, duration: 400 });
    }, 50);
  };

  const handleToggleDirection = () => {
    setLayoutDirection((prev) => (prev === 'TB' ? 'LR' : 'TB'));
    setTimeout(() => {
      rfInstance?.fitView({ padding: 0.25, duration: 400 });
    }, 100);
  };

  const handleFitView = () => {
    rfInstance?.fitView({ padding: 0.25, duration: 400 });
  };

  const handleReconcile = async () => {
    if (!onReconcileGraph || isReconciling) return;
    setIsReconciling(true);
    try {
      await onReconcileGraph();
      setTimeout(() => {
        rfInstance?.fitView({ padding: 0.25, duration: 400 });
      }, 150);
    } catch (err) {
      console.error('Failed to reconcile graph:', err);
    } finally {
      setIsReconciling(false);
    }
  };

  // ── Graph Export Generators ──────────────────────────────────────────────────

  const handleExportMermaid = () => {
    if (!graph) return;
    let text = 'graph TD\n';
    graph.nodes.forEach((n) => {
      const cleanLabel = n.label.replace(/["\[\]]/g, '');
      text += `    ${n.id}["[${n.node_type.toUpperCase()}] ${cleanLabel}"]\n`;
    });
    graph.edges.forEach((e) => {
      text += `    ${e.source_node_id} -->|${e.relation_type}| ${e.target_node_id}\n`;
    });
    setExportModalContent({ title: 'Mermaid Diagram Definition', text });
    setExportMenuOpen(false);
  };

  const handleExportDownload = (format: 'markdown' | 'bibtex' | 'obsidian') => {
    if (!sessionId) return;
    triggerExportDownload(sessionId, format);
    setExportMenuOpen(false);
  };

  return (
    <aside
      style={{
        width: width ? `${width}px` : undefined,
        minWidth: width ? `${width}px` : undefined,
      }}
      className="h-screen flex flex-col bg-[#0a0a0c] border-l border-zinc-800 text-zinc-100 select-none relative shrink-0 overflow-hidden"
    >
      {/* ── Graph Header & Controls Bar ──────────────────────────── */}
      <div className="p-2.5 border-b border-zinc-800 bg-[#0c0c0e] flex items-center justify-between text-xs gap-2">
        {/* Tab Switcher: Knowledge Graph vs Contradiction Radar */}
        <div className="flex items-center gap-1 font-mono text-[11px] shrink-0">
          <button
            onClick={() => setActiveTab('graph')}
            className={`px-2 py-1 rounded-[2px] flex items-center gap-1.5 transition-colors ${
              activeTab === 'graph'
                ? 'bg-zinc-800 text-zinc-100 font-semibold border border-zinc-700'
                : 'text-zinc-400 hover:text-zinc-200 border border-transparent'
            }`}
          >
            <Network size={12} />
            <span>GRAPH</span>
            <span className="text-[10px] text-zinc-400">
              ({graph ? graph.nodes.length : 0})
            </span>
          </button>

          <button
            onClick={() => setActiveTab('radar')}
            className={`px-2 py-1 rounded-[2px] flex items-center gap-1.5 transition-colors ${
              activeTab === 'radar'
                ? 'bg-zinc-800 text-zinc-100 font-semibold border border-zinc-700'
                : 'text-zinc-400 hover:text-zinc-200 border border-transparent'
            }`}
          >
            <AlertTriangle
              size={12}
              className={contradictions.length > 0 ? 'text-red-400' : 'text-zinc-400'}
            />
            <span>RADAR</span>
            {contradictions.length > 0 && (
              <span className="bg-red-950/60 text-red-400 border border-red-800/80 px-1 py-0.2 rounded-[2px] text-[9px] font-mono">
                {contradictions.length}
              </span>
            )}
          </button>
        </div>

        {/* Graph Layout & Sizing Action Buttons */}
        <div className="flex items-center gap-1 font-mono text-[11px]">
          {activeTab === 'graph' && (
            <>
              {/* Flow Direction Toggle (TB / LR) */}
              <button
                onClick={handleToggleDirection}
                title={`Switch flow: ${layoutDirection === 'TB' ? 'Horizontal (LR)' : 'Vertical (TB)'}`}
                className="flex items-center gap-1 px-1.5 py-1 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 rounded-[2px] transition-colors"
              >
                {layoutDirection === 'TB' ? (
                  <>
                    <ArrowDown size={11} className="text-zinc-400" />
                    <span className="text-[10px]">TB</span>
                  </>
                ) : (
                  <>
                    <ArrowRight size={11} className="text-zinc-400" />
                    <span className="text-[10px]">LR</span>
                  </>
                )}
              </button>

              {/* Tidy / Rearrange Spacing */}
              <button
                onClick={handleTidyLayout}
                title="Tidy & Re-space Graph Elements"
                className="flex items-center gap-1 px-1.5 py-1 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 rounded-[2px] transition-colors"
              >
                <Sparkles size={11} className="text-zinc-400" />
                <span className="text-[10px] hidden sm:inline">Tidy</span>
              </button>

              {/* Unify / Connect Isolated Subgraphs */}
              {onReconcileGraph && (
                <button
                  onClick={handleReconcile}
                  disabled={isReconciling}
                  title="Unify Graph: Synthesize sensible links to connect any isolated subgraphs"
                  className="flex items-center gap-1 px-1.5 py-1 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 rounded-[2px] transition-colors disabled:opacity-50"
                >
                  <GitMerge size={11} className={`text-zinc-400 ${isReconciling ? 'animate-spin' : ''}`} />
                  <span className="text-[10px] hidden sm:inline">{isReconciling ? 'Linking...' : 'Unify'}</span>
                </button>
              )}

              {/* Auto Fit View */}
              <button
                onClick={handleFitView}
                title="Fit All Elements in View"
                className="p-1 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 rounded-[2px] transition-colors"
              >
                <Focus size={11} />
              </button>
            </>
          )}

          {/* Quick Enlarge / Restore Sidebar Width */}
          {onToggleEnlarge && (
            <button
              onClick={onToggleEnlarge}
              title={isEnlarged ? 'Restore standard sidebar width' : 'Enlarge graph sidebar to view details'}
              className={`p-1 border rounded-[2px] transition-colors ${
                isEnlarged
                  ? 'bg-zinc-800 text-zinc-100 border-zinc-600'
                  : 'bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border-zinc-800'
              }`}
            >
              {isEnlarged ? <Minimize2 size={11} /> : <Maximize2 size={11} />}
            </button>
          )}

          {/* Export Studio Dropdown */}
          <div className="relative">
            <button
              onClick={() => setExportMenuOpen(!exportMenuOpen)}
              disabled={!sessionId}
              className="flex items-center gap-1 px-2 py-1 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 rounded-[2px] transition-colors disabled:opacity-40"
            >
              <Download size={11} />
              <span className="hidden sm:inline">Export</span>
              <ChevronDown size={11} />
            </button>

            {exportMenuOpen && (
              <div className="absolute right-0 top-8 w-48 bg-[#121215] border border-zinc-700 rounded-[2px] shadow-lg py-1 z-30 font-mono text-[11px]">
                <button
                  onClick={() => handleExportDownload('markdown')}
                  className="w-full px-3 py-1.5 text-left text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 flex items-center gap-2"
                >
                  <FileText size={12} className="text-zinc-400" />
                  <span>Markdown Dossier (.md)</span>
                </button>
                <button
                  onClick={() => handleExportDownload('bibtex')}
                  className="w-full px-3 py-1.5 text-left text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 flex items-center gap-2"
                >
                  <BookMarked size={12} className="text-zinc-400" />
                  <span>BibTeX Citations (.bib)</span>
                </button>
                <button
                  onClick={() => handleExportDownload('obsidian')}
                  className="w-full px-3 py-1.5 text-left text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 flex items-center gap-2"
                >
                  <Share2 size={12} className="text-zinc-400" />
                  <span>Obsidian Canvas (.canvas)</span>
                </button>
                <div className="border-t border-zinc-800 my-1" />
                <button
                  onClick={handleExportMermaid}
                  className="w-full px-3 py-1.5 text-left text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100 flex items-center gap-2"
                >
                  <Network size={12} className="text-zinc-400" />
                  <span>Mermaid Diagram (code)</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Main Pane Views: Graph vs Contradiction Radar ────────── */}
      {activeTab === 'graph' ? (
        <div className="flex-1 w-full h-full relative">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onInit={setRfInstance}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            fitViewOptions={{ padding: 0.25 }}
            minZoom={0.15}
            maxZoom={2.5}
          >
            <Background color="#1f1f23" gap={24} size={1} />
            <Controls showInteractive={false} position="bottom-right" />
          </ReactFlow>

          {(!graph || graph.nodes.length === 0) && (
            <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-xs font-mono text-zinc-400 pointer-events-none">
              Graph will materialize as research turns progress...
            </div>
          )}
        </div>
      ) : (
        /* ── Contradiction Radar List View ─────────────────────── */
        <div className="flex-1 w-full h-full overflow-y-auto p-3.5 space-y-3 font-sans">
          <div className="flex items-center justify-between text-xs font-mono pb-2 border-b border-zinc-800 text-zinc-400">
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-zinc-200 uppercase tracking-wide">
                DISPUTED CLAIMS RADAR
              </span>
              <span>({contradictions.length})</span>
            </div>
            <button
              onClick={loadContradictions}
              disabled={isLoadingContradictions}
              className="p-1 hover:text-zinc-200 transition-colors"
              title="Refresh contradictions"
            >
              <RefreshCw
                size={11}
                className={isLoadingContradictions ? 'animate-spin' : ''}
              />
            </button>
          </div>

          {contradictions.length === 0 ? (
            <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-zinc-400 space-y-2">
              <AlertTriangle size={24} className="text-zinc-600 stroke-[1.5]" />
              <div className="font-mono text-xs text-zinc-300">
                NO CONTRADICTIONS DETECTED
              </div>
              <p className="text-[11px] leading-relaxed max-w-xs text-zinc-400">
                Cross-examination across current evidence chunks and agent claims found
                no conflicting positions. Use counter-evidence search to stress-test claims.
              </p>
            </div>
          ) : (
            contradictions.map((pair, idx) => (
              <div
                key={pair.edge_id || idx}
                className="bg-[#101013] border border-red-900/40 rounded-[3px] p-3 space-y-2.5 text-xs text-zinc-200"
              >
                <div className="flex items-center justify-between font-mono text-[10px] text-zinc-400 border-b border-zinc-800/80 pb-1.5">
                  <span className="font-semibold text-red-400">
                    CONFLICT #{idx + 1}
                  </span>
                  <span>CONFIDENCE: {Math.round(pair.weight * 100)}%</span>
                </div>

                {/* Side-by-Side Contested Claims */}
                <div className="space-y-2">
                  <div className="p-2 bg-[#16161a] border border-zinc-800 rounded-[2px] space-y-1">
                    <div className="flex items-center justify-between font-mono text-[9px] text-zinc-400">
                      <span className="font-semibold uppercase text-zinc-300">
                        [{pair.source_node.type}] CLAIM A
                      </span>
                      <span className="truncate max-w-[120px]">{pair.source_node.id}</span>
                    </div>
                    <div className="text-xs text-zinc-100 font-medium leading-snug">
                      {pair.source_node.label}
                    </div>
                    {pair.source_node.description && (
                      <div className="text-[10px] font-mono text-zinc-400 leading-tight">
                        {pair.source_node.description}
                      </div>
                    )}
                  </div>

                  <div className="text-center font-mono text-[10px] text-red-400 tracking-wider">
                    ⟷ CONFLICTS WITH ⟷
                  </div>

                  <div className="p-2 bg-[#16161a] border border-zinc-800 rounded-[2px] space-y-1">
                    <div className="flex items-center justify-between font-mono text-[9px] text-zinc-400">
                      <span className="font-semibold uppercase text-zinc-300">
                        [{pair.target_node.type}] CLAIM B
                      </span>
                      <span className="truncate max-w-[120px]">{pair.target_node.id}</span>
                    </div>
                    <div className="text-xs text-zinc-100 font-medium leading-snug">
                      {pair.target_node.label}
                    </div>
                    {pair.target_node.description && (
                      <div className="text-[10px] font-mono text-zinc-400 leading-tight">
                        {pair.target_node.description}
                      </div>
                    )}
                  </div>
                </div>

                {/* Evidence Context */}
                {pair.evidence_text && (
                  <div className="p-2 bg-zinc-950/80 border border-zinc-800/80 rounded-[2px] text-[10px] font-mono text-zinc-400 leading-relaxed">
                    <span className="text-zinc-400 font-semibold uppercase mr-1">
                      EXTRACTED DISPUTE:
                    </span>
                    {pair.evidence_text}
                  </div>
                )}

                {/* Actions */}
                <div className="pt-1 flex gap-2 font-mono text-[10px]">
                  <button
                    onClick={() =>
                      onDivergeConcept(
                        `Investigate conflict: "${pair.source_node.label}" vs "${pair.target_node.label}". What evidence explains or resolves this disparity?`
                      )
                    }
                    className="flex-1 px-2 py-1.5 bg-zinc-100 hover:bg-zinc-300 text-zinc-950 font-medium rounded-[2px] flex items-center justify-center gap-1 transition-colors"
                  >
                    <GitFork size={11} />
                    <span>Investigate Dispute</span>
                  </button>
                  <button
                    onClick={() => onOpenEvidence(pair.source_node.label)}
                    className="px-2 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-750 rounded-[2px] flex items-center gap-1 transition-colors"
                  >
                    <ExternalLink size={10} />
                    <span>Evidence</span>
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* ── Selected Node Inspector Drawer (Precision Utilitarian) ─ */}
      {selectedNode && activeTab === 'graph' && (
        <div className="border-t border-zinc-800 bg-[#0d0d10] p-3.5 space-y-2.5 text-xs font-sans max-h-56 overflow-y-auto">
          <div className="flex items-center justify-between font-mono text-[10px] text-zinc-400">
            <span className="font-semibold uppercase text-zinc-200">
              [{selectedNode.node_type}] {selectedNode.id}
            </span>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-zinc-400 hover:text-zinc-200"
            >
              Close
            </button>
          </div>

          <div className="font-semibold text-zinc-100 text-xs leading-snug">
            {selectedNode.label}
          </div>

          {selectedNode.description && (
            <p className="text-[11px] text-zinc-300 font-sans leading-relaxed">
              {selectedNode.description}
            </p>
          )}

          {/* Action Buttons for Deviation & Backtracking */}
          <div className="pt-2 border-t border-zinc-800 flex gap-2 font-mono text-[10px]">
            <button
              onClick={() => onDivergeConcept(selectedNode.label)}
              className="flex-1 px-2 py-1.5 bg-zinc-100 hover:bg-zinc-300 text-zinc-950 font-medium rounded-[2px] flex items-center justify-center gap-1.5 transition-colors"
            >
              <GitFork size={11} />
              <span>Diverge Research</span>
            </button>
            <button
              onClick={() => onFindCounterEvidence(selectedNode.label)}
              className="px-2 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-700 rounded-[2px] flex items-center gap-1 transition-colors"
            >
              <AlertTriangle size={11} className="text-amber-400" />
              <span>Counter-Evidence</span>
            </button>
          </div>
        </div>
      )}

      {/* ── Export Modal Popup (Mermaid / Code) ────────────────────── */}
      {exportModalContent && (
        <div className="absolute inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
          <div className="bg-[#121215] border border-zinc-700 rounded-[3px] p-4 w-full max-w-md space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between text-zinc-200 font-semibold">
              <span>{exportModalContent.title}</span>
              <button
                onClick={() => setExportModalContent(null)}
                className="text-zinc-400 hover:text-zinc-200"
              >
                ✕
              </button>
            </div>
            <textarea
              readOnly
              rows={10}
              value={exportModalContent.text}
              className="w-full bg-[#09090b] border border-zinc-800 p-2 text-[11px] text-zinc-300 font-mono rounded-[2px] focus:outline-none"
            />
            <button
              onClick={() => {
                navigator.clipboard.writeText(exportModalContent.text);
                alert('Copied to clipboard!');
              }}
              className="w-full py-1.5 bg-zinc-200 text-zinc-950 font-semibold rounded-[2px] hover:bg-zinc-300"
            >
              Copy to Clipboard
            </button>
          </div>
        </div>
      )}
    </aside>
  );
};
