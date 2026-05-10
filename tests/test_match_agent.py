#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.match_agent import MatchAgent


STRONG_MATCH_JOB = """
AI Engineer - Graduate/Junior Level
Sydney, Australia (Hybrid)

We're looking for a passionate AI Engineer to join our growing team building cutting-edge LLM applications.

Requirements:
- Bachelor's degree in Computer Science or related field
- Strong Python programming skills
- Experience with Large Language Models (LLMs) and prompt engineering
- Knowledge of RAG (Retrieval-Augmented Generation) systems
- Understanding of API development and integration
- Solid computer science fundamentals
- 0-2 years of experience (graduate/entry-level welcome)

Nice to have:
- Experience with machine learning frameworks
- NLP background
- Cloud platform experience

This is a perfect role for recent graduates passionate about AI/ML looking to grow their career.
"""


WEAK_MATCH_JOB = """
Senior Java Backend Engineer
Melbourne, Australia

Enterprise software company seeking a Senior Java Backend Engineer with 8+ years of experience.

Requirements:
- 8+ years of professional Java development experience
- Expert in Spring Boot, Hibernate, and microservices architecture
- Strong experience with Oracle and PostgreSQL databases
- Leadership experience mentoring junior developers
- Enterprise application development background
- Experience with CI/CD pipelines (Jenkins, GitLab)
- Knowledge of Kubernetes and Docker

Required:
- Bachelor's degree in Computer Science
- Proven track record of leading large-scale projects
- Strong SQL and database optimization skills

Tech Stack: Java 17, Spring Boot, Oracle, Kubernetes, Jenkins
"""


MEDIUM_MATCH_JOB = """
Data Analyst - Junior Level
Sydney, Australia (Remote friendly)

Looking for a junior data analyst to help analyze customer data and build insights.

Requirements:
- Bachelor's degree in Computer Science, Statistics, or related field
- Strong Python programming skills
- Experience with data analysis and visualization
- SQL knowledge
- Good understanding of statistics and data interpretation
- API integration experience is a plus
- 0-2 years of experience

Responsibilities:
- Analyze customer data to identify trends
- Build dashboards and reports
- Work with APIs to extract data
- Collaborate with product team on insights
- Some light machine learning model evaluation

Nice to have:
- Machine learning basics
- Experience with ML model evaluation
- Natural language processing knowledge
"""


def run_tests():
    print("=" * 80)
    print("MATCH AGENT TEST SUITE")
    print("=" * 80)
    print()

    agent = MatchAgent()

    test_cases = [
        ("STRONG MATCH - AI Engineer (Graduate)", STRONG_MATCH_JOB, "Should score 80+"),
        ("WEAK MATCH - Senior Java Backend", WEAK_MATCH_JOB, "Should score below 40"),
        ("MEDIUM MATCH - Junior Data Analyst", MEDIUM_MATCH_JOB, "Should score 50-70")
    ]

    results = []

    for i, (name, job_desc, expectation) in enumerate(test_cases, 1):
        print(f"Test {i}: {name}")
        print("-" * 80)
        print(f"Expectation: {expectation}")
        print()

        try:
            result = agent.evaluate_match(job_desc)

            print(f"[OK] Score: {result.score:.1f}/100")
            print(f"[OK] Verdict: {result.verdict.upper()}")
            print(f"[OK] Matching Skills: {', '.join(result.matching_skills[:5])}{'...' if len(result.matching_skills) > 5 else ''}")
            print(f"[OK] Missing Skills: {', '.join(result.missing_skills[:5])}{'...' if len(result.missing_skills) > 5 else ''}")
            print(f"[OK] Reasoning: {result.reasons[:200]}...")

            results.append({
                "name": name,
                "score": result.score,
                "verdict": result.verdict,
                "passed": True
            })

        except Exception as e:
            print(f"[ERROR] {e}")
            results.append({
                "name": name,
                "score": 0,
                "verdict": "error",
                "passed": False
            })

        print()
        print("=" * 80)
        print()

    print("\nSUMMARY")
    print("-" * 80)
    for result in results:
        status = "[PASS]" if result["passed"] else "[FAIL]"
        print(f"{status} | {result['name']:<40} | Score: {result['score']:>5.1f} | Verdict: {result['verdict']:<7}")

    print()
    print("Test expectations:")
    print("1. Strong match should score 80+ (verdict: apply)")
    print("2. Weak match should score below 40 (verdict: skip)")
    print("3. Medium match should score 50-70 (verdict: maybe)")

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"\nTests completed: {passed}/{total} successful")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run_tests())
