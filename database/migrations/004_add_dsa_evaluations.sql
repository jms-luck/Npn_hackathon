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