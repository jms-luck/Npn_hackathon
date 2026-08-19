from scripts.import_companies import company_values


def test_company_values_keep_correct_columns() -> None:
    assert company_values("3i Group", 98247, "profile") == ("3i Group", "98247", "profile")


def test_company_values_repair_swapped_columns() -> None:
    assert company_values("98247", "3i Group", "profile") == ("3i Group", "98247", "profile")
