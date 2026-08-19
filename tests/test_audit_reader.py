import json

from backend.app.services.audit_reader import mask_client_ip, read_audit_events


def test_audit_reader_masks_ip_and_formats_events(tmp_path) -> None:
    records = [
        {"timestamp": "2026-08-20T10:00:00+00:00", "service": "auth", "action": "http_request", "request_id": "req-1", "method": "POST", "path": "/api/auth/login", "client_ip": "14.195.132.38", "status": 401, "outcome": "rejected", "duration_ms": 12.5},
        {"timestamp": "2026-08-20T10:01:00+00:00", "service": "jobs", "action": "http_request", "request_id": "req-2", "method": "GET", "path": "/api/jobs", "client_ip": "127.0.0.1", "user_id": "8", "role": "RECRUITER", "status": 200, "outcome": "success"},
    ]
    (tmp_path / "audit.log").write_text("\n".join(json.dumps(record) for record in records) + "\nmalformed", encoding="utf-8")

    total, items = read_audit_events(str(tmp_path), query="login", outcome="REJECTED")

    assert total == 1
    assert items[0]["event"] == "POST /api/auth/login"
    assert items[0]["client_network"] == "14.195.x.x"
    assert "14.195.132.38" not in items[0]["details"]


def test_ip_masking_handles_ipv4_ipv6_and_unknown_values() -> None:
    assert mask_client_ip("10.20.30.40") == "10.20.x.x"
    assert mask_client_ip("2001:db8::1").endswith("::/32")
    assert mask_client_ip("proxy-name") == "masked"