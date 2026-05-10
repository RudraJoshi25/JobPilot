from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class JobListing(BaseModel):
    job_id: str
    title: str
    company: str
    location: Optional[str] = None
    description: str
    requirements: List[str] = Field(default_factory=list)
    salary_range: Optional[str] = None
    url: str
    posted_date: Optional[datetime] = None
    scraped_at: datetime = Field(default_factory=datetime.now)
    raw_html: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResumeProfile(BaseModel):
    profile_id: str
    full_name: str
    email: str
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    summary: str
    skills: List[str] = Field(default_factory=list)
    experience: List[Dict[str, Any]] = Field(default_factory=list)
    education: List[Dict[str, Any]] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    projects: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class MatchScore(BaseModel):
    overall_score: float = Field(..., ge=0, le=100)
    skills_match: float = Field(..., ge=0, le=100)
    experience_match: float = Field(..., ge=0, le=100)
    education_match: float = Field(..., ge=0, le=100)


class MatchReport(BaseModel):
    report_id: str
    job_id: str
    profile_id: str
    match_score: MatchScore
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    should_apply: bool
    reasoning: str
    created_at: datetime = Field(default_factory=datetime.now)


class QACheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"


class QAReport(BaseModel):
    report_id: str
    job_id: str
    profile_id: str
    application_id: Optional[str] = None
    status: QACheckStatus
    checks_performed: List[str] = Field(default_factory=list)
    issues_found: List[Dict[str, Any]] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    fields_verified: Dict[str, bool] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"


class ApplicationRun(BaseModel):
    run_id: str
    job_id: str
    profile_id: str
    status: ApplicationStatus
    match_report_id: Optional[str] = None
    qa_report_id: Optional[str] = None
    cover_letter: Optional[str] = None
    application_data: Dict[str, Any] = Field(default_factory=dict)
    screenshots: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
