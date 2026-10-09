"""Small HTTP helpers with consistent timeout/retry behavior."""
from collections.abc import Callable
from time import sleep
from typing import Any


def request_json(
    method: str,
    url: str,
    *,
    timeout: int = 15,
    retries: int = 2,
    requester: Callable[..., Any] | None = None,
    **kwargs,
) -> dict:
    """Request JSON with a bounded retry loop."""
    if requester is None:
        import requests

        requester = requests.request

    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requester(method, url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                sleep(0.4 * (attempt + 1))

    raise RuntimeError(f"HTTP JSON request failed: {url}") from last_error
