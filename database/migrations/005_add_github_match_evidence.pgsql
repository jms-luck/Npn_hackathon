ALTER TABLE match_results ADD COLUMN IF NOT EXISTS github_score NUMERIC(6, 3);
ALTER TABLE match_results ADD COLUMN IF NOT EXISTS github_verified BOOLEAN;
ALTER TABLE match_results ADD COLUMN IF NOT EXISTS github_evidence JSONB NOT NULL DEFAULT '{}';