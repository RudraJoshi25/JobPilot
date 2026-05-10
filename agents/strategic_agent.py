"""
Layer 5 - Strategic Agent
Analyzes pipeline performance and generates weekly strategy recommendations.
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import Counter, defaultdict
from services.claude_client import ClaudeClient


class StrategicAgent:
    """Analyzes pipeline performance and recommends strategy adjustments."""

    def __init__(self):
        self.client = ClaudeClient(model="claude-opus-4-5")
        self.logs_dir = Path("logs")
        self.data_dir = Path("data")

    def generate_strategy_report(self, weeks_back: int = 4) -> Dict[str, Any]:
        """
        Generate comprehensive strategy report.

        Analyzes:
        - Pipeline performance over time
        - Job source effectiveness
        - Skill gaps and trends
        - Company patterns
        - Search term performance
        """
        print("\n" + "="*100)
        print("STRATEGIC AGENT - PERFORMANCE ANALYSIS")
        print("="*100)

        # Collect data
        print("\n[1/5] Collecting pipeline data...", flush=True)
        pipeline_data = self._collect_pipeline_data(weeks_back)

        print("[2/5] Analyzing application outcomes...", flush=True)
        application_data = self._collect_application_data()

        print("[3/5] Analyzing job patterns...", flush=True)
        job_patterns = self._analyze_job_patterns(pipeline_data)

        print("[4/5] Generating AI insights...", flush=True)
        ai_insights = self._generate_ai_insights(pipeline_data, application_data, job_patterns)

        print("[5/5] Compiling strategy report...", flush=True)
        report = self._compile_report(pipeline_data, application_data, job_patterns, ai_insights)

        # Save report
        report_path = self._save_report(report)

        print(f"\n[COMPLETE] Strategy report saved to: {report_path}")
        return report

    def _collect_pipeline_data(self, weeks_back: int) -> Dict[str, Any]:
        """Collect data from pipeline reports."""
        cutoff_date = datetime.now() - timedelta(weeks=weeks_back)

        reports = []
        if self.logs_dir.exists():
            for report_file in sorted(self.logs_dir.glob("pipeline_report_*.json")):
                try:
                    with open(report_file, 'r') as f:
                        data = json.load(f)

                    # Parse date from filename or started_at
                    if 'started_at' in data:
                        report_date = datetime.fromisoformat(data['started_at'])
                        if report_date >= cutoff_date:
                            reports.append(data)
                except Exception as e:
                    print(f"  [WARNING] Could not load {report_file}: {e}", flush=True)

        print(f"  Loaded {len(reports)} pipeline reports from last {weeks_back} weeks", flush=True)
        return {'reports': reports, 'weeks_analyzed': weeks_back}

    def _collect_application_data(self) -> Dict[str, Any]:
        """Collect data from application memory."""
        memory_path = self.data_dir / "application_memory.json"

        if not memory_path.exists():
            return {'applications': [], 'stats': {}}

        with open(memory_path, 'r') as f:
            data = json.load(f)

        print(f"  Loaded {len(data.get('applications', []))} application records", flush=True)
        return data

    def _analyze_job_patterns(self, pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze patterns across all jobs."""
        all_jobs = []
        source_counts = Counter()
        role_scores = defaultdict(list)
        company_scores = defaultdict(list)
        skill_frequency = Counter()

        for report in pipeline_data['reports']:
            # Source statistics
            if 'stages' in report and 'sourcing' in report['stages']:
                source_counts['total_jobs'] += report['stages']['sourcing'].get('jobs_found', 0)

            # Load jobs from this run if available
            # Note: We'd need to track which jobs came from which report
            # For now, analyze the most recent jobs_clean.json

        # Analyze current job data
        jobs_clean_path = self.data_dir / "jobs_clean.json"
        if jobs_clean_path.exists():
            with open(jobs_clean_path, 'r') as f:
                jobs = json.load(f)

            for job in jobs:
                source_counts[job.get('source', 'unknown')] += 1
                all_jobs.append(job)

                # Collect required skills
                for skill in job.get('required_skills', []):
                    skill_frequency[skill.lower()] += 1

        # Analyze shortlisted jobs
        shortlist_path = self.data_dir / "jobs_shortlisted.json"
        if shortlist_path.exists():
            with open(shortlist_path, 'r') as f:
                shortlisted = json.load(f)

            for item in shortlisted:
                job = item['job']
                score = item['match']['score']

                # Group by role type
                role = job.get('title', '').lower()
                if 'ml' in role or 'machine learning' in role:
                    role_scores['ML Engineer'].append(score)
                elif 'ai' in role:
                    role_scores['AI Engineer'].append(score)
                elif 'data scientist' in role:
                    role_scores['Data Scientist'].append(score)
                elif 'software' in role:
                    role_scores['Software Engineer'].append(score)
                else:
                    role_scores['Other'].append(score)

                # Track company scores
                company_scores[job.get('company', 'Unknown')].append(score)

        # Calculate averages
        avg_scores_by_role = {
            role: round(sum(scores) / len(scores), 1)
            for role, scores in role_scores.items()
        }

        top_companies = sorted(
            [(company, round(sum(scores) / len(scores), 1), len(scores))
             for company, scores in company_scores.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]

        patterns = {
            'total_jobs_analyzed': len(all_jobs),
            'source_distribution': dict(source_counts),
            'avg_scores_by_role': avg_scores_by_role,
            'top_companies': top_companies,
            'most_common_skills': skill_frequency.most_common(20),
            'role_counts': {role: len(scores) for role, scores in role_scores.items()}
        }

        print(f"  Analyzed {patterns['total_jobs_analyzed']} jobs", flush=True)
        return patterns

    def _generate_ai_insights(
        self,
        pipeline_data: Dict[str, Any],
        application_data: Dict[str, Any],
        job_patterns: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Use Claude to generate strategic insights."""

        # Build analysis prompt
        prompt = f"""Analyze this job search pipeline data and provide strategic recommendations.

PIPELINE PERFORMANCE (last {pipeline_data['weeks_analyzed']} weeks):
- Total pipeline runs: {len(pipeline_data['reports'])}
- Total applications submitted: {application_data.get('stats', {}).get('total_applied', 0)}
- Response rate: {application_data.get('stats', {}).get('response_rate', 0):.1f}%

JOB SOURCE DISTRIBUTION:
{json.dumps(job_patterns['source_distribution'], indent=2)}

AVERAGE MATCH SCORES BY ROLE TYPE:
{json.dumps(job_patterns['avg_scores_by_role'], indent=2)}

TOP 10 COMPANIES BY MATCH SCORE:
{json.dumps(job_patterns['top_companies'], indent=2)}

MOST COMMON REQUIRED SKILLS (top 20):
{json.dumps(job_patterns['most_common_skills'][:20], indent=2)}

ROLE TYPE DISTRIBUTION:
{json.dumps(job_patterns['role_counts'], indent=2)}

ANALYSIS TASKS:

1. SOURCE PERFORMANCE:
   - Which job sources are most effective?
   - Should we add/remove any sources?
   - Are there sources we should prioritize?

2. SKILL GAP ANALYSIS:
   - What skills appear repeatedly in high-scoring jobs that might be gaps?
   - Which skills should be highlighted more in the resume/profile?
   - Are there emerging skills we should learn?

3. ROLE TARGETING:
   - Which role types have the best match scores?
   - Should we adjust our search terms?
   - Are we targeting the right seniority levels?

4. COMPANY INSIGHTS:
   - Which companies consistently have high match scores?
   - Should we research these companies directly?
   - Are there company size or industry patterns?

5. SEARCH STRATEGY:
   - What new search terms should we add?
   - What terms should we remove or deprioritize?
   - Should we adjust location or other filters?

Provide 5-10 concrete, actionable recommendations. Be specific.

Return as JSON:
{{
    "source_recommendations": ["rec1", "rec2", ...],
    "skill_recommendations": ["rec1", "rec2", ...],
    "role_recommendations": ["rec1", "rec2", ...],
    "company_recommendations": ["rec1", "rec2", ...],
    "search_recommendations": ["rec1", "rec2", ...],
    "summary": "2-3 sentence executive summary"
}}"""

        try:
            insights = self.client.generate_json(
                prompt=prompt,
                system="You are a strategic advisor for job search optimization. Provide data-driven, actionable recommendations.",
                max_tokens=2048
            )
            print(f"  Generated {len(insights.get('source_recommendations', []))} source recommendations", flush=True)
            return insights
        except Exception as e:
            print(f"  [WARNING] AI insights generation failed: {e}", flush=True)
            return {
                'source_recommendations': ['Review source performance manually'],
                'skill_recommendations': ['Analyze skill gaps manually'],
                'role_recommendations': ['Review role targeting manually'],
                'company_recommendations': ['Research top companies manually'],
                'search_recommendations': ['Review search terms manually'],
                'summary': 'AI analysis unavailable - review data manually'
            }

    def _compile_report(
        self,
        pipeline_data: Dict[str, Any],
        application_data: Dict[str, Any],
        job_patterns: Dict[str, Any],
        ai_insights: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compile final strategy report."""
        return {
            'generated_at': datetime.now().isoformat(),
            'period': f"Last {pipeline_data['weeks_analyzed']} weeks",
            'summary': {
                'total_runs': len(pipeline_data['reports']),
                'total_applications': application_data.get('stats', {}).get('total_applied', 0),
                'response_rate': application_data.get('stats', {}).get('response_rate', 0),
                'total_jobs_analyzed': job_patterns['total_jobs_analyzed']
            },
            'source_performance': job_patterns['source_distribution'],
            'role_performance': job_patterns['avg_scores_by_role'],
            'top_companies': job_patterns['top_companies'],
            'skill_trends': job_patterns['most_common_skills'][:15],
            'ai_recommendations': ai_insights,
            'action_items': self._generate_action_items(ai_insights)
        }

    def _generate_action_items(self, ai_insights: Dict[str, Any]) -> List[str]:
        """Generate prioritized action items."""
        actions = []

        # Combine all recommendations
        for category in ['source_recommendations', 'skill_recommendations',
                        'role_recommendations', 'company_recommendations',
                        'search_recommendations']:
            recs = ai_insights.get(category, [])
            actions.extend(recs[:2])  # Top 2 from each category

        return actions[:10]  # Top 10 overall

    def _save_report(self, report: Dict[str, Any]) -> Path:
        """Save report to file."""
        # JSON version
        date_str = datetime.now().strftime("%Y%m%d")
        json_path = self.logs_dir / f"strategy_report_{date_str}.json"

        with open(json_path, 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # Markdown version for easy reading
        md_path = self.logs_dir / f"weekly_strategy_{date_str}.md"
        md_content = self._format_markdown_report(report)

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        return md_path

    def _format_markdown_report(self, report: Dict[str, Any]) -> str:
        """Format report as markdown."""
        md = f"""# Weekly Strategy Report
Generated: {report['generated_at']}
Period: {report['period']}

---

## Executive Summary

{report['ai_recommendations'].get('summary', 'No summary available')}

### Key Metrics
- **Pipeline Runs**: {report['summary']['total_runs']}
- **Applications Submitted**: {report['summary']['total_applications']}
- **Response Rate**: {report['summary']['response_rate']:.1f}%
- **Jobs Analyzed**: {report['summary']['total_jobs_analyzed']}

---

## Performance Analysis

### Source Performance
"""
        for source, count in report['source_performance'].items():
            md += f"- **{source}**: {count} jobs\n"

        md += "\n### Role Performance (Avg Match Score)\n"
        for role, score in report['role_performance'].items():
            md += f"- **{role}**: {score}/100\n"

        md += "\n### Top Companies by Match Score\n"
        for company, score, count in report['top_companies'][:5]:
            md += f"- **{company}**: {score}/100 ({count} jobs)\n"

        md += "\n### Most In-Demand Skills\n"
        for skill, count in report['skill_trends'][:10]:
            md += f"- {skill}: {count} occurrences\n"

        md += "\n---\n\n## AI-Generated Recommendations\n\n"

        recommendations = report['ai_recommendations']

        md += "### 📊 Source Strategy\n"
        for rec in recommendations.get('source_recommendations', []):
            md += f"- {rec}\n"

        md += "\n### 🎯 Skill Development\n"
        for rec in recommendations.get('skill_recommendations', []):
            md += f"- {rec}\n"

        md += "\n### 💼 Role Targeting\n"
        for rec in recommendations.get('role_recommendations', []):
            md += f"- {rec}\n"

        md += "\n### 🏢 Company Research\n"
        for rec in recommendations.get('company_recommendations', []):
            md += f"- {rec}\n"

        md += "\n### 🔍 Search Optimization\n"
        for rec in recommendations.get('search_recommendations', []):
            md += f"- {rec}\n"

        md += "\n---\n\n## Priority Action Items\n\n"
        for i, action in enumerate(report['action_items'], 1):
            md += f"{i}. {action}\n"

        md += "\n---\n\n*Report generated by Strategic Agent*\n"

        return md

    def print_summary(self, report: Dict[str, Any]):
        """Print summary to console."""
        print("\n" + "="*100)
        print("STRATEGY REPORT SUMMARY")
        print("="*100)

        print(f"\n{report['ai_recommendations'].get('summary', 'No summary')}")

        print(f"\n📊 METRICS ({report['period']})")
        print("-"*100)
        print(f"  Pipeline runs:      {report['summary']['total_runs']}")
        print(f"  Applications sent:  {report['summary']['total_applications']}")
        print(f"  Response rate:      {report['summary']['response_rate']:.1f}%")
        print(f"  Jobs analyzed:      {report['summary']['total_jobs_analyzed']}")

        print(f"\n🎯 TOP 3 ACTION ITEMS")
        print("-"*100)
        for i, action in enumerate(report['action_items'][:3], 1):
            print(f"  {i}. {action}")

        print(f"\n💼 TOP COMPANIES (by match score)")
        print("-"*100)
        for company, score, count in report['top_companies'][:5]:
            print(f"  {company:30s} {score:5.1f}/100  ({count} jobs)")

        print("\n" + "="*100)


def main():
    """Run strategic analysis."""
    agent = StrategicAgent()

    # Generate strategy report
    report = agent.generate_strategy_report(weeks_back=4)

    # Print summary
    agent.print_summary(report)


if __name__ == "__main__":
    main()
