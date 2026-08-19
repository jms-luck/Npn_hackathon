import hashlib
import ipaddress
import json
from pathlib import Path


KNOWN_FIELDS = {
    "timestamp", "level", "logger", "message", "service", "action", "request_id", "method", "path",
    "client_ip", "user_id", "role", "is_write", "status", "duration_ms", "outcome",
}


def mask_client_ip(value: str | None) -> str | None:
    if not value or value == "testclient":
        return value
    if value.endswith(".x.x") or value.endswith("::/32") or value == "masked":
        return value
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return "masked"
    if address.version == 4:
        octets = value.split(".")
        return f"{octets[0]}.{octets[1]}.x.x"
    return f"{address.exploded.split(':')[0]}:{address.exploded.split(':')[1]}::/32"


def _event_title(event: dict) -> str:
    if event.get("action") == "http_request":
        method = event.get("method", "REQUEST")
        path = event.get("path", "unknown route")
        return f"{method} {path}"
    if event.get("action") == "http_request_failed":
        return f"Failed {event.get('method', 'request')} {event.get('path', '')}".strip()
    return str(event.get("action") or event.get("message") or "System event").replace("_", " ").title()


def readable_event(event: dict, source: str, line_number: int) -> dict:
    request_id = str(event.get("request_id") or "")
    event_id = request_id or hashlib.sha256(f"{source}:{line_number}:{json.dumps(event, sort_keys=True)}".encode()).hexdigest()[:24]
    actor = f"{event.get('role', 'USER')} #{event['user_id']}" if event.get("user_id") else "Anonymous / system"
    client_network = mask_client_ip(event.get("client_ip"))
    extra = {key: value for key, value in event.items() if key not in KNOWN_FIELDS and key != "exception"}
    detail_lines = [
        f"Request ID: {request_id or 'not provided'}",
        f"Actor: {actor}",
        f"Client network: {client_network or 'not recorded'}",
        f"Method: {event.get('method') or 'n/a'}",
        f"Path: {event.get('path') or 'n/a'}",
        f"Status: {event.get('status') if event.get('status') is not None else 'n/a'}",
        f"Write operation: {'Yes' if event.get('is_write') else 'No'}",
    ]
    if extra:
        detail_lines.append(f"Additional context: {json.dumps(extra, default=str, sort_keys=True)}")
    return {
        "event_id": event_id,
        "timestamp": event.get("timestamp"),
        "event": _event_title(event),
        "service": event.get("service") or "system",
        "actor": actor,
        "outcome": str(event.get("outcome") or event.get("level") or "unknown").upper(),
        "status": event.get("status"),
        "duration_ms": event.get("duration_ms"),
        "request_id": request_id or None,
        "client_network": client_network,
        "details": "\n".join(detail_lines),
    }


def read_audit_events(
    log_dir: str,
    page: int = 1,
    limit: int = 20,
    query: str | None = None,
    service: str | None = None,
    outcome: str | None = None,
    order: str = "desc",
) -> tuple[int, list[dict]]:
    directory = Path(log_dir)
    paths = sorted(directory.glob("audit.log*"))
    events = []
    for path in paths:
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line_number, line in enumerate(stream, start=1):
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    item = readable_event(raw, path.name, line_number)
                    if service and item["service"].casefold() != service.casefold():
                        continue
                    if outcome and item["outcome"].casefold() != outcome.casefold():
                        continue
                    if query and query.casefold() not in json.dumps(item, default=str).casefold():
                        continue
                    events.append(item)
        except OSError:
            continue
    events.sort(key=lambda item: item.get("timestamp") or "", reverse=order == "desc")
    total = len(events)
    start = (page - 1) * limit
    return total, events[start : start + limit]