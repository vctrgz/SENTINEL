import re
from utils.prompt_loader import load_file


def extract_skills(agent_md_path: str) -> list:
    """
    Extrae skills desde la sección '## Skills' de AGENTS.md
    """

    content = load_file(agent_md_path)

    # buscar sección Skills
    skills_section = re.search(r"## Skills(.*?)##", content, re.DOTALL)

    if not skills_section:
        # si es la última sección
        skills_section = re.search(r"## Skills(.*)", content, re.DOTALL)

    if not skills_section:
        return []

    skills_block = skills_section.group(1)

    # extraer líneas tipo "- skill_name"
    skills = re.findall(r"-\s*([a-zA-Z0-9_]+)", skills_block)

    return skills