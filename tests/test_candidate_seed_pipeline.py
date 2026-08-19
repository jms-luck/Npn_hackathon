from scripts.seed_candidate_matching import final_counts


def test_candidate_seed_pipeline_exposes_verification_function() -> None:
    assert callable(final_counts)