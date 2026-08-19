import re


PREFIXES = {
    "company": "COMP",
    "user": "USER",
    "job": "JOB",
    "candidate": "CAND",
    "recruiter": "REC",
    "interviewer": "INT",
    "application": "APP",
    "resume": "RES",
}


def format_public_id(entity: str, database_id: int) -> str:
    prefix = PREFIXES[entity]
    return f"{prefix}_{int(database_id):03d}"


def parse_public_id(value: str, entity: str) -> int:
    prefix = PREFIXES[entity]
    match = re.fullmatch(rf"{prefix}_(\d+)", value.upper())
    if not match:
        raise ValueError(f"Invalid {entity} ID")
    return int(match.group(1))
