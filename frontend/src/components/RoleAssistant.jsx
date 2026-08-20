import { Bot, Send, X } from "lucide-react";
import { useState } from "react";

import { api } from "../api/client";


const roleCopy = {
  CANDIDATE: ["Candidate guide", "Applications, resumes, and job matches"],
  RECRUITER: ["Recruiter guide", "Jobs, applicants, verification, and scheduling"],
  INTERVIEWER: ["Interview guide", "Assigned candidates, evidence, and feedback"],
  ADMIN: ["Admin guide", "Platform records, governance, and audit"],
};


export default function RoleAssistant({ role }) {
  const [open, setOpen] = useState(false); const [message, setMessage] = useState(""); const [reply, setReply] = useState(null); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  const [title, subtitle] = roleCopy[role];
  async function send(text = message) { if (!text.trim()) return; setLoading(true); setError(""); try { setReply(await api("/assistant/chat", { method: "POST", body: JSON.stringify({ message: text }) })); setMessage(""); } catch (requestError) { setError(requestError.message); } finally { setLoading(false); } }
  return <div className={`role-assistant ${role.toLowerCase()}`}><button className="assistant-launch" onClick={() => setOpen(value => !value)} aria-label={`${open ? "Close" : "Open"} ${title}`}><Bot /></button>{open && <section className="assistant-panel"><header><div><strong>{title}</strong><small>{subtitle}</small></div><button className="icon" onClick={() => setOpen(false)}><X /></button></header><div className="assistant-body">{reply ? <><p>{reply.answer}</p><div className="assistant-suggestions">{reply.suggestions.map(item => <button key={item} onClick={() => send(item)}>{item}</button>)}</div><small>{reply.scope}</small></> : <p>Ask a question about the tools and records available to your role.</p>}{error && <p className="error">{error}</p>}</div><form onSubmit={event => { event.preventDefault(); send(); }}><input value={message} onChange={event => setMessage(event.target.value)} maxLength="500" placeholder="Ask your workspace assistant..." /><button className="icon" disabled={loading} aria-label="Send"><Send /></button></form></section>}</div>;
}