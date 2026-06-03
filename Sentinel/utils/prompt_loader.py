"""
utils/prompt_loader.py

Builds the system prompt for an agent by loading its AGENTS.md and the
skills listed in it. Every file read is traced to stdout + logs via
the RuntimeTracer so you can see exactly which .md files are being used.
"""

import os
from utils.file_utils import load_file
from utils.agent_parser import extract_skills
from utils.skill_loader import load_skills
from utils.runtime_tracer import get_tracer


def build_system_prompt(agent_dir: str) -> str:
    """
    Constructs the full system prompt:
      1. Loads AGENTS.md from agent_dir/
      2. Extracts skill names declared in AGENTS.md
      3. Loads each SKILL.md and concatenates
      4. Returns the combined prompt string

    All file reads are logged to stdout and logs/runtime_human.log
    """
    tracer = get_tracer()
    agent_name = os.path.basename(agent_dir)

    agent_md_path = os.path.join(agent_dir, "AGENTS.md")
    tracer.log_agent_md_load(agent_name, agent_md_path)

    agent_md = load_file(agent_md_path)
    if not agent_md:
        tracer.log("system", f"AGENTS.md not found: {agent_md_path}", level="WARN")

    # Extract and load skills
    skills = extract_skills(agent_md_path)
    tracer.log("skill", f"skills_for:{agent_name}", {"skills": skills})

    skills_content = load_skills(skills, agent_name=agent_name)

    system_prompt = f"""
{agent_md}

---

## AVAILABLE SKILLS
{skills_content}

---

## GLOBAL RULES
- ALWAYS return valid JSON when required
- NEVER add explanations unless explicitly requested
- FOLLOW output formats strictly
"""

    return system_prompt.strip()