"""Generate docs/TOOLS.md (every tool group and action with its parameters) from the live registry.

    python tools/gen_tool_docs.py > docs/TOOLS.md
"""

import importlib

from scratch_mcp import registry
from scratch_mcp.server import GROUP_MODULES

for m in GROUP_MODULES:
    importlib.import_module(f"scratch_mcp.groups.{m}")

print("# Tool reference\n")
print("Generated from the running server by `tools/gen_tool_docs.py` - do not edit by hand. Call a tool with "
      "`action=<name>` and `args={...}`; `action=\"help\"` returns the exact JSON schema of any action. "
      "Parameters marked * are required.\n")
total = 0
for group, actions in registry.GROUPS.items():
    print(f"## {group}\n")
    print(registry.GROUP_DOCS[group] + "\n")
    for act in actions.values():
        total += 1
        print(f"### {group}.{act.name}\n")
        print((act.summary or "(no description)") + "\n")
        if act.params:
            print("| parameter | type | description |\n| --- | --- | --- |")
            esc = lambda x: x.replace("|", "\\|")  # noqa: E731
            for n, t, req, d in act.params:
                print(f"| `{n}`{'*' if req else ''} | {esc(t)} | {esc(d)} |")
            print()
print(f"\n_{len(registry.GROUPS)} tools, {total} actions._")
