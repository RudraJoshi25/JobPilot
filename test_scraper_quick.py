#!/usr/bin/env python3
import asyncio
import sys
sys.stdout.reconfigure(line_buffering=True)

from agents.source_agent import MultiSourceAgent

async def test():
    agent = MultiSourceAgent(max_jobs_per_search=2)
    print('Starting scrape...', flush=True)
    jobs = await agent.run(['AI Engineer'], 'Sydney NSW')
    print(f'Done! Found {len(jobs)} jobs', flush=True)
    for j in jobs:
        print(f'  - {j["title"]} at {j["company"]}', flush=True)

asyncio.run(test())
