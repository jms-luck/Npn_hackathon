import pytest

from backend.app.services.public_ids import format_public_id, parse_public_id


def test_public_ids_are_stable_and_padded() -> None:
    assert format_public_id("company", 1) == "COMP_001"
    assert format_public_id("candidate", 25) == "CAND_025"
    assert format_public_id("job", 162905281405687) == "JOB_162905281405687"


def test_public_ids_parse_to_existing_database_keys() -> None:
    assert parse_public_id("REC_025", "recruiter") == 25
    assert parse_public_id("int_003", "interviewer") == 3
    with pytest.raises(ValueError):
        parse_public_id("USER_001", "company")
