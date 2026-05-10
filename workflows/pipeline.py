"""
Main job application pipeline orchestrator.
Wires together source, normalizer, and match agents.
"""
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from agents.source_agent import MultiSourceAgent
from agents.normalizer_agent import NormalizerAgent
from agents.match_agent import MatchAgent


class JobPipeline:
    """Main pipeline orchestrating the job application workflow."""

    def __init__(
        self,
        search_terms: List[str],
        location: str = "Sydney NSW",
        min_score_apply: int = 75,
        min_score_maybe: int = 60
    ):
        self.search_terms = search_terms
        self.location = location
        self.min_score_apply = min_score_apply
        self.min_score_maybe = min_score_maybe

        self.raw_jobs_file = Path("data/jobs_raw.json")
        self.clean_jobs_file = Path("data/jobs_clean.json")
        self.shortlisted_file = Path("data/jobs_shortlisted.json")

    async def run(self, test_mode: bool = False) -> Dict[str, Any]:
        """Run the complete pipeline."""
        print("=" * 100)
        print("JOB APPLICATION PIPELINE")
        print("=" * 100)
        print(f"Search terms: {', '.join(self.search_terms)}")
        print(f"Location: {self.location}")
        print(f"Filters: Apply (score >= {self.min_score_apply}), Maybe (score >= {self.min_score_maybe})")
        if test_mode:
            print(f"Mode: TEST (sequential processing for rate limits)")
        print("=" * 100)
        print()

        # Step 1: Source jobs
        raw_jobs = await self._source_jobs()

        # Step 2: Normalize jobs
        clean_jobs = self._normalize_jobs()

        # Step 3: Match jobs (parallel in production, sequential in test)
        shortlisted = await self._match_and_filter_jobs(clean_jobs, test_mode=test_mode)

        # Step 4: Save and display results
        self._save_shortlisted(shortlisted)
        self._print_summary(shortlisted)

        return {
            "raw_jobs": len(raw_jobs),
            "clean_jobs": len(clean_jobs),
            "shortlisted": len(shortlisted),
            "apply": sum(1 for j in shortlisted if j['match']['verdict'] == 'apply'),
            "maybe": sum(1 for j in shortlisted if j['match']['verdict'] == 'maybe')
        }

    async def _source_jobs(self) -> List[Dict[str, Any]]:
        """Source jobs using MultiSourceAgent or load existing data."""
        print("\n[STEP 1] SOURCING JOBS")
        print("-" * 100)

        if self._is_cache_valid():
            print(f"Found recent cache at {self.raw_jobs_file} (less than 24 hours old)")
            print("Loading existing jobs...")

            with open(self.raw_jobs_file, 'r', encoding='utf-8') as f:
                jobs = json.load(f)

            print(f"Loaded {len(jobs)} jobs from cache")
            return jobs

        print("No valid cache found. Scraping jobs from sources...")
        print()

        agent = MultiSourceAgent(headless=True, max_jobs_per_search=15)
        agent.visit_job_pages = False  # Set to True for full descriptions

        jobs = await agent.run(self.search_terms, self.location)

        return jobs

    def _normalize_jobs(self) -> List[Dict[str, Any]]:
        """Normalize jobs using NormalizerAgent."""
        print("\n[STEP 2] NORMALIZING JOBS")
        print("-" * 100)

        normalizer = NormalizerAgent(batch_size=5, batch_delay=1.0)

        normalizer.normalize_jobs(
            input_file=str(self.raw_jobs_file),
            output_file=str(self.clean_jobs_file),
            skipped_file="data/jobs_skipped.json"
        )

        return normalizer.normalized_jobs

    async def _match_and_filter_jobs(self, clean_jobs: List[Dict[str, Any]], test_mode: bool = False) -> List[Dict[str, Any]]:
        """
        Match jobs against candidate profile and filter by score.

        RATE LIMIT FIX: In test mode, process sequentially.
        In production, limit to 2 concurrent jobs with semaphore.
        """
        mode_str = "SEQUENTIAL (test mode)" if test_mode else "PARALLEL (max 2 concurrent)"
        print(f"\n[STEP 3] MATCHING & FILTERING JOBS ({mode_str})")
        print("-" * 100)

        match_agent = MatchAgent()

        print(f"Evaluating {len(clean_jobs)} jobs against candidate profile...")
        print()

        # IMPROVEMENT #1: Parallel matching using asyncio.gather with semaphore
        async def match_single_job(idx: int, job: Dict[str, Any], semaphore: Optional[asyncio.Semaphore] = None) -> tuple:
            """Match a single job and return result."""
            async def do_match():
                try:
                    job_description = self._format_job_for_matching(job)
                    match_result = match_agent.evaluate_match(job_description)

                    print(f"  [{idx}/{len(clean_jobs)}] {job['title'][:50]:50s} "
                          f"{'[KEEP]' if match_result.score >= self.min_score_maybe else '[SKIP]':7s} "
                          f"Score: {match_result.score:5.1f} ({match_result.verdict})", flush=True)

                    if match_result.score >= self.min_score_maybe:
                        return {
                            'job': job,
                            'match': {
                                'score': match_result.score,
                                'verdict': match_result.verdict,
                                'matching_skills': match_result.matching_skills,
                                'missing_skills': match_result.missing_skills,
                                'reasons': match_result.reasons
                            }
                        }
                    return None

                except Exception as e:
                    print(f"  [{idx}/{len(clean_jobs)}] {job['title'][:50]:50s} [ERROR] {str(e)[:30]}", flush=True)
                    return None

            # Use semaphore if provided (parallel mode)
            if semaphore:
                async with semaphore:
                    return await do_match()
            else:
                # Sequential mode
                return await do_match()

        # RATE LIMIT FIX: Test mode = sequential, production = parallel with limit
        if test_mode:
            # Sequential processing in test mode
            results = []
            for idx, job in enumerate(clean_jobs, 1):
                result = await match_single_job(idx, job, semaphore=None)
                results.append(result)
        else:
            # Parallel with max 2 concurrent in production
            semaphore = asyncio.Semaphore(2)
            tasks = [match_single_job(idx, job, semaphore) for idx, job in enumerate(clean_jobs, 1)]
            results = await asyncio.gather(*tasks)

        # Filter out None results
        shortlisted = [r for r in results if r is not None]
        shortlisted.sort(key=lambda x: x['match']['score'], reverse=True)

        return shortlisted

    def _format_job_for_matching(self, job: Dict[str, Any]) -> str:
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

    def _is_cache_valid(self) -> bool:
        """Check if cached raw jobs file is less than 24 hours old."""
        if not self.raw_jobs_file.exists():
            return False

        file_time = datetime.fromtimestamp(self.raw_jobs_file.stat().st_mtime)
        age = datetime.now() - file_time

        return age < timedelta(hours=24)

    def _save_shortlisted(self, shortlisted: List[Dict[str, Any]]):
        """Save shortlisted jobs to file."""
        self.shortlisted_file.parent.mkdir(exist_ok=True)

        with open(self.shortlisted_file, 'w', encoding='utf-8') as f:
            json.dump(shortlisted, f, indent=2, ensure_ascii=False)

        print(f"\nSaved {len(shortlisted)} shortlisted jobs to {self.shortlisted_file}")

    def _print_summary(self, shortlisted: List[Dict[str, Any]]):
        """Print summary table of shortlisted jobs."""
        print()
        print("=" * 100)
        print("SHORTLISTED JOBS")
        print("=" * 100)
        print()

        if not shortlisted:
            print("No jobs met the minimum score threshold.")
            return

        col_widths = [5, 35, 25, 8, 10, 30]
        headers = ["Rank", "Title", "Company", "Score", "Verdict", "Top Matching Skills"]

        self._print_table_row(headers, col_widths)
        self._print_separator(col_widths)

        for idx, item in enumerate(shortlisted, 1):
            job = item['job']
            match = item['match']

            top_skills = ', '.join(match['matching_skills'][:3])
            if len(match['matching_skills']) > 3:
                top_skills += '...'

            row = [
                str(idx),
                job['title'],
                job['company'],
                f"{match['score']:.1f}",
                match['verdict'].upper(),
                top_skills
            ]

            self._print_table_row(row, col_widths)

        self._print_separator(col_widths)

    def _print_table_row(self, cols, widths):
        """Print a formatted table row."""
        row = " | ".join(str(col)[:w].ljust(w) for col, w in zip(cols, widths))
        print(f"| {row} |")

    def _print_separator(self, widths):
        """Print table separator."""
        sep = "-+-".join("-" * w for w in widths)
        print(f"+-{sep}-+")


async def main():
    """Example pipeline execution."""
    pipeline = JobPipeline(
        search_terms=["AI Engineer", "Machine Learning Engineer", "GenAI Engineer"],
        location="Sydney NSW",
        min_score_apply=75,
        min_score_maybe=60
    )

    results = await pipeline.run()

    print()
    print(f"\nPipeline completed: {results['shortlisted']} jobs shortlisted")
    print(f"  - {results['apply']} to apply")
    print(f"  - {results['maybe']} maybes")

    return results


if __name__ == "__main__":
    asyncio.run(main())
