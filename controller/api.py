"""HTTP client for the simulator. The only module that touches the network."""
from __future__ import annotations

import json
import time
from typing import Iterator

import httpx


class SimError(Exception):
    """The simulator answered with an error status."""

    def __init__(self, status: int, body):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


def _body(r: httpx.Response):
    try:
        return r.json()
    except ValueError:
        return r.text[:300]


class SimClient:
    def __init__(self, base_url: str, timeout: float = 120.0, retries: int = 5):
        self._http = httpx.Client(base_url=base_url, timeout=timeout)
        self._retries = retries

    def _send(self, method: str, path: str, *, retry: bool, **kw) -> httpx.Response:
        """retry=True is only safe for reads. Writes are reconciled by the caller."""
        attempts = self._retries + 1 if retry else 1
        delay = 0.5
        for i in range(attempts):
            try:
                r = self._http.request(method, path, **kw)
                if r.status_code < 500:
                    if r.status_code >= 400:
                        raise SimError(r.status_code, _body(r))
                    return r
                err: Exception = SimError(r.status_code, _body(r))
            except httpx.TransportError as e:
                err = e
            if i == attempts - 1:
                raise err
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
        raise AssertionError("unreachable")

    def _get(self, path: str, **params):
        params = {k: v for k, v in params.items() if v is not None}
        return self._send("GET", path, retry=True, params=params or None).json()

    # ---- reads (safe to retry) ----
    def state(self):
        return self._get("/sim/state")

    def workflows(self):
        return self._get("/workflows")

    def workflow(self, wid: str):
        return self._get(f"/workflows/{wid}")

    def config(self, wid: str):
        return self._get(f"/workflows/{wid}/config")

    def config_history(self, wid: str):
        return self._get(f"/workflows/{wid}/config/history")

    def chunks(self, kind: str, after: int | None = None):
        return self._get("/events/chunks", kind=kind, after=after)

    def chunk_events(self, n: int) -> Iterator[dict]:
        text = self._send("GET", f"/events/chunks/{n}", retry=True).text
        for line in text.splitlines():
            if line:
                yield json.loads(line)

    def approvals(self, wid: str, status: str | None = None):
        return self._get("/approvals", workflow_id=wid, status=status)

    def approval(self, approval_id: str):
        return self._get(f"/approvals/{approval_id}")

    def submit_approval(self, body: dict):
        return self._send("POST", "/approvals", retry=False, json=body).json()

    def apply(self, wid: str, approval_id: str):
        return self._send("POST", f"/workflows/{wid}/apply", retry=False,
                          json={"approval_id": approval_id}).json()

    def put_config(self, wid: str, body: dict):
        return self._send("PUT", f"/workflows/{wid}/config", retry=False, json=body).json()

    def suggest_fixes(self, wid: str, problem: str):
        return self._send("POST", "/llm/suggest-fixes", retry=False,
                          json={"workflow_id": wid, "problem": problem}).json()

    def validate(self, wid: str, prompt: str, n: int):
        return self._send("POST", "/validation/runs", retry=False,
                          json={"workflow_id": wid, "prompt_version": prompt, "n": n}).json()

    # ---- writes (never blindly retried) ----
    def advance(self, minutes: int):
        return self._send("POST", "/sim/advance", retry=False, json={"minutes": minutes}).json()