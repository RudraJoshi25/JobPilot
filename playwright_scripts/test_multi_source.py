#!/usr/bin/env python3
"""
Quick test of multi-source scraping using only Seek and Indeed.
Collects 3 jobs per site maximum without visiting individual job pages.
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.source_agent import MultiSourceAgent


class FastTestAgent(MultiSourceAgent):
    """Fast test version that only uses Seek and Indeed."""

    def __init__(self):
        super().__init__(headless=True, max_jobs_per_search=3)
        self.visit_job_pages = False  # Skip individual job page visits

    async def run_fast_test(self, search_term: str, location: str):
        """Run only Seek and Indeed scrapers."""
        print("=" * 80)
        print("FAST MULTI-SOURCE TEST")
        print("=" * 80)
        print(f"Search term: '{search_term}'")
        print(f"Location: {location}")
        print(f"Max jobs per source: {self.max_jobs_per_search}")
        print(f"Visiting individual job pages: {self.visit_job_pages}")
        print("=" * 80)
        print()

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(user_agent=self.user_agent)

            print("Testing SEEK scraper...")
            print("-" * 80)
            seek_jobs = []
            try:
                seek_jobs = await self.seek_scraper(context, search_term, location)
                print(f"[OK] Seek found {len(seek_jobs)} jobs")
                self._print_jobs(seek_jobs, "Seek")
            except Exception as e:
                print(f"[ERROR] Seek scraper failed: {e}")

            print()
            print("Testing INDEED scraper...")
            print("-" * 80)
            indeed_jobs = []
            try:
                indeed_jobs = await self.indeed_scraper(context, search_term, location)
                print(f"[OK] Indeed found {len(indeed_jobs)} jobs")
                self._print_jobs(indeed_jobs, "Indeed")
            except Exception as e:
                print(f"[ERROR] Indeed scraper failed: {e}")

            await browser.close()

        print()
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Seek: {len(seek_jobs)} jobs")
        print(f"Indeed: {len(indeed_jobs)} jobs")
        print(f"Total: {len(seek_jobs) + len(indeed_jobs)} jobs")

        if len(seek_jobs) > 0 or len(indeed_jobs) > 0:
            print()
            print("[PASS] At least one scraper returned results")
            return 0
        else:
            print()
            print("[FAIL] No results from any scraper")
            return 1

    def _print_jobs(self, jobs, source_name):
        """Print job details."""
        if not jobs:
            print(f"  No jobs found on {source_name}")
            return

        print()
        for i, job in enumerate(jobs, 1):
            print(f"  [{i}] {job['title']}")
            print(f"      Company: {job['company']}")
            print(f"      Location: {job['location']}")
            if job.get('salary'):
                print(f"      Salary: {job['salary']}")
            print(f"      URL: {job['url'][:80]}...")
            if job.get('short_description'):
                desc = job['short_description'][:150].replace('\n', ' ')
                print(f"      Description: {desc}...")
            print()


async def main():
    agent = FastTestAgent()

    result = await agent.run_fast_test(
        search_term="AI Engineer",
        location="Sydney NSW"
    )

    return result


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
