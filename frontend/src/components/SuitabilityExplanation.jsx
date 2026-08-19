import { AlertTriangle, CheckCircle2, X } from "lucide-react";


export function SuitabilityEvidence({ explanation }) {
  if (!explanation) return null;
  return <div className="xai-evidence">
    <div className="xai-summary">
      <div><p className="eyebrow">Explainable suitability</p><h3>{explanation.summary}</h3></div>
      <div className="xai-overall"><strong>{explanation.overall_score == null ? "--" : `${explanation.overall_score.toFixed(1)}%`}</strong><small>{explanation.fit_level} FIT</small></div>
    </div>
    <div className="xai-factors">{explanation.factors.map(factor => <div className="xai-factor" key={factor.name}><div><strong>{factor.name}</strong><span>{factor.weight ? `${factor.weight}% weight` : "Diagnostic evidence"}</span></div><div className="xai-factor-score"><div><i style={{ width: `${factor.score || 0}%` }} /></div><b>{factor.score == null ? "--" : `${factor.score.toFixed(1)}%`}</b></div><p>{factor.evidence}</p></div>)}</div>
    <div className="xai-findings"><section><h4><CheckCircle2 /> Evidence supporting fit</h4>{explanation.strengths.map(item => <p key={item}>{item}</p>)}</section><section><h4><AlertTriangle /> Gaps to validate</h4>{explanation.gaps.map(item => <p key={item}>{item}</p>)}</section></div>
    {explanation.narrative && <div className="xai-narrative"><small>AI-GENERATED NARRATIVE</small><p>{explanation.narrative}</p></div>}
    <p className="xai-disclaimer">{explanation.disclaimer}</p>
  </div>;
}


export default function SuitabilityModal({ data, onClose }) {
  return <div className="modal-backdrop"><section className="admin-modal suitability-modal"><button className="icon modal-close" onClick={onClose} aria-label="Close explanation"><X /></button><p className="eyebrow">Interview preparation</p><h2>{data.candidate_name}</h2><p className="page-description">Suitability for {data.job_title}</p><SuitabilityEvidence explanation={data} /></section></div>;
}