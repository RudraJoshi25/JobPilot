#!/usr/bin/env python3
"""
Test QA Agent on previously generated resume and cover letter.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.qa_agent import QAAgent


def print_check_result(check_name, passed, details=""):
    """Print a single check result."""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {check_name}")
    if details and not passed:
        print(f"       {details}")


def run_qa_test():
    """Run QA test on generated documents."""
    print("=" * 100)
    print("QA AGENT TEST")
    print("=" * 100)
    print()

    # Find the most recent test artifacts
    test_resume_dir = Path("artifacts/test_resumes")
    test_cl_dir = Path("artifacts/test_cover_letters")

    if not test_resume_dir.exists() or not test_cl_dir.exists():
        print("[ERROR] Test artifacts not found. Run tests/test_pipeline.py first.")
        return 1

    # Get first resume and cover letter
    resume_files = list(test_resume_dir.glob("resume_*.md"))
    cl_files = list(test_cl_dir.glob("cover_letter_*.md"))

    if not resume_files or not cl_files:
        print("[ERROR] No resume or cover letter found in test artifacts.")
        return 1

    resume_path = str(resume_files[0])
    cl_path = str(cl_files[0])

    print(f"Testing documents:")
    print(f"  Resume:        {resume_path}")
    print(f"  Cover Letter:  {cl_path}")
    print()

    # Load actual job data from test pipeline
    test_clean_jobs = Path("data/test_pipeline_clean.json")
    if test_clean_jobs.exists():
        with open(test_clean_jobs, 'r') as f:
            clean_jobs = json.load(f)
            if clean_jobs:
                job = clean_jobs[0]
                print(f"Using actual job: {job.get('title')} at {job.get('company')}")
            else:
                print("[WARNING] No clean jobs found, using mock data")
                job = None
    else:
        job = None

    # Fallback to mock job if needed
    if job is None:
        job = {
            'title': 'Graduate AI Engineer',
            'company': 'None',  # Match what was actually in the test
            'job_hash': 'test123',
            'required_skills': [
                'Python', 'Machine Learning', 'LLMs', 'RAG',
                'Prompt Engineering', 'APIs', 'NLP'
            ]
        }

    # Run QA
    print("-" * 100)
    print("RUNNING QA CHECKS")
    print("-" * 100)

    agent = QAAgent()

    try:
        report = agent.run_qa(resume_path, cl_path, job, auto_fix=False)

        print()
        print("=" * 100)
        print("DETAILED QA REPORT")
        print("=" * 100)
        print()

        # Read files for manual checks display
        with open(resume_path, 'r', encoding='utf-8') as f:
            resume = f.read()
        with open(cl_path, 'r', encoding='utf-8') as f:
            cover_letter = f.read()

        # Display all checks
        print("HONESTY CHECKS")
        print("-" * 100)

        honesty_issues = [i for i in report.issues if 'honesty' in i.check_name or 'fabricat' in i.check_name.lower()]
        if not honesty_issues:
            print_check_result("No fabricated skills or claims", True)
            print_check_result("No unsupported metrics or numbers", True)
            print_check_result("No unlisted tools or technologies", True)
        else:
            for issue in honesty_issues:
                print_check_result(issue.check_name, False, issue.description)

        print()
        print("QUALITY CHECKS")
        print("-" * 100)

        # Word counts
        resume_words = len(resume.split())
        cl_words = len(cover_letter.split())

        wc_issue = next((i for i in report.issues if 'word_count' in i.check_name and 'resume' in i.check_name), None)
        print_check_result(
            f"Resume word count (400-700): {resume_words} words",
            wc_issue is None
        )

        cl_wc_issue = next((i for i in report.issues if 'word_count' in i.check_name and 'cover_letter' in i.check_name), None)
        print_check_result(
            f"Cover letter word count (150-300): {cl_words} words",
            cl_wc_issue is None
        )

        # Company and role mentions
        company_issue = next((i for i in report.issues if 'company_name' in i.check_name), None)
        print_check_result(
            f"Company name mentioned in cover letter",
            company_issue is None
        )

        role_issue = next((i for i in report.issues if 'role_title' in i.check_name), None)
        print_check_result(
            f"Role title mentioned in cover letter",
            role_issue is None
        )

        # Keywords
        keyword_issue = next((i for i in report.issues if 'keyword' in i.check_name), None)
        required_skills = job.get('required_skills', ['Python', 'Machine Learning', 'LLMs'])
        keyword_count = sum(1 for skill in required_skills if skill.lower() in resume.lower())
        print_check_result(
            f"JD keywords in resume: {keyword_count} found (need 3+)",
            keyword_issue is None
        )

        # Placeholders
        placeholder_issue = next((i for i in report.issues if 'placeholder' in i.check_name), None)
        print_check_result(
            "No placeholder text found",
            placeholder_issue is None
        )

        print()
        print("FORMAT CHECKS")
        print("-" * 100)

        # Section checks
        section_issue = next((i for i in report.issues if 'section' in i.check_name), None)
        print_check_result(
            "Resume has required sections (Summary, Skills, Experience, Education)",
            section_issue is None
        )

        # Paragraph structure
        structure_issue = next((i for i in report.issues if 'structure' in i.check_name), None)
        paragraphs = [p.strip() for p in cover_letter.split('\n\n') if p.strip() and len(p.strip()) > 50]
        print_check_result(
            f"Cover letter has 3 paragraphs: {len(paragraphs)} found",
            structure_issue is None
        )

        # Caps check
        caps_issue = next((i for i in report.issues if 'caps' in i.check_name), None)
        print_check_result(
            "No ALL CAPS sections (except headings)",
            caps_issue is None
        )

        # Repeated sentences
        repeat_issue = next((i for i in report.issues if 'repeat' in i.check_name), None)
        print_check_result(
            "No repeated sentences between documents",
            repeat_issue is None
        )

        print()
        print("=" * 100)
        print("QA SUMMARY")
        print("=" * 100)
        print()

        print(f"Overall Status:    {'PASSED' if report.passed else 'FAILED'}")
        print(f"Checks Run:        {report.checks_run}")
        print(f"Checks Passed:     {report.checks_passed}")
        print(f"Checks Failed:     {report.checks_run - report.checks_passed}")
        print(f"Recommendation:    {report.recommendation.upper()}")

        if report.issues:
            print()
            print("ISSUES FOUND:")
            print("-" * 100)
            for i, issue in enumerate(report.issues, 1):
                print(f"\n{i}. [{issue.severity.upper()}] {issue.check_name}")
                print(f"   Description: {issue.description}")
                print(f"   Suggestion:  {issue.suggestion}")

            if report.auto_fixable:
                print()
                print(f"Auto-fixable issues: {', '.join(report.auto_fixable)}")

        print()
        print("=" * 100)

        if report.passed:
            print("[SUCCESS] All QA checks passed! Documents are ready for submission.")
            return 0
        elif report.recommendation == "approve":
            print("[SUCCESS] QA approved with minor issues.")
            return 0
        elif report.recommendation == "fix_and_retry":
            print("[WARNING] Some issues need fixing. Auto-fix available for:", ', '.join(report.auto_fixable))
            return 0
        else:
            print("[FAILURE] QA rejected. Major issues found that require manual intervention.")
            return 1

    except Exception as e:
        print(f"\n[ERROR] QA test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_qa_test())
