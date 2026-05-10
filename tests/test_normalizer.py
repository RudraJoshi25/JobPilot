#!/usr/bin/env python3
"""
Test the normalizer agent on scraped test data.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.normalizer_agent import NormalizerAgent


def print_table_row(cols, widths):
    """Print a formatted table row."""
    row = " | ".join(str(col)[:w].ljust(w) for col, w in zip(cols, widths))
    print(f"| {row} |")


def print_table_separator(widths):
    """Print table separator."""
    sep = "-+-".join("-" * w for w in widths)
    print(f"+-{sep}-+")


def run_test():
    print("=" * 120)
    print("NORMALIZER AGENT TEST")
    print("=" * 120)
    print()

    test_input = "data/test_scrape.json"
    test_output = "data/test_normalized.json"
    test_skipped = "data/test_skipped.json"

    if not Path(test_input).exists():
        print(f"[ERROR] Test data not found at {test_input}")
        print("Run: python generate_test_data.py")
        return 1

    with open(test_input, 'r', encoding='utf-8') as f:
        test_jobs = json.load(f)

    print(f"Loaded {len(test_jobs)} test jobs from {test_input}")
    print()

    normalizer = NormalizerAgent(batch_size=5, batch_delay=1.0)

    print("Starting normalization...")
    print()

    try:
        results = normalizer.normalize_jobs(
            input_file=test_input,
            output_file=test_output,
            skipped_file=test_skipped
        )

        print()
        print("=" * 120)
        print("NORMALIZED JOBS TABLE")
        print("=" * 120)
        print()

        if normalizer.normalized_jobs:
            widths = [30, 20, 12, 14, 15, 18]
            headers = ["Title", "Company", "Seniority", "Employment", "Remote", "Skills Count"]

            print_table_separator(widths)
            print_table_row(headers, widths)
            print_table_separator(widths)

            for job in normalizer.normalized_jobs:
                row = [
                    job['title'],
                    job['company'],
                    job['seniority_level'],
                    job['employment_type'],
                    "Yes" if job['remote_friendly'] else "No",
                    f"{len(job['required_skills'])} required"
                ]
                print_table_row(row, widths)

            print_table_separator(widths)
            print()

            print("=" * 120)
            print("DETAILED FIELD VERIFICATION")
            print("=" * 120)
            print()

            required_fields = [
                'job_hash', 'title', 'company', 'location', 'employment_type',
                'seniority_level', 'apply_type', 'required_skills', 'nice_to_have_skills',
                'responsibilities', 'remote_friendly', 'jd_word_count', 'source',
                'url', 'raw_description', 'normalized_at'
            ]

            all_valid = True

            for idx, job in enumerate(normalizer.normalized_jobs, 1):
                print(f"\nJob {idx}: {job['title'][:60]}")
                print("-" * 80)

                missing_fields = [field for field in required_fields if field not in job]

                if missing_fields:
                    print(f"  [FAIL] Missing fields: {', '.join(missing_fields)}")
                    all_valid = False
                else:
                    print(f"  [OK] All required fields present")

                print(f"  [OK] Job hash: {job['job_hash']}")
                print(f"  [OK] Company: {job['company']}")
                print(f"  [OK] Location: {job['location']}")
                print(f"  [OK] Employment: {job['employment_type']}")
                print(f"  [OK] Seniority: {job['seniority_level']}")
                print(f"  [OK] Remote friendly: {job['remote_friendly']}")
                print(f"  [OK] Required skills: {len(job['required_skills'])} ({', '.join(job['required_skills'][:3])}...)")
                print(f"  [OK] Nice-to-have skills: {len(job['nice_to_have_skills'])}")
                print(f"  [OK] Responsibilities: {len(job['responsibilities'])}")
                print(f"  [OK] Visa sponsorship: {job['visa_sponsorship']}")
                print(f"  [OK] JD word count: {job['jd_word_count']}")

                if job.get('salary_min') or job.get('salary_max'):
                    print(f"  [OK] Salary range: ${job.get('salary_min', 0):,} - ${job.get('salary_max', 0):,}")

            print()
            print("=" * 120)

            if all_valid and results['normalized'] == len(test_jobs):
                print("[PASS] All jobs normalized successfully with all required fields")
                return 0
            elif all_valid:
                print(f"[PARTIAL] {results['normalized']}/{len(test_jobs)} jobs normalized successfully")
                return 0
            else:
                print("[FAIL] Some jobs missing required fields")
                return 1

        else:
            print("[FAIL] No jobs were normalized")
            return 1

    except Exception as e:
        print(f"\n[ERROR] Normalization failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_test())
