"""
Resume Agent (LaTeX Edition) - Edits existing LaTeX resume for specific jobs.
Uses Claude Sonnet 4.5 for high-quality targeted edits.
"""
import json
import subprocess
import difflib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from services.claude_client import ClaudeClient


class ResumeAgent:
    """Agent for editing LaTeX resumes based on job requirements."""

    def __init__(self, base_resume_path: str = "data/base_resume.tex", profile_path: str = "data/candidate_profile.json"):
        self.base_resume_path = base_resume_path
        self.profile_path = profile_path
        self.candidate_profile = self._load_profile()
        # COST OPTIMIZATION: Switch to Opus 4.5 (500K/min limit vs Sonnet's 30K/min)
        self.client = ClaudeClient(model="claude-opus-4-5")

    def _load_profile(self) -> Dict[str, Any]:
        """Load candidate profile."""
        with open(self.profile_path, 'r', encoding='utf-8') as f:
            return json.load(f)

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

        # Try to compile PDF if pdflatex is available
        pdf_file = self._try_compile_pdf(tex_file, output_path)

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
        prompt = self._build_modification_prompt(base_tex, job, match_report)
        system_prompt = self._build_system_prompt()

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

    def _build_system_prompt(self) -> str:
        """Build system prompt for LaTeX editing."""
        return """You are an expert LaTeX resume editor for AI/ML roles.

Your task is to modify an existing LaTeX resume to match a specific job posting.

CRITICAL RULES:
1. ONLY modify the content inside \\resumeItem{} tags (bullet points)
2. ONLY modify the skills section content
3. ONLY modify the summary/tagline line if present
4. NEVER change LaTeX commands, packages, document structure, or formatting
5. NEVER change section headers, dates, company names, job titles
6. Preserve ALL LaTeX special characters: \\\\, \\%, \\$, \\&, etc.
7. Preserve ALL line breaks and spacing exactly
8. Return the COMPLETE modified .tex file

OUTPUT FORMAT:
[Complete modified LaTeX file]

---CHANGELOG---

[Detailed list of what was changed and why]"""

    def _build_modification_prompt(self, base_tex: str, job: Dict[str, Any], match_report: Dict[str, Any]) -> str:
        """Build prompt for resume modification."""
        required_skills = job.get('required_skills', [])
        matching_skills = match_report.get('matching_skills', [])
        missing_skills = match_report.get('missing_skills', [])

        return f"""Edit this LaTeX resume to tailor it for a specific job.

JOB DETAILS:
Title: {job['title']}
Company: {job['company']}
Required Skills: {', '.join(required_skills[:10])}

MATCH ANALYSIS:
Score: {match_report['score']}/100
Matching Skills ({len(matching_skills)}): {', '.join(matching_skills[:10])}
Missing Skills ({len(missing_skills)}): {', '.join(missing_skills[:5])}

CURRENT LATEX RESUME:
{base_tex}

INSTRUCTIONS:
1. Modify bullet points (\\resumeItem{{...}}) to emphasize matching skills
2. Reword project bullets to include keywords from required skills naturally
3. In the skills section, reorder or emphasize JD-matching skills
4. If there's a summary line, update it to match the role focus
5. Keep all changes subtle and professional
6. DO NOT change any LaTeX commands or structure
7. Preserve all special characters exactly (\\\\, \\%, \\$, etc.)

Focus on PersonaQuery and HealthEcho projects if they match the JD requirements.

Return the complete modified .tex file, then "---CHANGELOG---", then explain changes."""

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

    def _try_compile_pdf(self, tex_file: Path, output_dir: Path) -> Path | None:
        """Try to compile LaTeX to PDF if pdflatex is available."""
        try:
            result = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode',
                 f'-output-directory={output_dir}',
                 str(tex_file)],
                capture_output=True,
                text=True,
                timeout=30
            )

            pdf_file = tex_file.with_suffix('.pdf')
            if pdf_file.exists():
                print(f"  [OK] PDF: {pdf_file}", flush=True)
                return pdf_file
            else:
                print(f"  [INFO] pdflatex ran but no PDF generated", flush=True)
                return None

        except FileNotFoundError:
            print(f"  [INFO] pdflatex not found - open {tex_file} in Overleaf to compile", flush=True)
            return None
        except subprocess.TimeoutExpired:
            print(f"  [WARNING] PDF compilation timed out", flush=True)
            return None
        except Exception as e:
            print(f"  [WARNING] PDF compilation failed: {e}", flush=True)
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
