from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from .config import settings


class Judge0Error(RuntimeError):
    pass


def language_id(language: str) -> int:
    mapping = {
        "python": settings.judge0_python_id,
        "javascript": settings.judge0_javascript_id,
        "java": settings.judge0_java_id,
    }
    try:
        return mapping[language]
    except KeyError as exc:
        raise Judge0Error(f"Unsupported Judge0 language: {language}") from exc


def _encoded(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _decoded(value: str | None) -> str:
    if not value:
        return ""
    try:
        return base64.b64decode(value).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return str(value)


def _request(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    # Judge0's public demo is protected by Cloudflare, which rejects the
    # default Python urllib browser signature with Cloudflare error 1010.
    # Explicit API/browser headers also remain valid for self-hosted Judge0.
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36 GAINT-Interns-Hub/5.0"
        ),
    }
    if settings.judge0_auth_token:
        headers[settings.judge0_auth_header] = settings.judge0_auth_token
    request = urllib.request.Request(
        f"{settings.judge0_url}{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise Judge0Error(f"Judge0 returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise Judge0Error(f"Judge0 is unavailable at {settings.judge0_url}: {exc}") from exc


def submit_tests(source_code: str, language: str, cases: list[dict]) -> list[str]:
    tokens = []
    for case in cases:
        result = _request(
            "/submissions?base64_encoded=true&wait=false",
            method="POST",
            payload={
                "language_id": language_id(language),
                "source_code": _encoded(source_code),
                "stdin": _encoded(str(case.get("stdin", ""))),
                "expected_output": _encoded(str(case.get("expected_output", ""))),
                "cpu_time_limit": 3,
                "wall_time_limit": 6,
                "memory_limit": 128000,
            },
        )
        token = result.get("token")
        if not token:
            raise Judge0Error(f"Judge0 did not return a submission token: {result}")
        tokens.append(token)
    return tokens


def fetch_results(tokens: list[str]) -> list[dict]:
    results = []
    fields = "token,status,stdout,stderr,compile_output,message,time,memory"
    for token in tokens:
        result = _request(f"/submissions/{token}?base64_encoded=true&fields={fields}")
        status = result.get("status") or {}
        results.append({
            "token": token,
            "status_id": int(status.get("id", 0)),
            "status": status.get("description", "Unknown"),
            "time": result.get("time"),
            "memory": result.get("memory"),
            "stdout": _decoded(result.get("stdout"))[:2_000],
            "stderr": _decoded(result.get("stderr"))[:2_000],
            "compile_output": _decoded(result.get("compile_output"))[:2_000],
            "message": _decoded(result.get("message"))[:1_000],
        })
    return results


def health() -> dict:
    try:
        result = _request("/about")
        return {"available": True, "version": result.get("version"), "url": settings.judge0_url}
    except Judge0Error as exc:
        return {"available": False, "url": settings.judge0_url, "detail": str(exc)}
