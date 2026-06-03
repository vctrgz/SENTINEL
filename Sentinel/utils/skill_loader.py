"""
utils/skill_loader.py

Finds and loads SKILL.md files for agents.
Every file read (or miss) is traced to stdout + logs/runtime_human.log.
"""

import os
import glob
from typing import Optional
from utils.file_utils import load_file


SKILLS_PATH = "skills"


def find_skill_file(skill_name: str) -> Optional[str]:
    """
    Recursive search for SKILL.md matching skill_name.

    Priority:
    1. skills/**/skill_name/SKILL.md
    2. skills/**/skill_name.md
    3. skills/skill_name/SKILL.md (direct)
    """
    pattern = os.path.join(SKILLS_PATH, "**", skill_name, "SKILL.md")
    matches = glob.glob(pattern, recursive=True)
    if matches:
        return matches[0]

    pattern2 = os.path.join(SKILLS_PATH, "**", f"{skill_name}.md")
    matches2 = glob.glob(pattern2, recursive=True)
    if matches2:
        return matches2[0]

    direct = os.path.join(SKILLS_PATH, skill_name, "SKILL.md")
    if os.path.exists(direct):
        return direct

    return None


def load_skills(skill_names: list, agent_name: str = "") -> str:
    """
    Load and concatenate SKILL.md content for each skill name.
    Logs each load (found or missing) to the RuntimeTracer.
    """
    # Import here to avoid circular imports at module level
    from utils.runtime_tracer import get_tracer
    tracer = get_tracer()

    if not skill_names:
        return "(No skills defined)"

    skills_content = []

    for skill in skill_names:
        path = find_skill_file(skill)
        if path:
            tracer.log_skill_load(skill, path, agent=agent_name)
            content = load_file(path)
            skills_content.append(f"# Skill: {skill}\n{content}")
        else:
            tracer.log("skill", f"skill_not_found:{skill}", {"agent": agent_name}, level="WARN")
            skills_content.append(f"# Skill: {skill}\n(Skill file not found)")

    return "\n\n".join(skills_content)