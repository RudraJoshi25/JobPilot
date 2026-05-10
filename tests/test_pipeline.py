#!/usr/bin/env python3
"""
Complete pipeline test using existing test scrape data.
Tests: normalizer → matcher → resume agent → cover letter agent
"""
import sys
import json
import shutil
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.normalizer_agent import NormalizerAgent
from agents.match_agent import MatchAgent
from agents.resume_agent import ResumeAgent
from agents.cover_letter_agent import CoverLetterAgent


def print_section_header(title):
    """Print section header."""
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)
    print()


def print_subsection(title):
    """Print subsection header."""
    print()
    print("-" * 100)
    print(title)
    print("-" * 100)


def run_pipeline_test():
    """Run complete pipeline test."""
    print_section_header("COMPLETE PIPELINE TEST")

    test_input = "data/test_scrape.json"

    if not Path(test_input).exists():
        print(f"[ERROR] Test data not found at {test_input}")
        return 1

    # Limit to 2 jobs to avoid rate limits
    with open(test_input, 'r', encoding='utf-8') as f:
        all_test_jobs = json.load(f)

    limited_jobs = all_test_jobs[:2]

    limited_test_file = "data/test_scrape_limited.json"
    with open(limited_test_file, 'w', encoding='utf-8') as f:
        json.dump(limited_jobs, f, indent=2)

    print(f"[INFO] Limited test to {len(limited_jobs)} jobs to avoid rate limits")

    # Step 1: Normalize test jobs
    print_subsection("STEP 1: NORMALIZING TEST JOBS")

    normalizer = NormalizerAgent(batch_size=10, batch_delay=3.0)

    try:
        normalizer.normalize_jobs(
            input_file=limited_test_file,
            output_file="data/test_pipeline_clean.json",
            skipped_file="data/test_pipeline_skipped.json"
        )

        clean_jobs = normalizer.normalized_jobs

        if not clean_jobs:
            print("[ERROR] No jobs were normalized")
            return 1

        print(f"\n[OK] Normalized {len(clean_jobs)} jobs")

    except Exception as e:
        print(f"[ERROR] Normalization failed: {e}")
        return 1

    # Step 2: Match jobs against candidate profile
    print_subsection("STEP 2: MATCHING JOBS AGAINST CANDIDATE PROFILE")

    match_agent = MatchAgent()
    scored_jobs = []

    for job in clean_jobs:
        try:
            job_description = format_job_for_matching(job)
            match_result = match_agent.evaluate_match(job_description)

            scored_jobs.append({
                'job': job,
                'match': {
                    'score': match_result.score,
                    'verdict': match_result.verdict,
                    'matching_skills': match_result.matching_skills,
                    'missing_skills': match_result.missing_skills,
                    'reasons': match_result.reasons
                }
            })

            print(f"  {job['title'][:50]:50} Score: {match_result.score:5.1f} ({match_result.verdict})")

            # Add delay between API calls
            time.sleep(3)

        except Exception as e:
            print(f"  {job['title'][:50]:50} [ERROR] {str(e)[:30]}")

    scored_jobs.sort(key=lambda x: x['match']['score'], reverse=True)

    print(f"\n[OK] Matched {len(scored_jobs)} jobs")

    if not scored_jobs:
        print("[ERROR] No jobs were scored")
        return 1

    # Step 3: Show top job details
    print_subsection("STEP 3: TOP SCORING JOB")

    top_job = scored_jobs[0]
    job = top_job['job']
    match = top_job['match']

    print(f"Title:             {job['title']}")
    print(f"Company:           {job['company']}")
    print(f"Location:          {job['location']}")
    print(f"Seniority:         {job['seniority_level']}")
    print(f"Employment Type:   {job['employment_type']}")
    print(f"Match Score:       {match['score']:.1f}/100")
    print(f"Verdict:           {match['verdict'].upper()}")
    print(f"Matching Skills:   {', '.join(match['matching_skills'][:5])}")
    print(f"Missing Skills:    {', '.join(match['missing_skills'][:5])}")

    # Step 4: Generate tailored resume
    print_subsection("STEP 4: GENERATING TAILORED RESUME")

    resume_agent = ResumeAgent()

    try:
        resume_files = resume_agent.generate_tailored_resume(
            job=job,
            match_report=match,
            output_dir="artifacts/test_resumes"
        )

        print("\n[OK] Resume generated successfully")

        # Read and display changelog
        with open(resume_files['changelog'], 'r', encoding='utf-8') as f:
            changelog = f.read()

        print_subsection("RESUME CHANGELOG")
        # Handle Unicode for Windows console
        try:
            print(changelog)
        except UnicodeEncodeError:
            print(changelog.encode('ascii', 'replace').decode('ascii'))

    except Exception as e:
        print(f"[ERROR] Resume generation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Step 5: Generate cover letter
    print_subsection("STEP 5: GENERATING COVER LETTER")

    cover_letter_agent = CoverLetterAgent()

    try:
        tailored_resume = None
        if Path(resume_files['markdown']).exists():
            with open(resume_files['markdown'], 'r', encoding='utf-8') as f:
                tailored_resume = f.read()

        cover_letter_files = cover_letter_agent.generate_cover_letter(
            job=job,
            match_report=match,
            tailored_resume=tailored_resume,
            output_dir="artifacts/test_cover_letters"
        )

        print("\n[OK] Cover letter generated successfully")

        # Read and display cover letter
        with open(cover_letter_files['markdown'], 'r', encoding='utf-8') as f:
            cover_letter = f.read()

        print_subsection("GENERATED COVER LETTER")
        # Handle Unicode for Windows console
        try:
            print(cover_letter)
        except UnicodeEncodeError:
            print(cover_letter.encode('ascii', 'replace').decode('ascii'))

    except Exception as e:
        print(f"[ERROR] Cover letter generation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Summary
    print_section_header("TEST SUMMARY")

    print("[PASS] Pipeline test completed successfully!")
    print()
    print(f"  1. Normalized {len(clean_jobs)} jobs")
    print(f"  2. Matched {len(scored_jobs)} jobs")
    print(f"  3. Top job: {job['title']} (score: {match['score']:.1f})")
    print(f"  4. Generated tailored resume")
    print(f"  5. Generated cover letter")
    print()
    print("Artifacts generated:")
    print(f"  - Resume (MD):     {resume_files['markdown']}")
    print(f"  - Resume (DOCX):   {resume_files['docx']}")
    print(f"  - Changelog:       {resume_files['changelog']}")
    print(f"  - Cover Letter (MD):   {cover_letter_files['markdown']}")
    print(f"  - Cover Letter (DOCX): {cover_letter_files['docx']}")

    print()
    return 0


def format_job_for_matching(job):
    """Format a normalized job for match evaluation."""
    parts = [
        f"Job Title: {job['title']}",
        f"Company: {job['company']}",
        f"Location: {job['location']}",
        f"Employment Type: {job['employment_type']}",
        f"Seniority Level: {job['seniority_level']}"
    ]

    if job.get('salary_min') or job.get('salary_max'):
        parts.append(f"Salary: ${job.get('salary_min', 0):,} - ${job.get('salary_max', 0):,}")

    if job['required_skills']:
        parts.append(f"Required Skills: {', '.join(job['required_skills'])}")

    if job['nice_to_have_skills']:
        parts.append(f"Nice to Have: {', '.join(job['nice_to_have_skills'])}")

    if job['responsibilities']:
        parts.append(f"Responsibilities:\n" + '\n'.join(f"- {r}" for r in job['responsibilities']))

    parts.append(f"\nJob Description:\n{job['raw_description']}")

    return '\n'.join(parts)


if __name__ == "__main__":
    sys.exit(run_pipeline_test())
