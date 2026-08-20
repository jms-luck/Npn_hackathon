from scripts.seed_job_catalog import run_with_retries


def test_job_catalog_pipeline_exposes_retry_runner() -> None:
    assert callable(run_with_retries)