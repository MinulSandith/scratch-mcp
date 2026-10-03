"""Static analysis of a project: broken references, dead code, hang risks. Complements validate.py."""

from __future__ import annotations

import json
from typing import Any

from . import schema
from .engine import Graph
from .validate import validate_project

Issue = dict[str, Any]


def _issue(sev: str, sprite: str | None, msg: str, hint: str | None = None, block: str | None = None, code: str = "") -> Issue:
    out: Issue = {"severity": sev, "sprite": sprite, "message": msg}
    if block:
        out["block"] = block
    if hint:
        out["hint"] = hint
    if code:
        out["code"] = code
    return out


def _name(t: dict[str, Any]) -> str:
    return "Stage" if t.get("isStage") else t["name"]


def analyze(project: dict[str, Any], assets: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    r = validate_project(project, assets)
    issues += [_issue("error", None, e, code="structure") for e in r.errors]
    issues += [_issue("warning", None, w, code="structure") for w in r.warnings]

    targets = project["targets"]
    stage = next(t for t in targets if t.get("isStage"))
    sprite_names = {t["name"] for t in targets if not t.get("isStage")}
    backdrops = {c["name"] for c in stage.get("costumes") or []}
    receivers: dict[str, list[tuple[str, str]]] = {}
    senders: dict[str, list[tuple[str, str]]] = {}
    dynamic_send = False
    var_set: set[str] = set()
    var_read: set[str] = set()
    all_vars = {vid: (v[0], _name(t)) for t in targets for vid, v in (t.get("variables") or {}).items()}

    for t in targets:
        who = _name(t)
        g = Graph(project, t)
        blocks = t.get("blocks") or {}
        costumes = {c["name"] for c in t.get("costumes") or []}
        sounds = {s["name"] for s in t.get("sounds") or []}
        procs = g.procedures()
        called: set[str] = set()
        hats_seen: dict[str, str] = {}
        for p in g.validate():
            sev = "info" if "never runs on its own" in p else "error"
            issues.append(_issue(sev, who, p, code="block_rules"))
        for bid, b in blocks.items():
            if isinstance(b, list):
                if len(b) > 2 and b[0] == 12:
                    var_read.add(b[2])
                continue
            op = b.get("opcode", "")
            fields = b.get("fields") or {}
            for inp in (b.get("inputs") or {}).values():
                for v in inp[1:] if isinstance(inp, list) else []:
                    if isinstance(v, list) and len(v) > 2 and v[0] == 12:
                        var_read.add(v[2])
            if op == "data_variable":
                var_read.add((fields.get("VARIABLE") or [None, None])[1])
            if op in ("data_setvariableto", "data_changevariableby"):
                var_set.add((fields.get("VARIABLE") or [None, None])[1])
            if op == "event_whenbroadcastreceived":
                receivers.setdefault((fields.get("BROADCAST_OPTION") or ["?"])[0], []).append((who, bid))
            if op in ("event_broadcast", "event_broadcastandwait"):
                inp = (b.get("inputs") or {}).get("BROADCAST_INPUT")
                if isinstance(inp, list) and len(inp) > 1 and isinstance(inp[1], list) and inp[1][0] == 11:
                    senders.setdefault(inp[1][1], []).append((who, bid))
                else:
                    dynamic_send = True
            if op == "procedures_call":
                called.add((b.get("mutation") or {}).get("proccode", ""))
                if (b.get("mutation") or {}).get("proccode") not in procs:
                    issues.append(_issue("error", who, f"call to undefined custom block '{(b.get('mutation') or {}).get('proccode')}'",
                                         "Define it with script_manager define_procedure or delete this call.", bid, "undefined_procedure"))
            # menu references to things that must exist
            if op == "looks_costume" and not b.get("shadow") is False:
                v = (fields.get("COSTUME") or [None])[0]
                if v is not None and v not in costumes and not t.get("isStage"):
                    issues.append(_issue("error", who, f"switches to costume '{v}' which doesn't exist (has: {sorted(costumes)})",
                                         "Rename the costume or fix the block.", b.get("parent"), "missing_costume"))
            if op == "looks_backdrops":
                v = (fields.get("BACKDROP") or [None])[0]
                if v is not None and v not in backdrops and v not in ("next backdrop", "previous backdrop", "random backdrop"):
                    issues.append(_issue("error", who, f"switches to backdrop '{v}' which doesn't exist (has: {sorted(backdrops)})",
                                         None, b.get("parent"), "missing_backdrop"))
            if op == "sound_sounds_menu":
                v = (fields.get("SOUND_MENU") or [None])[0]
                if v is not None and v not in sounds:
                    issues.append(_issue("error", who, f"plays sound '{v}' which doesn't exist (has: {sorted(sounds)})",
                                         "Add it with sound_manager or fix the name.", b.get("parent"), "missing_sound"))
            if op in ("motion_goto_menu", "motion_glideto_menu", "motion_pointtowards_menu", "sensing_touchingobjectmenu",
                      "event_touchingobjectmenu", "sensing_distancetomenu", "control_create_clone_of_menu", "sensing_of_object_menu"):
                v = next(iter(fields.values()), [None])[0]
                if v and not str(v).startswith("_") and v not in sprite_names:
                    issues.append(_issue("error", who, f"refers to sprite '{v}' which doesn't exist (sprites: {sorted(sprite_names)})",
                                         "Rename/create the sprite or fix the block.", b.get("parent"), "missing_sprite"))
            # empty / pointless loops
            if op in ("control_forever", "control_repeat", "control_repeat_until", "control_if", "control_if_else", "control_while") \
                    and "SUBSTACK" not in (b.get("inputs") or {}) and not b.get("shadow"):
                issues.append(_issue("warning", who, f"'{op}' has nothing inside it", None, bid, "empty_c_block"))
            if op in ("control_wait_until", "control_repeat_until", "control_while") and "CONDITION" not in (b.get("inputs") or {}):
                issues.append(_issue("warning", who, f"'{op}' has an empty condition (it will {'never wait' if op != 'control_wait_until' else 'wait forever'})",
                                     "Fill in a boolean block.", bid, "empty_condition"))
            if b.get("topLevel") and not b.get("shadow"):
                s = schema.spec(op) or {}
                if s.get("shape") == "hat" and op not in ("procedures_definition",):
                    key = op + json.dumps(fields, sort_keys=True) + json.dumps(b.get("inputs") or {}, sort_keys=True)
                    if key in hats_seen and op != "event_whenflagclicked":
                        issues.append(_issue("info", who, f"two scripts start with the same trigger ('{op}'); both will run",
                                             None, bid, "duplicate_hat"))
                    hats_seen[key] = bid
                    if not b.get("next"):
                        issues.append(_issue("info", who, f"script '{op}' has no blocks under it", None, bid, "empty_script"))
                elif s.get("shape") in ("statement", "c", "cap", "reporter", "boolean") and op != "procedures_call":
                    issues.append(_issue("info", who, f"loose '{op}' block isn't attached to a hat, so it never runs",
                                         "Connect it under a hat block (block_manager connect) or delete it.", bid, "orphan_block"))
        # unused custom blocks / hang risks
        for code, p in procs.items():
            if code not in called:
                issues.append(_issue("info", who, f"custom block '{code}' is defined but never called", None, p["definition"], "unused_procedure"))
            if p["warp"]:
                body = g.subtree_ids(p["definition"], include_next=True) if p["definition"] else []
                ops = {blocks[i]["opcode"] for i in body if isinstance(blocks.get(i), dict)}
                if ops & {"control_forever", "control_repeat_until", "control_wait_until", "control_while"}:
                    issues.append(_issue("warning", who, f"custom block '{code}' runs without screen refresh and contains a loop that depends on a condition",
                                         "If the condition never becomes true the project freezes; turn off 'run without screen refresh' or restructure.",
                                         p["definition"], "warp_loop_risk"))
                if code in {(blocks[i].get("mutation") or {}).get("proccode") for i in body
                            if isinstance(blocks.get(i), dict) and blocks[i].get("opcode") == "procedures_call"}:
                    issues.append(_issue("warning", who, f"warp custom block '{code}' calls itself (recursion without screen refresh)",
                                         "Deep recursion can freeze the project.", p["definition"], "warp_recursion"))
        # edge-triggered / sensor hats without anything to trigger them are fine; flag key hats that conflict? skip.

    for name, where in receivers.items():
        if name not in senders and not dynamic_send:
            for who, bid in where:
                issues.append(_issue("warning", who, f"waits for broadcast '{name}' but nothing ever sends it",
                                     "Add a 'broadcast' block somewhere or remove this script.", bid, "unsent_broadcast"))
    for name, where in senders.items():
        if name not in receivers:
            for who, bid in where:
                issues.append(_issue("info", who, f"broadcasts '{name}' but nothing receives it", None, bid, "unreceived_broadcast"))
    for vid, (vname, scope) in all_vars.items():
        if vid not in var_read and vid not in var_set:
            issues.append(_issue("info", scope if scope != "global" else "Stage", f"variable '{vname}' is never used", None, code="unused_variable"))
        elif vid in var_set and vid not in var_read and not any(m.get("id") == vid and m.get("visible") for m in project.get("monitors") or []):
            issues.append(_issue("info", scope if scope != "global" else "Stage",
                                 f"variable '{vname}' is set but never read or shown", "Show its monitor or use it in a block.", code="write_only_variable"))
    return issues


def summarize(issues: list[Issue]) -> dict[str, Any]:
    by = {"error": 0, "warning": 0, "info": 0}
    for i in issues:
        by[i["severity"]] += 1
    return {"ok": by["error"] == 0, "counts": by, "issues": issues}
