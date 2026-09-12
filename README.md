# Pricing Harness

A reusable pricing-management and pricing-strategy engine for repeated use across multiple
client engagements — not a one-off tool for a single company. This repository contains only
generic or fictional examples; client-specific data and engagement records are intentionally
excluded from the public repository.

This project is the first Private Consulting Harness Pilot inside a larger AI Knowledge
Platform — see the reference documents below before assuming this repo's own docs are the
top-level authority on governance, language policy, or curriculum structure.

**Reference documents:**

- Project-level architecture reference:
  [`docs/reference/AI_Knowledge_Platform_Project_Plan_v0.1.md`](docs/reference/AI_Knowledge_Platform_Project_Plan_v0.1.md)
- Pricing methodology reference:
  [`docs/reference/MASTER_NOTE_PRICING_REFERENCE.md`](docs/reference/MASTER_NOTE_PRICING_REFERENCE.md)

## What it is

The Pricing Harness is a pricing-analysis engine: give it one product's price/cost facts as a
JSON document (a **Client Input**), and it computes contribution margin, target price, allowable
cost, and break-even numbers, each tagged with a status so a consumer never has to guess whether
a number is real, missing, or undefined. It ships as a Python Core (the source of truth for every
calculation) plus a JSON contract (request/result schemas) plus an Excel Simulator that mirrors
the same formulas for live, interactive use and cross-checks itself against the Python Core.

Five capabilities are implemented today, all with passing tests and Excel parity:

- **MODE A** — current-price diagnosis
- **MODE B** — target price
- **MODE C** — allowable direct cost
- **BEP** — break-even point
- **Scenario Compare** — runs several of the above together and compares them against a baseline

## Architecture

```
Client Input  →  Validation  →  Pricing Engine  →  Analysis Result  →  Dashboard / Report / Quotation
```

- **Client Input** — one product's price/cost facts for one client, conforming to
  [`core/schemas/client_input.schema.json`](core/schemas/client_input.schema.json).
- **Validation** — every Client Input is checked against that schema before the engine touches it
  ([`core/engine/validation/validate_client_input.py`](core/engine/validation/validate_client_input.py)).
- **Pricing Engine** (`core/engine/`) — pure calculation logic shared by every client. Turns a
  Client Input into an Analysis Result. MODE A/B/C, BEP, and Scenario Compare are implemented —
  see [`core/engine/README.md`](core/engine/README.md) for the engine's internal structure.
- **Analysis Result** — the *only* computed artifact for a single Client Input, conforming to
  [`core/schemas/analysis_result.schema.json`](core/schemas/analysis_result.schema.json).
- **Dashboard / Report / Quotation** — all three (future work) read the Analysis Result only.
  **They never recompute anything themselves.** If a number needs to change, it changes in the
  engine, and every consumer picks it up from the next Analysis Result — there is exactly one
  place pricing math happens.

This is why every computed value in an Analysis Result is wrapped as `{value, status, unit}`
rather than a bare number: a consumer can render "미입력" instead of a number without knowing
*why* it's missing, and without ever substituting `0` for an unknown cost. See
[Interpreting results: status values](#interpreting-results-status-values) below.

## The five capabilities

Each has its own `SPEC.md` (developer spec) / `METHOD.md` (consulting methodology) /
`CASE.md` (worked example) under `docs/features/<feature>/` — these summaries are entry points,
not the full picture.

- **MODE A — current-price diagnosis** ([docs/features/mode_a_current_price/](docs/features/mode_a_current_price/SPEC.md))
  At the product's *current actual price*, how much is really left after direct and variable
  costs — its contribution margin and rate?
- **MODE B — target price** ([docs/features/mode_b_target_price/](docs/features/mode_b_target_price/SPEC.md))
  Given the current cost/fee structure, what price must you charge to hit a *target*
  contribution margin rate?
- **MODE C — allowable direct cost** ([docs/features/mode_c_allowable_cost/](docs/features/mode_c_allowable_cost/SPEC.md))
  Given a target market price and a target contribution margin rate, what is the maximum direct
  cost you can afford per unit?
- **BEP — break-even point** ([docs/features/bep/](docs/features/bep/SPEC.md))
  At the current price and contribution margin structure, how many units must you sell to
  recover the period's fixed operating cost?
- **Scenario Compare** ([docs/features/scenario_compare/](docs/features/scenario_compare/SPEC.md))
  An **orchestration layer, not a sixth calculation engine**: it runs MODE A/B/C and BEP over
  several named scenarios derived from one shared base input, then reports each scenario's
  absolute results plus its delta against a chosen baseline scenario. It never defines its own
  pricing formula — every number it shows comes from calling MODE A/B/C/BEP directly.

## Four content areas

| Area | Contains | Publishable? |
|---|---|---|
| `core/` | Formulas, calculation logic, schemas, strategy frameworks, report rules — common to every client. No company names. | Yes |
| `clients/` | One real company's actual products, costs, prices, channels, customers, competitors. | **No — gitignored, and excluded from this public repository entirely** |
| `samples/` | Fictional or anonymized data for GitHub / workshop use. | Yes |
| `cases/` | A specific engagement's application record — narrative + generated outputs, referencing `clients/` by path rather than duplicating the numbers. | Case narrative yes; underlying numbers only if the client data itself is public/anonymized. **Not included in this public repository.** |
| `curriculum/` | Concepts, methodology, teaching examples built from the above. | Yes |

`core/schemas/examples/` ships fictional sample data specifically so it's safe to publish and
use in the workshop described below.

## SPEC / METHOD / CASE

Every feature this Harness gets should leave three documents behind (`docs/features/<feature>/`):

- **SPEC.md** — software specification: inputs, outputs, formulas, edge cases. For developers.
- **METHOD.md** — consulting methodology: why this concept matters, when to use it, how to
  explain it to a client. For consultants.
- **CASE.md** — a worked example with real numbers (citing `cases/case_00N_.../`). For sales
  and teaching material.

The result: building the software simultaneously accumulates as a consulting methodology and
as teaching material — not three separate efforts.

## Purpose (all four, simultaneously)

This project is deliberately run so that one body of work supports:

1. **Real pricing consulting** — client engagements, tracked privately outside this repository.
2. **General-purpose Pricing Harness development** — a reusable engine, not client-specific code.
3. **Public GitHub practice material** — `samples/` and `core/schemas/examples/`.
4. **A 3-day, 9-hour workshop curriculum** — `curriculum/`.
5. **Accumulated textbook / case-study assets** — the SPEC/METHOD/CASE trio above.

## Installation

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` currently pins:

```
jsonschema>=4.20
pytest>=8.0
openpyxl>=3.1
```

This is enough to run the Python Core, the test suite, and schema validation, and to regenerate
the Excel Simulator workbook (`openpyxl` writes the `.xlsx` file). It is **not** enough to run
the Excel QA scripts — those additionally need **LibreOffice** installed on the machine (an
external, non-Python dependency used only for headless formula recalculation); see
[Excel QA](#excel-qa) below.

## Quick Start — Python

There is no CLI yet — every capability is a plain Python function you import. Run these from the
repository root (so `core/` resolves as a package).

**A. Single analysis (MODE A + B + C + BEP together)**

```python
import json
from core.engine.validation.validate_client_input import validate_client_input
from core.engine.result_builder import build_analysis_result

client_input = json.load(open("core/schemas/examples/valid/01_simple_one_time_product.json", encoding="utf-8"))

errors = validate_client_input(client_input)
assert not errors, errors  # validate before running the engine

result = build_analysis_result(client_input, client_input_ref="core/schemas/examples/valid/01_simple_one_time_product.json")
print(result["mode_a"]["status"])                                      # "OK"
print(result["mode_a"]["per_component"]["main"]["contribution_margin"])  # {"value": ..., "status": "OK", "unit": "KRW"}
```

`build_analysis_result()` ([`core/engine/result_builder.py`](core/engine/result_builder.py)) runs
MODE A, MODE B, MODE C, and BEP over the same Client Input and assembles one Analysis Result
(conforming to `core/schemas/analysis_result.schema.json`). To call a single mode directly, import
`run_mode_a`/`run_mode_b`/`run_mode_c` from `core.engine.modes.mode_a`/`mode_b`/`mode_c`, or
`run_bep` from `core.engine.modes.bep` — each takes just `client_input` and returns that mode's
own result block.

**B. Scenario Compare**

```python
import json
from core.engine.scenario_compare import run_scenario_compare

request = json.load(open(
    "core/schemas/examples/scenario_compare/01_baseline_price_up_cost_down.request.json",
    encoding="utf-8",
))
result = run_scenario_compare(request)
print(result["status"])                 # "OK"
print(result["baseline_scenario_id"])   # "A_baseline"
for scenario in result["scenarios"]:
    print(scenario["scenario_id"], scenario["scenario_status"])
```

`run_scenario_compare()` ([`core/engine/scenario_compare.py`](core/engine/scenario_compare.py))
validates the request against `core/schemas/scenario_compare_request.schema.json` internally, so
you don't need to call a separate validator first (unlike the single-analysis path above).

## Input / Output

| | Schema | Shipped examples |
|---|---|---|
| Single-analysis input | [`core/schemas/client_input.schema.json`](core/schemas/client_input.schema.json) | [`core/schemas/examples/valid/`](core/schemas/examples/valid/) (valid) / [`core/schemas/examples/invalid/`](core/schemas/examples/invalid/) (rejected, for reference) |
| Single-analysis output | [`core/schemas/analysis_result.schema.json`](core/schemas/analysis_result.schema.json) | [`core/schemas/examples/analysis_results/`](core/schemas/examples/analysis_results/) — generated by running the engine over every file in `examples/valid/`, not hand-written (regenerate with `python -m core.engine.generate_analysis_results`) |
| Scenario Compare input | [`core/schemas/scenario_compare_request.schema.json`](core/schemas/scenario_compare_request.schema.json) | [`core/schemas/examples/scenario_compare/*.request.json`](core/schemas/examples/scenario_compare/) |
| Scenario Compare output | [`core/schemas/scenario_compare_result.schema.json`](core/schemas/scenario_compare_result.schema.json) | [`core/schemas/examples/scenario_compare/*.result.json`](core/schemas/examples/scenario_compare/) |

## Interpreting results: status values

Every computed number carries a status instead of being a bare value. There are two different
status vocabularies — don't conflate them:

- **Per-metric status** (on individual numbers like `contribution_margin`): `OK` — every
  dependency resolved; `UNKNOWN` — a required input is missing (null); `ESTIMATED` — computed
  from an assumed/default value rather than a confirmed input; `NOT_APPLICABLE` — this metric has
  no meaning for this component/product shape (e.g. break-even quantity when there's no fixed
  cost item at all); `ERROR` — an input was present but computation still failed (e.g.
  contradictory inputs).
- **Module-level status** (on `mode_a`/`mode_b`/`mode_c`/`bep` as a whole): `OK`, `INCOMPLETE`
  (at least one of that module's metrics is `UNKNOWN`), `ERROR`, `NOT_RUN`, `NOT_IMPLEMENTED`.
  There is no module-level `UNKNOWN` or `NOT_APPLICABLE` — those only exist per-metric.

**Scenario Compare and invalid baselines**: if the *baseline* scenario itself fails validation,
every other (valid) scenario's own absolute results are still computed and shown normally — only
their delta-vs-baseline becomes `ERROR`, since there is nothing valid to compare against. A valid
sibling scenario is never penalized for an unrelated baseline's failure.

## Excel Simulator

[`tools/excel_simulator/Pricing_Harness_Excel_Simulator_v0.5.xlsx`](tools/excel_simulator/Pricing_Harness_Excel_Simulator_v0.5.xlsx)
is a tracked, ready-to-open workbook — you don't need to build anything to use it. It is a
**presentation/parity layer**, not a 1:1 UI over every Python Core capability: it exposes a
simplified, representative-slot version of each mode's inputs (see
[Current limitations](#current-limitations)) and exists mainly to demonstrate the formulas live
and to catch Python↔Excel drift.

To regenerate it from the current formula-generation code:

```bash
python tools/excel_simulator/build_workbook.py
```

This always writes to `tools/excel_simulator/Pricing_Harness_Excel_Simulator_v0.5.xlsx` relative
to the script's own location, regardless of your current working directory.

## Excel QA

```bash
python tools/excel_simulator/qa_check.py                     # MODE A
python tools/excel_simulator/qa_check_mode_b.py               # MODE B
python tools/excel_simulator/qa_check_mode_c.py               # MODE C
python tools/excel_simulator/qa_check_bep.py                  # BEP
python tools/excel_simulator/qa_check_scenario_compare.py     # Scenario Compare
```

Each script recalculates the tracked workbook via **LibreOffice headless** (so formulas are
genuinely re-evaluated, not read from a stale cached value) and compares the result against a
Python-computed reference. **Current limitation**: the LibreOffice executable path is currently
hardcoded to the default Windows install location
(`C:\Program Files\LibreOffice\program\soffice.exe`) inside each script — on any other OS, or a
non-default install path, these QA scripts will not run until that path is edited by hand. This
does not affect the Python Core, the test suite, or schema validation, which have no LibreOffice
dependency at all.

## Tests / Validation

```bash
pytest                                    # Python unit tests
python core/schemas/validate_examples.py  # schema validation of every shipped example
```

Audited baseline as of this repository state (not a permanent guarantee — re-run to confirm
against whatever commit you have checked out):

- `pytest`: 160 passed
- schema validation: ALL 13 CHECKS PASSED
- MODE A / MODE B Excel QA: PASS
- MODE C Excel QA: 20/20 PASS
- BEP Excel QA: PASS
- Scenario Compare Excel QA: 25 cases PASS
- raw Excel errors: 0

## Current limitations

- Scenario Compare's **interactive Excel UI** supports at most 5 scenarios at once; the Python
  Core has no such ceiling (2 minimum, otherwise unbounded).
- Excel cost overrides only expose a handful of **representative slots** (direct cost, fixed
  operating cost, one gross-payment fee rate); the Python Core accepts an arbitrary
  `item_id`/`component_id` override.
- Scenario Compare has **no multi-component support in Excel** (the Python Core's multi-component
  BEP gate has no Excel-side input structure to exercise it).
- **Structural overrides** (adding or removing a price component or cost item within a scenario)
  are not supported in either the Python Core or Excel — only overriding an existing field's
  value.
- A real **shared-cost allocation engine** is not implemented anywhere yet; Excel only simulates
  the allocation-status states (`none`/`unresolved`/`invalid`) as test controls, and the Python
  Core does not yet allocate a shared cost item across components.
- `build_workbook.py` has an import-time side effect (importing the module regenerates and saves
  the workbook) — always run it as a script (`python tools/excel_simulator/build_workbook.py`),
  never `import build_workbook` from another script or a REPL.

## Version identity

The Pricing Harness has four independent version axes — they track different things, are not
meant to match each other, and none of them should be read as covering what another one covers.

| Axis | Current value | Source of truth | What it tracks |
|---|---|---|---|
| **Product release** | `0.1.0-beta.2` | root [`VERSION`](VERSION) file, tagged in git as `v0.1.0-beta.2` | The Pricing Harness as a whole (Python Core + schemas + Excel Simulator + docs) at a point in time. This is the sanitized public repository's first release identity — current maturity is **Limited/Beta**. |
| Python engine marker | `0.4.0` | `ENGINE_VERSION` in [`core/engine/result_builder.py`](core/engine/result_builder.py) | The calculation engine's own internal iteration, stamped into every generated Analysis Result's `source.engine_version` field. |
| Excel Simulator artifact | `v0.5` | the workbook's own filename, `Pricing_Harness_Excel_Simulator_v0.5.xlsx` | This specific Excel build's own iteration, independent of the Python engine or the product release. |
| Schema / data contract | `1.1` | `schema_version` field inside every Client Input / Analysis Result / Scenario Compare document | The *shape* of the JSON documents flowing through the system — a data-compatibility version, not a software release. |

These four numbers will drift apart over time by design: a schema migration, an engine-only
formula fix, and an Excel-only build can each happen without changing the other axes. Read the
product release version from `VERSION` (or the matching git tag) — never infer it from the Excel
filename or `ENGINE_VERSION`.

## Repository map

```
core/                  Formulas, schemas, and calculation logic shared by every client — no company names
core/engine/           The Pricing Engine itself (MODE A/B/C, BEP, Scenario Compare) — see core/engine/README.md
core/schemas/          JSON Schema contracts (Client Input, Analysis Result, Scenario Compare) + shipped examples
docs/features/         SPEC/METHOD/CASE trio per capability (mode_a_current_price/, mode_b_target_price/, ...)
tests/                 pytest unit tests, one file per capability
tools/excel_simulator/ Excel workbook builder + QA scripts (Python↔Excel parity)
```

`clients/`, `samples/`, `cases/`, `curriculum/` are described in
[Four content areas](#four-content-areas) above.

## Out of scope for now

Explicitly deferred, though folder/data shapes are kept forward-compatible:

- External competitor research, market research, AI-generated pricing strategy
- Automated report generation
- Automated quotation generation
- Web dashboard
