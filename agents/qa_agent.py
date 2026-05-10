"""
QA Agent - Quality assurance for generated resumes and cover letters.
Uses Claude Haiku 4.5 for cost-effective validation.
"""
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from services.claude_client import ClaudeClient


class QAIssue(BaseModel):
    """Single QA issue."""
    check_name: str
    severity: str  # low, medium, high
    description: str
    suggestion: str


class QAReport(BaseModel):
    """Complete QA report."""
    passed: bool
    checks_run: int
    checks_passed: int
    issues: List[QAIssue] = Field(default_factory=list)
    auto_fixable: List[str] = Field(default_factory=list)
    recommendation: str  # approve, fix_and_retry, reject


class QAAgent:
    """Agent for quality assurance of application documents."""

    def __init__(self, profile_path: str = "data/candidate_profile.json"):
        self.profile_path = profile_path
        self.candidate_profile = self._load_profile()
        self.client = ClaudeClient(model="claude-haiku-4-5-20251001")

    def _load_profile(self) -> Dict[str, Any]:
        """Load candidate profile."""
        with open(self.profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def run_qa(
        self,
        resume_path: str,
        cover_letter_path: str,
        job: Dict[str, Any],
        auto_fix: bool = True
    ) -> QAReport:
        """Run complete QA on resume and cover letter."""
        print(f"\nRunning QA for: {job.get('title', 'Unknown')} at {job.get('company', 'Unknown')}")
        print("-" * 80)

        resume_text = self._read_file(resume_path)
        cover_letter_text = self._read_file(cover_letter_path)

        issues = []

        # HONESTY CHECKS
        print("Running honesty checks...")
        issues.extend(self._check_honesty(resume_text, cover_letter_text))

        # QUALITY CHECKS
        print("Running quality checks...")
        issues.extend(self._check_quality(resume_text, cover_letter_text, job))

        # FORMAT CHECKS
        print("Running format checks...")
        issues.extend(self._check_format(resume_text, cover_letter_text))

        # Calculate results
        checks_run = 14  # Total number of checks
        checks_passed = checks_run - len(issues)
        passed = len(issues) == 0

        # Determine auto-fixable issues
        auto_fixable = [
            issue.check_name for issue in issues
            if issue.severity == "low"
        ]

        # Determine recommendation
        if passed:
            recommendation = "approve"
        elif len([i for i in issues if i.severity == "high"]) > 0:
            recommendation = "reject"
        else:
            recommendation = "fix_and_retry"

        report = QAReport(
            passed=passed,
            checks_run=checks_run,
            checks_passed=checks_passed,
            issues=issues,
            auto_fixable=auto_fixable,
            recommendation=recommendation
        )

        print(f"\n[QA] {checks_passed}/{checks_run} checks passed")
        print(f"[QA] Recommendation: {recommendation.upper()}")

        return report

    def _check_honesty(self, resume: str, cover_letter: str) -> List[QAIssue]:
        """Run honesty checks using Claude."""
        issues = []

        # Extract all skills and tools from profile
        profile_skills = self._extract_profile_skills()
        profile_json = json.dumps(self.candidate_profile, indent=2)

        prompt = f"""Analyze these documents for SERIOUS honesty violations ONLY.

CANDIDATE PROFILE (GROUND TRUTH):
{profile_json}

RESUME:
{resume[:3000]}

COVER LETTER:
{cover_letter}

STRICT GUIDELINES - Only flag these as fabrication:
1. Company names NOT in work_experience (e.g., claiming to work at Google when profile shows TSPL)
2. Job titles NOT in work_experience (e.g., "Senior Engineer" when profile shows "Intern")
3. Years of experience that contradict profile dates
4. Completely invented projects not in the profile

DO NOT FLAG these (they are acceptable):
✓ Paraphrasing project highlights (e.g., "40% reduction" IS in HealthEcho project)
✓ Technical descriptions using profile skills (e.g., "RAG systems" when profile lists "RAG")
✓ Metrics from the profile projects (HealthEcho has "40% false positive reduction")
✓ Skill descriptions that naturally describe listed skills
✓ Reasonable inference from profile data (e.g., "production experience" when profile shows live projects)

ONLY flag clear fabrications - be VERY lenient with paraphrasing and technical descriptions.

Return JSON list of ONLY serious violations:
[
  {{
    "type": "fabricated_company|fabricated_role|fabricated_years",
    "content": "the exact fabricated text",
    "reason": "why this is clearly not in the profile"
  }}
]

If no serious violations found, return empty list: []"""

        try:
            result = self.client.generate_json(
                prompt=prompt,
                system="You are a lenient fact-checker. Only flag clear fabrications like fake companies or roles. Allow paraphrasing and technical descriptions of real profile content.",
                max_tokens=2048
            )

            if isinstance(result, list) and len(result) > 0:
                for item in result:
                    issues.append(QAIssue(
                        check_name=f"honesty_{item['type']}",
                        severity="high",
                        description=f"Fabricated content: {item['content']}",
                        suggestion=f"Remove or replace: {item['reason']}"
                    ))

        except Exception as e:
            print(f"  [WARNING] Honesty check failed: {e}")

        return issues

    def _check_quality(self, resume: str, cover_letter: str, job: Dict[str, Any]) -> List[QAIssue]:
        """Run quality checks."""
        issues = []

        # Check 5: LaTeX resume validity
        if not resume.strip().startswith('%') and '\\begin{document}' not in resume:
            issues.append(QAIssue(
                check_name="invalid_latex",
                severity="high",
                description="Resume does not appear to be valid LaTeX",
                suggestion="Ensure output contains \\begin{document} and LaTeX structure"
            ))

        # Check 5b: Resume has bullet points (LaTeX uses \item \small)
        bullet_count = resume.count('\\item \\small')
        if bullet_count < 10:
            issues.append(QAIssue(
                check_name="insufficient_bullets",
                severity="medium",
                description=f"Resume has only {bullet_count} bullet points (expected 10+)",
                suggestion="Add more detail to experience and projects sections"
            ))

        # Check 6: Cover letter word count
        cl_words = len(cover_letter.split())
        if cl_words < 150:
            issues.append(QAIssue(
                check_name="cover_letter_word_count",
                severity="medium",
                description=f"Cover letter too short: {cl_words} words (minimum 150)",
                suggestion="Add more specific examples"
            ))
        elif cl_words > 400:
            issues.append(QAIssue(
                check_name="cover_letter_word_count",
                severity="low",
                description=f"Cover letter too long: {cl_words} words (maximum 400)",
                suggestion="Be more concise"
            ))

        # Check 7: Company name mentioned in cover letter (skip if unknown)
        company = job.get('company', '')
        # Skip this check if company is unknown/generic placeholder
        if company and company not in ['None', 'Unknown', 'Unknown Company', 'N/A']:
            if company.lower() not in cover_letter.lower():
                issues.append(QAIssue(
                    check_name="company_name_missing",
                    severity="high",
                    description=f"Company name '{company}' not mentioned in cover letter",
                    suggestion=f"Add reference to {company} in the opening paragraph"
                ))

        # Check 8: Role title mentioned in cover letter
        title = job.get('title', '')
        if title and title.lower() not in cover_letter.lower():
            issues.append(QAIssue(
                check_name="role_title_missing",
                severity="medium",
                description=f"Role title '{title}' not mentioned in cover letter",
                suggestion=f"Reference the specific role in your cover letter"
            ))

        # Check 9: JD keywords in resume (only if we have required skills to check)
        required_skills = job.get('required_skills', [])
        if required_skills and len(required_skills) > 0:
            keyword_count = sum(1 for skill in required_skills[:10] if skill.lower() in resume.lower())
            if keyword_count < 3:
                issues.append(QAIssue(
                    check_name="insufficient_keywords",
                    severity="medium",
                    description=f"Only {keyword_count} JD keywords found in resume (need at least 3)",
                    suggestion=f"Incorporate more of these keywords: {', '.join(required_skills[:5])}"
                ))

        # Check 10: No placeholder text
        placeholders = [
            r'\[Company Name\]', r'\[company\]', r'\[Date\]', r'\[date\]',
            r'\[Role\]', r'\[role\]', r'\[Your Name\]', r'TODO', r'XXX'
        ]
        for pattern in placeholders:
            if re.search(pattern, resume, re.IGNORECASE) or re.search(pattern, cover_letter, re.IGNORECASE):
                issues.append(QAIssue(
                    check_name="placeholder_text",
                    severity="high",
                    description=f"Placeholder text found: {pattern}",
                    suggestion="Replace all placeholder text with actual content"
                ))
                break

        return issues

    def _check_format(self, resume: str, cover_letter: str) -> List[QAIssue]:
        """Run format checks."""
        issues = []

        # Check 11: LaTeX resume has required sections
        resume_lower = resume.lower()
        missing_sections = []

        # Check for LaTeX section markers or common section names
        if 'skill' not in resume_lower and 'technical' not in resume_lower:
            missing_sections.append('Skills')
        if 'education' not in resume_lower:
            missing_sections.append('Education')
        if 'experience' not in resume_lower and 'project' not in resume_lower:
            missing_sections.append('Experience or Projects')

        if missing_sections:
            issues.append(QAIssue(
                check_name="missing_sections",
                severity="high",
                description=f"Resume missing sections: {', '.join(missing_sections)}",
                suggestion="Add all required resume sections"
            ))

        # Check 12: Cover letter has 3-5 paragraphs (lenient)
        # Clean the text first - remove any headers/analysis sections
        cl_clean = cover_letter
        if '---' in cl_clean:
            parts = cl_clean.split('---')
            cl_clean = parts[-1]  # Take content after last separator

        # Remove common header patterns
        cl_clean = '\n'.join([line for line in cl_clean.split('\n')
                             if not line.strip().startswith('#')
                             and not line.strip().startswith('**(')])

        paragraphs = [p.strip() for p in cl_clean.split('\n\n') if p.strip() and len(p.strip()) > 50]

        if len(paragraphs) < 3:
            issues.append(QAIssue(
                check_name="cover_letter_structure",
                severity="medium",
                description=f"Cover letter has {len(paragraphs)} paragraphs (need 3-5)",
                suggestion="Structure as: 1) Opening insight, 2) Transparency, 3) Projects, 4) Closing"
            ))
        elif len(paragraphs) > 6:
            issues.append(QAIssue(
                check_name="cover_letter_structure",
                severity="low",
                description=f"Cover letter has {len(paragraphs)} paragraphs (should be 3-5)",
                suggestion="Combine paragraphs for better flow"
            ))

        # Check 13: No ALL CAPS sections (except LaTeX comments and headings)
        lines = resume.split('\n')
        for line in lines:
            line = line.strip()
            # Skip LaTeX comments
            if line.startswith('%'):
                continue
            if len(line) > 20 and line.isupper() and not line.startswith('#'):
                issues.append(QAIssue(
                    check_name="all_caps_text",
                    severity="low",
                    description=f"ALL CAPS text found: {line[:50]}...",
                    suggestion="Use title case instead of ALL CAPS"
                ))
                break

        # Check 14: No repeated sentences
        resume_sentences = [s.strip() for s in re.split(r'[.!?]', resume) if len(s.strip()) > 30]
        cl_sentences = [s.strip() for s in re.split(r'[.!?]', cover_letter) if len(s.strip()) > 30]

        for cl_sent in cl_sentences:
            for resume_sent in resume_sentences:
                if cl_sent.lower() == resume_sent.lower():
                    issues.append(QAIssue(
                        check_name="repeated_sentences",
                        severity="low",
                        description=f"Sentence repeated in both documents: {cl_sent[:60]}...",
                        suggestion="Vary wording between resume and cover letter"
                    ))
                    break

        return issues

    def _extract_profile_skills(self) -> List[str]:
        """Extract all skills from candidate profile."""
        skills = []

        if isinstance(self.candidate_profile.get('skills'), dict):
            for category, skill_list in self.candidate_profile['skills'].items():
                skills.extend(skill_list)
        elif isinstance(self.candidate_profile.get('skills'), list):
            skills = self.candidate_profile['skills']

        return [s.lower() for s in skills]

    def _read_file(self, filepath: str) -> str:
        """Read file content."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"  [ERROR] Failed to read {filepath}: {e}")
            return ""


def main():
    """Example usage."""
    agent = QAAgent()

    # Load a test job
    with open('data/jobs_shortlisted.json', 'r') as f:
        shortlisted = json.load(f)

    if shortlisted:
        job = shortlisted[0]['job']
        job_hash = job['job_hash']

        resume_path = f"artifacts/resumes/resume_{job_hash}.md"
        cover_letter_path = f"artifacts/cover_letters/cover_letter_{job_hash}.md"

        if Path(resume_path).exists() and Path(cover_letter_path).exists():
            report = agent.run_qa(resume_path, cover_letter_path, job)

            print("\n" + "=" * 80)
            print("QA REPORT")
            print("=" * 80)
            print(f"Status: {'PASSED' if report.passed else 'FAILED'}")
            print(f"Checks: {report.checks_passed}/{report.checks_run}")
            print(f"Recommendation: {report.recommendation.upper()}")

            if report.issues:
                print("\nIssues Found:")
                for issue in report.issues:
                    print(f"  [{issue.severity.upper()}] {issue.check_name}")
                    print(f"    {issue.description}")
                    print(f"    → {issue.suggestion}")


if __name__ == "__main__":
    main()
