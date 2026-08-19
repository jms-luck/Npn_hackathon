from types import SimpleNamespace

from backend.app.services import blob


def test_sas_url_uses_blob_client_canonical_url(monkeypatch) -> None:
    service = SimpleNamespace(
        account_name="account",
        credential=SimpleNamespace(account_key="secret"),
        get_blob_client=lambda container, path: SimpleNamespace(url=f"https://account.blob.core.windows.net/{container}/{path}"),
    )
    monkeypatch.setattr(blob, "get_blob_service", lambda: service)
    monkeypatch.setattr(blob, "generate_blob_sas", lambda **kwargs: "signed-token")

    url = blob.create_download_url("candidate_1/resume.pdf")

    assert url == "https://account.blob.core.windows.net/resumes/candidate_1/resume.pdf?signed-token"
    assert "blob.core.windows.net//" not in url
