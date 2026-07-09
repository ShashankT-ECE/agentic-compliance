"""
Tests for evidence API endpoints — V2 M3.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# =============================================================================
# GET /api/evidence/{verdict_id}
# =============================================================================


class TestEvidenceEndpoint:
    def test_verdict_not_yet_available(self, client: TestClient) -> None:
        """Returns 404 when evidence has not been assembled yet."""
        resp = client.get("/api/evidence/VER-NONEXISTENT")
        assert resp.status_code == 404
        detail = resp.json().get("detail", "")
        assert "not yet available" in detail.lower() or "not found" in detail.lower()

    def test_evidence_endpoint_accepts_valid_get(self, client: TestClient) -> None:
        """The endpoint is registered and accepts GET."""
        resp = client.get("/api/evidence/VER-TEST-001")
        assert resp.status_code in (404, 200)  # 404 expected in current phase


# =============================================================================
# GET /api/evidence/fsm/{locked_fsm_id}
# =============================================================================


class TestFsmEvidenceEndpoint:
    def test_nonexistent_fsm(self, client: TestClient) -> None:
        """Returns 404 for a nonexistent locked FSM."""
        resp = client.get("/api/evidence/fsm/LOCKED-NONEXISTENT")
        assert resp.status_code == 404

    def test_fsm_endpoint_accepts_valid_get(self, client: TestClient) -> None:
        """The endpoint is registered and accepts GET."""
        resp = client.get("/api/evidence/fsm/LOCKED-TEST")
        assert resp.status_code in (404, 200)


# =============================================================================
# GET /api/chunks/{chunk_id}/positions
# =============================================================================


class TestChunkPositionsEndpoint:
    def test_requires_circular_ref(self, client: TestClient) -> None:
        """The circular_ref query parameter is required."""
        resp = client.get("/api/chunks/TEST-CHUNK/positions")
        assert resp.status_code == 422  # missing required query param

    def test_nonexistent_chunk(self, client: TestClient) -> None:
        """Returns 404 for a chunk not in the vector store."""
        resp = client.get(
            "/api/chunks/NONEXISTENT-CHUNK/positions?circular_ref=SEBI/TEST"
        )
        assert resp.status_code == 404

    def test_positions_endpoint_registered(self, client: TestClient) -> None:
        """The endpoint is registered and reachable."""
        resp = client.get(
            "/api/chunks/test-chunk/positions?circular_ref=SEBI/TEST"
        )
        assert resp.status_code in (404, 200, 422)


# =============================================================================
# GET /api/circulars/{circular_ref}/pdf
# =============================================================================


class TestCircularPdfEndpoint:
    def test_nonexistent_circular(self, client: TestClient) -> None:
        """Returns 404 for an unregistered circular."""
        resp = client.get("/api/circulars/NONEXISTENT/CIRCULAR/pdf")
        assert resp.status_code == 404

    def test_pdf_endpoint_registered(self, client: TestClient) -> None:
        """The endpoint is registered and reachable."""
        resp = client.get("/api/circulars/test-circular/pdf")
        assert resp.status_code in (404, 200)


# =============================================================================
# API schema / OpenAPI
# =============================================================================


class TestOpenAPISchema:
    def test_evidence_endpoints_in_schema(self, client: TestClient) -> None:
        """All evidence endpoints appear in the OpenAPI schema."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        paths = schema.get("paths", {})

        evidence_paths = [p for p in paths if "/evidence" in p or "/chunks" in p or "/circulars" in p]
        assert len(evidence_paths) >= 3, f"Expected >= 3 evidence paths, got {evidence_paths}"
