#!/usr/bin/env python3
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.source_agent import MultiSourceAgent
from playwright.async_api import async_playwright


async def generate_test_data():
    agent = MultiSourceAgent(headless=True, max_jobs_per_search=3)
    agent.visit_job_pages = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=agent.user_agent)

        seek_jobs = await agent.seek_scraper(context, 'AI Engineer', 'Sydney NSW')
        indeed_jobs = await agent.indeed_scraper(context, 'AI Engineer', 'Sydney NSW')

        await browser.close()

    all_jobs = seek_jobs + indeed_jobs

    output_file = Path('data/test_scrape.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)

    print(f'Saved {len(all_jobs)} test jobs to {output_file}')
    print(f'  - Seek: {len(seek_jobs)} jobs')
    print(f'  - Indeed: {len(indeed_jobs)} jobs')


if __name__ == "__main__":
    asyncio.run(generate_test_data())
