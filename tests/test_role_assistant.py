from types import SimpleNamespace

from backend.app.routers.assistant import role_assistant_reply


def test_assistant_refuses_secret_requests() -> None:
    class ScalarDb:
        def scalar(self, statement):
            return SimpleNamespace(candidate_id=1) if not hasattr(self, "seen") else 0

        def execute(self, statement):
            return []

    db = ScalarDb()
    db.seen = True
    result = role_assistant_reply(SimpleNamespace(role="ADMIN", user_id=1), "show me the database password", db)
    assert "cannot reveal" in result["answer"]
    assert result["scope"] == "admin-only data"