"""
Master Agent - Main orchestrator for the complete job application pipeline.
Runs end-to-end: source → normalize → match → generate docs → QA → apply.

ReAct Enhancements:
- Autonomous ReAct decision loop per job (Reason → Act → Observe → Repeat)
- Self-healing error recovery (session failures, form errors, missing buttons)
- Seek session validation at apply-stage startup
- Daily intelligence report (logs/daily_intelligence.json)
"""
import json
import asyncio
import anthropic
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml

from agents.source_agent import MultiSourceAgent
from agents.normalizer_agent import NormalizerAgent
from agents.match_agent import MatchAgent
from agents.resume_agent_latex import ResumeAgent
from agents.cover_letter_agent import CoverLetterAgent
from agents.qa_agent import QAAgent
from agents.apply_agent import ApplyAgent
from agents.email_apply_agent import EmailApplyAgent

from core.skill_hooks import SkillRegistry


def load_profile_yaml(profile_path: str = "profile.yaml") -> Dict[str, Any]:
    """Load profile.yaml as single source of truth."""
    with open(profile_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class MasterAgent:
    """Master orchestrator for the job application pipeline with ReAct decision loop."""

    def __init__(self, config_path: str = "data/pipeline_config.json", profile_path: str = "profile.yaml", enable_guardrails: bool = False):
        self.config = self._load_config(config_path)
        self.profile = load_profile_yaml(profile_path)

        matching_config = self.profile.get('matching', {})
        self.config['score_threshold_maybe'] = matching_config.get('min_score', 50)
        self.config['score_threshold_priority'] = matching_config.get('priority_score', 65)

        search_config = self.profile.get('search', {})
        if 'search_terms' not in self.config or not self.config['search_terms']:
            self.config['search_terms'] = search_config.get('scraper_keywords', [])

        if 'location' not in self.config or not self.config['location']:
            tier1 = search_config.get('locations', {}).get('tier1', ['Sydney'])
            country = search_config.get('country', 'Australia')
            self.config['location'] = f"{tier1[0]} {country}" if tier1 else f"Sydney {country}"

        self.pipeline_log = {
            'started_at': datetime.now().isoformat(),
            'config': self.config,
            'stages': {},
            'applications': [],
            'decisions': []
        }

        # AI client for ReAct reasoning (Haiku for speed)
        self._ai_client = anthropic.Anthropic(api_key=__import__('os').environ.get("ANTHROPIC_API_KEY"))

        # Layer 3: Skill hooks
        self.skills = SkillRegistry()

        # Decision / reasoning logs
        self.decision_log_path = Path("logs/decisions.json")
        self.decision_log_path.parent.mkdir(exist_ok=True)
        self.reasoning_log_path = Path("logs/reasoning_log.json")
        self.reasoning_log_path.parent.mkdir(exist_ok=True)

        # Retry tracking
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3

        # Daily intelligence tracking (Req 8)
        self._confirmed_submitted: List[Dict] = []
        self._uncertain_submitted: List[Dict] = []
        self._failed_jobs: List[Dict] = []
        self._manual_queue: List[Dict] = []
        self._session_issues: List[str] = []
        self._seek_session_failed: bool = False

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load pipeline configuration."""
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async def run_pipeline(self, test_mode: bool = False, docs_only: bool = False, apply_only: bool = False, auto_mode: bool = False, apply_one: bool = False, verbose: bool = False, test_apply: bool = False):
        """Run complete pipeline."""
        self.config['test_mode'] = test_mode
        self.config['auto_mode'] = auto_mode
        self.config['apply_one'] = apply_one
        self.config['verbose'] = verbose
        self.config['test_apply'] = test_apply

        print("=" * 100)
        print("MASTER AGENT - JOB APPLICATION PIPELINE")
        print("=" * 100)
        print(f"Started: {self.pipeline_log['started_at']}")
        if test_apply:
            print("Mode: TEST-APPLY (Seek only · 1 keyword · 3 jobs · top-1 job · verbose · human confirm · no cache write)")
        if auto_mode:
            print("Mode: AUTO (unattended — score>=80 auto-apply, rest to manual review queue)")
        if apply_one:
            print("Mode: APPLY-ONE (pipeline runs fully, but only the top-scoring job is applied to)")
        if verbose:
            print("Mode: VERBOSE (full step-by-step output enabled)")
        if test_mode and not auto_mode and not test_apply:
            print("Mode: TEST")
            print("Rate Limiting: SEQUENTIAL processing to avoid 429 errors")
        elif not auto_mode and not test_apply:
            print("Mode: PRODUCTION")
        if docs_only:
            print("Mode: DOCUMENTS ONLY (skipping scraping)")
        if apply_only:
            print("Mode: APPLY ONLY (using existing queue)")
        print("=" * 100)
        print()

        try:
            if apply_only:
                await self._run_apply_stage()
            elif docs_only:
                await self._run_from_existing_jobs(test_mode)
            else:
                await self._run_full_pipeline(test_mode)

            self._save_final_report()
            self._write_daily_intelligence()

            print("\n" + "=" * 100)
            print("PIPELINE COMPLETED SUCCESSFULLY")
            print("=" * 100)
            self._print_summary()

        except Exception as e:
            print(f"\n[ERROR] Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            self.pipeline_log['error'] = str(e)
            self._save_final_report()
            self._write_daily_intelligence()

    async def _run_full_pipeline(self, test_mode: bool):
        """Run full pipeline from scratch."""
        print("\n[STAGE 1] SOURCING JOBS")
        print("-" * 100)

        test_apply = self.config.get('test_apply', False)

        if test_apply:
            print("[TEST-APPLY] Source: Seek only | Keyword: 'AI Engineer' | Limit: 3 jobs")
            source_agent = MultiSourceAgent(headless=True, max_jobs_per_search=3, profile=self.profile)
            raw_jobs = await source_agent.run(["AI Engineer"], self.config['location'], sources=["Seek"])
        else:
            source_agent = MultiSourceAgent(
                headless=True,
                max_jobs_per_search=2 if test_mode else self.config['max_jobs_per_source'],
                profile=self.profile
            )
            source_agent.visit_job_pages = self.config.get('visit_job_pages', False)
            search_terms = self.config['search_terms'][:2] if test_mode else self.config['search_terms']
            raw_jobs = await source_agent.run(search_terms, self.config['location'])

        self.pipeline_log['stages']['sourcing'] = {
            'jobs_found': len(raw_jobs),
            'sources': 4,
            'completed_at': datetime.now().isoformat()
        }

        await self._run_normalize_stage()
        await self._run_from_existing_jobs(test_mode)

    async def _run_from_existing_jobs(self, test_mode: bool):
        """Run pipeline from existing normalized jobs."""
        if Path("data/jobs_raw.json").exists() and not Path("data/jobs_clean.json").exists():
            await self._run_normalize_stage()

        print("\n[STAGE 3] MATCHING JOBS")
        print("-" * 100)

        with open("data/jobs_clean.json", 'r', encoding='utf-8') as f:
            clean_jobs = json.load(f)

        match_agent = MatchAgent(profile=self.profile)

        print(f"  Evaluating {len(clean_jobs)} jobs...")
        bands = match_agent.route_jobs(clean_jobs)

        shortlisted = []
        skipped = []

        for job in bands['PRIORITY']:
            match_result = job.get('match_result', {})
            shortlisted.append({
                'job': job,
                'match': {
                    'score': match_result.get('score', 0),
                    'verdict': match_result.get('verdict', 'apply'),
                    'matching_skills': match_result.get('matching_skills', []),
                    'missing_skills': match_result.get('missing_skills', []),
                    'reasons': match_result.get('reasons', '')
                }
            })
            print(f"  [PRIORITY] {job['title'][:50]}... Score: {match_result.get('score', 0):.1f}")

        for job in bands['STRETCH']:
            match_result = job.get('match_result', {})
            shortlisted.append({
                'job': job,
                'match': {
                    'score': match_result.get('score', 0),
                    'verdict': match_result.get('verdict', 'maybe'),
                    'matching_skills': match_result.get('matching_skills', []),
                    'missing_skills': match_result.get('missing_skills', []),
                    'reasons': match_result.get('reasons', '')
                }
            })
            print(f"  [STRETCH]  {job['title'][:50]}... Score: {match_result.get('score', 0):.1f}")

        for job in bands['SKIP']:
            match_result = job.get('match_result', {})
            skipped.append({
                'job': job,
                'match': match_result,
                'reason': f"Score {match_result.get('score', 0):.1f} below threshold",
                'skipped_at': datetime.now().isoformat()
            })
            print(f"  [SKIP]     {job['title'][:50]}... Score: {match_result.get('score', 0):.1f}")

        if self.config.get('test_apply'):
            # Combine all bands and pick the single highest-scoring job
            all_scored = shortlisted[:]
            for job in bands['SKIP']:
                match_result = job.get('match_result', {})
                all_scored.append({
                    'job': job,
                    'match': {
                        'score': match_result.get('score', 0),
                        'verdict': match_result.get('verdict', 'skip'),
                        'matching_skills': match_result.get('matching_skills', []),
                        'missing_skills': match_result.get('missing_skills', []),
                        'reasons': match_result.get('reasons', '')
                    }
                })
            all_scored.sort(key=lambda x: x['match'].get('score', 0), reverse=True)
            shortlisted = all_scored[:3]
            skipped = []
            if shortlisted:
                for rank, j in enumerate(shortlisted, 1):
                    print(f"\n[TEST-APPLY] Candidate #{rank}: {j['job']['title']} at {j['job'].get('company', '?')} (score: {j['match']['score']:.1f})")
            else:
                print("\n[TEST-APPLY] No scoreable jobs found — cannot proceed")
        else:
            shortlisted = self._apply_priority_queue(shortlisted)
            shortlisted, dynamic_skipped = self._apply_dynamic_routing(shortlisted)
            skipped.extend(dynamic_skipped)

            if len(shortlisted) > self.config['daily_application_limit']:
                print(f"\n[LIMIT] Limiting to top {self.config['daily_application_limit']} jobs (daily limit)")
                shortlisted = shortlisted[:self.config['daily_application_limit']]

        with open("data/jobs_shortlisted.json", 'w', encoding='utf-8') as f:
            json.dump(shortlisted, f, indent=2, ensure_ascii=False)

        if skipped:
            with open("data/jobs_skipped.json", 'w', encoding='utf-8') as f:
                json.dump(skipped, f, indent=2, ensure_ascii=False)

        self.pipeline_log['stages']['matching'] = {
            'jobs_evaluated': len(clean_jobs),
            'jobs_shortlisted': len(shortlisted),
            'jobs_skipped': len(skipped),
            'completed_at': datetime.now().isoformat()
        }

        print(f"\n[RESULT] Shortlisted {len(shortlisted)} jobs, skipped {len(skipped)} low-scoring jobs")
        await self._run_document_generation_stage(shortlisted)

    async def _run_normalize_stage(self):
        """Run normalization stage."""
        print("\n[STAGE 2] NORMALIZING JOBS")
        print("-" * 100)

        normalizer = NormalizerAgent(batch_size=5, batch_delay=1.0)
        results = normalizer.normalize_jobs(
            input_file="data/jobs_raw.json",
            output_file="data/jobs_clean.json",
            skipped_file="data/jobs_skipped.json"
        )

        self.pipeline_log['stages']['normalizing'] = {
            'jobs_normalized': results['normalized'],
            'jobs_skipped': results['skipped'],
            'completed_at': datetime.now().isoformat()
        }

    async def _run_document_generation_stage(self, shortlisted: List[Dict[str, Any]]):
        """Generate documents and run QA for shortlisted jobs with skill hooks."""
        print("\n[STAGE 4] GENERATING DOCUMENTS & RUNNING QA")
        print("-" * 100)

        qa_agent = QAAgent(profile=self.profile)
        human_review_queue = []

        for idx, item in enumerate(shortlisted, 1):
            job = item['job']
            match_report = item['match']
            routing = item.get('routing', 'standard_pipeline')

            print(f"\n[{idx}/{len(shortlisted)}] {job['title']} at {job['company']}")
            print(f"  Routing: {routing.upper()}")
            print("=" * 100)

            try:
                doc_result = await self._process_job_with_skills(job, match_report, routing)

                if not doc_result:
                    print(f"  [SKIP] Job processing failed or duplicate detected", flush=True)
                    continue

                resume_files = doc_result['resume']
                cover_letter_files = doc_result['cover_letter']

                print(f"  [QUALITY CHECK] Evaluating cover letter...", flush=True)
                cover_letter_text = self._read_file(cover_letter_files['markdown'])

                from agents.cover_letter_agent import CoverLetterAgent
                cl_agent = CoverLetterAgent(profile=self.profile)

                quality_score, quality_reason = self._check_cover_letter_quality(
                    cover_letter_text, job, cl_agent
                )

                print(f"  [QUALITY SCORE] {quality_score}/10", flush=True)

                if quality_score < 7:
                    print(f"  [REGENERATE] Score too low: {quality_reason}", flush=True)
                    cover_letter_files = self._regenerate_cover_letter(
                        cl_agent, job, match_report, self._read_file(resume_files['tex']),
                        quality_score, quality_reason
                    )
                    cover_letter_text = self._read_file(cover_letter_files['markdown'])
                    quality_score, _ = self._check_cover_letter_quality(
                        cover_letter_text, job, cl_agent
                    )
                    print(f"  [NEW QUALITY SCORE] {quality_score}/10", flush=True)

                qa_report = qa_agent.run_qa(
                    resume_files['tex'],
                    cover_letter_files['markdown'],
                    job
                )

                if qa_report.recommendation == "approve":
                    human_review_queue.append({
                        'job': job,
                        'match': match_report,
                        'resume': resume_files,
                        'cover_letter': cover_letter_files,
                        'qa_status': 'passed',
                        'qa_report': qa_report.model_dump(),
                        'cover_letter_quality_score': quality_score
                    })
                    print(f"  [QA PASSED] Added to review queue", flush=True)

                    print(f"\n  GENERATED COVER LETTER (Quality: {quality_score}/10):", flush=True)
                    print(f"  {'-' * 76}", flush=True)
                    for line in cover_letter_text.split('\n'):
                        print(f"  {line}", flush=True)
                    print(f"  {'-' * 76}\n", flush=True)
                else:
                    print(f"  [QA FAILED] {qa_report.recommendation}", flush=True)
                    for issue in qa_report.issues[:3]:
                        print(f"    - [{issue.severity}] {issue.description}", flush=True)

            except Exception as e:
                print(f"  [ERROR] {e}")

        with open("data/human_review_queue.json", 'w', encoding='utf-8') as f:
            json.dump(human_review_queue, f, indent=2, ensure_ascii=False)

        self.pipeline_log['stages']['document_generation'] = {
            'docs_generated': len(shortlisted),
            'qa_passed': len(human_review_queue),
            'completed_at': datetime.now().isoformat()
        }

        self._print_review_queue(human_review_queue)

        if self.config.get('test_apply'):
            # test-apply: skip the menu, apply to all candidates automatically.
            # Human confirmation prompt happens inside the apply agent itself.
            print("\n[TEST-APPLY] Bypassing selection menu — applying to all candidates")
            await self._auto_apply(human_review_queue)
        elif self.config.get('auto_mode'):
            await self._auto_apply(human_review_queue)
        else:
            await self._interactive_apply(human_review_queue)

    async def _run_apply_stage(self):
        """Run apply stage for existing review queue."""
        queue_file = Path("data/human_review_queue.json")

        if not queue_file.exists():
            print("[ERROR] No review queue found. Run document generation first.")
            return

        with open(queue_file, 'r') as f:
            review_queue = json.load(f)

        self._print_review_queue(review_queue)
        if self.config.get('auto_mode'):
            await self._auto_apply(review_queue)
        else:
            await self._interactive_apply(review_queue)

    async def _interactive_apply(self, review_queue: List[Dict[str, Any]]):
        """Interactive application process."""
        if not review_queue:
            print("\n[INFO] No jobs in review queue")
            return

        print("\n" + "=" * 100)
        print("READY TO APPLY")
        print("=" * 100)
        print(f"\nOptions:")
        print("  1. Apply to ALL {0} approved jobs".format(len(review_queue)))
        print("  2. Select specific jobs to apply to")
        print("  3. Skip application (documents saved)")
        print()

        try:
            choice = await asyncio.get_event_loop().run_in_executor(
                None, input, "Enter choice (1/2/3): "
            )

            if choice == "1":
                selected_indices = list(range(len(review_queue)))
            elif choice == "2":
                indices_str = await asyncio.get_event_loop().run_in_executor(
                    None, input, f"Enter job numbers to apply to (1-{len(review_queue)}), comma-separated: "
                )
                selected_indices = [int(i.strip()) - 1 for i in indices_str.split(',')]
            else:
                print("[SKIP] Applications skipped. Documents saved.")
                return

            await self._apply_to_jobs(review_queue, selected_indices)

        except KeyboardInterrupt:
            print("\n[CANCELLED] Application process cancelled")

    async def _auto_apply(self, review_queue: List[Dict[str, Any]]):
        """Unattended apply stage — no interactive prompts."""
        if not review_queue:
            print("\n[AUTO] No jobs in review queue")
            return

        if self.config.get('test_apply'):
            # In test mode, apply to all candidates (score filter bypassed).
            # _apply_to_jobs will stop after the first real (non-already_applied) attempt.
            print("\n[TEST-APPLY] Applying to all candidates (score filter bypassed)")
            indices = list(range(len(review_queue)))
            await self._apply_to_jobs(review_queue, indices)
            return

        auto_jobs = [
            item for item in review_queue
            if item['match']['score'] >= 80 and item.get('routing') != 'manual_review'
        ]
        manual_jobs = [
            item for item in review_queue
            if item['match']['score'] < 80 or item.get('routing') == 'manual_review'
        ]

        print("\n" + "=" * 100)
        print("AUTO MODE — APPLY STAGE")
        print("=" * 100)
        print(f"  Auto-apply  (score >= 80): {len(auto_jobs)} jobs")
        print(f"  Manual review             : {len(manual_jobs)} jobs")

        if auto_jobs:
            if self.config.get('apply_one'):
                auto_jobs = auto_jobs[:1]
                print(f"[APPLY-ONE] Targeting single highest-scoring job: {auto_jobs[0]['job']['title']} @ {auto_jobs[0]['job'].get('company', '')}")
            indices = [review_queue.index(item) for item in auto_jobs]
            await self._apply_to_jobs(review_queue, indices)

        if manual_jobs:
            self._log_manual_review_queue(manual_jobs)
            for item in manual_jobs:
                job = item['job']
                self._manual_queue.append({
                    'job': job.get('title', ''),
                    'company': job.get('company', ''),
                    'url': job.get('url', ''),
                    'reason': f"score_{item['match']['score']:.0f}_below_80",
                    'cover_letter_path': item.get('cover_letter', {}).get('markdown', '')
                })

        self.pipeline_log['auto_applied_jobs'] = [
            {
                'title': item['job'].get('title', 'N/A'),
                'company': item['job'].get('company', 'N/A'),
                'score': item['match']['score'],
                'url': item['job'].get('url', '')
            }
            for item in auto_jobs
        ]
        self.pipeline_log['manual_review_jobs'] = [
            {
                'title': item['job'].get('title', 'N/A'),
                'company': item['job'].get('company', 'N/A'),
                'score': item['match']['score'],
                'routing': item.get('routing', 'N/A'),
                'url': item['job'].get('url', '')
            }
            for item in manual_jobs
        ]

    # ------------------------------------------------------------------ #
    #  ReAct Apply Loop (Req 6)                                            #
    # ------------------------------------------------------------------ #

    async def _react_apply_loop(
        self,
        item: Dict[str, Any],
        apply_agent: ApplyAgent,
        email_agent: Any
    ) -> Dict[str, Any]:
        """
        Autonomous ReAct decision loop for a single job application.
        REASON → ACT → OBSERVE → REASON → ... until resolved.

        Every job exits with exactly one of:
          confirmed_submitted | uncertain_submitted |
          failed_with_reason  | manual_queue_with_context
        """
        job = item['job']
        title = job.get('title', 'Unknown')
        company = job.get('company', 'Unknown')
        score = item['match'].get('score', 0)
        source = job.get('source', 'unknown')
        apply_type = job.get('apply_type', 'portal')
        job_url = job.get('url', '')

        result: Optional[Dict[str, Any]] = None

        for iteration in range(3):
            # ── REASON ──────────────────────────────────────────────────
            ats_hint = ''
            if 'seek.com' in job_url:      ats_hint = 'seek'
            elif 'indeed.com' in job_url:  ats_hint = 'indeed'
            elif result:                   ats_hint = result.get('ats_type', '')

            prior_status = result.get('status', 'not_attempted') if result else 'not_attempted'
            prior_error  = (result.get('error') or result.get('manual_reason', '')) if result else ''

            reason_prompt = f"""Job application decision required.

Job: {title} at {company}
Match Score: {score}/100
Source: {source}
Apply Type: {apply_type}
URL: {job_url}
Detected ATS: {ats_hint or 'unknown'}
Iteration: {iteration + 1}/3
Prior Status: {prior_status}
Prior Error: {prior_error}

Choose the best apply strategy:
- "portal_auto": automated form fill via detected ATS portal
- "seek_direct": Seek direct apply (only if seek URL present)
- "indeed_easy": Indeed Easy Apply (only if indeed URL present)
- "email_apply": email application (only if apply_type is email)
- "manual_queue": skip automation, add to human review with context

Respond with JSON only:
{{"strategy": "portal_auto", "reason": "brief reason", "confidence": 0.85}}"""

            try:
                response = self._ai_client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=200,
                    messages=[{"role": "user", "content": reason_prompt}]
                )
                raw = response.content[0].text.strip()
                if "```" in raw:
                    raw = raw.split("```", 1)[1].split("```", 1)[0].strip()
                    if raw.startswith("json"):
                        raw = raw[4:].strip()
                decision = json.loads(raw)
            except Exception as e:
                decision = {"strategy": "portal_auto", "reason": f"AI fallback: {e}", "confidence": 0.5}

            strategy = decision.get("strategy", "portal_auto")
            reason_text = decision.get("reason", "")
            print(f"\n  [REACT] Iter {iteration+1}: strategy={strategy} | {reason_text}")

            # ── ACT ─────────────────────────────────────────────────────
            try:
                # Prefer compiled PDF; apply_agent will reject .tex with a clear error
                resume_file = item['resume'].get('pdf') or item['resume'].get('tex', '')
                if resume_file and resume_file.endswith('.tex'):
                    from pathlib import Path as _Path
                    _pdf = _Path(resume_file).with_suffix('.pdf')
                    if _pdf.exists():
                        resume_file = str(_pdf)
                        print(f"  [RESUME] Using compiled PDF: {resume_file}")
                    else:
                        print(f"  [WARN] Only .tex resume found — no PDF at {_pdf}. Apply will fail resume upload.")
                cl_path = item['cover_letter'].get('markdown', '')

                if strategy == "email_apply" or apply_type == 'email':
                    email_agent.draft_email_application(
                        job, resume_file, item['cover_letter'].get('docx', cl_path)
                    )
                    result = {
                        'status': 'email_draft',
                        'job_hash': job.get('job_hash'),
                        'job_title': title,
                        'company': company,
                        'ats_type': 'email',
                    }

                elif strategy == "manual_queue":
                    result = {
                        'status': 'manual_queue',
                        'job_hash': job.get('job_hash'),
                        'job_title': title,
                        'company': company,
                        'manual_reason': reason_text,
                        'resolved_url': job_url,
                    }

                else:
                    result = await apply_agent.apply_to_job(
                        job, resume_file, cl_path,
                        auto_mode=self.config.get('auto_mode', False)
                    )

            except Exception as e:
                result = {
                    'status': 'error',
                    'error': str(e),
                    'job_hash': job.get('job_hash'),
                    'job_title': title,
                    'company': company,
                }
                print(f"  [REACT] Act exception: {e}")

            # ── OBSERVE ─────────────────────────────────────────────────
            status = result.get('status', 'unknown')
            print(f"  [REACT] Observed: status={status}")

            if status == 'confirmed_submitted':
                print(f"  [REACT] SUCCESS — application confirmed submitted")
                self._confirmed_submitted.append({
                    'job': title, 'company': company,
                    'ats_type': result.get('ats_type', ''),
                    'time': datetime.now().isoformat()
                })
                break

            elif status == 'uncertain_submitted':
                print(f"  [REACT] WARNING — uncertain submission, screenshot saved")
                self._uncertain_submitted.append({
                    'job': title, 'company': company,
                    'screenshot_path': next(
                        (s for s in result.get('screenshots', []) if 'uncertain' in s), ''
                    )
                })
                break

            elif status == 'email_draft':
                print(f"  [REACT] Email draft created")
                self._confirmed_submitted.append({
                    'job': title, 'company': company,
                    'ats_type': 'email', 'time': datetime.now().isoformat()
                })
                break

            elif status == 'already_applied':
                print(f"  [REACT] ALREADY APPLIED — skipping (not a failure)")
                break

            elif status == 'manual_queue':
                manual_reason = result.get('manual_reason', 'unknown')
                print(f"  [REACT] MANUAL QUEUE — {manual_reason}")

                # Session failure: mark all remaining Seek jobs to skip
                if 'seek_session' in manual_reason:
                    self._seek_session_failed = True
                    issue = f"Seek session expired ({datetime.now().isoformat()})"
                    if issue not in self._session_issues:
                        self._session_issues.append(issue)
                    print("[ACTION NEEDED] Seek session expired. Run: python seed_login.py")

                self._manual_queue.append({
                    'job': title, 'company': company,
                    'url': result.get('resolved_url', job_url),
                    'reason': manual_reason,
                    'cover_letter_path': item['cover_letter'].get('markdown', '')
                })
                result['status'] = 'manual_queue_with_context'
                break

            else:
                # error / failed_with_reason / unexpected status
                error = result.get('error') or result.get('manual_reason', 'unknown')
                print(f"  [REACT] FAIL — {error}")

                # Self-healing: Seek session failure → skip remaining Seek jobs
                if 'seek_session' in str(error) or 'login_required' in str(error):
                    self._seek_session_failed = True
                    self._session_issues.append(
                        f"Seek login failure at {datetime.now().isoformat()}: {error}"
                    )
                    result['status'] = 'manual_queue_with_context'
                    result['manual_reason'] = 'seek_session_expired'
                    self._manual_queue.append({
                        'job': title, 'company': company,
                        'url': job_url, 'reason': str(error),
                        'cover_letter_path': item['cover_letter'].get('markdown', '')
                    })
                    break

                if iteration >= 2:
                    result['status'] = 'failed_with_reason'
                    self._failed_jobs.append({
                        'job': title, 'company': company, 'reason': str(error)
                    })
                    break
                # Otherwise loop back for retry with updated prior_status

        return result

    # ------------------------------------------------------------------ #
    #  Apply to jobs — uses ReAct loop per job (Req 6, 7)                 #
    # ------------------------------------------------------------------ #

    async def _apply_to_jobs(self, review_queue: List[Dict[str, Any]], selected_indices: List[int]):
        """Apply to selected jobs using the autonomous ReAct decision loop."""
        if self.config.get('apply_one') and len(selected_indices) > 1:
            selected_indices = selected_indices[:1]
            job = review_queue[selected_indices[0]]['job']
            print(f"[APPLY-ONE] Targeting single highest-scoring job: {job['title']} @ {job.get('company', '')}")

        test_apply = self.config.get('test_apply', False)
        if test_apply:
            # Force assisted mode (human must confirm) and verbose regardless of other flags
            apply_mode = 'assisted'
            apply_verbose = True
        else:
            apply_mode = self.config['apply_mode']
            apply_verbose = self.config.get('verbose', False)
        apply_agent = ApplyAgent(mode=apply_mode, verbose=apply_verbose)
        email_agent = EmailApplyAgent()

        # Req 5: Check Seek session at startup of apply stage
        has_seek_jobs = any(
            'seek.com' in review_queue[i]['job'].get('url', '') or
            review_queue[i]['job'].get('seek_url')
            for i in selected_indices
            if 0 <= i < len(review_queue)
        )
        if has_seek_jobs:
            print("\n[SESSION] Checking Seek session validity...")
            session_ok = await apply_agent.check_seek_session()
            if not session_ok:
                apply_agent._seek_session_expired = True
                self._seek_session_failed = True
                self._session_issues.append(
                    f"Seek session expired at pipeline start ({datetime.now().isoformat()})"
                )
                print("\n[ACTION NEEDED] Seek session expired. Run:")
                print("  python seed_login.py")
                print("Then re-run the pipeline.")
                print("Seek jobs will be added to manual queue for this run.\n")

        print("\n[APPLYING] Starting ReAct application loop...")
        print("-" * 100)

        for idx in selected_indices:
            if idx < 0 or idx >= len(review_queue):
                continue

            item = review_queue[idx]
            job = item['job']

            # Skip Seek jobs if session is known failed
            if self._seek_session_failed and (
                'seek.com' in job.get('url', '') or job.get('seek_url')
            ):
                print(f"\n[SKIP] {job['title']} @ {job.get('company','')} — Seek session expired")
                self._manual_queue.append({
                    'job': job['title'], 'company': job.get('company', ''),
                    'url': job.get('url', ''), 'reason': 'seek_session_expired',
                    'cover_letter_path': item.get('cover_letter', {}).get('markdown', '')
                })
                continue

            print(f"\n[{idx+1}] {job['title']} at {job.get('company', '')}")

            result = await self._react_apply_loop(item, apply_agent, email_agent)
            self.pipeline_log['applications'].append(result)

            final_status = result.get('status', '')

            # In test_apply mode: already-applied means try the next candidate
            if self.config.get('test_apply') and final_status == 'already_applied':
                print(f"  [TEST-APPLY] Already applied to this job — trying next candidate")
                continue

            # Store in application memory if submitted (skipped for --test-apply to keep cache clean)
            if final_status in ('confirmed_submitted', 'uncertain_submitted', 'email_draft'):
                if not self.config.get('test_apply'):
                    self.skills.application_memory('store', {
                        'job_hash': job.get('job_hash'),
                        'company': job.get('company'),
                        'role': job.get('title'),
                        'outcome': 'applied',
                        'score': item.get('match', {}).get('score', 0)
                    })
                else:
                    print(f"  [TEST-APPLY] Skipping cache write — job can be retested")

            # In test_apply mode, stop after the first real apply attempt
            if self.config.get('test_apply'):
                break

    # ------------------------------------------------------------------ #
    #  Daily Intelligence Report (Req 8)                                   #
    # ------------------------------------------------------------------ #

    def _write_daily_intelligence(self):
        """
        Write structured daily intelligence report to logs/daily_intelligence.json.
        Replaces the old daily_summary.txt with a machine-readable JSON report.
        """
        intel_path = Path("logs/daily_intelligence.json")
        intel_path.parent.mkdir(exist_ok=True)

        stages = self.pipeline_log.get('stages', {})

        report = {
            'run_date': datetime.now().strftime('%Y-%m-%d'),
            'run_timestamp': datetime.now().isoformat(),
            'pipeline_stats': {
                'jobs_found': stages.get('sourcing', {}).get('jobs_found', 0),
                'jobs_shortlisted': stages.get('matching', {}).get('jobs_shortlisted', 0),
                'docs_generated': stages.get('document_generation', {}).get('docs_generated', 0),
                'qa_passed': stages.get('document_generation', {}).get('qa_passed', 0),
            },
            'confirmed_submitted': self._confirmed_submitted,
            'uncertain_submitted': self._uncertain_submitted,
            'failed': self._failed_jobs,
            'manual_queue': self._manual_queue,
            'session_issues': self._session_issues,
        }

        # Append to existing file (preserve run history)
        existing = []
        if intel_path.exists():
            try:
                with open(intel_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                existing = data if isinstance(data, list) else [data]
            except Exception:
                existing = []

        existing.append(report)

        with open(intel_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        print(f"\n[INTEL] Daily intelligence report → {intel_path}")
        print(f"  Confirmed submitted  : {len(self._confirmed_submitted)}")
        print(f"  Uncertain submitted  : {len(self._uncertain_submitted)}")
        print(f"  Failed               : {len(self._failed_jobs)}")
        print(f"  Manual queue         : {len(self._manual_queue)}")
        if self._session_issues:
            print(f"  Session issues       : {len(self._session_issues)}")
            for issue in self._session_issues:
                print(f"    - {issue}")

    # ------------------------------------------------------------------ #
    #  Manual review queue log (kept for backwards compat)                #
    # ------------------------------------------------------------------ #

    def _log_manual_review_queue(self, manual_jobs: List[Dict[str, Any]]):
        """Append manual-review jobs to logs/manual_review_queue.txt."""
        log_path = Path("logs/manual_review_queue.txt")
        log_path.parent.mkdir(exist_ok=True)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"\n{'=' * 70}", f"Run: {now_str}", f"{'=' * 70}"]

        for item in manual_jobs:
            job = item['job']
            score = item['match']['score']
            routing = item.get('routing', 'unknown')
            resume_path = item.get('resume', {}).get('pdf') or item.get('resume', {}).get('tex', 'N/A')
            cl_path = item.get('cover_letter', {}).get('markdown', 'N/A')
            lines.append(
                f"  [{score:5.1f}]  [{routing:15s}]  {job.get('title', 'N/A')[:40]:40s}  @  {job.get('company', 'N/A')}"
            )
            lines.append(f"             Resume : {resume_path}")
            lines.append(f"             CL     : {cl_path}")
            lines.append(f"             URL    : {job.get('url', 'N/A')}")

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        print(f"\n[AUTO] {len(manual_jobs)} job(s) queued for manual review -> {log_path}", flush=True)

    # ═══════════════════════════════════════════════════════════
    # DYNAMIC ORCHESTRATION METHODS
    # ═══════════════════════════════════════════════════════════

    def _apply_priority_queue(self, shortlisted: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sort jobs by (score * recency_multiplier). Posted today=1.5x, this week=1.2x."""
        print("\n[PRIORITY QUEUE] Applying recency multiplier", flush=True)

        now = datetime.now()

        for item in shortlisted:
            job = item['job']
            score = item['match']['score']

            posted_date_str = job.get('normalized_at', job.get('scraped_at', ''))
            if posted_date_str:
                try:
                    posted_date = datetime.fromisoformat(posted_date_str)
                    age_days = (now - posted_date).days
                    if age_days == 0:
                        recency = 1.5
                    elif age_days <= 7:
                        recency = 1.2
                    else:
                        recency = 1.0
                except Exception:
                    recency = 1.0
            else:
                recency = 1.0

            priority_score = score * recency
            item['priority_score'] = priority_score
            item['recency_multiplier'] = recency

            if recency > 1.0:
                print(f"  {job['title'][:40]:40s} Score: {score:5.1f} → {priority_score:5.1f} (recency: {recency}x)", flush=True)

        shortlisted.sort(key=lambda x: x['priority_score'], reverse=True)
        print(f"  Sorted {len(shortlisted)} jobs by priority score", flush=True)
        return shortlisted

    def _apply_dynamic_routing(self, shortlisted: List[Dict[str, Any]]) -> tuple:
        """Route jobs by score: >=90 full, >=75 standard, >=60 manual, <60 skip."""
        print("\n[DYNAMIC ROUTING] Applying score-based routing with ReAct reasoning", flush=True)

        routed = []
        skipped = []

        for item in shortlisted:
            score = item['match']['score']
            job = item['job']
            job_hash = job.get('job_hash', 'unknown')
            title = job.get('title', 'Unknown')
            recency = item.get('recency_multiplier', 1.0)

            thought = self._generate_reasoning_thought(job, score, recency, item)

            if score >= 90:
                item['routing'] = 'full_pipeline'
                routed.append(item)
                print(f"  [FULL] {title[:50]:50s} Score: {score:5.1f}", flush=True)
                self._log_decision(job_hash, 'full_pipeline', f"Score {score} >= 90", score)
                self._log_reasoning(job, score, thought, 'run_full_pipeline', f"Score {score:.1f} >= 90")

            elif score >= 75:
                item['routing'] = 'standard_pipeline'
                routed.append(item)
                print(f"  [STD]  {title[:50]:50s} Score: {score:5.1f}", flush=True)
                self._log_decision(job_hash, 'standard_pipeline', f"Score {score} >= 75", score)
                self._log_reasoning(job, score, thought, 'run_standard_pipeline', f"Score {score:.1f} >= 75")

            elif score >= 60:
                item['routing'] = 'manual_review'
                item['manual_review_required'] = True
                routed.append(item)
                print(f"  [MAN]  {title[:50]:50s} Score: {score:5.1f} (manual review)", flush=True)
                self._log_decision(job_hash, 'manual_review', f"Score {score} in 60-75 range", score)
                self._log_reasoning(job, score, thought, 'queue_for_manual_review', f"Score {score:.1f} in 60-75 range")

            else:
                skipped.append({
                    'job': job,
                    'match': item['match'],
                    'reason': f'Score {score} < 60 (below threshold)',
                    'skipped_at': datetime.now().isoformat()
                })
                print(f"  [SKIP] {title[:50]:50s} Score: {score:5.1f} (too low)", flush=True)
                self._log_decision(job_hash, 'skip', f"Score {score} < 60", score)
                self._log_reasoning(job, score, thought, 'skip', f"Score {score:.1f} < 60")

        print(f"  Routed: {len(routed)} jobs, Skipped: {len(skipped)} jobs", flush=True)
        return routed, skipped

    def _generate_reasoning_thought(self, job: Dict[str, Any], score: float, recency: float, item: Dict[str, Any]) -> str:
        """Generate reasoning thought for ReAct pattern."""
        company = job.get('company', 'Unknown')
        title = job.get('title', 'Unknown')
        apply_type = job.get('apply_type', 'portal')
        location = job.get('location', 'Unknown')

        thoughts = []

        if score >= 90:
            thoughts.append(f"Score is {score:.1f} (excellent match)")
        elif score >= 75:
            thoughts.append(f"Score is {score:.1f} (good match)")
        elif score >= 60:
            thoughts.append(f"Score is {score:.1f} (moderate match)")
        else:
            thoughts.append(f"Score is {score:.1f} (weak match)")

        if recency >= 1.5:
            thoughts.append("Posted today (high priority)")
        elif recency >= 1.2:
            thoughts.append("Posted this week (recent)")

        if apply_type == 'easy_apply':
            thoughts.append("Easy Apply available")
        elif apply_type == 'email':
            thoughts.append("Email application")

        if company not in ('Unknown Company', 'Unknown', ''):
            thoughts.append(f"Company is {company}")

        if 'sydney' in location.lower():
            thoughts.append("Location matches (Sydney)")

        matching_skills = item.get('match', {}).get('matching_skills', [])
        if len(matching_skills) >= 10:
            thoughts.append(f"Strong skill match ({len(matching_skills)} skills)")
        elif len(matching_skills) >= 5:
            thoughts.append(f"Good skill match ({len(matching_skills)} skills)")

        if score >= 90 and recency >= 1.2:
            thoughts.append("Priority: HIGH")
        elif score >= 75:
            thoughts.append("Priority: MEDIUM")
        else:
            thoughts.append("Priority: LOW")

        return ". ".join(thoughts) + "."

    def _log_reasoning(self, job: Dict[str, Any], score: float, thought: str, action: str, reason: str):
        """Log reasoning trace for ReAct pattern."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'job': f"{job.get('title', 'Unknown')} at {job.get('company', 'Unknown')}",
            'score': score,
            'thought': thought,
            'action': action,
            'reason': reason
        }

        log = []
        if self.reasoning_log_path.exists():
            with open(self.reasoning_log_path, 'r') as f:
                log = json.load(f)

        log.append(entry)
        log = log[-500:]

        with open(self.reasoning_log_path, 'w') as f:
            json.dump(log, f, indent=2)

    def _log_decision(self, job_hash: str, decision: str, reason: str, confidence: float):
        """Log routing decision for audit trail."""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'job_hash': job_hash,
            'decision': decision,
            'reason': reason,
            'confidence': confidence
        }

        self.pipeline_log['decisions'].append(entry)

        decisions = []
        if self.decision_log_path.exists():
            with open(self.decision_log_path, 'r') as f:
                decisions = json.load(f)

        decisions.append(entry)
        decisions = decisions[-1000:]

        with open(self.decision_log_path, 'w') as f:
            json.dump(decisions, f, indent=2)

    async def _process_job_with_skills(
        self,
        job: Dict[str, Any],
        match_report: Dict[str, Any],
        routing: str
    ) -> Optional[Dict[str, Any]]:
        """Process a single job with skill hook integration and retry logic."""
        job_hash = job.get('job_hash', 'unknown')
        company = job.get('company', 'Unknown')

        if self.config.get('test_apply'):
            print(f"  [TEST MODE] Skipping dedup cache check — job can be retested", flush=True)
        elif self.skills.duplicate_checker(job_hash):
            print(f"  [DUPLICATE] Already applied to this job, skipping", flush=True)
            return None

        for attempt in range(3):
            try:
                company_data = None
                if routing == 'full_pipeline' and company != 'Unknown Company':
                    company_data = self.skills.company_researcher(company)
                    match_report['company_research'] = company_data

                salary_data = self.skills.salary_benchmarker(job.get('title', ''), job.get('location', ''))
                match_report['salary_benchmark'] = salary_data

                resume_agent = ResumeAgent(profile=self.profile)
                cover_letter_agent = CoverLetterAgent(profile=self.profile)

                test_mode = self.config.get('test_mode', False)

                if test_mode:
                    print(f"  [SEQUENTIAL] Generating resume then cover letter (test mode)...", flush=True)
                    resume_files = resume_agent.generate_tailored_resume(job, match_report)
                    base_resume_text = self._read_file(resume_files['tex'])
                    cover_letter_files = cover_letter_agent.generate_cover_letter(job, match_report, base_resume_text)
                else:
                    print(f"  [PARALLEL] Generating resume and cover letter concurrently...", flush=True)

                    async def generate_resume_wrapper():
                        await asyncio.sleep(1)
                        return resume_agent.generate_tailored_resume(job, match_report)

                    async def generate_cover_letter_wrapper():
                        base_resume_text = self._read_file('data/base_resume.tex')
                        return cover_letter_agent.generate_cover_letter(job, match_report, base_resume_text)

                    resume_files, cover_letter_files = await asyncio.gather(
                        generate_resume_wrapper(),
                        generate_cover_letter_wrapper()
                    )

                base_resume_text = self._read_file(resume_files['tex'])
                jd_text = job.get('raw_description', '')
                keyword_analysis = self.skills.keyword_density_analyzer(base_resume_text, jd_text, job)

                print(f"  [KEYWORDS] Match: {keyword_analysis['match_pct']}% "
                      f"({len(keyword_analysis['present_keywords'])}/{keyword_analysis['total_keywords_analyzed']})",
                      flush=True)

                if keyword_analysis['match_pct'] < 50 and keyword_analysis['missing_keywords']:
                    print(f"  [KEYWORDS] Suggest adding: {', '.join([k['keyword'] for k in keyword_analysis['missing_keywords'][:3]])}", flush=True)

                self.consecutive_failures = 0

                return {
                    'resume': resume_files,
                    'cover_letter': cover_letter_files,
                    'keyword_analysis': keyword_analysis,
                    'company_research': company_data,
                    'salary_benchmark': salary_data
                }

            except Exception as e:
                print(f"  [ERROR] Attempt {attempt + 1}/3 failed: {str(e)[:100]}", flush=True)

                if attempt < 2:
                    wait_time = 2 ** attempt
                    print(f"  [RETRY] Waiting {wait_time}s before retry...", flush=True)
                    await asyncio.sleep(wait_time)
                else:
                    self.consecutive_failures += 1
                    if self.consecutive_failures >= self.max_consecutive_failures:
                        print(f"  [CRITICAL] {self.max_consecutive_failures} consecutive failures — pausing pipeline", flush=True)
                        raise Exception(f"Pipeline paused after {self.max_consecutive_failures} consecutive failures")
                    return None

    def _check_cover_letter_quality(
        self,
        cover_letter: str,
        job: Dict[str, Any],
        cover_letter_agent,
        skip_regenerate: bool = False
    ) -> tuple:
        """Check cover letter quality and return (score, reason)."""
        from services.claude_client import ClaudeClient

        client = ClaudeClient(model="claude-haiku-4-5-20251001")
        company = job.get('company', 'Unknown Company')

        quality_check_prompt = f"""Rate this cover letter on a scale of 1-10 using these criteria:

Criteria:
1. Opens with domain/technical insight (not generic "I am applying"): /3 points
2. Contains specific project technical details (PersonaQuery, HealthEcho): /3 points
3. Mentions company by name with specific context: /2 points (skip if company is Unknown)
4. No banned generic phrases ("I am excited", "passionate about", etc.): /2 points

Cover Letter:
{cover_letter}

Job Company: {company}
Job Role: {job['title']}

Return JSON:
{{
    "domain_insight_opening": 0-3,
    "project_specifics": 0-3,
    "company_mention": 0-2,
    "no_generic_phrases": 0-2,
    "total_score": 0-10,
    "failure_reason": "specific explanation if score < 7"
}}"""

        try:
            result = client.generate_json(
                prompt=quality_check_prompt,
                system="You are a strict cover letter quality evaluator.",
                max_tokens=500
            )

            if company in ['Unknown Company', 'None', 'Unknown', 'N/A']:
                result['company_mention'] = 2
                result['total_score'] = (
                    result.get('domain_insight_opening', 0) +
                    result.get('project_specifics', 0) +
                    2 +
                    result.get('no_generic_phrases', 0)
                )

            return result.get('total_score', 5), result.get('failure_reason', 'Quality issues')

        except Exception as e:
            print(f"  [WARNING] Quality check failed: {e}", flush=True)
            return 7, "Could not evaluate"

    def _regenerate_cover_letter(
        self,
        cover_letter_agent,
        job,
        match_report,
        tailored_resume,
        previous_score,
        failure_reason
    ):
        """Regenerate cover letter with quality feedback."""
        print(f"  [INFO] Regenerating with feedback: {failure_reason}", flush=True)

        original_prompt = cover_letter_agent._build_cover_letter_prompt

        def modified_prompt(job, match_report, tailored_resume, company_name):
            base = original_prompt(job, match_report, tailored_resume, company_name)
            return f"""REGENERATION: Previous version scored {previous_score}/10.
Failure reason: {failure_reason}

REWRITE COMPLETELY. Do not reuse ANY sentences from the previous version.

{base}"""

        cover_letter_agent._build_cover_letter_prompt = modified_prompt

        try:
            new_files = cover_letter_agent.generate_cover_letter(job, match_report, tailored_resume)
            return new_files
        finally:
            cover_letter_agent._build_cover_letter_prompt = original_prompt

    def _print_review_queue(self, queue: List[Dict[str, Any]]):
        """Print human review queue table."""
        print("\n" + "=" * 120, flush=True)
        print("HUMAN REVIEW QUEUE", flush=True)
        print("=" * 120, flush=True)
        print(flush=True)

        if not queue:
            print("No jobs in queue", flush=True)
            return

        col_widths = [5, 28, 18, 12, 11, 16, 12, 12]
        headers = ["Rank", "Title", "Company", "Match", "Resume QA", "Cover Letter", "CL Quality", "Status"]

        self._print_table_row(headers, col_widths)
        self._print_separator(col_widths)

        for idx, item in enumerate(queue, 1):
            job = item['job']
            match = item['match']
            qa_report = item.get('qa_report', {})
            quality_score = item.get('cover_letter_quality_score', 0)

            qa_checks = qa_report.get('checks_passed', 0)
            qa_total = qa_report.get('checks_run', 14)

            row = [
                str(idx),
                job['title'][:26],
                job['company'][:16],
                f"{match['score']:.0f}/100",
                f"{qa_checks}/{qa_total}",
                Path(item['cover_letter'].get('markdown', 'cover.md')).name[:14],
                f"{quality_score}/10",
                item['qa_status'].upper()[:10]
            ]

            self._print_table_row(row, col_widths)

        self._print_separator(col_widths)

    def _print_table_row(self, cols, widths):
        """Print formatted table row."""
        row = " | ".join(str(col)[:w].ljust(w) for col, w in zip(cols, widths))
        print(f"| {row} |")

    def _print_separator(self, widths):
        """Print table separator."""
        sep = "-+-".join("-" * w for w in widths)
        print(f"+-{sep}-+")

    def _read_file(self, filepath: str) -> str:
        """Read file content."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return ""

    def _save_final_report(self):
        """Save final pipeline report."""
        self.pipeline_log['completed_at'] = datetime.now().isoformat()

        report_dir = Path("logs")
        report_dir.mkdir(exist_ok=True)

        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"pipeline_report_{date_str}.json"

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.pipeline_log, f, indent=2, ensure_ascii=False)

        print(f"\n[REPORT] Saved to {report_file}")

    def _print_summary(self):
        """Print pipeline summary."""
        stages = self.pipeline_log['stages']

        print("\nSUMMARY:")
        print("-" * 100)

        if 'sourcing' in stages:
            print(f"Jobs Found:        {stages['sourcing']['jobs_found']}")

        if 'normalizing' in stages:
            print(f"Jobs Normalized:   {stages['normalizing']['jobs_normalized']}")

        if 'matching' in stages:
            print(f"Jobs Shortlisted:  {stages['matching']['jobs_shortlisted']}")

        if 'document_generation' in stages:
            print(f"Docs Generated:    {stages['document_generation']['docs_generated']}")
            print(f"QA Passed:         {stages['document_generation']['qa_passed']}")

        confirmed = len(self._confirmed_submitted)
        uncertain = len(self._uncertain_submitted)
        print(f"Confirmed Submit:  {confirmed}")
        if uncertain:
            print(f"Uncertain Submit:  {uncertain} (screenshots saved for review)")
        print(f"Manual Queue:      {len(self._manual_queue)}")
        print(f"Failed:            {len(self._failed_jobs)}")
        print()


async def main():
    """Main execution."""
    master = MasterAgent()
    await master.run_pipeline(test_mode=True)


if __name__ == "__main__":
    asyncio.run(main())
