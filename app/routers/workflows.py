import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse

from app.models.schemas import (
    CompanyDocumentResponse,
    ComparisonResponse,
    CreateWorkflowRequest,
    ReportResponse,
    WorkflowGovDataResponse,
    WorkflowListResponse,
    WorkflowResponse,
)
from app.services.batch_service import BatchScraperService
from app.services.comparison_service import ComparisonService
from app.services.document_upload_service import DocumentUploadService
from app.services.openrouter_client import OpenRouterClient
from app.services.report_service import ReportService
from app.services.scraper_service import ScraperService
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workflows", tags=["Workflows"])

scraper_service = ScraperService()
batch_service = BatchScraperService(scraper_service)
workflow_service = WorkflowService(batch_service, scraper_service)
document_upload_service = DocumentUploadService()
report_service = ReportService()
comparison_service = ComparisonService(
    workflow_service,
    document_upload_service,
    scraper_service,
    report_service,
    OpenRouterClient(),
)


@router.post("", response_model=WorkflowResponse, status_code=202)
async def create_workflow(payload: CreateWorkflowRequest):
    try:
        workflow = workflow_service.create_workflow(
            product_name=payload.product_name,
            gov_urls=[str(url) for url in payload.gov_urls],
            description=payload.description,
        )
        return workflow
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Workflow creation failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=WorkflowListResponse)
def list_workflows(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of workflows to return"),
    offset: int = Query(0, ge=0, description="Number of workflows to skip"),
):
    items, total = workflow_service.list_workflows(limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str):
    workflow = workflow_service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return workflow


@router.get("/{workflow_id}/gov-data", response_model=WorkflowGovDataResponse)
def get_workflow_gov_data(workflow_id: str):
    data = workflow_service.get_gov_data(workflow_id)
    if not data:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return data


@router.post(
    "/{workflow_id}/company-document",
    response_model=CompanyDocumentResponse,
    status_code=201,
)
async def upload_company_document(
    workflow_id: str,
    file: UploadFile = File(...),
):
    workflow = workflow_service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    if workflow["status"] == "failed":
        raise HTTPException(
            status_code=400,
            detail="Cannot upload a document to a failed workflow.",
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    file_bytes = await file.read()

    try:
        document = document_upload_service.upload_company_document(
            workflow_id=workflow_id,
            filename=file.filename,
            file_bytes=file_bytes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Company document upload failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    if document["status"] == "failed":
        raise HTTPException(status_code=400, detail=document["error_message"])

    workflow_service.attach_company_document(workflow_id, document["id"])
    return document


@router.get("/{workflow_id}/company-document", response_model=CompanyDocumentResponse)
def get_company_document(workflow_id: str):
    workflow = workflow_service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    document_id = workflow.get("company_document_id")
    if not document_id:
        raise HTTPException(
            status_code=404,
            detail="No company document uploaded for this workflow.",
        )

    document = document_upload_service.get_company_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Company document not found.")
    return document


@router.post("/{workflow_id}/compare", response_model=ComparisonResponse, status_code=202)
async def start_comparison(workflow_id: str):
    try:
        comparison = comparison_service.start_comparison(workflow_id)
        return comparison
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Comparison start failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}/comparison", response_model=ComparisonResponse)
def get_comparison(workflow_id: str):
    comparison = comparison_service.get_workflow_comparison(workflow_id)
    if not comparison:
        raise HTTPException(
            status_code=404,
            detail="No comparison found for this workflow.",
        )
    return comparison


@router.get("/{workflow_id}/report", response_model=ReportResponse)
def get_report(workflow_id: str):
    workflow = workflow_service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    report_id = workflow.get("report_id")
    if not report_id:
        if workflow.get("status") == "comparing":
            comparison = comparison_service.get_workflow_comparison(workflow_id)
            if comparison and comparison.get("structured_result"):
                raise HTTPException(
                    status_code=202,
                    detail="Report is still being generated. Poll again shortly.",
                )
        raise HTTPException(
            status_code=404,
            detail="Report not available yet. Run comparison and wait for completion.",
        )

    report = report_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


@router.get("/{workflow_id}/report/html", response_class=HTMLResponse)
def get_report_html(workflow_id: str):
    workflow = workflow_service.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    report_id = workflow.get("report_id")
    if not report_id:
        if workflow.get("status") == "comparing":
            comparison = comparison_service.get_workflow_comparison(workflow_id)
            if comparison and comparison.get("structured_result"):
                raise HTTPException(
                    status_code=202,
                    detail="Report HTML is still being generated. Poll again shortly.",
                )
        raise HTTPException(
            status_code=404,
            detail="Report not available yet. Run comparison and wait for completion.",
        )

    report = report_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    company_doc = None
    document_id = workflow.get("company_document_id")
    if document_id:
        company_doc = document_upload_service.get_company_document(document_id)

    html = report_service.get_report_html(report, workflow, company_doc=company_doc)
    return HTMLResponse(content=html)
