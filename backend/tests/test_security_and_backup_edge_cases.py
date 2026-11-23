"""Comprehensive security, auth, CORS, PII guardrail, and backup restore edge-case tests."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient


PROTECTED_GET_ENDPOINTS = [
    "/api/v1/vault",
    "/api/v1/vault/qa-rules",
    "/api/v1/resumes",
    "/api/v1/jobs",
    "/api/v1/watchlist",
    "/api/v1/collectors/health",
    "/api/v1/collectors/runs",
    "/api/v1/collectors/progress",
    "/api/v1/collectors/scheduler",
    "/api/v1/applications",
    "/api/v1/applications/analytics",
    "/api/v1/backup/export",
]

PROTECTED_POST_ENDPOINTS = [
    ("/api/v1/jobs/ingest", {"jobs": []}),
    ("/api/v1/jobs/rescore", {}),
    ("/api/v1/extension/check-page", {"page_url": "https://example.com"}),
    ("/api/v1/applications/draft", {"company_slug": "razorpay"}),
    ("/api/v1/collectors/scheduler/start", {}),
    ("/api/v1/collectors/scheduler/stop", {}),
]


def test_missing_empty_and_malformed_tokens_rejected_everywhere(client: TestClient) -> None:
    """Every protected /api/v1 route must reject missing, empty, or wrong X-Local-Token with 401."""
    bad_headers_list = [
        {},
        {"X-Local-Token": ""},
        {"X-Local-Token": "   "},
        {"X-Local-Token": "0" * 64},
        {"X-Local-Token": "Bearer some-token"},
    ]

    for url in PROTECTED_GET_ENDPOINTS:
        for hdrs in bad_headers_list:
            resp = client.get(url, headers=hdrs)
            assert resp.status_code == 401, f"GET {url} with {hdrs} returned {resp.status_code}"
            assert "X-Local-Token" in resp.json()["detail"]

    for url, body in PROTECTED_POST_ENDPOINTS:
        for hdrs in bad_headers_list:
            resp = client.post(url, json=body, headers=hdrs)
            assert resp.status_code == 401, f"POST {url} with {hdrs} returned {resp.status_code}"


def test_cors_origins_and_preflight_behavior(client: TestClient) -> None:
    """Verify allowed loopback/chrome-extension origins vs blocked external origins and bad extension IDs."""
    # Allowed localhost dev origin (in Settings.allowed_cors_origins)
    r_local = client.options(
        "/api/v1/jobs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type,X-Local-Token",
        },
    )
    assert r_local.status_code == 200
    assert r_local.headers.get("access-control-allow-origin") == "http://localhost:5173"

    # Valid 32-char [a-p] Chrome extension ID allowed
    ext_ok = "chrome-extension://" + ("a" * 32)
    r_ext = client.options(
        "/api/v1/extension/check-page",
        headers={"Origin": ext_ok, "Access-Control-Request-Method": "POST"},
    )
    assert r_ext.headers.get("access-control-allow-origin") == ext_ok

    # Malformed Chrome extension ID (wrong length or non [a-p] chars) must NOT be allowed
    for bad_origin in [
        "chrome-extension://shortid",
        "chrome-extension://" + ("z" * 32),
        "https://attacker.evil.com",
        "http://192.168.1.50:8000",
        "null",
    ]:
        r_bad = client.options(
            "/api/v1/vault",
            headers={"Origin": bad_origin, "Access-Control-Request-Method": "GET"},
        )
        assert r_bad.headers.get("access-control-allow-origin") is None


def test_pii_guardrail_comprehensive_indian_patterns(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Block all variants of PAN, Aadhaar, Passport, DOB, Bank/IFSC, and UAN/PF."""
    blocked_cases = [
        ("PAN", "SafeValue123"),
        ("Permanent Account Number", "SafeValue123"),
        ("Enter your Aadhaar Card UIDAI", "NotANum"),
        ("Aadhar no", "12345"),
        ("What is your Passport #?", "NotAPassport"),
        ("Applicant Date of Birth", "1998-01-01"),
        ("DOB", "01/01/1998"),
        ("Birth Date", "15 Aug 1998"),
        ("Bank Account Details", "SBI"),
        ("Provide IFSC Code", "SBIN0001234"),
        ("Account Number for stipend", "123456"),
        ("EPFO / PF Account Number", "MH123"),
        ("UAN no", "999"),
        # Innocent question containing PAN or Aadhaar value pattern
        ("Referral ID", "ABCDE1234F"),
        ("Reference number", "abcdE9876z"),
        ("Candidate Identifier", "4567 8901 2345"),
        ("Candidate Identifier Dashed", "4567-8901-2345"),
        ("Candidate Identifier Compact", "456789012345"),
    ]

    for question, answer in blocked_cases:
        resp = client.post(
            "/api/v1/vault/qa-rules",
            headers=auth_headers,
            json={"question": question, "verified_answer": answer},
        )
        assert resp.status_code == 422, f"Expected PII rejection for ({question}, {answer}), got {resp.status_code}"

    # Verify non-PII technical/compensation answers pass cleanly
    allowed_cases = [
        ("What is your expected CTC in LPA?", "28 LPA"),
        ("Are you willing to relocate to Bengaluru?", "Yes"),
        ("Years of experience with Kubernetes?", "3.5"),
    ]
    for question, answer in allowed_cases:
        resp = client.post(
            "/api/v1/vault/qa-rules",
            headers=auth_headers,
            json={"question": question, "verified_answer": answer},
        )
        assert resp.status_code == 201


def test_backup_restore_malicious_and_corrupted_archives(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Reject Zip Slip traversal, drive-letter paths, missing jobs.db, non-SQLite headers, and corrupt SQLite."""
    # 1. Zip missing jobs.db
    buf_no_db = io.BytesIO()
    with zipfile.ZipFile(buf_no_db, "w") as zf:
        zf.writestr("manifest.json", "{}")
    r_no_db = client.post(
        "/api/v1/backup/restore",
        headers=auth_headers,
        files={"file": ("no_db.zip", buf_no_db.getvalue(), "application/zip")},
    )
    assert r_no_db.status_code == 422
    assert "missing required 'jobs.db'" in r_no_db.json()["detail"].lower()

    # 2. Fake SQLite header (fails PRAGMA quick_check / SQLite magic)
    buf_bad_magic = io.BytesIO()
    with zipfile.ZipFile(buf_bad_magic, "w") as zf:
        zf.writestr("jobs.db", b"NotAnSQLiteFileAtAll")
    r_bad_magic = client.post(
        "/api/v1/backup/restore",
        headers=auth_headers,
        files={"file": ("bad_magic.zip", buf_bad_magic.getvalue(), "application/zip")},
    )
    assert r_bad_magic.status_code == 422
    assert "not a valid sqlite" in r_bad_magic.json()["detail"].lower()

    # 3. Corrupted SQLite bytes starting with valid magic header (fails sqlite3 PRAGMA quick_check)
    buf_corrupt_sqlite = io.BytesIO()
    with zipfile.ZipFile(buf_corrupt_sqlite, "w") as zf:
        zf.writestr("jobs.db", b"SQLite format 3\x00" + b"\xff" * 2048)
    r_corrupt = client.post(
        "/api/v1/backup/restore",
        headers=auth_headers,
        files={"file": ("corrupt_db.zip", buf_corrupt_sqlite.getvalue(), "application/zip")},
    )
    assert r_corrupt.status_code == 422

    # 4. Unsafe Zip paths (Windows backslash traversal, drive letter, leading slash)
    for evil_name in [
        "..\\..\\evil.pdf",
        "resumes/../../escape.pdf",
        "/etc/passwd",
        "C:\\Windows\\System32\\cmd.exe",
    ]:
        buf_evil = io.BytesIO()
        with zipfile.ZipFile(buf_evil, "w") as zf:
            zf.writestr(evil_name, "evil")
            zf.writestr("jobs.db", b"SQLite format 3\x00dummy")
        r_evil = client.post(
            "/api/v1/backup/restore",
            headers=auth_headers,
            files={"file": ("evil.zip", buf_evil.getvalue(), "application/zip")},
        )
        assert r_evil.status_code == 422, f"Failed to block unsafe path: {evil_name}"
        assert "unsafe" in r_evil.json()["detail"].lower()


def test_spa_html_token_injection_and_404_api_routes(client: TestClient) -> None:
    """Verify root returns 200 HTML and unknown /api routes return 404 instead of SPA fallback."""
    r_root = client.get("/")
    assert r_root.status_code == 200
    assert "text/html" in r_root.headers["content-type"]

    r_missing_api = client.get("/api/v1/nonexistent-endpoint")
    # Unauthenticated /api/v1 still hits token middleware first -> 401
    assert r_missing_api.status_code == 401
    r_missing_auth = client.get(
        "/api/v1/nonexistent-endpoint",
        headers={"X-Local-Token": client.app.state.local_token},
    )
    assert r_missing_auth.status_code == 404

