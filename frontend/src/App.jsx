import { useEffect, useState } from "react";
import { BriefcaseBusiness, Database, Download, FileSpreadsheet, FileText, Gauge, GitBranch, Lightbulb, LogOut, Menu, Plus, Search, Sparkles, Upload, Users, X } from "lucide-react";
import { Navigate, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { api, apiBlob } from "./api/client";
import AdminPanel from "./components/AdminPanel";
import ApplicantGraphModal from "./components/ApplicantGraphModal";
import DsaStrengthPanel from "./components/DsaStrengthPanel";
import SuitabilityModal from "./components/SuitabilityExplanation";
import { useAuth } from "./context/AuthContext";
import { formatJobId } from "./utils/publicIds";

const navByRole = {
  CANDIDATE: [["Dashboard", "/candidate/dashboard", Gauge], ["Job matches", "/candidate/matches", Sparkles], ["All jobs", "/candidate/jobs", Search], ["Resumes", "/candidate/resumes", FileText], ["Applications", "/candidate/applications", BriefcaseBusiness]],
  RECRUITER: [["Dashboard", "/recruiter/dashboard", Gauge], ["My jobs", "/recruiter/jobs", BriefcaseBusiness], ["Create job", "/recruiter/jobs/create", Plus]],
  INTERVIEWER: [["Dashboard", "/interviewer/dashboard", Gauge], ["Candidates", "/interviewer/candidates", Users]],
  ADMIN: [["Dashboard", "/admin/dashboard", Gauge], ["All data", "/admin/data", Database]],
};

function Shell({ children }) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  return <div className="shell">
    <aside className={open ? "sidebar open" : "sidebar"}>
      <div className="brand"><span>HA</span><strong>Hire<br />AI</strong></div>
      <button className="icon close" onClick={() => setOpen(false)} aria-label="Close navigation"><X /></button>
      <nav>{navByRole[user.role].map(([label, path, Icon]) => <NavLink key={path} to={path} onClick={() => setOpen(false)}><Icon />{label}</NavLink>)}</nav>
      <div className="account"><div className="avatar">{user.name.slice(0, 2).toUpperCase()}</div><div><strong>{user.name}</strong><small>{user.role.toLowerCase()}</small></div><button className="icon" onClick={logout} title="Log out"><LogOut /></button></div>
    </aside>
    <main><header className="topbar"><button className="icon menu" onClick={() => setOpen(true)} aria-label="Open navigation"><Menu /></button><span>Talent intelligence workspace</span><span className="status"><i /> Systems ready</span></header>{children}</main>
  </div>;
}

function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [role, setRole] = useState("CANDIDATE");
  async function submit(event) {
    event.preventDefault(); setError("");
    const form = new FormData(event.currentTarget);
    try { const current = await login(form.get("email"), form.get("password"), role); navigate(`/${current.role.toLowerCase()}/dashboard`); } catch (err) { setError(err.message); }
  }
  if (user) return <Navigate to={`/${user.role.toLowerCase()}/dashboard`} />;
  return <div className="auth-page"><section className="auth-copy"><div className="brand light"><span>HA</span><strong>Hire AI</strong></div><p className="eyebrow">Evidence-led hiring</p><h1>Find the signal.<br />Build the team.</h1><p>One workspace for candidates and hiring teams to make clearer, faster decisions.</p></section><form className="auth-form" onSubmit={submit}><p className="eyebrow">Welcome back</p><h2>Sign in to continue</h2><div className="segments four" role="group" aria-label="Sign in role">{["CANDIDATE", "RECRUITER", "INTERVIEWER", "ADMIN"].map(item => <button type="button" key={item} className={role === item ? "active" : ""} onClick={() => setRole(item)}>{item.toLowerCase()}</button>)}</div><label>Email<input name="email" type="email" autoComplete="email" required /></label><label>Password<input name="password" type="password" autoComplete="current-password" required /></label>{error && <p className="error">{error}</p>}<button className="primary">Sign in as {role.toLowerCase()}</button><p className="auth-switch">New to Hire AI? <NavLink to="/register">Create an account</NavLink></p></form></div>;
}

function Register({ initialType = "candidate" }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [accountType, setAccountType] = useState(initialType);
  const [companies, setCompanies] = useState([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!["recruiter", "interviewer"].includes(accountType)) return;
    api("/companies/options").then(setCompanies).catch(err => setError(err.message));
  }, [accountType]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    const form = new FormData(event.currentTarget);
    if (form.get("password") !== form.get("confirm_password")) {
      setError("Passwords do not match");
      return;
    }
    const payload = Object.fromEntries(form);
    delete payload.confirm_password;
    if (["recruiter", "interviewer"].includes(accountType)) payload.company_id = Number(payload.company_id);
    else delete payload.company_id;
    setSubmitting(true);
    try {
      await api(`/auth/register/${accountType}`, { method: "POST", body: JSON.stringify(payload) });
      navigate("/login");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (user) return <Navigate to={`/${user.role.toLowerCase()}/dashboard`} />;
  const isStaff = ["recruiter", "interviewer"].includes(accountType);
  return <div className="auth-page register-page"><section className="auth-copy"><div className="brand light"><span>HA</span><strong>Hire AI</strong></div><p className="eyebrow">Your next chapter</p><h1>Make your move.<br />Meet your match.</h1><p>Build a candidate profile or open a hiring workspace for your company.</p></section><form className="auth-form register-form" onSubmit={submit}><p className="eyebrow">Join Hire AI</p><h2>Create your account</h2><div className="segments three" role="group" aria-label="Account type">{["candidate", "recruiter", "interviewer"].map(item => <button type="button" key={item} className={accountType === item ? "active" : ""} onClick={() => setAccountType(item)}>{item}</button>)}</div><div className="register-fields"><label>Full name<input name="name" required /></label><label>Email<input name="email" type="email" required /></label><label>Phone<input name="phone" type="tel" /></label>{accountType === "candidate" && <><label>Location<input name="location" /></label><label>LinkedIn (username or URL)<input name="linkedin_url" placeholder="jane-doe or linkedin.com/in/jane-doe" /></label><label>GitHub (username or URL)<input name="github_url" placeholder="janedoe or github.com/janedoe" /></label></>}{isStaff && <><label>Company<select name="company_id" required defaultValue=""><option value="" disabled>Select company</option>{companies.map(company => <option key={company.company_id} value={company.company_id}>{company.company_name}</option>)}</select></label><label>Designation<input name="designation" /></label><label>Verification code<input name="verification_code" required /></label></>}<label>Password<input name="password" type="password" minLength="8" required /></label><label>Confirm password<input name="confirm_password" type="password" minLength="8" required /></label></div>{error && <p className="error">{error}</p>}<button className="primary" disabled={submitting}>{submitting ? "Creating account..." : `Create ${accountType} account`}</button><p className="auth-switch">Already registered? <NavLink to="/login">Sign in</NavLink></p></form></div>;
}

function Protected({ children, roles }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center">Loading workspace...</div>;
  if (!user) return <Navigate to="/login" />;
  if (roles && !roles.includes(user.role)) return <Navigate to={`/${user.role.toLowerCase()}/dashboard`} />;
  return <Shell>{children}</Shell>;
}

function Page({ eyebrow, title, action, children }) { return <div className="page"><div className="page-head"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div>{action}</div>{children}</div>; }
function Empty({ title, text }) { return <div className="empty"><FileText /><h3>{title}</h3><p>{text}</p></div>; }

function compareValues(left, right) {
  if (left == null) return 1;
  if (right == null) return -1;
  if (!Number.isNaN(Number(left)) && !Number.isNaN(Number(right))) return Number(left) - Number(right);
  const leftDate = Date.parse(left); const rightDate = Date.parse(right);
  if (!Number.isNaN(leftDate) && !Number.isNaN(rightDate) && String(left).includes("-")) return leftDate - rightDate;
  return String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
}

function useListView(items, defaultSort, filterField) {
  const [query, setQuery] = useState(""); const [sort, setSort] = useState(defaultSort); const [order, setOrder] = useState("asc"); const [filter, setFilter] = useState("");
  const filters = filterField ? [...new Set(items.map(item => item[filterField]).filter(Boolean))].sort() : [];
  const visible = items.filter(item => !query || JSON.stringify(item).toLowerCase().includes(query.toLowerCase())).filter(item => !filter || item[filterField] === filter).sort((a, b) => compareValues(a[sort], b[sort]) * (order === "asc" ? 1 : -1));
  return { query, setQuery, sort, setSort, order, setOrder, filter, setFilter, filters, visible };
}

function ListControls({ view, sortOptions, placeholder = "Filter results..." }) {
  return <div className="list-controls"><label>Search<input value={view.query} onChange={event => view.setQuery(event.target.value)} placeholder={placeholder} /></label>{view.filters.length > 0 && <label>Filter<select value={view.filter} onChange={event => view.setFilter(event.target.value)}><option value="">All</option>{view.filters.map(item => <option key={item} value={item}>{item}</option>)}</select></label>}<label>Sort<select value={view.sort} onChange={event => view.setSort(event.target.value)}>{sortOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Order<select value={view.order} onChange={event => view.setOrder(event.target.value)}><option value="asc">Ascending</option><option value="desc">Descending</option></select></label><span>{view.visible.length} results</span></div>;
}

const publicJobPageCache = new Map();
function loadPublicJobPage(path) {
  const cached = publicJobPageCache.get(path);
  if (cached && cached.expiresAt > Date.now()) return cached.promise;
  const promise = api(path).catch(error => { publicJobPageCache.delete(path); throw error; });
  publicJobPageCache.set(path, { promise, expiresAt: Date.now() + 30_000 });
  return promise;
}

function Dashboard() {
  const { user } = useAuth();
  const [profile, setProfile] = useState(null); const [profileError, setProfileError] = useState("");
  useEffect(() => { api("/auth/profile").then(setProfile).catch(error => setProfileError(error.message)); }, []);
  const copy = { CANDIDATE: ["Candidate command center", "Track applications and discover work that fits."], RECRUITER: ["Hiring command center", "Move from open role to strong shortlist."], INTERVIEWER: ["Interview command center", "Keep every conversation focused and useful."], ADMIN: ["Administration command center", "Review platform data and protected company settings."] }[user.role];
  const hidden = new Set(["role", "name", "email", "default_admin"]); const fields = profile ? Object.entries(profile).filter(([key, value]) => !hidden.has(key) && value != null && value !== "") : [];
  return <Page eyebrow={copy[0]} title={`Good to see you, ${user.name.split(" ")[0]}.`}><div className="metric-grid"><article><small>WORKSPACE</small><strong>Ready</strong><p>{copy[1]}</p></article><article><small>FOCUS</small><strong>{user.role === "CANDIDATE" ? "Opportunities" : user.role === "ADMIN" ? "Governance" : "People"}</strong><p>Use the navigation to continue your workflow.</p></article><article className="accent"><small>{user.role === "ADMIN" ? "ACCESS" : "AI MATCHING"}</small><strong>{user.role === "ADMIN" ? "Protected" : "Semantic"}</strong><p>{user.role === "ADMIN" ? "Sensitive data is restricted to administrators." : "Evidence from resumes and job requirements."}</p></article></div><div className="dashboard-panels"><section className="profile-panel"><p className="eyebrow">Your profile</p><h2>{profile?.name || user.name}</h2><p>{profile?.email || user.email} · {user.role.toLowerCase()}</p>{profileError && <p className="error">{profileError}</p>}{!profile && !profileError && <p className="notice">Loading profile...</p>}<dl>{fields.map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl></section><section className="vector-panel"><p className="eyebrow">Vector matching algorithm</p><h2>HNSW + Cosine Similarity</h2><p>Azure OpenAI <strong>text-embedding-3-large</strong> converts job descriptions and resumes into 3,072-dimensional vectors.</p><dl><div><dt>Vector index</dt><dd>Qdrant HNSW approximate nearest neighbors</dd></div><div><dt>Distance metric</dt><dd>Cosine similarity</dd></div><div><dt>Ranking</dt><dd>Highest semantic similarity first</dd></div></dl></section></div>{user.role === "CANDIDATE" && <DsaStrengthPanel />}</Page>;
}

function Jobs({ recruiter = false }) {
  const pageSize = 24; const [page, setPage] = useState(0); const [jobs, setJobs] = useState([]); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  useEffect(() => { let active = true; const base = recruiter ? "/recruiter/jobs" : "/jobs"; const path = `${base}?limit=${pageSize}&offset=${page * pageSize}`; const request = recruiter ? api(path) : loadPublicJobPage(path); request.then(items => { if (!active) return; setError(""); setJobs(items); if (!recruiter && items.length === pageSize) loadPublicJobPage(`${base}?limit=${pageSize}&offset=${(page + 1) * pageSize}`); }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [recruiter, page]);
  const view = useListView(jobs, "job_title", "status");
  return <Page eyebrow={recruiter ? "Company roles" : "Opportunity board"} title={recruiter ? "My jobs" : "Active jobs"} action={recruiter && <NavLink className="primary" to="/recruiter/jobs/create"><Plus /> New job</NavLink>}>{loading && <p className="notice">Loading page {page + 1}...</p>}{error && <p className="error">{error}</p>}<ListControls view={view} sortOptions={[["job_title", "Title"], ["company_name", "Company"], ["location", "Location"], ["country", "Country"], ["job_id", "Newest ID"]]} placeholder="Search this page..." /><div className="list job-list">{view.visible.map(job => <NavLink className="job-row job-card" key={job.job_id} to={recruiter ? `/recruiter/jobs/${job.job_id}` : `/candidate/jobs/${job.job_id}`}><div><span className="pill">{job.Job_Id || formatJobId(job.job_id)} · {job.status}</span><h3>{job.job_title}</h3><p className="job-company">{job.company_name || "Company not specified"}</p><div className="job-facts"><span><small>Location</small>{job.location || "Flexible"}</span><span><small>Country</small>{job.country || "Not specified"}</span><span><small>Salary</small>{job.salary_range || "Not disclosed"}</span><span><small>Qualification</small>{job.qualifications || "Not specified"}</span></div></div><strong>{job.role || "View role"}</strong></NavLink>)}</div>{!view.visible.length && !error && !loading && <Empty title="No matching roles" text="Adjust the filters or move to another page." />}<div className="pagination"><button className="secondary" disabled={page === 0 || loading} onClick={() => { setLoading(true); setPage(value => value - 1); }}>Previous</button><span>Page {page + 1}</span><button className="secondary" disabled={jobs.length < pageSize || loading} onClick={() => { setLoading(true); setPage(value => value + 1); }}>Next</button></div></Page>;
}

function RecommendedJobs() {
  const [resumes, setResumes] = useState([]); const [resumeId, setResumeId] = useState(""); const [jobs, setJobs] = useState([]); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  async function loadMatches(selectedResumeId) { setLoading(true); setError(""); try { setJobs(await api(`/candidate/recommended-jobs?resume_id=${selectedResumeId}&limit=50`)); } catch (requestError) { setError(requestError.message); setJobs([]); } finally { setLoading(false); } }
  useEffect(() => { api("/candidate/resumes").then(items => { setResumes(items); if (items.length) { const selected = String(items[0].resume_id); setResumeId(selected); return api(`/candidate/recommended-jobs?resume_id=${selected}&limit=50`).then(setJobs); } return null; }).catch(requestError => setError(requestError.message)).finally(() => setLoading(false)); }, []);
  return <Page eyebrow="Resume-to-role vector search" title="Your job matches" action={resumes.length > 0 && <button className="primary" onClick={() => loadMatches(resumeId)} disabled={loading}><Sparkles /> Refresh matches</button>}>
    {resumes.length > 0 && <div className="match-resume-picker"><label>Resume used for matching<select value={resumeId} onChange={event => { setResumeId(event.target.value); loadMatches(event.target.value); }}>{resumes.map(resume => <option key={resume.resume_id} value={resume.resume_id}>v{resume.version} · {resume.original_filename}</option>)}</select></label><p>Qdrant compares the resume vector against the entire indexed active-job collection and returns the top 50 by cosine similarity.</p></div>}
    {loading && <p className="notice">Searching the vector index for suitable roles...</p>}{error && <p className="error">{error}</p>}
    {!loading && !resumes.length && <Empty title="Upload a resume first" text="A parsed PDF or DOCX resume is required for job matching." />}
    <div className="list job-list">{jobs.map((job, index) => <NavLink className="job-row job-card recommendation-row" key={job.job_id} to={`/candidate/jobs/${job.job_id}`}><div><span className="pill">#{index + 1} · {job.Job_Id || formatJobId(job.job_id)}</span><h3>{job.job_title}</h3><p className="job-company">{job.company_name || "Company not specified"}</p><div className="job-facts"><span><small>Location</small>{job.location || "Flexible"}</span><span><small>Role</small>{job.role || "Open"}</span><span><small>Experience</small>{job.experience || "Not specified"}</span><span><small>Work type</small>{job.work_type || "Not specified"}</span></div></div><div className="candidate-match-score"><strong>{job.semantic_score.toFixed(1)}%</strong><small>RESUME MATCH</small></div></NavLink>)}</div>
    {!loading && resumes.length > 0 && !jobs.length && !error && <Empty title="No indexed matches yet" text="Job embeddings may still be seeding. Refresh after indexing progresses." />}
  </Page>;
}

function JobDetail({ recruiter = false }) {
  const { jobId } = useParams(); const [job, setJob] = useState(null); const [message, setMessage] = useState("");
  const [resumes, setResumes] = useState([]); const [resumeId, setResumeId] = useState(""); const [applied, setApplied] = useState(false); const [bulkMessage, setBulkMessage] = useState(""); const [bulkUploading, setBulkUploading] = useState(false);
  useEffect(() => { api(recruiter ? `/recruiter/jobs/${jobId}` : `/jobs/${jobId}`).then(setJob).catch(err => setMessage(err.message)); }, [jobId, recruiter]);
  useEffect(() => {
    if (recruiter) return;
    Promise.all([api("/candidate/resumes"), api("/candidate/applications")]).then(([resumeItems, applications]) => {
      setResumes(resumeItems);
      if (resumeItems.length) setResumeId(String(resumeItems[0].resume_id));
      setApplied(applications.some(application => String(application.job_id) === jobId));
    }).catch(err => setMessage(err.message));
  }, [jobId, recruiter]);
  if (!job) return <Page eyebrow="Role" title="Loading role..."><p className="error">{message}</p></Page>;
  async function publish() { const updated = await api(`/recruiter/jobs/${jobId}/publish`, { method: "POST" }); setJob(updated); }
  async function applyForJob() {
    setMessage("");
    try {
      await api(`/jobs/${jobId}/apply`, { method: "POST", body: JSON.stringify({ resume_id: Number(resumeId) }) });
      setApplied(true); setMessage("Application submitted successfully.");
    } catch (err) { setMessage(err.message); }
  }
  async function downloadBulkTemplate() { try { const blob = await apiBlob(`/recruiter/jobs/${jobId}/applicants/bulk-template`); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `job-${jobId}-applicants-template.csv`; link.click(); URL.revokeObjectURL(url); } catch (err) { setBulkMessage(err.message); } }
  async function uploadBulkApplicants(event) { event.preventDefault(); setBulkMessage(""); setBulkUploading(true); try { const result = await api(`/recruiter/jobs/${jobId}/applicants/bulk`, { method: "POST", body: new FormData(event.currentTarget) }); setBulkMessage(`${result.applications_created} applications created; ${result.duplicates_skipped} duplicates skipped${result.indexed ? ". Resumes indexed." : ". Indexing will retry when applicants open."}`); event.currentTarget.reset(); } catch (err) { setBulkMessage(err.message); } finally { setBulkUploading(false); } }
  return <Page eyebrow={job.status} title={job.job_title} action={recruiter && job.status === "DRAFT" && <button className="primary" onClick={publish}>Publish role</button>}><div className="detail-grid"><section><h2>Role brief</h2><p>{job.job_description || "No description provided."}</p><h2>Responsibilities</h2><p>{job.responsibilities || "Not specified."}</p>{recruiter && <div className="bulk-panel"><div><p className="eyebrow">HR bulk intake</p><h2>Upload applicants</h2><p>Download the CSV, keep resume filenames identical, then upload the completed CSV with PDF or DOCX resumes.</p></div><button className="secondary" type="button" onClick={downloadBulkTemplate}><Download /> Download CSV template</button><form onSubmit={uploadBulkApplicants}><label>Completed CSV<input name="csv_file" type="file" accept=".csv,text/csv" required /></label><label>Resume files<input name="resume_files" type="file" accept=".pdf,.docx" multiple required /></label><button className="primary" disabled={bulkUploading}><FileSpreadsheet /> {bulkUploading ? "Uploading and indexing..." : "Upload applicants"}</button></form>{bulkMessage && <p className={bulkMessage.includes("created") ? "success" : "error"}>{bulkMessage}</p>}</div>}</section><aside><dl><dt>Job ID</dt><dd>{job.Job_Id || formatJobId(job.job_id)}</dd><dt>Company</dt><dd>{job.company_name || "Not specified"}</dd><dt>Role</dt><dd>{job.role || "Open"}</dd><dt>Experience</dt><dd>{job.experience || "Open"}</dd><dt>Location</dt><dd>{job.location || "Flexible"}</dd><dt>Country</dt><dd>{job.country || "Not specified"}</dd><dt>Salary</dt><dd>{job.salary_range || "Not disclosed"}</dd><dt>Qualifications</dt><dd>{job.qualifications || "Not specified"}</dd><dt>Skills</dt><dd>{job.skills || "Not specified"}</dd></dl>{recruiter ? <NavLink className="secondary" to={`/recruiter/jobs/${jobId}/applicants`}>View applicants</NavLink> : <div className="apply-panel"><h3>Apply for this role</h3>{applied ? <p className="success">Application submitted</p> : resumes.length ? <><label>Resume version<select value={resumeId} onChange={event => setResumeId(event.target.value)}>{resumes.map(resume => <option key={resume.resume_id} value={resume.resume_id}>Version {resume.version} · {resume.original_filename}</option>)}</select></label><button className="primary" onClick={applyForJob} disabled={!resumeId}>Apply now</button></> : <><p>Upload a resume before applying.</p><NavLink className="secondary" to="/candidate/resumes">Go to resumes</NavLink></>}{message && <p className={message.includes("successfully") ? "success" : "error"}>{message}</p>}</div>}</aside></div></Page>;
}

function CreateJob() {
  const navigate = useNavigate(); const [error, setError] = useState("");
  async function submit(event) { event.preventDefault(); const form = Object.fromEntries(new FormData(event.currentTarget)); try { const job = await api("/recruiter/jobs", { method: "POST", body: JSON.stringify(form) }); navigate(`/recruiter/jobs/${job.job_id}`); } catch (err) { setError(err.message); } }
  return <Page eyebrow="New requisition" title="Create a job"><form className="form-grid" onSubmit={submit}><label>Job title<input name="job_title" required /></label><label>Role<input name="role" /></label><label>Location<input name="location" /></label><label>Work type<input name="work_type" /></label><label>Experience<input name="experience" /></label><label>Skills<input name="skills" /></label><label className="wide">Description<textarea name="job_description" rows="5" /></label><label className="wide">Responsibilities<textarea name="responsibilities" rows="4" /></label>{error && <p className="error wide">{error}</p>}<button className="primary">Save draft</button></form></Page>;
}

function Resumes() {
  const [resumes, setResumes] = useState([]); const [message, setMessage] = useState(""); const [loading, setLoading] = useState(true);
  const load = () => { setLoading(true); setMessage(""); return api("/candidate/resumes").then(setResumes).catch(err => setMessage(err.message)).finally(() => setLoading(false)); }; useEffect(() => { api("/candidate/resumes").then(setResumes).catch(err => setMessage(err.message)).finally(() => setLoading(false)); }, []);
  async function upload(event) { const file = event.target.files[0]; if (!file) return; const data = new FormData(); data.append("file", file); try { setMessage("Processing resume..."); await api("/resumes/upload", { method: "POST", body: data }); setMessage("Resume uploaded and indexed."); load(); } catch (err) { setMessage(err.message); } }
  async function viewResume(resumeId) { const tab = window.open("about:blank", "_blank"); try { const result = await api(`/resumes/${resumeId}`); if (tab) tab.location.assign(result.download_url); else window.location.assign(result.download_url); } catch (err) { if (tab) tab.close(); setMessage(err.message); } }
  const view = useListView(resumes, "version", "parsing_status");
  return <Page eyebrow="Candidate documents" title="Resume library" action={<label className="primary upload"><Upload /> Upload<input type="file" accept=".pdf,.docx" onChange={upload} /></label>}>{loading && <p className="notice">Loading your resumes...</p>}{message && <p className={message.includes("uploaded") ? "success" : "error"}>{message}</p>}<ListControls view={view} sortOptions={[["version", "Version"], ["original_filename", "Filename"], ["created_at", "Upload date"]]} placeholder="Search resumes..." /><div className="list">{view.visible.map(resume => <div className="job-row" key={resume.resume_id}><div><span className="pill">VERSION {resume.version}</span><h3>{resume.original_filename}</h3><p>{resume.parsing_status}</p></div><button className="secondary" onClick={() => viewResume(resume.resume_id)}><FileText /> View Resume</button></div>)}</div>{!view.visible.length && !loading && <Empty title="No matching resumes" text="Upload a resume or adjust the controls." />}</Page>;
}

function Applications() { const [items, setItems] = useState([]); useEffect(() => { api("/candidate/applications").then(setItems); }, []); const view = useListView(items, "applied_at", "status"); return <Page eyebrow="Your search" title="Applications"><ListControls view={view} sortOptions={[["applied_at", "Applied date"], ["job_id", "Job ID"], ["resume_id", "Resume ID"]]} placeholder="Search job or resume ID..." /><div className="list">{view.visible.map(item => <div className="job-row" key={item.application_id}><div><span className="pill">{item.status}</span><h3>Job #{item.job_id}</h3><p>Resume #{item.resume_id}</p></div><strong>{new Date(item.applied_at).toLocaleDateString()}</strong></div>)}</div>{!view.visible.length && <Empty title="No matching applications" text="Submitted roles appear here." />}</Page>; }

function Applicants() {
  const { jobId } = useParams(); const [items, setItems] = useState([]); const [error, setError] = useState(""); const [loading, setLoading] = useState(true); const [verifying, setVerifying] = useState(false); const [graph, setGraph] = useState(null); const [graphLoading, setGraphLoading] = useState(null);
  async function loadApplicants() { return api(`/recruiter/jobs/${jobId}/applicants`).then(setItems); }
  useEffect(() => { api(`/recruiter/jobs/${jobId}/applicants`).then(setItems).catch(err => setError(err.message)).finally(() => setLoading(false)); }, [jobId]);
  async function verifyAndRerank() { setVerifying(true); setError(""); try { await api(`/recruiter/jobs/${jobId}/match`, { method: "POST" }); await loadApplicants(); } catch (err) { setError(err.message); } finally { setVerifying(false); } }
  async function openGraph(item) { setGraphLoading(item.candidate_id); setError(""); try { const result = await api(`/recruiter/jobs/${jobId}/applicants/${item.candidate_id}/suitability`); setGraph({ ...result, candidate_name: item.candidate_name }); } catch (err) { setError(err.message); } finally { setGraphLoading(null); } }
  const view = useListView(items, "ranking", "scope");
  return <Page eyebrow={`Role #${jobId}`} title="Ranked applicants" action={<button className="primary" onClick={verifyAndRerank} disabled={verifying || loading}><GitBranch />{verifying ? "Verifying projects..." : "Verify GitHub & rerank"}</button>}>{loading && <p className="notice">Indexing resumes and calculating semantic matches...</p>}{verifying && <p className="notice">Checking public GitHub profiles and comparing repository evidence with resume projects...</p>}{error && <p className="error">{error}</p>}<ListControls view={view} sortOptions={[["ranking", "Rank"], ["overall_score", "Overall score"], ["semantic_score", "Semantic score"], ["github_score", "GitHub relevance"], ["candidate_name", "Candidate name"], ["applied_at", "Applied date"]]} placeholder="Search candidate or resume..." /><div className="list">{view.visible.map(item => <div className="job-row applicant-row" key={item.application_id}><div className="applicant-rank"><strong>{item.ranking ? `#${item.ranking}` : "--"}</strong><small>RANK</small></div><div className="applicant-copy"><span className="pill">{item.scope === "ALL_JOBS" ? "TALENT POOL" : item.status}</span><h3><button className="applicant-name" onClick={() => openGraph(item)} disabled={graphLoading === item.candidate_id}>{graphLoading === item.candidate_id ? "Loading graph..." : item.candidate_name}</button></h3><p>Submitted resume #{item.resume_id} - {new Date(item.applied_at).toLocaleDateString()}</p>{item.github_evidence && <small className={item.github_verified ? "github-verified" : "github-unverified"}>{item.github_verified ? `GitHub verified · ${item.github_score?.toFixed(1) ?? 0}% project relevance` : `GitHub: ${item.github_evidence.verification_status?.replaceAll("_", " ").toLowerCase()}`}</small>}</div><div className={`match-score ${item.semantic_score == null ? "pending" : ""}`}><strong>{item.semantic_score == null ? "Pending" : `${(item.overall_score ?? item.semantic_score).toFixed(1)}%`}</strong><small>{item.overall_score == null ? "SEMANTIC MATCH" : "FINAL MATCH"}</small>{item.overall_score != null && <span>{item.semantic_score.toFixed(1)} semantic</span>}</div></div>)}</div>{!view.visible.length && !error && !loading && <Empty title="No matching applicants" text="Adjust the search, scope, or sorting controls." />}{graph && <ApplicantGraphModal data={graph} onClose={() => setGraph(null)} />}</Page>;
}

function Interviews() {
  const [items, setItems] = useState([]); const [explanation, setExplanation] = useState(null); const [loadingId, setLoadingId] = useState(null); const [error, setError] = useState("");
  useEffect(() => { api("/interviewer/candidates").then(setItems).catch(requestError => setError(requestError.message)); }, []);
  async function explain(item) { setLoadingId(item.interview_id); setError(""); try { setExplanation(await api(`/interviewer/interviews/${item.interview_id}/suitability`)); } catch (requestError) { setError(requestError.message); } finally { setLoadingId(null); } }
  const view = useListView(items, "scheduled_at", "status");
  return <Page eyebrow="Assigned conversations" title="Interview queue">{error && <p className="error">{error}</p>}<ListControls view={view} sortOptions={[["scheduled_at", "Schedule"], ["candidate_name", "Candidate"], ["job_title", "Job role"], ["score", "Score"]]} placeholder="Search candidate, role, or application..." /><div className="list">{view.visible.map(item => <div className="job-row interview-row" key={item.interview_id}><div><span className="pill">{item.status}</span><h3>{item.candidate_name || `Application #${item.application_id}`}</h3><p>{item.job_title || "Job role"} · {item.scheduled_at ? new Date(item.scheduled_at).toLocaleString() : "Schedule pending"}</p></div><div className="interview-actions"><strong>{item.score == null ? "Not scored" : `${item.score}/100`}</strong><button className="secondary" onClick={() => explain(item)} disabled={loadingId === item.interview_id}><Lightbulb />{loadingId === item.interview_id ? "Analyzing..." : "Why suitable?"}</button></div></div>)}</div>{!view.visible.length && <Empty title="No matching interviews" text="Scheduled candidate conversations appear here." />}{explanation && <SuitabilityModal data={explanation} onClose={() => setExplanation(null)} />}</Page>;
}

export default function App() {
  return <Routes><Route path="/login" element={<Login />} /><Route path="/register" element={<Register />} /><Route path="/register/candidate" element={<Register initialType="candidate" />} /><Route path="/register/recruiter" element={<Register initialType="recruiter" />} /><Route path="/register/interviewer" element={<Register initialType="interviewer" />} /><Route path="/" element={<Navigate to="/login" />} />
    <Route path="/candidate/dashboard" element={<Protected roles={["CANDIDATE"]}><Dashboard /></Protected>} /><Route path="/candidate/matches" element={<Protected roles={["CANDIDATE"]}><RecommendedJobs /></Protected>} /><Route path="/candidate/jobs" element={<Protected roles={["CANDIDATE"]}><Jobs /></Protected>} /><Route path="/candidate/jobs/:jobId" element={<Protected roles={["CANDIDATE"]}><JobDetail /></Protected>} /><Route path="/candidate/resumes" element={<Protected roles={["CANDIDATE"]}><Resumes /></Protected>} /><Route path="/candidate/applications" element={<Protected roles={["CANDIDATE"]}><Applications /></Protected>} />
    <Route path="/recruiter/dashboard" element={<Protected roles={["RECRUITER"]}><Dashboard /></Protected>} /><Route path="/recruiter/jobs" element={<Protected roles={["RECRUITER"]}><Jobs recruiter /></Protected>} /><Route path="/recruiter/jobs/create" element={<Protected roles={["RECRUITER"]}><CreateJob /></Protected>} /><Route path="/recruiter/jobs/:jobId" element={<Protected roles={["RECRUITER"]}><JobDetail recruiter /></Protected>} /><Route path="/recruiter/jobs/:jobId/applicants" element={<Protected roles={["RECRUITER"]}><Applicants /></Protected>} />
    <Route path="/interviewer/dashboard" element={<Protected roles={["INTERVIEWER"]}><Dashboard /></Protected>} /><Route path="/interviewer/candidates" element={<Protected roles={["INTERVIEWER"]}><Interviews /></Protected>} />
    <Route path="/admin/dashboard" element={<Protected roles={["ADMIN"]}><Dashboard /></Protected>} /><Route path="/admin/data" element={<Protected roles={["ADMIN"]}><AdminPanel /></Protected>} /><Route path="*" element={<Navigate to="/login" />} /></Routes>;
}