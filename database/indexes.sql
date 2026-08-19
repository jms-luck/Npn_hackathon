CREATE INDEX IF NOT EXISTS idx_jobs_active ON job_postings (status, job_id DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON job_postings (company_id, job_id DESC);
CREATE INDEX IF NOT EXISTS idx_applications_job ON applications (job_id, applied_at DESC);
CREATE INDEX IF NOT EXISTS idx_applications_candidate ON applications (candidate_id, applied_at DESC);
CREATE INDEX IF NOT EXISTS idx_resumes_candidate ON resumes (candidate_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_matches_job_ranking ON match_results (job_id, ranking);