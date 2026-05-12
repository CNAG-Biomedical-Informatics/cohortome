import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { PhenoFile } from "../../api/types";

type GraphNode = {
  id: string;
  label: string;
};

type GraphEdge = {
  source: string;
  target: string;
  weight: number | null;
};

export function PhenoGraphPreview({ file, metric }: { file: PhenoFile; metric: string }) {
  const [showLabels, setShowLabels] = useState("selected");
  const query = useQuery({
    queryKey: ["pheno-graph", file.url],
    queryFn: async () => {
      const response = await fetch(file.url, { credentials: "same-origin" });
      if (!response.ok) throw new Error("Unable to load graph data.");
      return response.json();
    },
  });

  const graph = useMemo(() => normalizeCytoscapeGraph(query.data), [query.data]);
  const edges = graph.edges.slice(0, 160);
  const nodes = graph.nodes.slice(0, 80);
  const positions = circularLayout(nodes, 760, 420);
  const weights = edges.map((edge) => edge.weight).filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const min = weights.length ? Math.min(...weights) : 0;
  const max = weights.length ? Math.max(...weights) : 1;

  if (query.isLoading) return <div className="empty">Loading graph...</div>;
  if (query.error) return <div className="empty">{(query.error as Error).message}</div>;
  if (!nodes.length) return <div className="empty">Graph file did not contain nodes.</div>;

  return (
    <div>
      <div className="pheno-graph-controls">
        <label className="pheno-graph-select-label">
          <span>Edge values</span>
          <select value={showLabels} onChange={(event) => setShowLabels(event.target.value)}>
            <option value="off">Off</option>
            <option value="selected">Key edges</option>
            <option value="visible">Visible</option>
          </select>
        </label>
        <div className="section-note-inline">
          Showing {nodes.length} nodes and {edges.length} edges. Line width encodes edge value.
        </div>
      </div>
      <svg className="react-pheno-graph" viewBox="0 0 760 420" role="img" aria-label="Pheno-Ranker graph preview">
        {edges.map((edge, index) => {
          const source = positions.get(edge.source);
          const target = positions.get(edge.target);
          if (!source || !target) return null;
          const width = edgeWidth(edge.weight, min, max);
          const color = edgeColor(edge.weight, metric);
          const labelVisible = showLabels === "visible" || (showLabels === "selected" && index < 20);
          const midX = (source.x + target.x) / 2;
          const midY = (source.y + target.y) / 2;
          return (
            <g key={`${edge.source}-${edge.target}-${index}`}>
              <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} stroke={color} strokeWidth={width} strokeOpacity="0.72" />
              {labelVisible && typeof edge.weight === "number" ? (
                <text x={midX} y={midY} className="react-pheno-edge-label">{formatWeight(edge.weight)}</text>
              ) : null}
            </g>
          );
        })}
        {nodes.map((node) => {
          const position = positions.get(node.id);
          if (!position) return null;
          return (
            <g key={node.id}>
              <circle cx={position.x} cy={position.y} r="7" />
              <text x={position.x + 10} y={position.y + 4}>{node.label}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function normalizeCytoscapeGraph(raw: unknown): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const elements = Array.isArray((raw as { elements?: unknown })?.elements)
    ? (raw as { elements: unknown[] }).elements
    : Array.isArray((raw as { elements?: { nodes?: unknown[]; edges?: unknown[] } })?.elements?.nodes)
      ? [...((raw as { elements: { nodes?: unknown[]; edges?: unknown[] } }).elements.nodes || []), ...((raw as { elements: { nodes?: unknown[]; edges?: unknown[] } }).elements.edges || [])]
      : [];
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  for (const item of elements) {
    const data = (item as { data?: Record<string, unknown> })?.data || {};
    const id = String(data.id || data.name || "").trim();
    const source = String(data.source || "").trim();
    const target = String(data.target || "").trim();
    if (source && target) {
      const rawWeight = data.weight ?? data.value ?? data.distance ?? data.similarity;
      const weight = typeof rawWeight === "number" ? rawWeight : Number(rawWeight);
      edges.push({ source, target, weight: Number.isFinite(weight) ? weight : null });
    } else if (id) {
      nodes.push({ id, label: String(data.label || data.name || id) });
    }
  }
  return { nodes, edges };
}

function circularLayout(nodes: GraphNode[], width: number, height: number): Map<string, { x: number; y: number }> {
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) * 0.38;
  const positions = new Map<string, { x: number; y: number }>();
  nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1);
    positions.set(node.id, {
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius,
    });
  });
  return positions;
}

function edgeWidth(weight: number | null, min: number, max: number): number {
  if (typeof weight !== "number" || !Number.isFinite(weight) || max <= min) return 1.5;
  return 1.5 + ((weight - min) / (max - min)) * 5;
}

function edgeColor(weight: number | null, metric: string): string {
  if (typeof weight !== "number") return "#64748b";
  if (metric === "jaccard" && weight === 1) return "#111827";
  if (metric !== "jaccard" && weight === 0) return "#111827";
  return "#2563eb";
}

function formatWeight(weight: number): string {
  return Number.isInteger(weight) ? String(weight) : weight.toFixed(3);
}
