"""The project explainer: a lecture-handout page Claude writes once into the vault (660)."""

# The page's 9 sections, in order: the Explainer tab (661) and Obsidian show them as they are.
SECTIONS = (
    "In one sentence",
    "The problem",
    "Big picture",
    "Stages",
    "Key ideas",
    "Results",
    "Weak spots",
    "How to run",
    "Glossary",
)
# The stages of each `type:` in project.md.
STAGES = {
    "ml": ("data", "windows / prep", "features", "split", "models", "shrink", "on the device"),
    "app": ("user", "screens", "API", "data"),
    "robotics": ("sensors", "nodes and topics", "control", "actuators"),
    "report": ("goal", "method", "results", "conclusion"),
}
KINDS = {
    "ml": "ML / embedded",
    "app": "app / web",
    "robotics": "robotics / ROS",
    "report": "school report / TP",
}
HEAD = "Write the explainer of project"  # FakeChat knows the explainer turn by it
TYPE_LINE = "type: "  # the first line of the answer when project.md has no `type:`


def _stages(kind: str) -> str:
    extra = " Give one flow per main feature." if kind == "app" else ""
    return f"{kind} ({KINDS[kind]}): " + " → ".join(STAGES[kind]) + "." + extra


def prompt(name: str, kind: str | None) -> str:
    """The fixed explainer prompt. `kind` None: Claude picks the type and says which first."""
    if kind is None:
        stages = [
            f"project.md has no `type:`. Pick the type that fits best and make the very first "
            f"line of your answer `{TYPE_LINE}<type>` (one of {', '.join(STAGES)}), then the page. "
            "The Stages section follows the stages of that type:",
            *(f"- {_stages(k)}" for k in STAGES),
        ]
    else:
        stages = [f"The Stages section follows these stages: {_stages(kind)}"]
    return "\n".join(
        [
            f"{HEAD} {name}: a page that teaches it like a lecture handout, for someone who "
            "knows programming but not this project. Read the README, the code and the code "
            "graph if there is one. Only read: write no file and run nothing else.",
            "",
            "Answer with the page only, as plain markdown (no frontmatter, no preamble), with "
            "exactly these `## ` headings, in this order:",
            *(f"{i}. {s}" for i, s in enumerate(SECTIONS, 1)),
            "",
            *stages,
            "",
            "In the Stages section, after a short paragraph per stage, put one fenced block:",
            "```stages",
            "<stage name> | <what goes in> | <what comes out> | <its numbers> | <its files>",
            "```",
            "one line per stage. Under In one sentence, put the 3 or 4 numbers that matter most:",
            "```kpis",
            "<value> | <label>",
            "```",
            "Under Results, the results worth comparing as bars (value: a plain number):",
            "```bars",
            "<label> | <value>",
            "```",
            "",
            "Rules: plain words, short sentences, explain every term once (in the Glossary too). "
            "Every number comes from the README or the code: never invent, round or guess one; "
            "leave a number out when you cannot find it. File, function and command names go in "
            "inline code, e.g. `split.py` or `main()`. Weak spots: what is missing, fragile or "
            "untested, from the code. How to run: the real commands from the README.",
        ]
    )
