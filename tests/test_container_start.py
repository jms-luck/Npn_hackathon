from scripts.container_start import requires_rebuild, requires_seed


def test_external_index_seed_decision_uses_source_deficit() -> None:
    assert requires_seed(100, 99)
    assert not requires_seed(100, 100)
    assert not requires_seed(100, 120)
    assert requires_seed(0, None) is None
    assert requires_rebuild(100, 120)
    assert not requires_rebuild(100, 100)
    assert not requires_rebuild(100, 99)