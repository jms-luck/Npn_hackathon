import { ExternalLink, GitBranch, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { api } from "../api/client";


export default function GitHubEvidencePanel({ githubUrl }) {
  const [evidence, setEvidence] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function verify() {
    setLoading(true);
    setError("");
    try {
      setEvidence(await api("/candidate/github-evaluation", { method: "POST" }));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return <section className="github-panel">
    <div className="github-heading"><div><p className="eyebrow">Public project evidence</p><h2>GitHub verification</h2><p>{githubUrl || "No GitHub profile is attached to this candidate."}</p></div>{githubUrl && <button className="primary" onClick={verify} disabled={loading}><GitBranch />{loading ? "Verifying..." : "Verify projects"}</button>}</div>
    {error && <p className="error">{error}</p>}
    {!evidence && githubUrl && !error && <p className="notice">Verify that the public profile resolves and compare repository metadata with your latest resume.</p>}
    {evidence && <div className="github-results">
      <div className={evidence.verified ? "github-status verified" : "github-status"}><ShieldCheck /><small>PROFILE STATUS</small><strong>{evidence.verification_status.replaceAll("_", " ")}</strong><a href={evidence.profile_url} target="_blank" rel="noreferrer">@{evidence.username}<ExternalLink /></a></div>
      <dl><div><dt>Resume project relevance</dt><dd>{evidence.relevance_score}%</dd></div><div><dt>Public repositories</dt><dd>{evidence.public_repositories}</dd></div><div><dt>Recently active</dt><dd>{evidence.recently_active_repositories}</dd></div><div><dt>Evidence source</dt><dd>Latest parsed resume</dd></div></dl>
      <div className="github-repositories"><small>STRONGEST REPOSITORY EVIDENCE</small>{evidence.repositories.length ? evidence.repositories.map(repository => <a href={repository.url} target="_blank" rel="noreferrer" key={repository.url}><span><strong>{repository.name}</strong><small>{repository.language || "Language not reported"} · {repository.matched_terms.join(", ") || "No explicit term overlap"}</small></span><b>{repository.relevance_score}%</b><ExternalLink /></a>) : <p>No public, non-fork repositories were available.</p>}</div>
      <p className="github-disclaimer">{evidence.disclaimer}</p>
    </div>}
  </section>;
}