from backend.app.services.verification_codes import VERIFICATION_ALPHABET, generate_company_verification_code


def test_company_verification_codes_are_random_and_human_readable() -> None:
    first = generate_company_verification_code()
    second = generate_company_verification_code()
    assert first.startswith("COMP-")
    assert len(first) == 15
    assert set(first.removeprefix("COMP-")) <= set(VERIFICATION_ALPHABET)
    assert first != second