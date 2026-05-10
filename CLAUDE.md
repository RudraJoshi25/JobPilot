# Job Agent — Project Constitution

## Architecture
- All writing agents use claude-opus-4-5
- All routing/utility agents use claude-haiku-4-5-20251001
- Never switch models without checking rate limits first
- Pipeline entry: main.py

## Agent Roles
- master_agent: ReAct orchestration (Haiku)
- resume_agent_latex.py: LaTeX tailoring (Opus)
- cover_letter_agent.py: Critic-Actor writing (Opus)
- strategic_agent.py: Role targeting (Opus)
- matching_agent.py: JD scoring (Haiku)

## Rules
- Never hardcode "claude-sonnet-4-5" — Sonnet has 30K/min limit
- Always run on .venv
- Output goes to output/ folder