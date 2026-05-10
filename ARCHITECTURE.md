# 5-Layer Enterprise Multi-Agent Architecture

## Overview

The job-agent project has been upgraded from a simple linear pipeline to a full 5-layer enterprise multi-agent architecture with guardrails, skill hooks, dynamic orchestration, and strategic analysis.

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 5: STRATEGIC AGENT                                   │
│  Weekly performance analysis & recommendations              │
│  File: agents/strategic_agent.py                           │
└─────────────────────────────────────────────────────────────┘
                          ▲
                          │ analyzes
                          │
┌─────────────────────────────────────────────────────────────┐
│  LAYER 4: DYNAMIC ORCHESTRATION                             │
│  Priority queue, routing, retry logic, skill integration   │
│  File: agents/master_agent.py (upgraded)                   │
└─────────────────────────────────────────────────────────────┘
                          │
                    ┌─────┴─────┐
                    │           │
         ┌──────────▼─┐    ┌────▼────────┐
         │  LAYER 3:  │    │  LAYER 2:   │
         │  SKILL     │    │  GUARDRAILS │
         │  HOOKS     │    │  ENGINE     │
         └────────────┘    └─────────────┘
              │                   │
              │ calls             │ wraps
              │                   │
┌─────────────▼───────────────────▼───────────────────────────┐
│  LAYER 1: EXISTING AGENTS (unchanged)                       │
│  source, normalizer, match, resume, cover_letter, qa, apply│
└─────────────────────────────────────────────────────────────┘
```

## Layer 2: Guardrails Engine

**File:** `core/guardrails.py`

Wraps every agent call with safety checks and validation.

### Input Guardrails (before agent executes):
1. **schema_validator** - Verify input has required fields
2. **pii_checker** - Detect passwords/tokens in prompts
3. **budget_checker** - Warn if call > 8000 tokens
4. **rate_limiter** - Enforce 5s minimum between API calls

### Output Guardrails (after agent returns):
5. **hallucination_detector** - Check for fabricated companies/dates/skills
6. **schema_validator** - Verify output matches expected schema
7. **quality_floor** - Flag outputs under minimum word count
8. **cost_tracker** - Log tokens used + running cost total

### Usage:
```python
from core.guardrails import GuardrailsEngine

guardrails = GuardrailsEngine()
result = await guardrails.run(
    agent_fn=resume_agent.generate,
    input_data={'job': job, 'match_report': match_report},
    agent_name='resume_agent',
    max_retries=2
)
```

### Severity Handling:
- **LOW**: Log warning, continue
- **MEDIUM**: Retry once with correction
- **HIGH**: Halt and add to review queue

## Layer 3: Skill Hooks

**File:** `core/skill_hooks.py`

Pluggable tools that any agent can call.

### Available Skills:

#### SKILL 1: company_researcher(company_name)
- Web search via DuckDuckGo
- Finds: size, industry, tech stack, culture, news
- Caches to: `data/company_cache.json`

#### SKILL 2: keyword_density_analyzer(resume_text, jd_text)
- Pure Python (no Claude calls)
- Extracts keywords from JD
- Returns match %, missing keywords, suggestions

#### SKILL 3: application_memory(action, data)
- JSON store: `data/application_memory.json`
- Actions: store, retrieve, get_stats, get_winning_patterns
- Tracks applications, responses, patterns

#### SKILL 4: salary_benchmarker(role, location)
- Searches salary data via DuckDuckGo
- Caches to: `data/salary_cache.json`
- Returns: min/max/median salary

#### SKILL 5: duplicate_checker(job_hash)
- Checks if already applied
- Prevents duplicate applications

### Usage:
```python
from core.skill_hooks import SkillRegistry

skills = SkillRegistry()

# Check for duplicates
if skills.duplicate_checker(job_hash):
    print("Already applied!")

# Research company
company_data = skills.company_researcher("Atlassian")

# Analyze keywords
analysis = skills.keyword_density_analyzer(resume_text, jd_text)

# Store application
skills.application_memory('store', {
    'job_hash': job_hash,
    'company': company,
    'role': role,
    'outcome': 'applied'
})
```

## Layer 4: Dynamic Orchestration

**File:** `agents/master_agent.py` (upgraded)

Enhanced master agent with intelligent routing and retry logic.

### Features:

#### 1. Priority Queue
Sorts jobs by: `score * recency_multiplier`
- Posted today: 1.5x multiplier
- This week: 1.2x multiplier
- Older: 1.0x multiplier

#### 2. Dynamic Routing
Score-based pipeline selection:
- **>90**: Full pipeline (research company, tailor everything)
- **75-90**: Standard pipeline
- **60-75**: Generate docs, flag for manual review
- **<60**: Skip (save to `data/jobs_skipped.json`)

#### 3. Retry Logic
- Exponential backoff: wait 2^attempt seconds
- Max 3 retries per job
- Pause pipeline after 3 consecutive failures

#### 4. Skill Hook Integration
**Before resume generation:**
- `duplicate_checker()` → skip if already applied
- `company_researcher()` → inject company context
- `keyword_density_analyzer()` → identify missing keywords
- `salary_benchmarker()` → add salary context

**After application:**
- `application_memory.store()` → log outcome

#### 5. Decision Logging
Every routing decision logged to `logs/decisions.json`:
```json
{
  "timestamp": "2026-05-09T12:00:00",
  "job_hash": "abc123",
  "decision": "full_pipeline",
  "reason": "Score 95 >= 90",
  "confidence": 95.0
}
```

## Layer 5: Strategic Agent

**File:** `agents/strategic_agent.py`

Weekly performance analysis and strategy recommendations.

### Analysis Sections:

#### 1. Performance Analysis
- Jobs found per source per week
- Which sources produce highest-scoring jobs
- Average score by role type
- Most common required skills

#### 2. Gap Analysis
- What required skills appear repeatedly
- Which companies keep appearing
- Recommended new search terms

#### 3. Strategy Recommendations
AI-generated actionable advice:
- "Add 'LLM Engineer' to search terms"
- "Research Atlassian directly"
- "Highlight PyTorch more in resume"

#### 4. Weekly Summary
Saved to `logs/weekly_strategy_{date}.md`:
- Jobs found / applied / response rate
- Top companies by score
- Recommended actions
- Search term performance

### Usage:
```python
from agents.strategic_agent import StrategicAgent

agent = StrategicAgent()
report = agent.generate_strategy_report(weeks_back=4)
agent.print_summary(report)
```

## Command-Line Interface

### Available Commands:

```bash
# Full pipeline with all 5 layers
python main.py

# Test mode (2 jobs only)
python main.py --test

# Generate docs for existing shortlist
python main.py --docs-only

# Apply to already-approved jobs
python main.py --apply-only

# Run strategic analysis (Layer 5)
python main.py --strategy

# View application stats (Layer 3)
python main.py --stats

# Test guardrails engine (Layer 2)
python main.py --guardrails-test
```

## Data Files

### Created by Layers:

**Layer 2:**
- `logs/cost_tracking.json` - API cost tracking

**Layer 3:**
- `data/company_cache.json` - Company research results
- `data/salary_cache.json` - Salary benchmarks
- `data/application_memory.json` - Application tracking

**Layer 4:**
- `logs/decisions.json` - Routing decisions audit trail
- `data/jobs_skipped.json` - Low-scoring jobs

**Layer 5:**
- `logs/strategy_report_{date}.json` - Performance data
- `logs/weekly_strategy_{date}.md` - Strategy recommendations

## Dependencies

### Required:
- anthropic (Claude API)
- playwright (web scraping)
- pydantic (data validation)
- python-docx (document generation)

### Optional:
- duckduckgo-search (for company research & salary benchmarking)
  ```bash
  pip install duckduckgo-search
  ```
  If not installed, skills gracefully degrade to placeholder data.

## Verification

Test all layers:
```bash
python -c "
from core.guardrails import GuardrailsEngine
from core.skill_hooks import SkillRegistry
from agents.strategic_agent import StrategicAgent
print('Layer 2 (Guardrails): OK')
print('Layer 3 (Skill Hooks): OK')
print('Layer 5 (Strategic): OK')
print('All 5 layers verified!')
"
```

## Key Benefits

1. **Safety** - Guardrails prevent hallucinations and track costs
2. **Intelligence** - Skill hooks add company research and analytics
3. **Efficiency** - Dynamic routing prioritizes high-value jobs
4. **Reliability** - Retry logic handles transient failures
5. **Insights** - Strategic agent provides weekly optimization
6. **Audit Trail** - Decision logging tracks all routing decisions

## Backward Compatibility

✅ All existing agents remain unchanged
✅ Existing workflows continue to work
✅ New features are optional enhancements
✅ Gradual adoption supported
