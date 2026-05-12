"""
Apply Agent - Handles job application submission via web forms.
Supports draft, assisted, and auto modes.
"""
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Literal
from playwright.async_api import async_playwright, Page, Browser


class ApplyAgent:
    """Agent for submitting job applications through web portals."""

    def __init__(
        self,
        profile_path: str = "data/candidate_profile.json",
        mode: Literal["draft", "assisted", "auto"] = "assisted"
    ):
        self.profile_path = profile_path
        self.candidate_profile = self._load_profile()
        self.mode = mode
        self.apply_log = []

    def _load_profile(self) -> Dict[str, Any]:
        """Load candidate profile."""
        with open(self.profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async def apply_to_job(
        self,
        job: Dict[str, Any],
        resume_path: str,
        cover_letter_path: Optional[str] = None,
        auto_mode: bool = False
    ) -> Dict[str, Any]:
        """Apply to a job with specified mode."""
        job_hash = job.get('job_hash', 'unknown')
        job_url = job.get('url', '')
        apply_type = job.get('apply_type', 'portal')

        print(f"\nApplying to: {job.get('title')} at {job.get('company')}")
        print(f"Mode: {self.mode.upper()}")
        print(f"URL: {job_url}")
        print("-" * 80)

        # Determine actual mode based on apply_type
        actual_mode = self._determine_mode(apply_type)

        if actual_mode != self.mode:
            print(f"[INFO] Switching from {self.mode} to {actual_mode} mode based on apply_type: {apply_type}")

        result = {
            'job_hash': job_hash,
            'job_title': job['title'],
            'company': job['company'],
            'url': job_url,
            'mode': actual_mode,
            'status': 'pending',
            'timestamp': datetime.now().isoformat(),
            'fields_filled': [],
            'fields_skipped': [],
            'screenshots': [],
            'error': None
        }

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)  # Show browser
                context = await browser.new_context()
                page = await context.new_page()

                # Navigate to job URL
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2000)

                # Detect ATS type
                ats_type = await self._detect_ats_type(page)
                result['ats_type'] = ats_type
                print(f"[DETECT] ATS Type: {ats_type}")

                # Take initial screenshot
                screenshot_dir = Path("artifacts/screenshots")
                screenshot_dir.mkdir(parents=True, exist_ok=True)

                before_screenshot = screenshot_dir / f"{job_hash}_before_submit.png"
                await page.screenshot(path=str(before_screenshot), full_page=True)
                result['screenshots'].append(str(before_screenshot))
                print(f"[SCREENSHOT] {before_screenshot}")

                if actual_mode == "draft":
                    result['status'] = 'draft_only'
                    print("[DRAFT] Screenshot taken, no further action")

                elif actual_mode == "assisted":
                    await self._fill_application_fields(page, job, resume_path, result, ats_type)

                    print("\n" + "=" * 80)
                    print("FIELDS FILLED:")
                    for field in result['fields_filled']:
                        print(f"  [OK] {field}")

                    if result['fields_skipped']:
                        print("\nFIELDS NOT FILLED (manual entry needed):")
                        for field in result['fields_skipped']:
                            print(f"  [SKIP] {field}")

                    print("=" * 80)

                    if auto_mode:
                        # Unattended run — submit without prompting
                        print("\n[AUTO] Submitting immediately (auto mode, no approval prompt)")
                        await self._submit_application(page, ats_type)
                        result['status'] = 'submitted'
                        print("[AUTO] Application submitted")
                    else:
                        print("\nWAITING FOR HUMAN APPROVAL")
                        print("Press Enter to submit or Ctrl+C to cancel...")
                        try:
                            await asyncio.get_event_loop().run_in_executor(None, input)
                            await self._submit_application(page, ats_type)
                            result['status'] = 'submitted'
                            print("[SUCCESS] Application submitted")
                        except KeyboardInterrupt:
                            result['status'] = 'cancelled_by_user'
                            print("\n[CANCELLED] Application not submitted")

                    if result['status'] == 'submitted':
                        after_screenshot = screenshot_dir / f"{job_hash}_after_submit.png"
                        await page.screenshot(path=str(after_screenshot), full_page=True)
                        result['screenshots'].append(str(after_screenshot))

                elif actual_mode == "auto":
                    await self._fill_application_fields(page, job, resume_path, result, ats_type)

                    # Auto-submit
                    await self._submit_application(page, ats_type)
                    result['status'] = 'submitted'
                    print("[AUTO] Application submitted automatically")

                    # Take after screenshot
                    after_screenshot = screenshot_dir / f"{job_hash}_after_submit.png"
                    await page.screenshot(path=str(after_screenshot), full_page=True)
                    result['screenshots'].append(str(after_screenshot))

                await browser.close()

        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            print(f"[ERROR] Application failed: {e}")

        # Log the result
        self._log_application(result)

        return result

    def _determine_mode(self, apply_type: str) -> str:
        """Determine actual mode based on apply_type."""
        if self.mode == "auto":
            if apply_type == "easy_apply":
                return "auto"
            else:
                print(f"[WARNING] Cannot auto-apply to {apply_type} jobs, switching to assisted mode")
                return "assisted"
        return self.mode

    async def _detect_ats_type(self, page: Page) -> str:
        """Detect which ATS/portal is being used."""
        url = page.url.lower()
        page_content = await page.content()
        content_lower = page_content.lower()

        if 'seek.com' in url:
            return 'seek'
        elif 'indeed.com' in url:
            return 'indeed'
        elif 'greenhouse.io' in url or 'greenhouse' in content_lower:
            return 'greenhouse'
        elif 'lever.co' in url or 'lever' in content_lower:
            return 'lever'
        elif 'myworkdayjobs.com' in url or 'workday' in content_lower:
            return 'workday'
        elif 'gradconnection.com' in url:
            return 'gradconnection'
        elif 'talent.com' in url:
            return 'talent'
        else:
            return 'generic'

    async def _fill_application_fields(
        self,
        page: Page,
        job: Dict[str, Any],
        resume_path: str,
        result: Dict[str, Any],
        ats_type: str = 'generic'
    ):
        """Fill application form fields."""
        print("[FILL] Starting to fill application fields...")

        # Seek loads form fields via JS; give it time to render
        await page.wait_for_timeout(3000)

        # Seek requires the user to be signed in before form fields appear
        if ats_type == 'seek':
            logged_in = await self._check_seek_login(page)
            if not logged_in:
                print("\n[ACTION NEEDED] Please log in to Seek in the browser window, "
                      "then press Enter to continue.")
                await asyncio.get_event_loop().run_in_executor(None, input)
                # Let the page settle and re-render after login
                await page.wait_for_timeout(3000)

        # Extract candidate info
        name = self.candidate_profile.get('name', 'Rudra Joshi')
        first_name, last_name = name.split(' ', 1) if ' ' in name else (name, '')

        email = self.candidate_profile.get('email', '')
        phone = self.candidate_profile.get('phone', '')
        location = self.candidate_profile.get('location', 'Sydney, NSW, Australia')

        # Try to fill common fields
        fields_to_fill = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'location': location
        }

        for field_name, value in fields_to_fill.items():
            if value:
                filled = await self._try_fill_field(page, field_name, value)
                if filled:
                    result['fields_filled'].append(f"{field_name}: {value}")
                else:
                    result['fields_skipped'].append(f"{field_name} (not found or couldn't fill)")

        # Try to upload resume
        if Path(resume_path).exists():
            uploaded = await self._try_upload_resume(page, resume_path)
            if uploaded:
                result['fields_filled'].append(f"resume: {Path(resume_path).name}")
            else:
                result['fields_skipped'].append("resume upload (couldn't find upload button)")

    async def _check_seek_login(self, page: Page) -> bool:
        """Return False if Seek shows a login wall, True if the user appears signed in."""
        current_url = page.url.lower()
        if any(token in current_url for token in ('login', 'signin', 'sign-in', 'register')):
            return False

        login_selectors = [
            'a:has-text("Sign in")',
            'a:has-text("Log in")',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            '[data-automation="sign-in"]',
            '[data-testid="sign-in"]',
            'a[href*="/login"]',
            'a[href*="/signin"]',
        ]
        for selector in login_selectors:
            try:
                element = await page.query_selector(selector)
                if element and await element.is_visible():
                    return False
            except Exception:
                continue

        return True

    async def _try_fill_field(self, page: Page, field_name: str, value: str) -> bool:
        """Try to fill a field by various selectors."""
        selectors = self._get_field_selectors(field_name)

        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    await element.fill(value)
                    print(f"  [OK] Filled {field_name}")
                    return True
            except:
                continue

        return False

    async def _try_upload_resume(self, page: Page, resume_path: str) -> bool:
        """Try to upload resume file."""
        upload_selectors = [
            'input[type="file"]',
            'input[name*="resume"]',
            'input[name*="cv"]',
            'input[id*="resume"]',
            'input[id*="cv"]',
            'input[accept*="pdf"]',
            'input[accept*="doc"]'
        ]

        for selector in upload_selectors:
            try:
                file_input = await page.query_selector(selector)
                if file_input:
                    await file_input.set_input_files(resume_path)
                    print(f"  [OK] Uploaded resume")
                    await page.wait_for_timeout(2000)
                    return True
            except:
                continue

        return False

    def _get_field_selectors(self, field_name: str) -> list:
        """Get possible selectors for a field."""
        selectors_map = {
            'first_name': [
                'input[name="firstName"]',
                'input[name="first_name"]',
                'input[id="firstName"]',
                'input[placeholder*="First name"]',
                'input[placeholder*="first name"]'
            ],
            'last_name': [
                'input[name="lastName"]',
                'input[name="last_name"]',
                'input[id="lastName"]',
                'input[placeholder*="Last name"]',
                'input[placeholder*="last name"]'
            ],
            'email': [
                'input[name="email"]',
                'input[type="email"]',
                'input[id="email"]',
                'input[placeholder*="email"]'
            ],
            'phone': [
                'input[name="phone"]',
                'input[type="tel"]',
                'input[id="phone"]',
                'input[placeholder*="phone"]'
            ],
            'location': [
                'input[name="location"]',
                'input[name="city"]',
                'input[id="location"]',
                'input[placeholder*="location"]',
                'input[placeholder*="city"]'
            ]
        }

        return selectors_map.get(field_name, [])

    async def _submit_application(self, page: Page, ats_type: str):
        """Submit the application."""
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
            'button:has-text("Send Application")',
            'a:has-text("Submit")'
        ]

        for selector in submit_selectors:
            try:
                submit_btn = await page.query_selector(selector)
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_timeout(3000)
                    return
            except:
                continue

        print("[WARNING] Could not find submit button")

    def _log_application(self, result: Dict[str, Any]):
        """Log application attempt to file."""
        log_file = Path("logs/apply_log.json")
        log_file.parent.mkdir(exist_ok=True)

        self.apply_log.append(result)

        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                existing_log = json.load(f)
        else:
            existing_log = []

        existing_log.append(result)

        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(existing_log, f, indent=2, ensure_ascii=False)


async def main():
    """Example usage."""
    agent = ApplyAgent(mode="draft")

    mock_job = {
        'job_hash': 'test123',
        'title': 'AI Engineer',
        'company': 'Test Company',
        'url': 'https://www.seek.com.au/job/12345',
        'apply_type': 'portal'
    }

    result = await agent.apply_to_job(
        job=mock_job,
        resume_path="artifacts/resumes/resume_test.docx"
    )

    print(f"\nResult: {result['status']}")


if __name__ == "__main__":
    asyncio.run(main())
