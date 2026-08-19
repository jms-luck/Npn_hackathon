CREATE TABLE IF NOT EXISTS users (
    user_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(30) NOT NULL CHECK (role IN ('CANDIDATE', 'RECRUITER', 'INTERVIEWER', 'ADMIN')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS companies (
    company_id BIGSERIAL PRIMARY KEY,
    company_name VARCHAR(255) UNIQUE NOT NULL,
    company_size VARCHAR(100),
    company_profile TEXT,
    verification_code VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recruiters (
    recruiter_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL REFERENCES companies(company_id),
    designation VARCHAR(255),
    phone VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    phone VARCHAR(50),
    location VARCHAR(255),
    profile_summary TEXT,
    linkedin_url TEXT,
    github_url TEXT,
    portfolio_url TEXT
);

CREATE TABLE IF NOT EXISTS dsa_evaluations (
    evaluation_id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT UNIQUE NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    leetcode_username VARCHAR(30) NOT NULL,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    level VARCHAR(30) NOT NULL,
    result_json JSONB NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dsa_evaluations_username ON dsa_evaluations(leetcode_username);

CREATE TABLE IF NOT EXISTS interviewers (
    interviewer_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL REFERENCES companies(company_id),
    designation VARCHAR(255),
    phone VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS job_postings (
    job_id BIGSERIAL PRIMARY KEY,
    external_job_id VARCHAR(255) UNIQUE,
    company_id BIGINT NOT NULL REFERENCES companies(company_id),
    recruiter_id BIGINT REFERENCES recruiters(recruiter_id),
    experience VARCHAR(255),
    qualifications TEXT,
    salary_range VARCHAR(255),
    location VARCHAR(255),
    country VARCHAR(255),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    work_type VARCHAR(100),
    job_posting_date DATE,
    preference TEXT,
    contact_person VARCHAR(255),
    contact VARCHAR(255),
    job_title VARCHAR(255) NOT NULL,
    role VARCHAR(255),
    job_portal VARCHAR(255),
    job_description TEXT,
    benefits TEXT,
    skills TEXT,
    responsibilities TEXT,
    source_type VARCHAR(30) NOT NULL DEFAULT 'RECRUITER' CHECK (source_type IN ('DATASET', 'RECRUITER')),
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'ACTIVE', 'CLOSED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resumes (
    resume_id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    original_filename VARCHAR(255) NOT NULL,
    blob_path TEXT UNIQUE NOT NULL,
    content_type VARCHAR(255),
    extracted_text TEXT,
    parsing_status VARCHAR(30) NOT NULL DEFAULT 'PENDING' CHECK (parsing_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (candidate_id, version)
);

CREATE TABLE IF NOT EXISTS applications (
    application_id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT NOT NULL REFERENCES candidates(candidate_id),
    job_id BIGINT NOT NULL REFERENCES job_postings(job_id),
    resume_id BIGINT NOT NULL REFERENCES resumes(resume_id),
    status VARCHAR(30) NOT NULL DEFAULT 'APPLIED' CHECK (status IN ('APPLIED', 'SHORTLISTED', 'REJECTED', 'INTERVIEW', 'HIRED')),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (candidate_id, job_id)
);

CREATE TABLE IF NOT EXISTS global_applicants (
    global_applicant_id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT UNIQUE NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    resume_id BIGINT NOT NULL REFERENCES resumes(resume_id),
    status VARCHAR(30) NOT NULL DEFAULT 'APPLIED' CHECK (status IN ('APPLIED', 'SHORTLISTED', 'REJECTED', 'INTERVIEW', 'HIRED')),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS match_results (
    match_id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES job_postings(job_id) ON DELETE CASCADE,
    candidate_id BIGINT NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    resume_id BIGINT NOT NULL REFERENCES resumes(resume_id) ON DELETE CASCADE,
    semantic_score NUMERIC(6, 3) NOT NULL,
    github_score NUMERIC(6, 3),
    github_verified BOOLEAN,
    github_evidence JSONB NOT NULL DEFAULT '{}',
    skill_score NUMERIC(6, 3),
    experience_score NUMERIC(6, 3),
    qualification_score NUMERIC(6, 3),
    overall_score NUMERIC(6, 3) NOT NULL,
    matched_skills JSONB NOT NULL DEFAULT '[]',
    missing_skills JSONB NOT NULL DEFAULT '[]',
    explanation TEXT,
    ranking INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (job_id, resume_id)
);

CREATE TABLE IF NOT EXISTS interviews (
    interview_id BIGSERIAL PRIMARY KEY,
    application_id BIGINT UNIQUE NOT NULL REFERENCES applications(application_id) ON DELETE CASCADE,
    interviewer_id BIGINT NOT NULL REFERENCES interviewers(interviewer_id),
    scheduled_at TIMESTAMPTZ,
    status VARCHAR(30) NOT NULL DEFAULT 'SCHEDULED' CHECK (status IN ('SCHEDULED', 'COMPLETED', 'CANCELLED')),
    feedback TEXT,
    score NUMERIC(5, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);