import asyncio
import json
import random
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
from playwright.async_api import async_playwright, Page, Browser
import requests
import os


class MultiSourceAgent:
    def __init__(self, headless: bool = True, max_jobs_per_search: int = 15):
        self.headless = headless
        self.max_jobs_per_search = max_jobs_per_search
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.all_jobs = []

    async def run(self, search_terms: List[str], location: str = "Sydney NSW") -> List[Dict[str, Any]]:
        """Run all scrapers for all search terms and deduplicate results."""
        print(f"Starting multi-source job scraping...", flush=True)
        print(f"Search terms: {search_terms}", flush=True)
        print(f"Location: {location}", flush=True)
        print("-" * 80, flush=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(user_agent=self.user_agent)

            for search_term in search_terms:
                print(f"\nSearching for: '{search_term}'", flush=True)
                print("-" * 80, flush=True)

                await self._run_scraper("Seek", self.seek_scraper, context, search_term, location)
                await self._run_scraper("Indeed", self.indeed_scraper, context, search_term, location)
                await self._run_scraper("GradConnection", self.gradconnection_scraper, context, search_term, location)
                await self._run_scraper("Adzuna", self.adzuna_scraper, context, search_term, location)
                # await self._run_scraper("Talent", self.talent_scraper, context, search_term, location)  # Disabled: returns 0 jobs

            await browser.close()

        unique_jobs = self._deduplicate_jobs()
        self._save_results(unique_jobs)

        print("\n" + "=" * 80, flush=True)
        print(f"SUMMARY: Found {len(unique_jobs)} unique jobs from {len(self.all_jobs)} total across 4 sources", flush=True)
        print("=" * 80, flush=True)

        return unique_jobs

    async def _run_scraper(self, name: str, scraper_func, context, search_term: str, location: str):
        """Run a single scraper with error handling and 60s timeout."""
        try:
            async with asyncio.timeout(60):
                jobs = await scraper_func(context, search_term, location)
            self.all_jobs.extend(jobs)
            print(f"[{name}] Found {len(jobs)} jobs", flush=True)
        except asyncio.TimeoutError:
            print(f"[{name}] TIMEOUT: Scraper took too long (>60s)", flush=True)
        except Exception as e:
            print(f"[{name}] ERROR: {e}", flush=True)

    async def seek_scraper(self, context, keywords: str, location: str) -> List[Dict[str, Any]]:
        """Scrape jobs from seek.com.au"""
        page = await context.new_page()
        jobs = []

        try:
            keywords_slug = quote_plus(keywords.lower().replace(" ", "-"))
            location_slug = quote_plus(location.lower().replace(" ", "-"))
            url = f"https://www.seek.com.au/{keywords_slug}-jobs/in-{location_slug}"

            await page.goto(url, timeout=30000, wait_until="networkidle")
            await asyncio.sleep(2.0)

            job_cards = await page.query_selector_all('[data-card-type="JobCard"], article[data-testid*="job"], div[data-testid*="job-card"]')

            for i, card in enumerate(job_cards[:self.max_jobs_per_search]):
                try:
                    job = await self._extract_seek_job(card, page)
                    if job:
                        job['source'] = 'seek'
                        jobs.append(job)

                    if i < len(job_cards) - 1:
                        await self._random_delay()

                except Exception as e:
                    print(f"  [Seek] Failed to extract job {i+1}: {e}")
                    continue

        except Exception as e:
            raise Exception(f"Seek scraper failed: {e}")
        finally:
            await page.close()

        return jobs

    async def _extract_seek_job(self, card, page: Page) -> Optional[Dict[str, Any]]:
        """Extract job details from Seek card."""
        title = await card.query_selector('a[data-testid*="job-title"], h3 a, a[class*="JobCard_title"]')

        # Try multiple selectors for company name
        company_selectors = [
            '[data-automation="jobCardAdvertiserName"]',
            '[data-testid="job-card-company"]',
            'a[data-automation="jobCompany"]',
            'span[data-automation="jobCardCompany"]',
            'a[data-automation="jobCardCompany"]',
            '[data-testid*="company-name"]',
            '[data-testid*="advertiser-name"]',
            'span[class*="y735df0"]',
            'a[class*="y735df0"]',
        ]

        company = None
        for selector in company_selectors:
            company = await card.query_selector(selector)
            if company:
                break

        location_elem = await card.query_selector('[data-testid*="location"], span[class*="location"]')
        salary = await card.query_selector('[data-testid*="salary"], span[class*="salary"]')
        description = await card.query_selector('[data-testid*="description"], span[class*="jobSnippet"]')

        if not title:
            return None

        title_text = await title.inner_text()
        job_url = await title.get_attribute('href')
        if job_url and not job_url.startswith('http'):
            job_url = f"https://www.seek.com.au{job_url}"

        company_name = 'Unknown Company'
        if company:
            company_text = await company.inner_text()
            company_name = company_text.strip() if company_text.strip() else 'Unknown Company'

        job_data = {
            'title': title_text.strip(),
            'company': company_name,
            'location': (await location_elem.inner_text()).strip() if location_elem else 'Sydney NSW',
            'url': job_url or '',
            'short_description': (await description.inner_text()).strip() if description else '',
            'salary': (await salary.inner_text()).strip() if salary else None,
            'posted_date': None,
            'scraped_at': datetime.now().isoformat()
        }

        if job_url and hasattr(self, 'visit_job_pages') and self.visit_job_pages:
            full_desc = await self._visit_seek_job_page(page.context, job_url)
            if full_desc:
                job_data['full_description'] = full_desc

        return job_data

    async def _visit_seek_job_page(self, context, url: str) -> Optional[str]:
        """Visit individual Seek job page to extract full description."""
        job_page = await context.new_page()
        try:
            await job_page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await job_page.wait_for_timeout(1000)

            desc_elem = await job_page.query_selector('[data-testid="jobDetailsDescription"], div[class*="jobDescription"]')
            if desc_elem:
                return (await desc_elem.inner_text()).strip()
        except Exception as e:
            print(f"    Failed to load job page: {e}")
        finally:
            await job_page.close()

        return None

    async def indeed_scraper(self, context, keywords: str, location: str) -> List[Dict[str, Any]]:
        """Scrape jobs from au.indeed.com"""
        page = await context.new_page()
        jobs = []

        try:
            url = f"https://au.indeed.com/jobs?q={quote_plus(keywords)}&l={quote_plus(location)}"

            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(2.0)

            job_cards = await page.query_selector_all('div.job_seen_beacon, div[class*="jobsearch-ResultsList"] > li, td.resultContent')

            for i, card in enumerate(job_cards[:self.max_jobs_per_search]):
                try:
                    job = await self._extract_indeed_job(card, page)
                    if job:
                        job['source'] = 'indeed'
                        jobs.append(job)

                    if i < len(job_cards) - 1:
                        await self._random_delay()

                except Exception as e:
                    print(f"  [Indeed] Failed to extract job {i+1}: {e}")
                    continue

        except Exception as e:
            raise Exception(f"Indeed scraper failed: {e}")
        finally:
            await page.close()

        return jobs

    async def _extract_indeed_job(self, card, page: Page) -> Optional[Dict[str, Any]]:
        """Extract job details from Indeed card."""
        title = await card.query_selector('h2 a, h2 span, a[class*="jcs-JobTitle"]')

        # Try multiple selectors for company name
        company_selectors = [
            'span[class*="companyName"]',
            'div[class*="company"]',
            '[data-testid="company-name"]',
            'span[data-testid="company-name"]',
            'div.company_location'
        ]

        company = None
        for selector in company_selectors:
            company = await card.query_selector(selector)
            if company:
                break

        location_elem = await card.query_selector('div[class*="companyLocation"], span[class*="location"]')
        salary = await card.query_selector('div[class*="salary-snippet"], span[class*="salary"]')
        description = await card.query_selector('div[class*="job-snippet"], td[class*="snippetCol"]')

        if not title:
            return None

        title_text = await title.inner_text()

        link_elem = await card.query_selector('h2 a, a[class*="jcs-JobTitle"]')
        job_url = None
        if link_elem:
            href = await link_elem.get_attribute('href')
            if href:
                job_url = f"https://au.indeed.com{href}" if href.startswith('/') else href

        company_name = 'Unknown Company'
        if company:
            company_text = await company.inner_text()
            if company_text and company_text.strip():
                # Take only first line and clean
                company_name = company_text.split('\n')[0].strip()
                if not company_name:
                    company_name = 'Unknown Company'

        job_data = {
            'title': title_text.strip(),
            'company': company_name,
            'location': (await location_elem.inner_text()).strip() if location_elem else 'Sydney NSW',
            'url': job_url or '',
            'short_description': (await description.inner_text()).strip() if description else '',
            'salary': (await salary.inner_text()).strip() if salary else None,
            'posted_date': None,
            'scraped_at': datetime.now().isoformat()
        }

        if job_url and hasattr(self, 'visit_job_pages') and self.visit_job_pages:
            full_desc = await self._visit_indeed_job_page(page.context, job_url)
            if full_desc:
                job_data['full_description'] = full_desc

        return job_data

    async def _visit_indeed_job_page(self, context, url: str) -> Optional[str]:
        """Visit individual Indeed job page to extract full description."""
        job_page = await context.new_page()
        try:
            await job_page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await job_page.wait_for_timeout(1000)

            desc_elem = await job_page.query_selector('div#jobDescriptionText, div[class*="jobsearch-jobDescriptionText"]')
            if desc_elem:
                return (await desc_elem.inner_text()).strip()
        except Exception as e:
            print(f"    Failed to load job page: {e}")
        finally:
            await job_page.close()

        return None

    async def gradconnection_scraper(self, context, keywords: str, location: str) -> List[Dict[str, Any]]:
        """Scrape jobs from gradconnection.com.au"""
        page = await context.new_page()
        jobs = []

        try:
            url = f"https://au.gradconnection.com/jobs/?search={quote_plus(keywords)}"

            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(2.0)

            job_cards = await page.query_selector_all('div[class*="job-card"], article.job, div.job-listing')

            for i, card in enumerate(job_cards[:self.max_jobs_per_search]):
                try:
                    job = await self._extract_gradconnection_job(card, page)
                    if job:
                        job['source'] = 'gradconnection'
                        jobs.append(job)

                    if i < len(job_cards) - 1:
                        await self._random_delay()

                except Exception as e:
                    print(f"  [GradConnection] Failed to extract job {i+1}: {e}")
                    continue

        except Exception as e:
            raise Exception(f"GradConnection scraper failed: {e}")
        finally:
            await page.close()

        return jobs

    async def _extract_gradconnection_job(self, card, page: Page) -> Optional[Dict[str, Any]]:
        """Extract job details from GradConnection card."""
        title = await card.query_selector('h3 a, h2 a, a[class*="job-title"]')
        company = await card.query_selector('span[class*="company"], div[class*="employer"]')
        location_elem = await card.query_selector('span[class*="location"]')
        description = await card.query_selector('div[class*="description"], p[class*="snippet"]')

        if not title:
            return None

        title_text = await title.inner_text()
        job_url = await title.get_attribute('href')
        if job_url and not job_url.startswith('http'):
            job_url = f"https://au.gradconnection.com{job_url}"

        job_data = {
            'title': title_text.strip(),
            'company': (await company.inner_text()).strip() if company else 'Unknown',
            'location': (await location_elem.inner_text()).strip() if location_elem else 'Sydney NSW',
            'url': job_url or '',
            'short_description': (await description.inner_text()).strip() if description else '',
            'salary': None,
            'posted_date': None,
            'scraped_at': datetime.now().isoformat()
        }

        if job_url and hasattr(self, 'visit_job_pages') and self.visit_job_pages:
            full_desc = await self._visit_gradconnection_job_page(page.context, job_url)
            if full_desc:
                job_data['full_description'] = full_desc

        return job_data

    async def _visit_gradconnection_job_page(self, context, url: str) -> Optional[str]:
        """Visit individual GradConnection job page to extract full description."""
        job_page = await context.new_page()
        try:
            await job_page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await job_page.wait_for_timeout(1000)

            desc_elem = await job_page.query_selector('div[class*="description"], div.job-details')
            if desc_elem:
                return (await desc_elem.inner_text()).strip()
        except Exception as e:
            print(f"    Failed to load job page: {e}")
        finally:
            await job_page.close()

        return None
    
    async def adzuna_scraper(self, context, search_term: str, location: str) -> List[Dict[str, Any]]:
        # Fetch jobs from Adzuna API - no Playwright needed, pure HTTP
        jobs = []
        try:
            city = location.split()[0]

            params = {
                "app_id": os.getenv("ADZUNA_APP_ID", "30979ee5"),
                "app_key": os.getenv("ADZUNA_APP_KEY", ""),
                "what": search_term,
                "where": city,
                "results_per_page": self.max_jobs_per_search,
                "content-type": "application/json",
                "sort_by": "date",
                "max_days_old": 14
            }

            if not params["app_key"]:
                print("  [Adzuna] No API key found in .env", flush=True)
                return []

            url = "https://api.adzuna.com/v1/api/jobs/au/search/1"
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            for job in data.get("results", []):
                jobs.append({
                    "title": job.get("title", ""),
                    "company": job.get("company", {}).get("display_name", "Unknown Company"),
                    "location": job.get("location", {}).get("display_name", location),
                    "url": job.get("redirect_url", ""),
                    "short_description": job.get("description", "")[:500],
                    "salary": job.get("salary_min"),
                    "posted_date": job.get("created", None),
                    "scraped_at": datetime.now().isoformat(),
                    "source": "adzuna"
                })

        except Exception as e:
            print(f"  [Adzuna] Error: {e}", flush=True)

        return jobs

    async def talent_scraper(self, context, keywords: str, location: str) -> List[Dict[str, Any]]:
        """Scrape jobs from au.talent.com"""
        page = await context.new_page()
        jobs = []

        try:
            url = f"https://au.talent.com/jobs?k={quote_plus(keywords)}&l={quote_plus(location)}"

            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await asyncio.sleep(2.0)

            job_cards = await page.query_selector_all('div[class*="job-card"], article.job, li[class*="job"]')

            for i, card in enumerate(job_cards[:self.max_jobs_per_search]):
                try:
                    job = await self._extract_talent_job(card, page)
                    if job:
                        job['source'] = 'talent'
                        jobs.append(job)

                    if i < len(job_cards) - 1:
                        await self._random_delay()

                except Exception as e:
                    print(f"  [Talent] Failed to extract job {i+1}: {e}")
                    continue

        except Exception as e:
            raise Exception(f"Talent scraper failed: {e}")
        finally:
            await page.close()

        return jobs

    async def _extract_talent_job(self, card, page: Page) -> Optional[Dict[str, Any]]:
        """Extract job details from Talent card."""
        title = await card.query_selector('h2 a, h3 a, a[class*="job-title"]')
        company = await card.query_selector('span[class*="company"], div[class*="company"]')
        location_elem = await card.query_selector('span[class*="location"]')
        salary = await card.query_selector('span[class*="salary"], div[class*="salary"]')
        description = await card.query_selector('div[class*="description"], p[class*="snippet"]')

        if not title:
            return None

        title_text = await title.inner_text()
        job_url = await title.get_attribute('href')
        if job_url and not job_url.startswith('http'):
            job_url = f"https://au.talent.com{job_url}"

        job_data = {
            'title': title_text.strip(),
            'company': (await company.inner_text()).strip() if company else 'Unknown',
            'location': (await location_elem.inner_text()).strip() if location_elem else 'Sydney NSW',
            'url': job_url or '',
            'short_description': (await description.inner_text()).strip() if description else '',
            'salary': (await salary.inner_text()).strip() if salary else None,
            'posted_date': None,
            'scraped_at': datetime.now().isoformat()
        }

        if job_url and hasattr(self, 'visit_job_pages') and self.visit_job_pages:
            full_desc = await self._visit_talent_job_page(page.context, job_url)
            if full_desc:
                job_data['full_description'] = full_desc

        return job_data

    async def _visit_talent_job_page(self, context, url: str) -> Optional[str]:
        """Visit individual Talent job page to extract full description."""
        job_page = await context.new_page()
        try:
            await job_page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await job_page.wait_for_timeout(1000)

            desc_elem = await job_page.query_selector('div[class*="description"], div.job-content')
            if desc_elem:
                return (await desc_elem.inner_text()).strip()
        except Exception as e:
            print(f"    Failed to load job page: {e}")
        finally:
            await job_page.close()

        return None

    async def _random_delay(self):
        """Add random delay between requests to appear more human."""
        delay = random.uniform(2.0, 4.0)
        await asyncio.sleep(delay)

    def _deduplicate_jobs(self) -> List[Dict[str, Any]]:
        """Remove duplicate jobs based on title + company."""
        seen = set()
        unique = []

        for job in self.all_jobs:
            key = self._normalize_key(job['title'], job['company'])

            if key not in seen:
                seen.add(key)
                unique.append(job)

        return unique

    def _normalize_key(self, title: str, company: str) -> str:
        """Normalize title and company for deduplication."""
        title_clean = re.sub(r'[^\w\s]', '', title.lower()).strip()
        company_clean = re.sub(r'[^\w\s]', '', company.lower()).strip()
        return f"{title_clean}|{company_clean}"

    def _save_results(self, jobs: List[Dict[str, Any]]):
        """Save results to JSON file."""
        output_path = Path("data/jobs_raw.json")
        output_path.parent.mkdir(exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, indent=2, ensure_ascii=False)

        print(f"\nSaved {len(jobs)} jobs to {output_path}")


async def main():
    """Example usage."""
    agent = MultiSourceAgent(headless=True, max_jobs_per_search=15)

    search_terms = [
        "AI Engineer",
        "Machine Learning Engineer",
        "GenAI Engineer",
        "Graduate AI"
    ]

    location = "Sydney NSW"

    results = await agent.run(search_terms, location)
    return results


if __name__ == "__main__":
    asyncio.run(main())

