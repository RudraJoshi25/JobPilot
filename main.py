#!/usr/bin/env python3
"""
Main entry point for the Job Application Pipeline.
Single command to run the complete system.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

import asyncio
import argparse
from pathlib import Path
from agents.master_agent import MasterAgent


def print_banner():
    """Print welcome banner."""
    banner = """
    ==============================================================

         JOB APPLICATION AUTOMATION PIPELINE
         Powered by Claude AI

      Source -> Normalize -> Match -> Generate -> QA -> Apply

    ==============================================================
    """
    print(banner)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Job Application Pipeline - Automated job search and application system'
    )

    parser.add_argument(
        '--test',
        action='store_true',
        help='Run in test mode (max 2 jobs, faster execution)'
    )

    parser.add_argument(
        '--docs-only',
        action='store_true',
        help='Skip scraping, generate documents for existing shortlist'
    )

    parser.add_argument(
        '--apply-only',
        action='store_true',
        help='Skip to apply stage for already-approved jobs'
    )

    # Layer 5: Strategic Agent
    parser.add_argument(
        '--strategy',
        action='store_true',
        help='Run strategic agent only (weekly performance analysis)'
    )

    # Layer 3: Skill Hooks Stats
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Print application memory statistics'
    )

    # Layer 2: Guardrails Testing
    parser.add_argument(
        '--guardrails-test',
        action='store_true',
        help='Test guardrails engine in isolation'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='data/pipeline_config.json',
        help='Path to pipeline configuration file'
    )

    args = parser.parse_args()

    # Handle special modes first (non-pipeline commands)

    # LAYER 5: Strategic Agent
    if args.strategy:
        print_banner()
        print("\n[STRATEGIC AGENT] Generating performance analysis...")
        print("="*100 + "\n")

        from agents.strategic_agent import StrategicAgent
        agent = StrategicAgent()
        report = agent.generate_strategy_report(weeks_back=4)
        agent.print_summary(report)
        return 0

    # LAYER 3: Application Memory Stats
    if args.stats:
        print_banner()
        print("\n[APPLICATION MEMORY STATS]")
        print("="*100 + "\n")

        from core.skill_hooks import SkillRegistry
        skills = SkillRegistry()

        stats = skills.application_memory('get_stats')
        print(f"📊 Overview:")
        print(f"  Total applications:  {stats.get('total_applied', 0)}")
        print(f"  Total responses:     {stats.get('total_responses', 0)}")
        print(f"  Response rate:       {stats.get('response_rate', 0):.1f}%")

        patterns = skills.application_memory('get_winning_patterns')

        if patterns.get('total_responses', 0) > 0:
            print(f"\n🏆 Winning Patterns:")
            print(f"  Top companies:       {patterns.get('top_companies', [])[:3]}")
            print(f"  Top role types:      {patterns.get('top_role_types', [])[:3]}")
            print(f"  Avg score (responding): {patterns.get('avg_score_of_responses', 0):.1f}/100")
        else:
            print(f"\n  No responses yet to analyze patterns")

        print("\n" + "="*100)
        return 0

    # LAYER 2: Guardrails Test
    if args.guardrails_test:
        print_banner()
        print("\n[GUARDRAILS ENGINE TEST]")
        print("="*100 + "\n")

        from core.guardrails import GuardrailsEngine

        async def test_guardrails():
            """Test guardrails with dummy agent."""
            async def dummy_agent(job, match_report):
                await asyncio.sleep(0.1)
                return {
                    'resume_markdown': 'Test resume content with sufficient words. ' * 40,
                    'changelog': 'Test changes'
                }

            engine = GuardrailsEngine()

            result = await engine.run(
                agent_fn=dummy_agent,
                input_data={
                    'job': {'title': 'Test AI Engineer', 'company': 'Test Company'},
                    'match_report': {'score': 85}
                },
                agent_name='test_agent',
                max_retries=2
            )

            print(f"✓ Test Result:")
            print(f"  Success:     {result['success']}")
            print(f"  Violations:  {len(result['violations'])}")
            print(f"  Cost:        ${result['cost']:.6f}")
            print(f"  Retries:     {result['retries']}")

            if result['violations']:
                print(f"\n  Violations detected:")
                for v in result['violations']:
                    print(f"    [{v.severity.upper()}] {v.guardrail}: {v.message}")

            stats = engine.get_stats()
            print(f"\n✓ Engine Stats:")
            print(f"  Total cost:  ${stats['total_cost']:.4f}")
            print(f"  Total calls: {stats['total_calls']}")

            print("\n" + "="*100)
            print("[SUCCESS] Guardrails test completed!")

        await test_guardrails()
        return 0

    print_banner()

    # Verify config exists
    if not Path(args.config).exists():
        print(f"[ERROR] Configuration file not found: {args.config}")
        print("Please create data/pipeline_config.json with your settings")
        return 1

    # Initialize master agent
    master = MasterAgent(config_path=args.config)

    try:
        # Run pipeline based on mode
        await master.run_pipeline(
            test_mode=args.test,
            docs_only=args.docs_only,
            apply_only=args.apply_only
        )

        print("\n[SUCCESS] Pipeline execution completed successfully!")
        return 0

    except KeyboardInterrupt:
        print("\n\n[CANCELLED] Pipeline interrupted by user")
        return 1

    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
