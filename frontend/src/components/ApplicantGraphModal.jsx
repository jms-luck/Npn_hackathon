import { X } from "lucide-react";

import { SuitabilityEvidence } from "./SuitabilityExplanation";


const colors = { Candidate: "#c9f06b", Resume: "#f4bb60", Job: "#74b9ff", Company: "#ff8f70", Skill: "#d9d2ff" };

function nodeColor(node) {
  if (node.type !== "Skill") return colors[node.type] || "#ddd";
  return node.properties?.matched ? "#b9e6c8" : "#ffc9c2";
}


export default function ApplicantGraphModal({ data, onClose }) {
  const nodes = data?.graph?.nodes || [];
  const edges = data?.graph?.edges || [];
  const width = 900;
  const height = 560;
  const center = { x: 450, y: 280 };
  const radius = Math.min(220, 140 + nodes.length * 4);
  const positions = new Map(nodes.map((node, index) => node.type === "Candidate"
    ? [node.id, center]
    : [node.id, {
      x: center.x + Math.cos((index - 1) * Math.PI * 2 / Math.max(1, nodes.length - 1)) * radius,
      y: center.y + Math.sin((index - 1) * Math.PI * 2 / Math.max(1, nodes.length - 1)) * radius,
    }]));

  return <div className="modal-backdrop graph-backdrop"><section className="graph-modal">
    <button className="icon modal-close" onClick={onClose} aria-label="Close applicant graph"><X /></button>
    <div className="graph-head"><div><p className="eyebrow">Neo4j applicant relationship graph</p><h2>{data.candidate_name}</h2><p>{data.explanation}</p></div><div className="graph-score"><strong>{data.semantic_score == null ? "--" : `${data.semantic_score.toFixed(1)}%`}</strong><small>SEMANTIC MATCH</small></div></div>
    <SuitabilityEvidence explanation={data.explainability} />
    <div className="graph-canvas"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Relationship graph for ${data.candidate_name}`}>
      <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#789087" /></marker><marker id="match-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#2f7d5d" /></marker><marker id="gap-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#b74843" /></marker></defs>
      {edges.map((edge, index) => {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) return null;
        const middleX = (from.x + to.x) / 2;
        const middleY = (from.y + to.y) / 2;
        const isGap = edge.type === "MISSING_SKILL";
        const isMatch = edge.type === "HAS_SKILL";
        const stroke = isGap ? "#b74843" : isMatch ? "#2f7d5d" : "#789087";
        const marker = isGap ? "url(#gap-arrow)" : isMatch ? "url(#match-arrow)" : "url(#arrow)";
        return <g key={`${edge.type}-${index}`}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={stroke} strokeWidth={isGap || isMatch ? 3 : 2} strokeDasharray={isGap ? "8 5" : undefined} markerEnd={marker} /><text x={middleX} y={middleY - 6} textAnchor="middle" className={`edge-label ${isGap ? "gap" : isMatch ? "match" : ""}`}>{edge.type.replaceAll("_", " ")}</text></g>;
      })}
      {nodes.map(node => {
        const point = positions.get(node.id);
        return <g key={node.id} transform={`translate(${point.x},${point.y})`}><circle r={node.type === "Candidate" ? 44 : 34} fill={nodeColor(node)} stroke="#173f35" strokeWidth="3" /><text textAnchor="middle" y="-3" className="node-type">{node.type}</text><text textAnchor="middle" y="14" className="node-label">{node.label.length > 20 ? `${node.label.slice(0, 18)}...` : node.label}</text></g>;
      })}
    </svg></div><div className="graph-legend"><span><i className="matched" /> Candidate has skill</span><span><i className="gap" /> Skill gap</span><span><i className="required" /> Job requirement</span></div>
    <div className="graph-evidence"><div><small>MATCHED SKILLS</small><p>{data.matched_skills?.length ? data.matched_skills.join(", ") : "No explicit skill matches verified"}</p></div><div><small>MISSING / UNVERIFIED</small><p>{data.missing_skills?.length ? data.missing_skills.join(", ") : "None"}</p></div><span className="pill">{data.source === "neo4j" ? "LIVE NEO4J" : "RELATIONAL FALLBACK"}</span></div>
  </section></div>;
}