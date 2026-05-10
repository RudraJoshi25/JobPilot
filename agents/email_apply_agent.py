"""
Email Apply Agent - Handles job applications via email.
Drafts email with attachments but does NOT send automatically.
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


class EmailApplyAgent:
    """Agent for drafting email-based job applications."""

    def __init__(self, profile_path: str = "data/candidate_profile.json"):
        self.profile_path = profile_path
        self.candidate_profile = self._load_profile()

    def _load_profile(self) -> Dict[str, Any]:
        """Load candidate profile."""
        with open(self.profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def draft_email_application(
        self,
        job: Dict[str, Any],
        resume_path: str,
        cover_letter_path: str
    ) -> Dict[str, Any]:
        """Draft an email application for human review and sending."""
        print(f"\nDrafting email application for: {job.get('title')} at {job.get('company')}")
        print("-" * 80)

        # Extract email info from job description or URL
        email_to = self._extract_email(job)

        if not email_to:
            print("[WARNING] No email address found in job posting")
            email_to = "[EMAIL_ADDRESS_NOT_FOUND]"

        # Get candidate info
        name = self.candidate_profile.get('name', 'Rudra Joshi')
        email = self.candidate_profile.get('email', '')

        # Draft subject line
        subject = f"Application for {job['title']} - {name}"

        # Draft email body
        body = self._draft_email_body(job, name)

        # Create email draft
        draft = {
            'job_hash': job.get('job_hash'),
            'job_title': job['title'],
            'company': job['company'],
            'to': email_to,
            'from': email,
            'subject': subject,
            'body': body,
            'attachments': [resume_path, cover_letter_path],
            'status': 'draft',
            'created_at': datetime.now().isoformat()
        }

        # Save draft to file
        self._save_draft(draft, job.get('job_hash'))

        # Print draft for review
        self._print_draft(draft)

        return draft

    def _extract_email(self, job: Dict[str, Any]) -> str:
        """Extract email address from job data."""
        # Look in job description
        description = job.get('raw_description', '')

        import re
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, description)

        if emails:
            return emails[0]

        return None

    def _draft_email_body(self, job: Dict[str, Any], candidate_name: str) -> str:
        """Draft email body."""
        body = f"""Dear Hiring Manager,

Please find attached my resume and cover letter for the {job['title']} position at {job['company']}.

I am a recent Computer Science graduate from the University of Wollongong with hands-on experience in AI/ML technologies, particularly Large Language Models, RAG systems, and prompt engineering. I am excited about this opportunity and believe my skills align well with the role requirements.

I have attached:
1. Resume (DOCX)
2. Cover Letter (DOCX)

I am based in Sydney, NSW and available for immediate start. I would welcome the opportunity to discuss how my background could contribute to your team.

Thank you for considering my application.

Best regards,
{candidate_name}"""

        return body

    def _save_draft(self, draft: Dict[str, Any], job_hash: str):
        """Save draft to file."""
        draft_dir = Path("artifacts/email_drafts")
        draft_dir.mkdir(parents=True, exist_ok=True)

        draft_file = draft_dir / f"email_draft_{job_hash}.json"

        with open(draft_file, 'w', encoding='utf-8') as f:
            json.dump(draft, f, indent=2, ensure_ascii=False)

        print(f"\n[SAVED] Draft saved to {draft_file}")

    def _print_draft(self, draft: Dict[str, Any]):
        """Print draft for human review."""
        print("\n" + "=" * 80)
        print("EMAIL APPLICATION DRAFT")
        print("=" * 80)
        print(f"\nTo:      {draft['to']}")
        print(f"From:    {draft['from']}")
        print(f"Subject: {draft['subject']}")
        print("\nAttachments:")
        for attachment in draft['attachments']:
            print(f"  - {Path(attachment).name}")
        print("\nBody:")
        print("-" * 80)
        print(draft['body'])
        print("-" * 80)
        print("\n[ACTION REQUIRED] Please review and send this email manually")
        print("Draft saved for your reference")
        print("=" * 80)


def main():
    """Example usage."""
    agent = EmailApplyAgent()

    mock_job = {
        'job_hash': 'test123',
        'title': 'AI Engineer',
        'company': 'Test Company',
        'raw_description': 'Please send your resume to jobs@testcompany.com'
    }

    draft = agent.draft_email_application(
        job=mock_job,
        resume_path="artifacts/resumes/resume_test.docx",
        cover_letter_path="artifacts/cover_letters/cover_letter_test.docx"
    )


if __name__ == "__main__":
    main()
