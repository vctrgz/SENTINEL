import json
import re


def _extract_markdown_block(text: str) -> str | None:
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    return match.group(1).strip() if match else None


def _extract_balanced_json(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    return None


def _remove_trailing_commas(candidate: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", candidate)


def _escape_invalid_backslashes(candidate: str) -> str:
    valid_escapes = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0

    while index < len(candidate):
        char = candidate[index]

        if not in_string:
            result.append(char)
            if char == '"':
                in_string = True
            index += 1
            continue

        if escaped:
            result.append(char)
            escaped = False
            index += 1
            continue

        if char == "\\":
            next_char = candidate[index + 1] if index + 1 < len(candidate) else ""
            if next_char in valid_escapes:
                result.append(char)
                escaped = True
            else:
                result.append("\\\\")
            index += 1
            continue

        result.append(char)
        if char == '"':
            in_string = False
        index += 1

    return "".join(result)


def _candidate_variants(candidate: str) -> list[str]:
    stripped = candidate.strip()
    repaired = _escape_invalid_backslashes(_remove_trailing_commas(stripped))
    variants = [stripped]
    if repaired != stripped:
        variants.append(repaired)
    return variants


def safe_json_parse(text: str) -> dict:
    """
    Extrae y parsea JSON de la respuesta del LLM de forma robusta.

    Estrategias:
    1. Parse directo
    2. Bloque markdown ```json
    3. Primer objeto JSON balanceado
    4. Reparacion basica de escapes invalidados por el modelo
    """
    if not text or not isinstance(text, str):
        raise ValueError("El modelo devolvio una respuesta vacia o invalida")

    raw_candidates = [text.strip()]

    markdown_candidate = _extract_markdown_block(text)
    if markdown_candidate:
        raw_candidates.append(markdown_candidate)

    balanced_candidate = _extract_balanced_json(text)
    if balanced_candidate:
        raw_candidates.append(balanced_candidate)

    seen: set[str] = set()
    for raw_candidate in raw_candidates:
        for candidate in _candidate_variants(raw_candidate):
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

    raise ValueError(
        f"No se pudo parsear JSON de la respuesta del modelo.\n"
        f"Respuesta recibida (primeros 300 chars): {text[:300]}"
    )
