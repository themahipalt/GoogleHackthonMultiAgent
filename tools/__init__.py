"""
Assembles Gemini Tool objects and the unified dispatch_tool() function
by merging schemas and handlers from each domain module.

JSON Schema → google.genai.types.Tool conversion happens here so that
each tool file stays framework-agnostic (plain dicts).
"""
from google.genai import types as genai_types
from tools import task_tools, calendar_tools, notes_tools

# ── Collect raw schemas from every tool module ────────────────────────────────
_ALL_SCHEMAS: list[dict] = (
    task_tools.SCHEMAS
    + calendar_tools.SCHEMAS
    + notes_tools.SCHEMAS
)

# ── Merged handler registry ───────────────────────────────────────────────────
_HANDLERS: dict = {
    **task_tools.HANDLERS,
    **calendar_tools.HANDLERS,
    **notes_tools.HANDLERS,
}


# ── JSON Schema → google.genai.types.Schema converter ────────────────────────
_TYPE_MAP = {
    "string":  genai_types.Type.STRING,
    "integer": genai_types.Type.INTEGER,
    "number":  genai_types.Type.NUMBER,
    "boolean": genai_types.Type.BOOLEAN,
    "object":  genai_types.Type.OBJECT,
    "array":   genai_types.Type.ARRAY,
}


def _to_schema(s: dict) -> genai_types.Schema:
    """Recursively convert a JSON Schema dict to a genai Schema object.

    google.genai requires its own typed Schema objects rather than raw dicts.
    This function walks the JSON Schema tree depth-first: leaf types (string,
    integer, …) terminate immediately; object types recurse into their
    properties so nested objects are fully converted.
    """
    t = _TYPE_MAP.get(s.get("type", "string").lower(), genai_types.Type.STRING)
    kwargs: dict = {"type": t}

    if desc := s.get("description"):
        kwargs["description"] = desc
    if enum := s.get("enum"):
        kwargs["enum"] = enum
    # Recurse into nested object properties so sub-schemas are also converted
    if props := s.get("properties"):
        kwargs["properties"] = {k: _to_schema(v) for k, v in props.items()}
    if required := s.get("required"):
        kwargs["required"] = required

    return genai_types.Schema(**kwargs)


def _to_function_declaration(tool: dict) -> genai_types.FunctionDeclaration:
    return genai_types.FunctionDeclaration(
        name=tool["name"],
        description=tool["description"],
        parameters=_to_schema(tool["input_schema"]),
    )


# ── GEMINI_TOOLS — passed to client.chats.create(config=...) ─────────────────
# All function declarations are wrapped in a single Tool object. Gemini expects
# a list[Tool], where each Tool groups related declarations; here we use one
# Tool for all sub-agents so the orchestrator can call any of them freely.
GEMINI_TOOLS: list[genai_types.Tool] = [
    genai_types.Tool(
        function_declarations=[_to_function_declaration(s) for s in _ALL_SCHEMAS]
    )
]


# ── Dispatcher ────────────────────────────────────────────────────────────────
async def dispatch_tool(name: str, inputs: dict, user_id: str) -> dict:
    """Route a Gemini function_call to the correct domain handler."""
    handler = _HANDLERS.get(name)
    if not handler:
        return {"error": f"Unknown tool: {name}"}
    return handler(inputs, user_id)


__all__ = ["GEMINI_TOOLS", "dispatch_tool"]
