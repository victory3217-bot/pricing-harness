# Core Engine

Pure Python calculation logic: takes a validated Client Input (or, for Scenario Compare, a
Scenario Compare Request) and produces the corresponding result, following the rules in
[`../schemas/dependency_rules.md`](../schemas/dependency_rules.md). Nothing in this package reads
or writes files, talks to Excel, or has any side effect beyond computing and returning a dict —
see `tools/excel_simulator/` for the separate layer that mirrors these formulas in Excel.

## Implemented capabilities

| Capability | Entry function | Module | SPEC |
|---|---|---|---|
| MODE A (current-price diagnosis) | `run_mode_a(client_input)` | [`modes/mode_a.py`](modes/mode_a.py) | [docs/features/mode_a_current_price/SPEC.md](../../docs/features/mode_a_current_price/SPEC.md) |
| MODE B (target price) | `run_mode_b(client_input)` | [`modes/mode_b.py`](modes/mode_b.py) | [docs/features/mode_b_target_price/SPEC.md](../../docs/features/mode_b_target_price/SPEC.md) |
| MODE C (allowable direct cost) | `run_mode_c(client_input)` | [`modes/mode_c.py`](modes/mode_c.py) | [docs/features/mode_c_allowable_cost/SPEC.md](../../docs/features/mode_c_allowable_cost/SPEC.md) |
| BEP (break-even point) | `run_bep(client_input)` | [`modes/bep.py`](modes/bep.py) | [docs/features/bep/SPEC.md](../../docs/features/bep/SPEC.md) |
| Combined single-analysis result | `build_analysis_result(client_input, client_input_ref)` | [`result_builder.py`](result_builder.py) | calls all four of the above and assembles one `analysis_result.schema.json`-shaped dict |
| Scenario Compare | `run_scenario_compare(request)` | [`scenario_compare.py`](scenario_compare.py) | [docs/features/scenario_compare/SPEC.md](../../docs/features/scenario_compare/SPEC.md) |

Each `run_mode_*`/`run_bep` function takes just `client_input: dict` (already merged/resolved,
not yet validated) and returns that mode's own result block — it does **not** validate its input
itself; validation is a separate step (see below). `build_analysis_result` and
`run_scenario_compare` are the two functions most callers actually want; see the repository root
[`README.md`](../../README.md#quick-start--python) for runnable examples of both.

`shared/`-style cost allocation (splitting one cost item's amount across multiple components) is
**not implemented** in any of the four modes yet — see the root README's
[Current limitations](../../README.md#current-limitations).

## Validation relationship

Neither `run_mode_a`/`run_mode_b`/`run_mode_c`/`run_bep` nor `build_analysis_result` validates
its own input — the caller is expected to validate first:

- Single-analysis path: call
  [`validation/validate_client_input.py`](validation/validate_client_input.py)'s
  `validate_client_input(instance) -> list[str]` (empty list = valid) against
  `client_input.schema.json` *before* calling `build_analysis_result`/`run_mode_*`.
- Scenario Compare: `run_scenario_compare()` in [`scenario_compare.py`](scenario_compare.py)
  **does** validate its own request internally (via
  [`validation/validate_scenario_compare.py`](validation/validate_scenario_compare.py)'s
  `validate_scenario_compare_request`), then merges each scenario's overrides onto the shared
  `base_input` and validates *that* merged Client Input per-scenario the same way MODE A/B/C/BEP
  themselves require. A scenario whose merged input fails this per-scenario validation gets
  `scenario_status: "ERROR"` with no absolute results, while every other (valid) scenario in the
  same request still runs normally.

## Analysis Result relationship

`build_analysis_result(client_input, client_input_ref)` is the one place that assembles MODE A +
MODE B + MODE C + BEP into a single Analysis Result conforming to
[`../schemas/analysis_result.schema.json`](../schemas/analysis_result.schema.json) — it stamps a
`source` block (including `client_input_ref`, the caller-supplied string identifying where the
input came from, and `engine_version`, an internal marker unrelated to any repository-wide
version) and a `blended` block (still a `NOT_IMPLEMENTED` stub). Nothing outside this function
should hand-assemble that shape — if you need MODE A alone, call `run_mode_a` directly instead of
picking `result["mode_a"]` out of a full `build_analysis_result` call.

Scenario Compare's result shape is separate
(`../schemas/scenario_compare_result.schema.json`) — each scenario's `results` block reuses
MODE A/B/C/BEP's own block *definitions* by `$ref` (so the two schemas never drift apart in what
a "MODE A block" looks like), but Scenario Compare never calls `build_analysis_result`; it calls
the four `run_mode_*`/`run_bep` functions directly per scenario and adds its own delta/summary
views on top.
