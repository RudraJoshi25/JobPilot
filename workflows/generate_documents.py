"""
Document generation workflow.
Generates tailored resumes and cover letters for shortlisted jobs.
"""
import json
from pathlib import Path
from typing import Dict, Any, List
from agents.resume_agent import ResumeAgent
from agents.cover_letter_agent import CoverLetterAgent


class DocumentGenerator:
    """Generates resumes and cover letters for shortlisted jobs."""

    def __init__(self):
        self.resume_agent = ResumeAgent()
        self.cover_letter_agent = CoverLetterAgent()
        self.manifest = []

    def generate_all(self, shortlisted_file: str = "data/jobs_shortlisted.json") -> Dict[str, Any]:
        """Generate documents for all shortlisted jobs."""
        print("=" * 100)
        print("DOCUMENT GENERATION")
        print("=" * 100)
        print()

        shortlisted = self._load_shortlisted(shortlisted_file)

        if not shortlisted:
            print("No shortlisted jobs found.")
            return {"total": 0, "generated": 0}

        print(f"Generating documents for {len(shortlisted)} shortlisted job(s)...")
        print()

        for idx, item in enumerate(shortlisted, 1):
            job = item['job']
            match_report = item['match']

            print(f"[{idx}/{len(shortlisted)}] {job['title']} at {job['company']}")
            print("=" * 100)

            try:
                resume_files = self.resume_agent.generate_tailored_resume(
                    job=job,
                    match_report=match_report
                )

                tailored_resume = self._read_file(resume_files['markdown'])

                cover_letter_files = self.cover_letter_agent.generate_cover_letter(
                    job=job,
                    match_report=match_report,
                    tailored_resume=tailored_resume
                )

                self.manifest.append({
                    'job_hash': job.get('job_hash'),
                    'job_title': job['title'],
                    'company': job['company'],
                    'match_score': match_report['score'],
                    'verdict': match_report['verdict'],
                    'resume': resume_files,
                    'cover_letter': cover_letter_files,
                    'generated_at': self._get_timestamp()
                })

                print(f"  [COMPLETE] Documents generated successfully")
                print()

            except Exception as e:
                print(f"  [ERROR] Failed to generate documents: {e}")
                print()

        self._save_manifest()

        print("=" * 100)
        print(f"COMPLETED: Generated documents for {len(self.manifest)}/{len(shortlisted)} jobs")
        print("=" * 100)

        return {
            "total": len(shortlisted),
            "generated": len(self.manifest)
        }

    def _load_shortlisted(self, filepath: str) -> List[Dict[str, Any]]:
        """Load shortlisted jobs."""
        path = Path(filepath)
        if not path.exists():
            return []

        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _read_file(self, filepath: str) -> str:
        """Read file content."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            return ""

    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()

    def _save_manifest(self):
        """Save document generation manifest."""
        manifest_file = Path("data/documents_manifest.json")

        with open(manifest_file, 'w', encoding='utf-8') as f:
            json.dump(self.manifest, f, indent=2, ensure_ascii=False)

        print(f"\nSaved manifest to {manifest_file}")


def main():
    """Main execution."""
    generator = DocumentGenerator()
    results = generator.generate_all("data/jobs_shortlisted.json")

    print(f"\nGenerated documents for {results['generated']}/{results['total']} jobs")


if __name__ == "__main__":
    main()
