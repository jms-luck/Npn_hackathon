from types import SimpleNamespace

from backend.app.routers import matching
from backend.app.services import ai
from backend.app.models import JobPosting


def test_job_resume_collection_is_deterministic() -> None:
    assert ai.job_resume_collection(42) == "job_42_applicant_resumes"


def test_match_progress_payload_is_bounded_and_identifiable(monkeypatch) -> None:
    stored = []
    monkeypatch.setattr(matching, "cache_set", lambda key, value, ttl: stored.append((key, value, ttl)))
    payload = matching.publish_match_progress(42, processed=7, total=20, github_processed=3, llm_processed=7, percent=35)
    assert payload["job_id"] == 42
    assert payload["processed"] == 7
    assert payload["percent"] == 35
    assert stored[0][0] == "match:progress:42"
    assert "candidate" not in payload


def test_qdrant_upserts_are_batched() -> None:
    batch_sizes = []

    class FakeQdrantClient:
        def upsert(self, collection_name: str, points, wait: bool = True) -> None:
            batch_sizes.append(len(points))

    points = [SimpleNamespace(id=index) for index in range(65)]

    ai._upsert_points(FakeQdrantClient(), "applicants", points)

    assert batch_sizes == [32, 32, 1]


def test_qdrant_upsert_reconnects_after_transient_failure(monkeypatch) -> None:
    attempts = []

    class FailingClient:
        def upsert(self, collection_name: str, points, wait: bool = True) -> None:
            attempts.append("failed")
            raise ConnectionError("temporary disconnect")

    class HealthyClient:
        def upsert(self, collection_name: str, points, wait: bool = True) -> None:
            attempts.append("succeeded")

    monkeypatch.setattr(ai, "sleep", lambda seconds: None)
    monkeypatch.setattr(ai, "qdrant_client", lambda: HealthyClient())

    ai._upsert_points(FailingClient(), "applicants", [SimpleNamespace(id=1)])

    assert attempts == ["failed", "succeeded"]


def test_embeddings_retry_after_transient_failure(monkeypatch) -> None:
    attempts = []

    class FailingEmbeddings:
        def create(self, **kwargs):
            attempts.append("failed")
            raise ConnectionError("temporary DNS failure")

    class HealthyEmbeddings:
        def create(self, **kwargs):
            attempts.append("succeeded")
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1, 0.2])])

    clients = iter([SimpleNamespace(embeddings=FailingEmbeddings()), SimpleNamespace(embeddings=HealthyEmbeddings())])
    monkeypatch.setattr(ai, "openai_client", lambda: next(clients))
    monkeypatch.setattr(ai, "sleep", lambda seconds: None)

    assert ai.embed_texts(["resume text"]) == [[0.1, 0.2]]
    assert attempts == ["failed", "succeeded"]


def test_index_resume_for_job_caches_and_copies_vector(monkeypatch) -> None:
    upserts = []
    payload_indexes = []

    class FakeQdrantClient:
        def __init__(self) -> None:
            self.collections = set()

        def collection_exists(self, name: str) -> bool:
            return name in self.collections

        def create_collection(self, name: str, vectors_config) -> None:
            self.collections.add(name)

        def get_collection(self, name: str):
            return SimpleNamespace(payload_schema={})

        def create_payload_index(self, collection_name: str, field_name: str, field_schema, wait: bool = True) -> None:
            payload_indexes.append((collection_name, field_name))

        def retrieve(self, collection_name: str, ids, **kwargs):
            return []

        def upsert(self, collection_name: str, points, wait: bool = True) -> None:
            upserts.append((collection_name, points, wait))

    client = FakeQdrantClient()
    monkeypatch.setattr(ai, "qdrant_client", lambda: client)
    monkeypatch.setattr(ai, "embed_texts", lambda texts: [[0.1, 0.2, 0.3] for _ in texts])
    job = SimpleNamespace(job_id=42)
    resume = SimpleNamespace(resume_id=7, candidate_id=3, extracted_text="Python and FastAPI")

    ai.index_resume_for_job(job, resume)

    assert [item[0] for item in upserts] == [ai.settings.qdrant_resume_collection, "job_42_applicant_resumes"]
    assert upserts[1][1][0].payload == {"job_id": 42, "resume_id": 7, "candidate_id": 3}
    assert all(item[2] for item in upserts)
    assert payload_indexes == [("job_42_applicant_resumes", "resume_id")]


def test_candidate_job_search_reuses_stored_resume_vector(monkeypatch) -> None:
    queries = []

    class FakeQdrantClient:
        def collection_exists(self, name):
            return True

        def retrieve(self, collection_name, ids, with_vectors=True):
            return [SimpleNamespace(id=7, vector=[0.2, 0.4], payload={})]

        def query_points(self, collection_name, query, limit):
            queries.append((collection_name, query, limit))
            return SimpleNamespace(points=[SimpleNamespace(payload={"job_id": 9}, score=0.8)])

    monkeypatch.setattr(ai, "qdrant_client", lambda: FakeQdrantClient())
    monkeypatch.setattr(ai, "embed_texts", lambda texts: (_ for _ in ()).throw(AssertionError("resume should not be re-embedded")))
    points = ai.search_jobs_for_resume(SimpleNamespace(resume_id=7, candidate_id=3, extracted_text="Python"), 12)
    assert points[0].payload["job_id"] == 9
    assert queries == [(ai.settings.qdrant_job_collection, [0.2, 0.4], 12)]


def test_ranked_applicants_are_sorted_by_semantic_score(monkeypatch) -> None:
    items = [
        {"application_id": 1, "candidate_id": 1, "candidate_name": "Lower", "resume_id": 11},
        {"application_id": 2, "candidate_id": 2, "candidate_name": "Higher", "resume_id": 22},
    ]
    resumes = [SimpleNamespace(resume_id=11), SimpleNamespace(resume_id=22)]
    points = [
        SimpleNamespace(payload={"resume_id": 22}, score=0.91),
        SimpleNamespace(payload={"resume_id": 11}, score=0.52),
    ]
    monkeypatch.setattr(matching, "applicant_items", lambda job_id, db: (items, resumes))
    monkeypatch.setattr(matching, "search_applicant_resumes", lambda job, candidates: points)

    db = SimpleNamespace(commit=lambda: None)
    ranked, returned_points = matching.ranked_applicant_items(SimpleNamespace(job_id=9), db)

    assert [item["candidate_name"] for item in ranked] == ["Higher", "Lower"]
    assert [item["ranking"] for item in ranked] == [1, 2]
    assert [item["semantic_score"] for item in ranked] == [91.0, 52.0]
    assert returned_points == points


def test_ranking_degrades_without_hiding_applicants(monkeypatch) -> None:
    items = [{"application_id": 1, "candidate_id": 1, "candidate_name": "Available", "resume_id": 11}]
    monkeypatch.setattr(matching, "applicant_items", lambda job_id, db: (items, [SimpleNamespace(resume_id=11)]))

    def unavailable(job, resumes):
        raise RuntimeError("Qdrant unavailable")

    monkeypatch.setattr(matching, "search_applicant_resumes", unavailable)

    db = SimpleNamespace(commit=lambda: None)
    ranked, points = matching.ranked_applicant_items(SimpleNamespace(job_id=9), db)

    assert ranked[0]["candidate_name"] == "Available"
    assert ranked[0]["ranking_status"] == "UNAVAILABLE"
    assert ranked[0]["semantic_score"] is None
    assert points == []


def test_verified_github_relevance_has_bounded_match_weight() -> None:
    evidence = {"verified": True, "relevance_score": 90}
    assert matching.combined_match_score(80, evidence) == 81.5
    assert matching.combined_match_score(80, {"verified": False, "relevance_score": 90}) == 80
    assert matching.combined_match_score(80, {"verified": False, "relevance_score": None}) == 80


def test_candidate_match_returns_ranked_job_details(monkeypatch) -> None:
    resume = SimpleNamespace(resume_id=11, candidate_id=5, extracted_text="Python FastAPI PostgreSQL")
    job = JobPosting(job_id=42, company_id=3, recruiter_id=None, job_title="Backend Engineer", source_type="DATASET", status="ACTIVE")

    class Rows:
        def all(self):
            return [(job, "Acme")]

    class FakeDb:
        def get(self, model, item_id):
            return resume

        def execute(self, statement):
            return Rows()

    monkeypatch.setattr(matching, "search_jobs_for_resume", lambda selected_resume, limit: [SimpleNamespace(payload={"job_id": 42}, score=0.876)])
    result = matching.candidate_match(11, 20, SimpleNamespace(candidate_id=5), FakeDb())
    assert result[0]["job_title"] == "Backend Engineer"
    assert result[0]["company_name"] == "Acme"
    assert result[0]["semantic_score"] == 87.6
    assert result[0]["score"] == 0.876
