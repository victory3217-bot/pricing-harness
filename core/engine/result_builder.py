# -*- coding: utf-8 -*-
"""
Assembles a full Analysis Result (conforming to core/schemas/analysis_result.schema.json)
from a validated Client Input. MODE A, MODE B, MODE C, and BEP are implemented; blended is
still a stub block with status NOT_IMPLEMENTED until that step is built.
"""
from __future__ import annotations

import datetime

from core.engine.modes.bep import run_bep
from core.engine.modes.mode_a import run_mode_a
from core.engine.modes.mode_b import run_mode_b
from core.engine.modes.mode_c import run_mode_c

ENGINE_VERSION = "0.4.0"


def build_analysis_result(client_input: dict, client_input_ref: str) -> dict:
    mode_a_result = run_mode_a(client_input)
    mode_b_result = run_mode_b(client_input)
    mode_c_result = run_mode_c(client_input)
    bep_result = run_bep(client_input)

    missing_input_paths = sorted({
        p
        for w in mode_a_result["warnings"] + mode_b_result["warnings"] + mode_c_result["warnings"] + bep_result["warnings"]
        for p in w["dependency_paths"]
        if not p.startswith("mode_a.") and not p.startswith("mode_b.")
        and not p.startswith("mode_c.") and not p.startswith("bep.") and not p.startswith("blended.")
    })

    return {
        "schema_version": "1.1",
        "source": {
            "client_id": client_input["client_id"],
            "case_id": client_input["case_id"],
            "client_input_ref": client_input_ref,
            "engine_version": ENGINE_VERSION,
            "calculated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "currency": {"reporting": client_input["fx"]["reporting_currency"]},
        "mode_a": mode_a_result,
        "blended": {"status": "NOT_IMPLEMENTED"},
        "mode_b": mode_b_result,
        "mode_c": mode_c_result,
        "bep": bep_result,
        "meta": {"missing_input_paths": missing_input_paths},
    }
