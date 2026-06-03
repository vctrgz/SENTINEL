# Skill: command_classification

## Description
Classify commands into execution categories.

---

## Capabilities
- Identify command type (filesystem, network, package, etc.)
- Map commands to executor types

---

## How to Think
- Focus on WHAT the command does
- Ignore syntax complexity
- Use categories, not exact matching

---

## Rules
- MUST classify every command
- DO NOT leave commands unclassified

---

## When to Use
- Before routing commands

---

## Output Format
{
  "commands": [
    {
      "cmd": "string",
      "type": "filesystem|network|package|system|other"
    }
  ]
}