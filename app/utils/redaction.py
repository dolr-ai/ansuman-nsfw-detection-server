from urllib.parse import urlsplit, urlunsplit


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    redacted_query = "REDACTED" if parts.query else ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, redacted_query, ""))

