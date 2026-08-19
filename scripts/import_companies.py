import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from backend.app.services.verification_codes import generate_company_verification_code


def clean(value):
    return None if pd.isna(value) or str(value).strip() == "" else str(value).strip()


def company_values(company, company_size, company_profile):
    name = clean(company)
    size = clean(company_size)
    if name and name.isdigit() and size and not size.isdigit():
        name, size = size, name
    return name, size, clean(company_profile)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(ROOT / "job_processed_selected_5_columns.csv"))
    parser.add_argument("--chunk-size", type=int, default=25_000)
    parser.add_argument("--checkpoint", default=str(ROOT / "companies_checkpoint.json"))
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint)
    start_chunk = 0
    if checkpoint_path.exists() and not args.restart:
        start_chunk = json.loads(checkpoint_path.read_text()).get("next_chunk", 0)

    from backend.app.core.config import settings
    connection = psycopg2.connect(settings.database_url)
    try:
        for chunk_number, frame in enumerate(pd.read_csv(args.file, chunksize=args.chunk_size)):
            if chunk_number < start_chunk:
                continue
            frame.columns = [column.strip().lower() for column in frame.columns]
            normalized = [company_values(row.company, row.company_size, row.company_profile) for row in frame.itertuples()]
            rows = {name: (name, size, profile, generate_company_verification_code()) for name, size, profile in normalized if name}
            with connection.cursor() as cursor:
                execute_values(
                    cursor,
                          """INSERT INTO companies (company_name, company_size, company_profile, verification_code)
                       VALUES %s
                       ON CONFLICT (company_name) DO UPDATE SET
                           company_size = COALESCE(EXCLUDED.company_size, companies.company_size),
                              company_profile = COALESCE(EXCLUDED.company_profile, companies.company_profile),
                              verification_code = COALESCE(NULLIF(BTRIM(companies.verification_code), ''), EXCLUDED.verification_code)""",
                    list(rows.values()),
                )
            connection.commit()
            checkpoint_path.write_text(json.dumps({"next_chunk": chunk_number + 1}, indent=2))
            print(f"companies chunk {chunk_number + 1} committed ({len(rows)} unique names)")
    finally:
        connection.close()


if __name__ == "__main__":
    main()