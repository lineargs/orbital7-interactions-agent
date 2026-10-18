# ==========================================
# 1. Tool declarations (what the model sees)
# ==========================================
# Descriptions say what each tool does and what it needs.
# They never say in which order to use them: working that out is the agent's job.

TOOL_DECLARATIONS = [
    {
        "type": "function",
        "name": "get_station_status",
        "description": "Station-wide dashboard from the telemetry array. Cheap overview, but the array needs power to give live data.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "run_diagnostic",
        "description": "Reads one subsystem directly from its local sensors, on battery power. Accurate even when telemetry is down.",
        "parameters": {
            "type": "object",
            "properties": {
                "subsystem": {"type": "string", "enum": ["reactor", "power", "life_support", "comms"]},
            },
            "required": ["subsystem"],
        },
    },
    {
        "type": "function",
        "name": "vent_coolant",
        "description": "Releases coolant through one of two independent valves to lower the reactor core temperature. Coolant is limited.",
        "parameters": {
            "type": "object",
            "properties": {
                "valve": {"type": "string", "enum": ["A", "B"]},
            },
            "required": ["valve"],
        },
    },
    {
        "type": "function",
        "name": "set_sector_power",
        "description": (
            "Sets the power allocation for one sector. Works while the bus is down (it changes the saved configuration). "
            "Sectors: life_support (oxygen scrubbers), comms (telemetry array), "
            "hydroponics (algae farm; the algae freeze if left unpowered for too long), research_labs (non-critical)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sector": {"type": "string", "enum": ["life_support", "comms", "hydroponics", "research_labs"]},
                "megawatts": {"type": "integer", "minimum": 0, "maximum": 60},
            },
            "required": ["sector", "megawatts"],
        },
    },
    {
        "type": "function",
        "name": "restart_power_bus",
        "description": "Attempts to re-energise the main power bus using the saved sector configuration.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "restart_life_support",
        "description": "Attempts to start the oxygen scrubbers.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "escalate_to_human",
        "description": "Hands the incident to ground control. Use when there is no safe way to continue.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]

TOOL_NAMES = {tool["name"] for tool in TOOL_DECLARATIONS}


# ==========================================
# 2. Tool execution (what actually runs)
# ==========================================

def execute_tool(station, name, arguments):
    """Runs one tool against the station. Returns (output_text, is_error).

    Errors are returned to the model instead of crashing the script,
    so the agent can read what went wrong and adapt.
    """
    if name not in TOOL_NAMES:
        return f"Unknown tool '{name}'.", True
    try:
        output = getattr(station, name)(**(arguments or {}))
        return output, output.startswith(("STATION LOST", "SESSION CLOSED"))
    except (ValueError, RuntimeError, TypeError) as error:
        return f"ERROR: {error}", True
