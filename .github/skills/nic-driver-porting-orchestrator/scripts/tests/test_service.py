"""
Test suite for the FastAPI service (service/app.py).

Tests request models, endpoints (health/ready), and request validation
without needing an actual LLM connection.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)

# Mock azure and langchain before importing app to avoid startup issues
with patch.dict(os.environ, {
    "AZURE_OPENAI_ENDPOINT": "https://fake.openai.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT": "gpt-4.1",
}):
    # Patch lifespan to avoid calling real LLM init
    import service.app as _svc_mod
    @_svc_mod.asynccontextmanager
    async def _noop_lifespan(app):
        yield
    _svc_mod.app.router.lifespan_context = _noop_lifespan

    from service.app import (
        app, JobStatus, PortRequest, JobResult,
    )

from fastapi.testclient import TestClient


class TestModels(unittest.TestCase):
    """Test Pydantic request/response models."""

    def test_port_request_required_field(self):
        req = PortRequest(driver_name="ixgbe")
        self.assertEqual(req.driver_name, "ixgbe")
        self.assertEqual(req.target_os, "freebsd")  # default
        self.assertIsNone(req.source_dir)
        self.assertIsNone(req.connection_info)

    def test_port_request_custom(self):
        req = PortRequest(
            driver_name="ice",
            target_os="windows",
            source_dir="/src/ice",
            connection_info={"host": "10.0.0.1"},
        )
        self.assertEqual(req.driver_name, "ice")
        self.assertEqual(req.target_os, "windows")
        self.assertEqual(req.source_dir, "/src/ice")
        self.assertEqual(req.connection_info, {"host": "10.0.0.1"})

    def test_job_status_values(self):
        self.assertEqual(JobStatus.PENDING, "pending")
        self.assertEqual(JobStatus.RUNNING, "running")
        self.assertEqual(JobStatus.COMPLETED, "completed")
        self.assertEqual(JobStatus.FAILED, "failed")

    def test_job_result_defaults(self):
        result = JobResult(job_id="abc123", status=JobStatus.PENDING)
        self.assertEqual(result.job_id, "abc123")
        self.assertIsNone(result.report)
        self.assertIsNone(result.native_score)
        self.assertIsNone(result.portability_score)
        self.assertIsNone(result.errors)


class TestEndpoints(unittest.TestCase):
    """Test health/ready endpoints (no LLM required)."""

    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_ready_no_llm(self):
        """Readiness probe should fail when LLM is not initialised."""
        import service.app as svc
        original = svc._llm
        svc._llm = None
        try:
            response = self.client.get("/ready")
            self.assertEqual(response.status_code, 503)
        finally:
            svc._llm = original

    def test_ready_with_llm(self):
        """Readiness probe should succeed when LLM is set."""
        import service.app as svc
        original = svc._llm
        svc._llm = MagicMock()  # fake LLM
        try:
            response = self.client.get("/ready")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ready"})
        finally:
            svc._llm = original

    def test_get_nonexistent_job(self):
        response = self.client.get("/port/nonexistent123")
        self.assertEqual(response.status_code, 404)

    def test_openapi_schema(self):
        """Verify the OpenAPI schema loads and has correct metadata."""
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertEqual(schema["info"]["title"], "NIC Driver Porting Orchestrator")
        self.assertEqual(schema["info"]["version"], "2.0.0")
        self.assertIn("/port", schema["paths"])
        self.assertIn("/health", schema["paths"])


if __name__ == "__main__":
    unittest.main()
