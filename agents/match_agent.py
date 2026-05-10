import json
import os
from pathlib import Path
from typing import Dict, Any
from services.claude_client import ClaudeClient
from pydantic import BaseModel, Field


class MatchResult(BaseModel):
    score: float = Field(..., ge=0, le=100, description="Overall match score from 0-100")
    verdict: str = Field(..., description="apply, maybe, or skip")
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reasons: str = Field(..., description="Detailed reasoning for the verdict")


class MatchAgent:
    def __init__(self, profile_path: str = None, claude_client: ClaudeClient = None):
        self.profile_path = profile_path or os.path.join("data", "candidate_profile.json")
        self.candidate_profile = self._load_profile()
        self.client = claude_client or ClaudeClient(model="claude-haiku-4-5-20251001")

    def _load_profile(self) -> Dict[str, Any]:
        profile_file = Path(self.profile_path)
        if not profile_file.exists():
            raise FileNotFoundError(f"Candidate profile not found at {self.profile_path}")

        with open(profile_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def evaluate_match(self, job_description: str) -> MatchResult:
        prompt = self._build_evaluation_prompt(job_description)
        system_prompt = self._build_system_prompt()

        result = self.client.generate_structured(
            prompt=prompt,
            response_model=MatchResult,
            system=system_prompt,
            max_tokens=2048
        )

        if result.score >= 75:
            result.verdict = "apply"
        elif result.score >= 50:
            result.verdict = "maybe"
        else:
            result.verdict = "skip"

        return result

    def _build_system_prompt(self) -> str:
        return """You are an expert career advisor and recruiter specializing in AI/ML roles.
Your task is to evaluate how well a candidate matches a job posting.

Scoring guidelines:
- 90-100: Exceptional match, candidate meets all requirements and exceeds expectations
- 75-89: Strong match, candidate meets most key requirements
- 50-74: Moderate match, candidate has some relevant skills but gaps exist
- 25-49: Weak match, significant skill gaps or misalignment
- 0-24: Poor match, fundamentally different role or requirements

Consider:
1. Skills alignment (technical skills, tools, frameworks)
2. Experience level match (junior/senior alignment)
3. Role type match (job title and responsibilities)
4. Domain expertise match (AI/ML vs other domains)
5. Education requirements

Be honest and realistic. Don't inflate scores. Consider the candidate's constraints around honest representation."""

    def _build_evaluation_prompt(self, job_description: str) -> str:
        profile_summary = self._format_profile()

        return f"""Evaluate how well this candidate matches the job posting.

CANDIDATE PROFILE:
{profile_summary}

JOB POSTING:
{job_description}

Provide:
1. A score from 0-100 indicating match quality
2. List of matching_skills (skills the candidate has that the job requires)
3. List of missing_skills (required skills the candidate lacks)
4. Detailed reasons explaining your assessment

Be critical but fair. Consider experience level appropriateness."""

    def _format_profile(self) -> str:
        profile = self.candidate_profile

        skills_all = []
        if isinstance(profile.get("skills"), dict):
            for category, skill_list in profile["skills"].items():
                skills_all.extend(skill_list)
        elif isinstance(profile.get("skills"), list):
            skills_all = profile["skills"]

        education_str = ""
        if profile.get("education"):
            edu = profile["education"][0] if isinstance(profile["education"], list) else profile["education"]
            education_str = f"{edu.get('degree', 'N/A')} - {edu.get('institution', 'N/A')} ({edu.get('graduation_year', 'N/A')})"

        return f"""Name: {profile.get('name', 'N/A')}
Location: {profile.get('location', 'N/A')} - {profile.get('remote_preference', 'N/A')}
Target Roles: {', '.join(profile.get('target_roles', []))}
Experience Level: {profile.get('experience_level', 'Graduate/Entry-level')}
Preferred Seniority: {', '.join(profile.get('preferred_seniority', []))}
Education: {education_str}
Skills: {', '.join(skills_all)}
Key Strengths: {', '.join(profile.get('key_strengths', []))}"""


def match_job(job_description: str, profile_path: str = None) -> MatchResult:
    agent = MatchAgent(profile_path=profile_path)
    return agent.evaluate_match(job_description)
