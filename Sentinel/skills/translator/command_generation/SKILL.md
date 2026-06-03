# Skill: command_generation

## Description
Convert structured tasks into precise and executable shell commands.

---

## Capabilities
- Translate task descriptions into valid shell commands
- Use the native tools and conventions of the detected OS
- Generate minimal and efficient commands

---

## How to Think
- Focus on HOW to execute the task
- Prefer simple commands over complex pipelines
- Use widely available tools
- Avoid unnecessary flags

---

## Rules
- Commands MUST be executable
- Commands MUST match the detected OS family: Windows, Linux, macOS, FreeBSD, or Android
- DO NOT include explanations
- DO NOT chain commands unless necessary
- DO NOT assume unavailable tools

---

## When to Use
- When converting tasks into commands

---

## When NOT to Use
- When analyzing errors
- When validating risk

---

## Output Expectations
- A list of shell commands

---

## Output Format
{
  "commands": [
    {
      "cmd": "string",
      "risk": "low|medium|high"
    }
  ]
}

---

## Failure Modes
- Invalid command syntax
- Overcomplicated commands
- Using non-installed tools

---

## Examples

### Input
"listar archivos"

### Output
{
  "commands": [
    {"cmd": "ls", "risk": "low"}
  ]
}
