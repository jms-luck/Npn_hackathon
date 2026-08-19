# Architecture

The React client calls only the FastAPI REST API. FastAPI owns authentication, role authorization, company isolation, application workflows, and orchestration of PostgreSQL, Azure Blob Storage, Azure OpenAI, and Qdrant.

PostgreSQL is the source of truth. Blob Storage contains private resume binaries. Qdrant contains only job and resume vectors plus identifiers that link back to PostgreSQL.

## Trust boundaries

- Candidate, recruiter, and interviewer identities are resolved from JWT subjects.
- Recruiter company IDs and candidate IDs are never accepted from client authorization claims.
- A recruiter may retrieve only the exact resume version submitted to a job belonging to their company.
- Candidate-visible job queries return only `ACTIVE` records.

## Global dummy applicant pool

Bulk demo candidates that must appear against every job are stored once in `global_applicants` rather than materializing a candidate-job cross product. Recruiter applicant queries merge this pool with explicit `applications`; an explicit job submission takes precedence for that candidate and preserves its selected resume version.