"""
Resume Agent (LaTeX Edition) - Edits existing LaTeX resume for specific jobs.
Uses Claude Opus 4.5 for high-quality targeted edits.
"""
import json
import subprocess
import difflib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from services.claude_client import ClaudeClient
import yaml


def load_profile_yaml(profile_path: str = "profile.yaml") -> Dict[str, Any]:
    """Load profile.yaml as single source of truth."""
    with open(profile_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class ResumeAgent:
    """Agent for editing LaTeX resumes based on job requirements."""

    def __init__(self, base_resume_path: str = "data/base_resume.tex", profile: Dict[str, Any] = None):
        self.base_resume_path = base_resume_path
        self.profile = profile or load_profile_yaml()
        self.candidate_profile = self._build_candidate_profile()
        self.client = ClaudeClient(model="claude-opus-4-5")

    def _build_candidate_profile(self) -> Dict[str, Any]:
        """Build candidate profile dict from profile.yaml structure."""
        candidate = self.profile.get('candidate', {})
        skills = self.profile.get('skills', {})
        projects = self.profile.get('projects', [])

        all_skills = []
        for category in skills.values():
            if isinstance(category, list):
                all_skills.extend(category)

        return {
            'name': candidate.get('name', ''),
            'location': candidate.get('location', ''),
            'education': [{
                'degree': candidate.get('degree', ''),
                'institution': candidate.get('university', ''),
                'graduation_year': candidate.get('graduation', '')
            }],
            'skills': all_skills,
            'projects': projects
        }

    def generate_tailored_resume(
        self,
        job: Dict[str, Any],
        match_report: Dict[str, Any],
        output_dir: str = "artifacts/resumes"
    ) -> Dict[str, str]:
        """Generate a tailored LaTeX resume for a specific job."""
        print(f"\nGenerating tailored resume for: {job['title']} at {job['company']}", flush=True)
        print("-" * 80, flush=True)

        # Load base resume
        base_tex = self._load_base_resume()

        # Generate modified resume
        modified_tex, changes = self._modify_resume(base_tex, job, match_report)

        # Save outputs
        job_hash = job.get('job_hash', 'unknown')
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        tex_file = output_path / f"resume_{job_hash}.tex"
        changelog_file = output_path / f"resume_{job_hash}_changelog.txt"
        diff_file = output_path / f"resume_{job_hash}_diff.txt"

        # Write files
        with open(tex_file, 'w', encoding='utf-8') as f:
            f.write(modified_tex)

        with open(changelog_file, 'w', encoding='utf-8') as f:
            f.write(changes)

        # Generate diff
        diff = self._generate_diff(base_tex, modified_tex)
        with open(diff_file, 'w', encoding='utf-8') as f:
            f.write(diff)

        print(f"  [OK] LaTeX: {tex_file}", flush=True)
        print(f"  [OK] Changelog: {changelog_file}", flush=True)
        print(f"  [OK] Diff: {diff_file}", flush=True)

        # Compile PDF — MiKTeX must be installed
        pdf_file = self._try_compile_pdf(tex_file, output_path, job_hash)

        return {
            'tex': str(tex_file),
            'changelog': str(changelog_file),
            'diff': str(diff_file),
            'pdf': str(pdf_file) if pdf_file else None
        }

    def _load_base_resume(self) -> str:
        """Load base LaTeX resume."""
        with open(self.base_resume_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _modify_resume(self, base_tex: str, job: Dict[str, Any], match_report: Dict[str, Any]) -> tuple:
        """Modify LaTeX resume for specific job."""
        job_title = job.get('title', 'this role')
        prompt = self._build_modification_prompt(base_tex, job, match_report, job_title)
        system_prompt = self._build_system_prompt(job_title)

        # Get modified resume
        response = self.client.generate(
            prompt=prompt,
            system=system_prompt,
            max_tokens=8192
        )

        # Split into resume and changelog
        if "---CHANGELOG---" in response:
            parts = response.split("---CHANGELOG---")
            modified_tex = parts[0].strip()
            changelog = parts[1].strip()
        else:
            modified_tex = response.strip()
            changelog = "No changelog provided"

        # Clean up any markdown code blocks if present
        if modified_tex.startswith("```"):
            lines = modified_tex.split('\n')
            modified_tex = '\n'.join(lines[1:-1]) if len(lines) > 2 else modified_tex

        return modified_tex, changelog

    def _build_system_prompt(self, job_title: str) -> str:
        """Build system prompt for LaTeX editing."""
        return f"""You are a professional resume writer tailoring a LaTeX resume for a real job applicant. Your output will be reviewed by human recruiters and hiring managers at top companies. Every change must look like a skilled human career coach made it — not an AI keyword optimizer.

ABSOLUTE PROHIBITIONS — never do these:

1. NEVER keyword-stuff the skills section with field names like "Machine Learning", "Deep Learning", "Generative AI", "NLP" as if they are skills. List tools and frameworks only (PyTorch, scikit-learn, LangChain). Concepts are not skills.

2. NEVER add \\textbf{{}} bold tags inside bullet point prose. Bold is ONLY allowed on: project names, company names, and Tech: lines. Never bold a keyword mid-sentence.

3. NEVER append summary sentences to patents or publications. Citations stand alone.

4. NEVER alter factual details to insert keywords. If the original said Java, it was Java. Never insert Python or any technology not actually used in that role.

5. NEVER make project subtitles generic keyword phrases like "Generative AI Application with RAG & LLMs". Keep subtitles specific and technical.

6. NEVER spell out acronyms already known in tech (LLM, NLP, RAG, API, REST).

7. NEVER repeat the same concept in multiple forms on one line (LLMs and "Large Language Models" on the same line).

8. NEVER add hollow filler phrases. Permanently banned:
   - "applicable to [industry] use cases"
   - "adaptable to industry verticals"
   - "enabling rapid customization for specific use cases"
   - "demonstrating [X] for automated workflows"
   - "leveraging [tool] for [generic outcome]"

9. NEVER use these verbs: Leveraged, Utilized, Facilitated, Demonstrated, Enabled, Showcased. Use instead: Built, Implemented, Designed, Reduced, Deployed, Shipped, Optimised, Engineered, Automated, Benchmarked.

10. NEVER change \\vspace values, font size commands, the header block (name, phone, email), or add bullets that push a project past its current line count without removing an equivalent bullet.

11. NEVER use em dashes (—) or double hyphens (--) as punctuation inside bullet points or anywhere in the resume body. These are a strong signal of AI-written text. Use a single hyphen (-), a comma, or restructure the sentence instead.
   BAD:  "Built a RAG pipeline — applicable to enterprise search use cases"
   BAD:  "Designed evaluation harness -- reduces retrieval regressions"
   GOOD: "Built a RAG pipeline for enterprise-style semantic search"
   GOOD: "Designed evaluation harness that reduces retrieval regressions"
   Exception: LaTeX en-dash in date ranges (e.g. "Jan 2023 -- Dec 2023") is standard formatting — keep as-is.

FACTUAL INTEGRITY — non-negotiable:
- Never add a technology not in the base resume
- Never change metrics, percentages, or numbers
- Never change dates, company names, degree names
- Never remove the "(actively upskilling)" qualifier from Azure
- Never claim production experience for a PoC/project
- If the JD requires a skill not in the base resume, do NOT add it silently — add a note in the changelog: "[MISSING SKILL] JD requires X — not added"

WHAT GOOD TAILORING LOOKS LIKE:
- Reorder skills within a section to front-load keywords from the JD
- Swap synonyms to match JD language where candidate actually has the skill
- Elevate the most relevant bullet to the top of a project section
- Adjust project subtitle to emphasise the most relevant specific aspect
- Ensure the exact role title '{job_title}' appears naturally somewhere in the resume — either in the subtitle or a project description — exactly once

SKILLS SECTION RULES:
- Each line: Category: tool1, tool2, framework3, technique4
- Maximum ~12 items per line
- No field names as skills ("Machine Learning" is not a skill — PyTorch is)
- No duplicate concepts across categories

BULLET POINT QUALITY CHECK (apply to every bullet before output):
- Starts with a strong past-tense action verb
- Contains a specific technical detail or measurable outcome
- Could plausibly have been written by the candidate themselves
- Does not contain any banned phrases or verbs

SELF-CHECK before returning output — verify all of these:
[ ] No inline \\textbf{{}} added inside bullet prose
[ ] No appended sentences on patent/publication entries
[ ] No factual changes (technologies, metrics, dates)
[ ] No generic project subtitles
[ ] No spelled-out acronyms that were already abbreviated
[ ] No banned verbs or filler phrases
[ ] Skills section contains tools/frameworks only, not field names
[ ] Exact role title appears naturally exactly once
[ ] Page length unchanged
[ ] Changelog lists every change with line references

OUTPUT FORMAT:
[Complete modified LaTeX file]

---CHANGELOG---

[Detailed list of every change made, with line references]"""

    def _build_modification_prompt(self, base_tex: str, job: Dict[str, Any], match_report: Dict[str, Any], job_title: str) -> str:
        """Build prompt for resume modification."""
        required_skills = job.get('required_skills', [])
        matching_skills = match_report.get('matching_skills', [])
        missing_skills = match_report.get('missing_skills', [])

        return f"""Tailor this LaTeX resume for the following role.

TARGET ROLE: {job_title} at {job['company']}
Required Skills: {', '.join(required_skills[:10])}

MATCH ANALYSIS:
Score: {match_report['score']}/100
Matching Skills ({len(matching_skills)}): {', '.join(matching_skills[:10])}
Missing Skills ({len(missing_skills)}): {', '.join(missing_skills[:5])}

CURRENT LATEX RESUME:
{base_tex}

INSTRUCTIONS:
1. Reorder or lightly reword bullet points to front-load skills the JD requires
2. In the skills section, reorder items to emphasise JD-matching tools first
3. Adjust project subtitles to highlight the most relevant technical aspect (specific, not generic)
4. Ensure the exact role title "{job_title}" appears naturally exactly once — subtitle or a project description
5. Follow all rules in the system prompt without exception
6. Preserve all LaTeX commands, special characters, and spacing exactly

Focus on these projects if they match the JD requirements:
{self._format_projects()}

Return the complete modified .tex file, then "---CHANGELOG---", then list every change with line references."""

    def _format_projects(self) -> str:
        """Format projects from profile for prompt."""
        projects = self.profile.get('projects', [])
        lines = []
        for p in projects:
            name = p.get('name', '')
            desc = p.get('description', '').strip().replace('\n', ' ')
            stack = ', '.join(p.get('stack', []))
            metrics = ', '.join(p.get('metrics', []))
            lines.append(f"- {name}: {desc[:200]} (Stack: {stack}) (Metrics: {metrics})")
        return '\n'.join(lines) if lines else "PersonaQuery and HealthEcho"

    def _generate_diff(self, original: str, modified: str) -> str:
        """Generate a unified diff showing changes."""
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile='base_resume.tex',
            tofile='modified_resume.tex',
            lineterm=''
        )

        return ''.join(diff)

    # MiKTeX per-user install location (added to subprocess env so the venv
    # inherits it even when the system shell PATH differs from the user PATH)
    MIKTEX_BIN = r"C:\Users\rjjos\AppData\Local\Programs\MiKTeX\miktex\bin\x64"

    def _try_compile_pdf(self, tex_file: Path, output_dir: Path, job_hash: str = '') -> Path | None:
        """Compile LaTeX to PDF using pdflatex. Logs stderr on failure."""
        import os as _os
        label = job_hash or tex_file.stem

        # Build env with MiKTeX prepended so subprocess can find pdflatex
        env = _os.environ.copy()
        env['PATH'] = self.MIKTEX_BIN + _os.pathsep + env.get('PATH', '')

        pdflatex_exe = _os.path.join(self.MIKTEX_BIN, 'pdflatex.exe')
        try:
            proc = subprocess.run(
                [pdflatex_exe, '-interaction=nonstopmode',
                 f'-output-directory={output_dir}',
                 str(tex_file)],
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )

            pdf_file = output_dir / tex_file.with_suffix('.pdf').name
            if pdf_file.exists():
                print(f"  [OK] PDF: {pdf_file}", flush=True)
                return pdf_file

            print(f"  [ERROR] PDF compilation failed for {label}", flush=True)
            # Print pdflatex error lines from stdout (pdflatex logs errors there)
            if proc.stdout:
                error_lines = [l for l in proc.stdout.splitlines()
                               if l.startswith('!') or 'Error' in l or 'error' in l]
                if error_lines:
                    print("  [PDFLATEX ERRORS]:", flush=True)
                    for line in error_lines[:15]:
                        print(f"    {line}", flush=True)
            # Print stderr if present
            if proc.stderr and proc.stderr.strip():
                print("  [PDFLATEX STDERR]:", flush=True)
                for line in proc.stderr.strip().splitlines()[-20:]:
                    print(f"    {line}", flush=True)
            return None

        except FileNotFoundError:
            print(f"  [INFO] pdflatex not found — install MiKTeX or compile {tex_file.name} in Overleaf", flush=True)
            return None
        except subprocess.TimeoutExpired:
            print(f"  [ERROR] PDF compilation timed out for {label} (>60s)", flush=True)
            return None
        except Exception as e:
            print(f"  [ERROR] PDF compilation failed for {label}: {e}", flush=True)
            return None


def main():
    """Example usage."""
    agent = ResumeAgent()

    # Load a shortlisted job
    with open('data/jobs_shortlisted.json', 'r') as f:
        shortlisted = json.load(f)

    if shortlisted:
        top_job = shortlisted[0]
        files = agent.generate_tailored_resume(
            job=top_job['job'],
            match_report=top_job['match']
        )
        print(f"\nGenerated files: {files}")


if __name__ == "__main__":
    main()
