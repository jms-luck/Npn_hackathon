import { useEffect, useState } from "react";
import { ExternalLink, RefreshCw, Trophy } from "lucide-react";

import { api } from "../api/client";


export default function DsaStrengthPanel() {
  const [evaluation, setEvaluation] = useState(null);
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/candidate/dsa-evaluation")
      .then(result => { setEvaluation(result); setValue(result.username); })
      .catch(requestError => {
        if (!requestError.message.includes("No DSA evaluation")) setError(requestError.message);
      });
  }, []);

  async function evaluate(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await api("/candidate/dsa-evaluation", {
        method: "POST",
        body: JSON.stringify({ username_or_url: value }),
      });
      setEvaluation(result);
      setValue(result.username);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return <section className="dsa-panel">
    <div className="dsa-heading">
      <div><p className="eyebrow">Verified problem-solving signal</p><h2>DSA core strength</h2></div>
      {evaluation && <a className="dsa-profile-link" href={evaluation.profile_url} target="_blank" rel="noreferrer">@{evaluation.username}<ExternalLink /></a>}
    </div>
    <form className="dsa-form" onSubmit={evaluate}>
      <label>LeetCode username or profile URL<input value={value} onChange={event => setValue(event.target.value)} placeholder="username or leetcode.com/u/username" required /></label>
      <button className="primary" disabled={loading}>{loading ? <><RefreshCw className="spin" /> Evaluating...</> : <><Trophy /> {evaluation ? "Re-evaluate" : "Evaluate strength"}</>}</button>
    </form>
    {error && <p className="error">{error}</p>}
    {!evaluation && !error && <p className="notice">Run an evaluation to see topic coverage, difficulty depth, and improvement priorities.</p>}
    {evaluation && <div className="dsa-results">
      <div className="dsa-score-block"><small>CORE SCORE</small><strong>{evaluation.score}</strong><span>/ 100</span><b>{evaluation.level}</b></div>
      <div className="dsa-summary">
        <div className="difficulty-strip"><span><small>SOLVED</small><strong>{evaluation.total_solved}</strong></span>{Object.entries(evaluation.difficulty).map(([level, count]) => <span key={level}><small>{level}</small><strong>{count}</strong></span>)}</div>
        <div className="dsa-lists"><div><small>STRONGEST</small><p>{evaluation.strongest_topics.join(" · ") || "More evidence needed"}</p></div><div><small>NEXT FOCUS</small><p>{evaluation.focus_topics.join(" · ") || "Core targets reached"}</p></div></div>
      </div>
      <div className="topic-grid">{evaluation.topics.map(topic => <div className="topic-row" key={topic.slug}><div><span>{topic.name}</span><small>{topic.solved} / {topic.target}</small></div><div className="topic-track"><i style={{ width: `${topic.strength}%` }} /></div><strong>{topic.strength}%</strong></div>)}</div>
      {evaluation.recent_solved.length > 0 && <div className="recent-problems"><small>RECENT ACCEPTED</small><div>{evaluation.recent_solved.slice(0, 5).map((problem, index) => <a href={problem.url} target="_blank" rel="noreferrer" key={`${problem.url}-${index}`}>{problem.title}<ExternalLink /></a>)}</div></div>}
      <p className="dsa-method">{evaluation.methodology}</p>
    </div>}
  </section>;
}