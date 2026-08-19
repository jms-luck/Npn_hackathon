import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")


def clean(value):
    if pd.isna(value) or str(value).strip() == "":
        return None
    return value.item() if hasattr(value, "item") else value


def connect_with_retry(database_url: str, attempts: int = 5):
    for attempt in range(attempts):
        try:
            return psycopg2.connect(database_url)
        except psycopg2.OperationalError:
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(ROOT / "job_descriptions.csv"))
    parser.add_argument("--chunk-size", type=int, default=1_000)
    parser.add_argument("--checkpoint", default=str(ROOT / "jobs_checkpoint.json"))
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint)
    start_chunk = 0
    if checkpoint_path.exists() and not args.restart:
        start_chunk = json.loads(checkpoint_path.read_text()).get("next_chunk", 0)

    from backend.app.core.config import settings
    with connect_with_retry(settings.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT company_name, company_id FROM companies")
            companies = {name: company_id for name, company_id in cursor.fetchall()}

    columns = (
        "job_id", "external_job_id", "company_id", "experience", "qualifications", "salary_range",
        "location", "country", "latitude", "longitude", "work_type", "job_posting_date",
        "preference", "contact_person", "contact", "job_title", "role", "job_portal",
        "job_description", "benefits", "skills", "responsibilities", "source_type", "status",
    )
    insert_sql = f"INSERT INTO job_postings ({', '.join(columns)}) VALUES %s ON CONFLICT (external_job_id) DO NOTHING"
    connection = None
    try:
        for chunk_number, frame in enumerate(pd.read_csv(args.file, chunksize=args.chunk_size)):
            if chunk_number < start_chunk:
                continue
            rows = []
            for record in frame.to_dict("records"):
                company_name = str(record.get("Company", "")).strip()
                company_id = companies.get(company_name)
                if not company_id or not clean(record.get("Job Title")):
                    continue
                external_job_id = str(record.get("Job Id"))
                rows.append((
                    int(record.get("Job Id")), external_job_id, company_id, clean(record.get("Experience")),
                    clean(record.get("Qualifications")), clean(record.get("Salary Range")),
                    clean(record.get("location")), clean(record.get("Country")), clean(record.get("latitude")),
                    clean(record.get("longitude")), clean(record.get("Work Type")), clean(record.get("Job Posting Date")),
                    clean(record.get("Preference")), clean(record.get("Contact Person")), clean(record.get("Contact")),
                    clean(record.get("Job Title")), clean(record.get("Role")), clean(record.get("Job Portal")),
                    clean(record.get("Job Description")), clean(record.get("Benefits")), clean(record.get("skills")),
                    clean(record.get("Responsibilities")), "DATASET", "ACTIVE",
                ))
            if connection is None or (chunk_number - start_chunk) % 50 == 0:
                if connection is not None:
                    connection.close()
                connection = connect_with_retry(settings.database_url)
            try:
                with connection.cursor() as cursor:
                    execute_values(cursor, insert_sql, rows, page_size=args.chunk_size)
                connection.commit()
            except psycopg2.OperationalError:
                connection.close()
                connection = connect_with_retry(settings.database_url)
                with connection.cursor() as cursor:
                    execute_values(cursor, insert_sql, rows, page_size=args.chunk_size)
                connection.commit()
            checkpoint_path.write_text(json.dumps({"next_chunk": chunk_number + 1}, indent=2))
            print(f"jobs chunk {chunk_number + 1} committed ({len(rows)} jobs)")
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()