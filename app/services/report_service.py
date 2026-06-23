import logging
import uuid

from app.config import settings
from app.services.html_report_renderer import render_compliance_html
from app.services.scraper_service import utcnow_iso
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class ReportService:
    def __init__(self):
        self.storage = StorageService()

    def generate_report(
        self,
        workflow: dict,
        comparison: dict,
    ) -> dict:
        structured = comparison.get("structured_result") or {}
        report_id = str(uuid.uuid4())
        now = utcnow_iso()

        html = self._render_html(workflow, structured, report_id=report_id, created_at=now)
        html_path = self.storage.save_report_html(report_id, html)

        score = structured.get("overall_compliance_score")

        report = {
            "id": report_id,
            "workflow_id": workflow["id"],
            "comparison_id": comparison["id"],
            "product_name": workflow["product_name"],
            "summary": structured.get("executive_summary", ""),
            "assessment_confidence": structured.get("assessment_confidence", "low"),
            "compliance_score": score,
            "compliance_level": structured.get("compliance_level", "undetermined"),
            "missing_evidence": structured.get("missing_evidence") or [],
            "structured_result": structured,
            "html": html,
            "html_path": html_path,
            "created_at": now,
        }

        self.storage.save_report(report_id, report)
        logger.info("Generated HTML report %s for workflow %s", report_id, workflow["id"])
        return report

    def get_report(self, report_id: str) -> dict | None:
        return self.storage.load_report(report_id)

    def get_report_html(self, report: dict, workflow: dict) -> str:
        if report.get("html"):
            return report["html"]

        html = self._render_html(
            workflow,
            report.get("structured_result") or {},
            report_id=report["id"],
            created_at=report.get("created_at", ""),
        )
        report["html"] = html
        report["html_path"] = self.storage.save_report_html(report["id"], html)
        self.storage.save_report(report["id"], report)
        return html

    def _render_html(
        self,
        workflow: dict,
        result: dict,
        *,
        report_id: str,
        created_at: str,
    ) -> str:
        return render_compliance_html(
            workflow,
            result,
            report_id=report_id,
            created_at=created_at,
        )
