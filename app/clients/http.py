import httpx


def create_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=True)

