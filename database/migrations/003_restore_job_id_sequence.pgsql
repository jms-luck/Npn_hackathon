CREATE SEQUENCE IF NOT EXISTS job_postings_job_id_seq;
SELECT setval('job_postings_job_id_seq', COALESCE((SELECT MAX(job_id) FROM job_postings), 0) + 1, false);
ALTER SEQUENCE job_postings_job_id_seq OWNED BY job_postings.job_id;
ALTER TABLE job_postings ALTER COLUMN job_id SET DEFAULT nextval('job_postings_job_id_seq');
