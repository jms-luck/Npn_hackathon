# Database

Run `database/schema.sql`, followed by `database/indexes.sql`, against PostgreSQL. The application ORM creates the same tables during initial setup.

Dataset loading is intentionally separate:

1. `scripts/import_companies.py` upserts unique companies in committed chunks.
2. `scripts/import_jobs.py` resolves company IDs and inserts jobs with `external_job_id` idempotency.

Both scripts write a checkpoint after each successful commit and can be resumed safely.

`scripts/import_dummy_applicants.py` consolidates duplicate emails into candidate accounts, stores every supplied PDF as a resume version in private Blob Storage, and associates each unique candidate with `global_applicants`. This normalized table makes the demo pool visible to every job without creating a candidate-job cross product.