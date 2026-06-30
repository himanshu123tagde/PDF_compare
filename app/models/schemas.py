from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, HttpUrl, Field


class ExtractUrlRequest(BaseModel):
    url: HttpUrl


class BatchExtractRequest(BaseModel):
    urls: List[HttpUrl] = Field(..., min_length=1)


class BatchJobItemResponse(BaseModel):
    url: str
    status: str
    article_id: Optional[str] = None
    error_message: Optional[str] = None


class BatchJobResponse(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed"]
    total: int
    completed: int
    succeeded: int
    failed: int
    pending: int
    running: int
    items: List[BatchJobItemResponse]
    created_at: str
    updated_at: str


class UpdateArticleRequest(BaseModel):
    extracted_title: Optional[str] = None
    cleaned_text: Optional[str] = None
    admin_edited_text: Optional[str] = None


class ScrapedArticleResponse(BaseModel):
    id: str
    url: str
    domain: str
    status: str
    extracted_title: Optional[str] = None
    extracted_text: Optional[str] = None
    cleaned_text: Optional[str] = None
    admin_edited_text: Optional[str] = None
    ai_regenerated_text: Optional[str] = None
    extraction_method: Optional[str] = None
    extraction_log: List[str] = []
    metadata: Dict[str, Any] = {}
    error_message: Optional[str] = None
    word_count: int = 0


class ArticleListResponse(BaseModel):
    items: List[ScrapedArticleResponse]
    total: int


class CreateWorkflowRequest(BaseModel):
    product_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    gov_urls: List[HttpUrl] = Field(..., min_length=1, max_length=10)


class WorkflowGovArticleSummary(BaseModel):
    id: str
    url: str
    status: str
    extracted_title: Optional[str] = None
    cleaned_text: Optional[str] = None
    admin_edited_text: Optional[str] = None
    word_count: int = 0
    error_message: Optional[str] = None


class CompanyDocumentResponse(BaseModel):
    id: str
    workflow_id: str
    filename: str
    file_type: str
    word_count: int
    status: Literal["processed", "failed"]
    error_message: Optional[str] = None
    extracted_text: Optional[str] = None
    created_at: str


class WorkflowResponse(BaseModel):
    id: str
    product_name: str
    description: Optional[str] = None
    status: Literal["scraping", "ready", "comparing", "completed", "failed"]
    gov_urls: List[str]
    gov_article_ids: List[str] = []
    batch_job_id: Optional[str] = None
    company_document_id: Optional[str] = None
    comparison_id: Optional[str] = None
    report_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class WorkflowListResponse(BaseModel):
    items: List[WorkflowResponse]
    total: int
    limit: int
    offset: int


class WorkflowGovDataResponse(BaseModel):
    workflow_id: str
    product_name: str
    status: str
    articles: List[WorkflowGovArticleSummary]


class ComparisonGovSourceResponse(BaseModel):
    article_id: str
    url: str
    title: Optional[str] = None


class ComparisonResponse(BaseModel):
    id: str
    workflow_id: str
    status: Literal["queued", "running", "completed", "failed"]
    model: str
    gov_sources: List[ComparisonGovSourceResponse]
    company_document_id: str
    structured_result: Optional[Dict[str, Any]] = None
    token_usage: Optional[Dict[str, int]] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None


class ReportResponse(BaseModel):
    id: str
    workflow_id: str
    comparison_id: str
    product_name: str
    summary: str
    assessment_confidence: str
    compliance_score: Optional[int] = None
    compliance_level: str
    missing_evidence: List[str] = []
    structured_result: Dict[str, Any]
    html_type: str = "fixed_document"
    html: str
    html_path: str
    created_at: str
