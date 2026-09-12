# -*- coding: utf-8 -*-
"""
Scenario Compare — orchestration layer over MODE A/B/C/BEP.

Not a fifth calculation engine: this module never defines a price/CM/BEP/VAT/allocation formula
of its own. It takes a `scenario_compare_request` (docs/features/scenario_compare/SPEC.md,
core/schemas/scenario_compare_request.schema.json), derives one ordinary `client_input` per
scenario (base_input + a narrow, identifier-addressed set of field overrides — never by array
index), runs the existing `run_mode_a`/`run_mode_b`/`run_mode_c`/`run_bep` on each, and arranges
their unmodified outputs into a `scenario_compare_result`
(core/schemas/scenario_compare_result.schema.json). Every number in the result traces back to
exactly one of those four calls.

Six-step pipeline (SPEC.md section 7):
    STEP 1 - request-level preflight (see _preflight()) -> whole request ERROR, no mode runs.
    STEP 2 - base + override merge (see _merge_overrides()) -> pure field replacement.
    STEP 3 - merged client_input schema validation -> that scenario alone is ERROR, siblings
             still run their own STEP 2-6 independently.
    STEP 4 - run_mode_a/run_mode_b/run_mode_c/run_bep.
    STEP 5 - summary (read-only from the four results, SPEC.md section 10).
    STEP 6 - baseline delta (SPEC.md section 14/14a).
"""
from __future__ import annotations

import copy

from core.engine.modes.bep import run_bep
from core.engine.modes.mode_a import run_mode_a
from core.engine.modes.mode_b import run_mode_b
from core.engine.modes.mode_c import run_mode_c
from core.engine.validation.validate_client_input import validate_client_input

OK = "OK"
UNKNOWN = "UNKNOWN"
ERROR = "ERROR"
INCOMPLETE = "INCOMPLETE"
NOT_APPLICABLE = "NOT_APPLICABLE"

_COMPONENT_OVERRIDE_FIELDS = ("actual_price", "target_market_price", "price_includes_vat", "discount_rate")
_COST_ITEM_OVERRIDE_FIELDS = ("amount", "rate")

_DELTA_TIER = {ERROR: 0, UNKNOWN: 1, NOT_APPLICABLE: 2, OK: 3}


def _sc_warning(code, severity, metric_path, dependency_paths, message):
    return {
        "origin_module": "scenario_compare",
        "code": code,
        "severity": severity,
        "metric_path": metric_path,
        "dependency_paths": list(dependency_paths),
        "message": message,
    }


def _tagged(warning, origin_module):
    tagged = dict(warning)
    tagged["origin_module"] = origin_module
    return tagged


# ---------------------------------------------------------------------------
# STEP 1 — request-level preflight
# ---------------------------------------------------------------------------
def _preflight(request):
    """Returns a list of scenario_compare-origin warnings. Empty list = request passes
    preflight. Never mutates `request`."""
    problems = []

    base_input = request.get("base_input") or {}
    baseline_scenario_id = request.get("baseline_scenario_id")
    scenarios = request.get("scenarios") or []

    if len(scenarios) < 2:
        problems.append(_sc_warning(
            "SCENARIO_COUNT_BELOW_MINIMUM", "blocking", "scenario_compare",
            ["scenarios"],
            f"Scenario Compare는 최소 2개 시나리오가 필요합니다 — {len(scenarios)}개가 주어졌습니다.",
        ))

    seen_ids = set()
    dup_ids = set()
    for s in scenarios:
        sid = s.get("scenario_id")
        if sid in seen_ids:
            dup_ids.add(sid)
        seen_ids.add(sid)
    if dup_ids:
        problems.append(_sc_warning(
            "DUPLICATE_SCENARIO_ID", "blocking", "scenario_compare",
            [f"scenarios[scenario_id={sid}]" for sid in sorted(dup_ids)],
            f"scenario_id가 중복되었습니다: {sorted(dup_ids)}.",
        ))

    if not baseline_scenario_id:
        problems.append(_sc_warning(
            "MISSING_BASELINE_SCENARIO_ID", "blocking", "scenario_compare",
            ["baseline_scenario_id"],
            "baseline_scenario_id가 지정되지 않았습니다 — 첫 번째 시나리오를 자동으로 baseline으로 취급하지 않습니다.",
        ))
    elif baseline_scenario_id not in seen_ids:
        problems.append(_sc_warning(
            "BASELINE_SCENARIO_ID_NOT_FOUND", "blocking", "scenario_compare",
            ["baseline_scenario_id"],
            f"baseline_scenario_id '{baseline_scenario_id}'가 scenarios 목록에 존재하지 않습니다.",
        ))

    components = (base_input.get("product") or {}).get("price_components") or []
    component_ids = [c.get("component_id") for c in components]
    dup_component_ids = {cid for cid in component_ids if component_ids.count(cid) > 1}
    if dup_component_ids:
        problems.append(_sc_warning(
            "DUPLICATE_COMPONENT_ID_IN_BASE_INPUT", "blocking", "scenario_compare",
            [f"base_input.product.price_components[component_id={cid}]" for cid in sorted(dup_component_ids)],
            f"base_input에 중복된 component_id가 있습니다: {sorted(dup_component_ids)}.",
        ))

    items = (base_input.get("costs") or {}).get("items") or []
    item_ids = [it.get("item_id") for it in items]
    dup_item_ids = {iid for iid in item_ids if item_ids.count(iid) > 1}
    if dup_item_ids:
        problems.append(_sc_warning(
            "DUPLICATE_ITEM_ID_IN_BASE_INPUT", "blocking", "scenario_compare",
            [f"base_input.costs.items[item_id={iid}]" for iid in sorted(dup_item_ids)],
            f"base_input에 중복된 item_id가 있습니다: {sorted(dup_item_ids)}.",
        ))

    component_id_set = set(component_ids)
    item_id_set = set(item_ids)
    for s in scenarios:
        sid = s.get("scenario_id")
        overrides = s.get("overrides") or {}

        comp_overrides = overrides.get("components") or []
        seen_comp_targets = set()
        for co in comp_overrides:
            cid = co.get("component_id")
            if cid in seen_comp_targets:
                problems.append(_sc_warning(
                    "DUPLICATE_OVERRIDE_TARGET", "blocking", "scenario_compare",
                    [f"scenarios[scenario_id={sid}].overrides.components[component_id={cid}]"],
                    f"시나리오 '{sid}'의 overrides.components에서 component_id '{cid}'가 두 번 이상 등장합니다.",
                ))
            seen_comp_targets.add(cid)
            if cid not in component_id_set:
                problems.append(_sc_warning(
                    "UNKNOWN_OVERRIDE_COMPONENT_ID", "blocking", "scenario_compare",
                    [f"scenarios[scenario_id={sid}].overrides.components[component_id={cid}]"],
                    f"시나리오 '{sid}'가 base_input에 존재하지 않는 component_id '{cid}'를 override 대상으로 지정했습니다.",
                ))

        item_overrides = overrides.get("cost_items") or []
        seen_item_targets = set()
        for io in item_overrides:
            iid = io.get("item_id")
            if iid in seen_item_targets:
                problems.append(_sc_warning(
                    "DUPLICATE_OVERRIDE_TARGET", "blocking", "scenario_compare",
                    [f"scenarios[scenario_id={sid}].overrides.cost_items[item_id={iid}]"],
                    f"시나리오 '{sid}'의 overrides.cost_items에서 item_id '{iid}'가 두 번 이상 등장합니다.",
                ))
            seen_item_targets.add(iid)
            if iid not in item_id_set:
                problems.append(_sc_warning(
                    "UNKNOWN_OVERRIDE_ITEM_ID", "blocking", "scenario_compare",
                    [f"scenarios[scenario_id={sid}].overrides.cost_items[item_id={iid}]"],
                    f"시나리오 '{sid}'가 base_input에 존재하지 않는 item_id '{iid}'를 override 대상으로 지정했습니다.",
                ))

    return problems


# ---------------------------------------------------------------------------
# STEP 2 — semantic merge (base_input is never mutated)
# ---------------------------------------------------------------------------
def _merge_overrides(base_input, overrides):
    client_input = copy.deepcopy(base_input)
    overrides = overrides or {}

    comp_by_id = {c["component_id"]: c for c in client_input["product"]["price_components"]}
    for co in overrides.get("components") or []:
        comp = comp_by_id[co["component_id"]]
        for field in _COMPONENT_OVERRIDE_FIELDS:
            if field in co:
                comp[field] = co[field]

    item_by_id = {it["item_id"]: it for it in client_input["costs"]["items"]}
    for io in overrides.get("cost_items") or []:
        item = item_by_id[io["item_id"]]
        for field in _COST_ITEM_OVERRIDE_FIELDS:
            if field in io:
                item[field] = io[field]

    targets_override = overrides.get("targets") or {}
    if "target_contribution_margin_rate" in targets_override:
        client_input.setdefault("targets", {})["target_contribution_margin_rate"] = targets_override["target_contribution_margin_rate"]

    tax_override = overrides.get("tax") or {}
    if "vat_rate" in tax_override:
        client_input["tax"]["vat_rate"] = tax_override["vat_rate"]

    fx_override = overrides.get("fx") or {}
    if "rate_base_per_reporting" in fx_override:
        client_input["fx"]["rate_base_per_reporting"] = fx_override["rate_base_per_reporting"]

    return client_input


# ---------------------------------------------------------------------------
# STEP 4/5 — mode execution + summary
# ---------------------------------------------------------------------------
def _module_rollup(statuses):
    """Canonical 3-tier rollup (dependency_rules.md section 5 / SPEC.md section 9)."""
    if any(s == ERROR for s in statuses):
        return ERROR
    if any(s == INCOMPLETE for s in statuses):
        return INCOMPLETE
    return OK


def _component_summary(cid, mode_a_res, mode_b_res, mode_c_res, bep_res):
    ma = mode_a_res["per_component"][cid]
    mb = mode_b_res["per_component"][cid]
    mc = mode_c_res["per_component"][cid]
    bep_component = bep_res["per_component"].get(cid)

    summary = {
        "mode_a": {
            "status": mode_a_res["status"],
            "actual_price_ex_vat": ma["actual_price_ex_vat"],
            "contribution_margin": ma["contribution_margin"],
            "contribution_margin_rate": ma["contribution_margin_rate"],
        },
        "mode_b": {
            "status": mode_b_res["status"],
            "required_selling_price": mb["required_selling_price"],
            "required_list_price": mb["required_list_price"],
        },
        "mode_c": {
            "status": mode_c_res["status"],
            "allowable_direct_cost": mc["allowable_direct_cost"],
            "actual_direct_cost": mc["actual_direct_cost"],
            "direct_cost_gap": mc["direct_cost_gap"],
        },
        "bep": None,
    }
    if bep_component is not None:
        summary["bep"] = {
            "status": bep_res["status"],
            "fixed_operating_cost": bep_component["fixed_operating_cost"],
            "contribution_margin_per_unit": bep_component["contribution_margin_per_unit"],
            "break_even_quantity_exact": bep_component["break_even_quantity_exact"],
            "analysis_period_basis": bep_component["analysis_period_basis"],
        }
    return summary


def _run_scenario_modes(client_input):
    """STEP 4 + STEP 5 for one already-schema-valid scenario. Returns
    (scenario_status, results, summary, warnings)."""
    mode_a_res = run_mode_a(client_input)
    mode_b_res = run_mode_b(client_input)
    mode_c_res = run_mode_c(client_input)
    bep_res = run_bep(client_input)

    results = {"mode_a": mode_a_res, "mode_b": mode_b_res, "mode_c": mode_c_res, "bep": bep_res}

    warnings = []
    for module, res in results.items():
        for w in res["warnings"]:
            warnings.append(_tagged(w, module))

    component_ids = [c["component_id"] for c in client_input["product"]["price_components"]]
    per_component_summary = {
        cid: _component_summary(cid, mode_a_res, mode_b_res, mode_c_res, bep_res)
        for cid in component_ids
    }
    summary = {"per_component": per_component_summary}

    scenario_status = _module_rollup([mode_a_res["status"], mode_b_res["status"], mode_c_res["status"], bep_res["status"]])

    return scenario_status, results, summary, warnings


# ---------------------------------------------------------------------------
# STEP 6 — delta
# ---------------------------------------------------------------------------
def _delta_field(scenario_metric, baseline_metric):
    """One delta field's {value, status}, per SPEC.md section 14's ERROR>UNKNOWN>
    NOT_APPLICABLE>OK propagation. `scenario_metric`/`baseline_metric` are {value,status,unit}
    metric objects (or None if the owning summary/bep block itself is absent)."""
    if scenario_metric is None or baseline_metric is None:
        return {"value": None, "status": ERROR}
    s_status = scenario_metric["status"]
    b_status = baseline_metric["status"]
    # tier order is ERROR(0) < UNKNOWN(1) < NOT_APPLICABLE(2) < OK(3); worst = lowest tier number.
    worst = min((s_status, b_status), key=lambda s: _DELTA_TIER.get(s, 99))
    if worst != OK:
        return {"value": None, "status": worst}
    return {"value": scenario_metric["value"] - baseline_metric["value"], "status": OK}


def _component_delta(scenario_component_summary, baseline_component_summary):
    sa = scenario_component_summary["mode_a"]
    ba = baseline_component_summary["mode_a"]
    s_bep = scenario_component_summary["bep"]
    b_bep = baseline_component_summary["bep"]
    return {
        "net_sales_ex_vat_delta": _delta_field(sa["actual_price_ex_vat"], ba["actual_price_ex_vat"]),
        "contribution_margin_delta": _delta_field(sa["contribution_margin"], ba["contribution_margin"]),
        "contribution_margin_rate_delta": _delta_field(sa["contribution_margin_rate"], ba["contribution_margin_rate"]),
        "break_even_quantity_delta": _delta_field(
            s_bep["break_even_quantity_exact"] if s_bep else None,
            b_bep["break_even_quantity_exact"] if b_bep else None,
        ),
    }


_ERROR_DELTA_COMPONENT = {
    "net_sales_ex_vat_delta": {"value": None, "status": ERROR},
    "contribution_margin_delta": {"value": None, "status": ERROR},
    "contribution_margin_rate_delta": {"value": None, "status": ERROR},
    "break_even_quantity_delta": {"value": None, "status": ERROR},
}


def _deltas_for_scenario(scenario_summary, baseline_summary):
    """baseline_summary=None means the baseline scenario itself failed STEP 3 (SPEC.md
    section 14a) -- every delta becomes ERROR/null regardless of this scenario's own summary."""
    if scenario_summary is None:
        return None
    per_component = {}
    for cid, comp_summary in scenario_summary["per_component"].items():
        baseline_comp = baseline_summary["per_component"].get(cid) if baseline_summary else None
        if baseline_summary is None or baseline_comp is None:
            per_component[cid] = dict(_ERROR_DELTA_COMPONENT)
        else:
            per_component[cid] = _component_delta(comp_summary, baseline_comp)
    return {"per_component": per_component}


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------
def run_scenario_compare(request: dict) -> dict:
    preflight_problems = _preflight(request)
    baseline_scenario_id = request.get("baseline_scenario_id")

    if preflight_problems:
        return {
            "status": ERROR,
            "baseline_scenario_id": baseline_scenario_id or "",
            "scenarios": [],
            "warnings": preflight_problems,
        }

    base_input = request["base_input"]
    scenarios_in = request["scenarios"]

    # STEP 2/3/4/5 for every scenario, independently.
    scenario_results = {}
    for s in scenarios_in:
        sid = s["scenario_id"]
        client_input = _merge_overrides(base_input, s.get("overrides"))
        schema_errors = validate_client_input(client_input)

        if schema_errors:
            scenario_results[sid] = {
                "scenario_id": sid,
                "label": s.get("label", ""),
                "scenario_status": ERROR,
                "results": None,
                "summary": None,
                "warnings": [_sc_warning(
                    "SCENARIO_CLIENT_INPUT_INVALID", "blocking", f"scenario_compare.scenarios[{sid}]",
                    [f"scenarios[scenario_id={sid}].overrides"],
                    "이 시나리오의 override를 적용한 결과가 client_input.schema.json을 통과하지 못했습니다: "
                    + "; ".join(schema_errors),
                )],
            }
            continue

        scenario_status, results, summary, mode_warnings = _run_scenario_modes(client_input)
        scenario_results[sid] = {
            "scenario_id": sid,
            "label": s.get("label", ""),
            "scenario_status": scenario_status,
            "results": results,
            "summary": summary,
            "warnings": mode_warnings,
        }

    baseline_entry = scenario_results[baseline_scenario_id]
    baseline_summary = baseline_entry["summary"]  # None if baseline itself failed STEP 3

    # STEP 6 — deltas. If the baseline itself failed STEP 3, every OTHER scenario's deltas
    # become ERROR/null (SPEC.md section 14a) -- this is a single scenario_compare-level
    # condition (the baseline dependency is broken for the whole comparison), so it is recorded
    # ONCE at the top-level warnings, never duplicated into each sibling's own warnings[].
    top_level_warnings = []
    for entry in scenario_results.values():
        entry["deltas"] = _deltas_for_scenario(entry["summary"], baseline_summary)
    if baseline_summary is None:
        top_level_warnings.append(_sc_warning(
            "BASELINE_SCENARIO_INVALID_FOR_DELTA", "blocking", "scenario_compare",
            [f"scenarios[scenario_id={baseline_scenario_id}]"],
            f"baseline scenario '{baseline_scenario_id}'가 client_input 검증에 실패해 "
            "다른 시나리오들의 delta를 계산할 수 없습니다 (해당 시나리오들의 absolute 결과는 정상 보존됩니다).",
        ))

    ordered = [scenario_results[s["scenario_id"]] for s in scenarios_in]
    for entry in ordered:
        # expose the four mode results with clean keys (or omit entirely if STEP 3 failed)
        if entry["results"] is not None:
            entry["results"] = {
                "mode_a": entry["results"]["mode_a"],
                "mode_b": entry["results"]["mode_b"],
                "mode_c": entry["results"]["mode_c"],
                "bep": entry["results"]["bep"],
            }
        else:
            del entry["results"]
        if entry["summary"] is None:
            del entry["summary"]
        if entry["deltas"] is None:
            del entry["deltas"]

    overall_status = _module_rollup([e["scenario_status"] for e in ordered])

    return {
        "status": overall_status,
        "baseline_scenario_id": baseline_scenario_id,
        "scenarios": ordered,
        "warnings": top_level_warnings,
    }
