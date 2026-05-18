"""
Layer 3 - Skill Hooks Registry
Pluggable tools that any agent can call: company research, keyword analysis,
application memory, salary benchmarking, duplicate checking.
"""
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import Counter


class SkillRegistry:
    """Registry of pluggable skills for agents."""

    def __init__(self):
        self.company_cache_path = Path("data/company_cache.json")
        self.salary_cache_path = Path("data/salary_cache.json")
        self.memory_path = Path("data/application_memory.json")

        # Ensure data directory exists
        Path("data").mkdir(exist_ok=True)

        # Initialize memory if not exists
        if not self.memory_path.exists():
            self._init_memory()

    def _init_memory(self):
        """Initialize application memory."""
        initial_data = {
            'applications': [],
            'stats': {
                'total_applied': 0,
                'total_responses': 0,
                'response_rate': 0.0
            }
        }
        with open(self.memory_path, 'w') as f:
            json.dump(initial_data, f, indent=2)

    # ═══════════════════════════════════════════════════════════
    # SKILL 1 — Company Researcher
    # ═══════════════════════════════════════════════════════════

    def company_researcher(self, company_name: str) -> Dict[str, Any]:
        """
        Research company using web search.
        Returns cached data if available, otherwise searches and caches.
        """
        print(f"  [SKILL] Researching company: {company_name}", flush=True)

        # Check cache first
        if self.company_cache_path.exists():
            with open(self.company_cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                if company_name in cache:
                    print(f"  [SKILL] Using cached data for {company_name}", flush=True)
                    return cache[company_name]
        else:
            cache = {}

        # Search for company info
        try:
            from ddgs import DDGS

            result = {
                'company': company_name,
                'size': 'Unknown',
                'industry': 'Unknown',
                'tech_stack': [],
                'culture_notes': '',
                'recent_news': [],
                'researched_at': datetime.now().isoformat()
            }

            # Search for general company info
            ddgs = DDGS()
            try:
                # Company overview
                overview_results = list(ddgs.text(
                    f"{company_name} company size industry overview",
                    max_results=3
                ))

                # Extract info from snippets
                for r in overview_results:
                    snippet = r.get('body', '').lower()

                    # Try to detect size
                    if any(word in snippet for word in ['startup', 'small', '10-50']):
                        result['size'] = 'Small (10-50)'
                    elif any(word in snippet for word in ['medium', '50-200', '100-500']):
                        result['size'] = 'Medium (50-500)'
                    elif any(word in snippet for word in ['large', '500+', 'enterprise']):
                        result['size'] = 'Large (500+)'

                    # Try to detect industry
                    industries = ['fintech', 'healthtech', 'ai', 'saas', 'e-commerce', 'consulting']
                    for ind in industries:
                        if ind in snippet:
                            result['industry'] = ind.title()
                            break

                # Tech stack search
                tech_results = list(ddgs.text(
                    f"{company_name} tech stack engineering blog careers",
                    max_results=3
                ))

                common_techs = ['python', 'react', 'aws', 'kubernetes', 'tensorflow',
                               'pytorch', 'postgres', 'redis', 'kafka', 'docker']

                tech_counter = Counter()
                for r in tech_results:
                    snippet = r.get('body', '').lower()
                    for tech in common_techs:
                        if tech in snippet:
                            tech_counter[tech] += 1

                result['tech_stack'] = [tech for tech, _ in tech_counter.most_common(5)]

                # Recent news
                news_results = list(ddgs.text(
                    f"{company_name} news funding hiring 2026",
                    max_results=2
                ))

                result['recent_news'] = [
                    {'title': r.get('title', ''), 'url': r.get('href', '')}
                    for r in news_results
                ]
            finally:
                if hasattr(ddgs, 'session'):
                    ddgs.session.close()

            # Cache the result
            cache[company_name] = result
            with open(self.company_cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)

            print(f"  [SKILL] Researched {company_name}: {result['size']}, {result['industry']}", flush=True)
            return result

        except ImportError:
            print(f"  [SKILL] duckduckgo-search not installed, returning minimal data", flush=True)
            return {
                'company': company_name,
                'size': 'Unknown',
                'industry': 'Unknown',
                'tech_stack': [],
                'culture_notes': 'Install duckduckgo-search for company research',
                'recent_news': [],
                'researched_at': datetime.now().isoformat()
            }
        except Exception as e:
            print(f"  [SKILL] Company research failed: {e}", flush=True)
            return {
                'company': company_name,
                'size': 'Unknown',
                'industry': 'Unknown',
                'tech_stack': [],
                'culture_notes': f'Research failed: {str(e)[:100]}',
                'recent_news': [],
                'researched_at': datetime.now().isoformat()
            }

    # ═══════════════════════════════════════════════════════════
    # SKILL 2 — Keyword Density Analyzer
    # ═══════════════════════════════════════════════════════════

    def keyword_density_analyzer(
        self,
        resume_text: str,
        jd_text: str,
        job: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyze keyword density between resume and JD.
        Pure Python implementation without Claude.

        Args:
            resume_text: Full text of the tailored resume.
            jd_text: Job description text (raw_description field).
            job: Full job dict — used as fallback when jd_text is empty.
        """
        print(f"  [SKILL] Analyzing keyword density", flush=True)

        # Always augment jd_text from all available job fields
        if job:
            all_desc_parts = []
            if jd_text:
                all_desc_parts.append(jd_text)
            for field in ('raw_description', 'description', 'job_description', 'body',
                          'short_description', 'full_description'):
                val = (job.get(field) or '').strip()
                if val and val not in all_desc_parts:
                    all_desc_parts.append(val)
            req = job.get('required_skills') or []
            if isinstance(req, list) and req:
                skills_str = ' '.join(req)
                if skills_str not in all_desc_parts:
                    all_desc_parts.append(skills_str)
            resp = job.get('responsibilities') or []
            if isinstance(resp, list) and resp:
                resp_str = ' '.join(resp)
                if resp_str not in all_desc_parts:
                    all_desc_parts.append(resp_str)
            title = (job.get('title') or '').strip()
            if title and title not in all_desc_parts:
                all_desc_parts.append(title)
            jd_text = ' '.join(all_desc_parts)

        # Debug: show exactly what text is being analysed
        print(
            f"  [SKILL] JD text: {len(jd_text)} chars | Resume: {len(resume_text)} chars",
            flush=True
        )
        if jd_text:
            print(f"  [SKILL] JD preview: {jd_text[:200]!r}", flush=True)

        if not jd_text:
            print(
                f"  [SKILL] WARNING: job description is empty — keyword analysis skipped",
                flush=True
            )
            return {
                'match_pct': 0.0,
                'total_keywords_analyzed': 0,
                'present_keywords': [],
                'missing_keywords': [],
                'suggestions': []
            }

        # Common stopwords to exclude
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                    'of', 'with', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has',
                    'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
                    'might', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he',
                    'she', 'it', 'we', 'they', 'them', 'their', 'our', 'your'}

        # Extract keywords from JD (2-3 word phrases + single words)
        jd_lower = jd_text.lower()
        resume_lower = resume_text.lower()

        # Extract multi-word phrases (2-3 words)
        jd_phrases = []
        words = re.findall(r'\b\w+\b', jd_lower)

        for i in range(len(words) - 2):
            # 2-word phrases
            if words[i] not in stopwords or words[i+1] not in stopwords:
                phrase = f"{words[i]} {words[i+1]}"
                jd_phrases.append(phrase)

            # 3-word phrases
            if i < len(words) - 2:
                if any(w not in stopwords for w in [words[i], words[i+1], words[i+2]]):
                    phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
                    jd_phrases.append(phrase)

        # Count phrase frequencies in JD
        phrase_counter = Counter(jd_phrases)

        # Get single technical keywords
        single_words = [w for w in words if w not in stopwords and len(w) > 3]
        word_counter = Counter(single_words)

        # Combine and get top keywords
        all_keywords = []

        # Top phrases (appear 2+ times)
        for phrase, count in phrase_counter.most_common(30):
            if count >= 2:
                all_keywords.append((phrase, count))

        # Top single words
        for word, count in word_counter.most_common(20):
            if count >= 2:
                all_keywords.append((word, count))

        # Sort by frequency
        all_keywords.sort(key=lambda x: x[1], reverse=True)

        # Check which are present in resume
        present_keywords = []
        missing_keywords = []

        for keyword, count in all_keywords[:30]:
            if keyword in resume_lower:
                present_keywords.append(keyword)
            else:
                missing_keywords.append({'keyword': keyword, 'jd_frequency': count})

        # Calculate match percentage
        total_keywords = len(present_keywords) + len(missing_keywords)
        match_pct = (len(present_keywords) / total_keywords * 100) if total_keywords > 0 else 0

        result = {
            'match_pct': round(match_pct, 1),
            'total_keywords_analyzed': total_keywords,
            'present_keywords': present_keywords[:20],
            'missing_keywords': missing_keywords[:10],
            'suggestions': [
                f"Add '{kw['keyword']}' (appears {kw['jd_frequency']}x in JD)"
                for kw in missing_keywords[:5]
            ]
        }

        print(f"  [SKILL] Keyword match: {match_pct:.1f}% ({len(present_keywords)}/{total_keywords})", flush=True)
        return result

    # ═══════════════════════════════════════════════════════════
    # SKILL 3 — Application Memory
    # ═══════════════════════════════════════════════════════════

    def application_memory(self, action: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Simple JSON-based memory store for application tracking.

        Actions:
            - store: Save application result
            - retrieve: Get applications by company
            - get_stats: Get statistics
            - get_winning_patterns: Analyze successful applications
        """
        with open(self.memory_path, 'r') as f:
            memory = json.load(f)

        if action == 'store':
            if not data:
                return {'error': 'No data provided'}

            memory['applications'].append({
                'job_hash': data.get('job_hash'),
                'company': data.get('company'),
                'role': data.get('role'),
                'outcome': data.get('outcome', 'applied'),
                'score': data.get('score'),
                'applied_at': datetime.now().isoformat(),
                'responded_at': data.get('responded_at'),
                'notes': data.get('notes', '')
            })

            # Update stats
            memory['stats']['total_applied'] = len(memory['applications'])
            responses = [a for a in memory['applications'] if a.get('responded_at')]
            memory['stats']['total_responses'] = len(responses)
            memory['stats']['response_rate'] = (
                len(responses) / len(memory['applications']) * 100
                if memory['applications'] else 0.0
            )

            with open(self.memory_path, 'w') as f:
                json.dump(memory, f, indent=2)

            print(f"  [SKILL] Stored application: {data.get('company')} - {data.get('role')}", flush=True)
            return {'success': True, 'total_applications': len(memory['applications'])}

        elif action == 'retrieve':
            company = data.get('company', '') if data else ''
            apps = [a for a in memory['applications'] if a.get('company') == company]
            print(f"  [SKILL] Retrieved {len(apps)} applications for {company}", flush=True)
            return {'company': company, 'applications': apps}

        elif action == 'get_stats':
            print(f"  [SKILL] Stats: {memory['stats']['total_applied']} applied, "
                  f"{memory['stats']['response_rate']:.1f}% response rate", flush=True)
            return memory['stats']

        elif action == 'get_winning_patterns':
            # Analyze successful applications
            responses = [a for a in memory['applications'] if a.get('responded_at')]

            if not responses:
                return {'patterns': [], 'message': 'No responses yet to analyze'}

            # Group by company
            company_counts = Counter(a.get('company') for a in responses)

            # Group by role keywords
            role_keywords = []
            for app in responses:
                role = app.get('role', '').lower()
                if 'ml' in role or 'machine learning' in role:
                    role_keywords.append('ML')
                elif 'ai' in role or 'artificial intelligence' in role:
                    role_keywords.append('AI')
                elif 'data' in role:
                    role_keywords.append('Data')
                elif 'engineer' in role:
                    role_keywords.append('Engineering')

            role_counts = Counter(role_keywords)

            # Average score of responding jobs
            avg_score = sum(a.get('score', 0) for a in responses) / len(responses)

            patterns = {
                'top_companies': company_counts.most_common(5),
                'top_role_types': role_counts.most_common(3),
                'avg_score_of_responses': round(avg_score, 1),
                'total_responses': len(responses),
                'response_rate': memory['stats']['response_rate']
            }

            print(f"  [SKILL] Winning patterns: {patterns['top_role_types']}", flush=True)
            return patterns

        else:
            return {'error': f'Unknown action: {action}'}

    # ═══════════════════════════════════════════════════════════
    # SKILL 4 — Salary Benchmarker
    # ═══════════════════════════════════════════════════════════

    def salary_benchmarker(self, role: str, location: str) -> Dict[str, Any]:
        """
        Search for salary data and cache results.
        """
        print(f"  [SKILL] Benchmarking salary for {role} in {location}", flush=True)

        cache_key = f"{role}_{location}".lower().replace(' ', '_')

        # Check cache
        if self.salary_cache_path.exists():
            with open(self.salary_cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)
                if cache_key in cache:
                    cached = cache[cache_key]
                    # Check if cache is recent (within 30 days)
                    cached_date = datetime.fromisoformat(cached.get('cached_at', '2020-01-01'))
                    age_days = (datetime.now() - cached_date).days
                    if age_days < 30:
                        print(f"  [SKILL] Using cached salary data (age: {age_days} days)", flush=True)
                        return cached
        else:
            cache = {}

        # Search for salary data
        try:
            from ddgs import DDGS

            query = f"{role} salary {location} 2026 site:glassdoor.com OR site:seek.com.au OR site:levels.fyi"

            ddgs = DDGS()
            try:
                results = list(ddgs.text(query, max_results=5))
            finally:
                if hasattr(ddgs, 'session'):
                    ddgs.session.close()

            # Try to extract salary numbers from results
            salary_numbers = []
            for r in results:
                text = r.get('body', '')
                # Look for patterns like "$80,000", "$80k", "80000"
                numbers = re.findall(r'\$?(\d{2,3})[,k]?(\d{3})?', text)
                for match in numbers:
                    if match[0]:
                        num = int(match[0]) * 1000
                        if match[1]:
                            num += int(match[1])
                        if 30000 <= num <= 300000:  # Reasonable salary range
                            salary_numbers.append(num)

            if salary_numbers:
                salary_numbers.sort()
                result = {
                    'role': role,
                    'location': location,
                    'min_salary': salary_numbers[0],
                    'max_salary': salary_numbers[-1],
                    'median_salary': salary_numbers[len(salary_numbers) // 2],
                    'source': 'DuckDuckGo aggregated',
                    'sample_size': len(salary_numbers),
                    'cached_at': datetime.now().isoformat()
                }
            else:
                # No data found, return estimates
                result = {
                    'role': role,
                    'location': location,
                    'min_salary': 80000,
                    'max_salary': 120000,
                    'median_salary': 100000,
                    'source': 'Estimated (no data found)',
                    'sample_size': 0,
                    'cached_at': datetime.now().isoformat()
                }

            # Cache the result
            cache[cache_key] = result
            with open(self.salary_cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=2)

            print(f"  [SKILL] Salary range: ${result['min_salary']:,} - ${result['max_salary']:,}", flush=True)
            return result

        except ImportError:
            print(f"  [SKILL] duckduckgo-search not installed, returning estimates", flush=True)
            return {
                'role': role,
                'location': location,
                'min_salary': 80000,
                'max_salary': 120000,
                'median_salary': 100000,
                'source': 'Estimated (install duckduckgo-search)',
                'sample_size': 0,
                'cached_at': datetime.now().isoformat()
            }
        except Exception as e:
            print(f"  [SKILL] Salary benchmarking failed: {e}", flush=True)
            return {
                'role': role,
                'location': location,
                'min_salary': None,
                'max_salary': None,
                'median_salary': None,
                'source': f'Error: {str(e)[:100]}',
                'sample_size': 0,
                'cached_at': datetime.now().isoformat()
            }

    # ═══════════════════════════════════════════════════════════
    # SKILL 5 — Duplicate Checker
    # ═══════════════════════════════════════════════════════════

    def duplicate_checker(self, job_hash: str) -> bool:
        """
        Check if we've already applied to this job.
        Returns True if duplicate (already applied).
        """
        with open(self.memory_path, 'r') as f:
            memory = json.load(f)

        applied_hashes = [a.get('job_hash') for a in memory['applications']]
        is_duplicate = job_hash in applied_hashes

        if is_duplicate:
            print(f"  [SKILL] Duplicate detected: {job_hash} (already applied)", flush=True)
        else:
            print(f"  [SKILL] No duplicate: {job_hash} (not yet applied)", flush=True)

        return is_duplicate


def main():
    """Test skill registry."""
    registry = SkillRegistry()

    print("\n" + "="*80)
    print("TESTING SKILL REGISTRY")
    print("="*80)

    # Test 1: Keyword analyzer
    print("\n[TEST 1] Keyword Density Analyzer")
    print("-"*80)
    resume = """
    I have experience with Python, machine learning, and TensorFlow.
    Built RAG systems using LangChain and deployed with FastAPI.
    """
    jd = """
    We need a Python engineer with machine learning experience.
    Must know PyTorch, RAG, and have deployed production systems.
    LangChain and vector databases are a plus.
    """
    result = registry.keyword_density_analyzer(resume, jd)
    print(f"Match: {result['match_pct']}%")
    print(f"Missing: {[k['keyword'] for k in result['missing_keywords'][:3]]}")

    # Test 2: Application memory
    print("\n[TEST 2] Application Memory")
    print("-"*80)

    registry.application_memory('store', {
        'job_hash': 'test123',
        'company': 'Test Co',
        'role': 'ML Engineer',
        'outcome': 'applied',
        'score': 85
    })

    stats = registry.application_memory('get_stats')
    print(f"Total applications: {stats['total_applied']}")

    # Test 3: Duplicate checker
    print("\n[TEST 3] Duplicate Checker")
    print("-"*80)
    is_dup = registry.duplicate_checker('test123')
    print(f"Is duplicate: {is_dup}")

    is_dup2 = registry.duplicate_checker('new_job_456')
    print(f"Is duplicate: {is_dup2}")

    # Test 4: Company researcher (will fail gracefully if no internet)
    print("\n[TEST 4] Company Researcher")
    print("-"*80)
    company_data = registry.company_researcher('Atlassian')
    print(f"Company: {company_data['company']}")
    print(f"Size: {company_data['size']}")
    print(f"Industry: {company_data['industry']}")

    # Test 5: Salary benchmarker
    print("\n[TEST 5] Salary Benchmarker")
    print("-"*80)
    salary_data = registry.salary_benchmarker('AI Engineer', 'Sydney')
    print(f"Median salary: ${salary_data['median_salary']:,}")
    print(f"Source: {salary_data['source']}")

    print("\n" + "="*80)
    print("ALL SKILLS TESTED")
    print("="*80)


if __name__ == "__main__":
    main()
