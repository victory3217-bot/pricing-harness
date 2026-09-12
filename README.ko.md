[English](README.md) | [한국어](README.ko.md)

# Pricing Harness

여러 클라이언트 참여(engagement)에 걸쳐 반복적으로 재사용할 수 있는 가격 관리·가격 전략 엔진입니다 —
특정 회사 하나만을 위한 일회성 도구가 아닙니다. 이 저장소에는 일반화되었거나 가상의 예제만 포함되어
있으며, 특정 고객의 데이터와 실제 참여(engagement) 기록은 이 공개 저장소에서 의도적으로 제외되어
있습니다.

이 프로젝트는 더 큰 AI Knowledge Platform 안에 있는 첫 Private Consulting Harness Pilot입니다 —
이 저장소 자체의 문서를 governance, language policy, curriculum 구조에 대한 최상위 권위 있는
문서로 가정하기 전에 아래 참고 문서를 먼저 확인하십시오.

**참고 문서:**

- 프로젝트 레벨 아키텍처 참고 문서:
  [`docs/reference/AI_Knowledge_Platform_Project_Plan_v0.1.md`](docs/reference/AI_Knowledge_Platform_Project_Plan_v0.1.md)
- 가격 방법론 참고 문서:
  [`docs/reference/MASTER_NOTE_PRICING_REFERENCE.md`](docs/reference/MASTER_NOTE_PRICING_REFERENCE.md)

## What it is (개요)

Pricing Harness는 가격 분석 엔진입니다: 상품 하나의 가격/원가 정보를 JSON 문서(**Client Input**)로
주면, 공헌이익(contribution margin), 목표 가격, 허용 원가, 손익분기 수치를 계산하며, 각 값에는
status가 함께 태그되어 있어 사용 측에서 그 값이 실제 값인지, 누락된 값인지, 정의되지 않은 값인지
추측할 필요가 없습니다. Python Core(모든 계산의 source of truth) + JSON contract(request/result
schema) + 동일한 공식을 그대로 미러링해 실시간·인터랙티브로 확인할 수 있고 Python Core와 스스로
대조 검증하는 Excel Simulator로 구성되어 있습니다.

현재 다음 5개 기능이 구현되어 있으며, 모두 테스트와 Excel parity 검증을 통과합니다:

- **MODE A** — 현재가 기준 진단(current-price diagnosis)
- **MODE B** — 목표 가격(target price)
- **MODE C** — 허용 직접원가(allowable direct cost)
- **BEP** — 손익분기점(break-even point)
- **Scenario Compare** — 위 기능들을 여러 시나리오에 대해 함께 실행하고 baseline 대비 비교

## Architecture (아키텍처)

```
Client Input  →  Validation  →  Pricing Engine  →  Analysis Result  →  Dashboard / Report / Quotation
```

- **Client Input** — 한 클라이언트의 상품 하나에 대한 가격/원가 정보로,
  [`core/schemas/client_input.schema.json`](core/schemas/client_input.schema.json)을 따릅니다.
- **Validation** — 모든 Client Input은 engine이 다루기 전에 이 schema로 검증됩니다
  ([`core/engine/validation/validate_client_input.py`](core/engine/validation/validate_client_input.py)).
- **Pricing Engine** (`core/engine/`) — 모든 클라이언트가 공유하는 순수 계산 로직입니다. Client
  Input을 Analysis Result로 변환합니다. MODE A/B/C, BEP, Scenario Compare가 구현되어 있습니다 —
  엔진 내부 구조는 [`core/engine/README.md`](core/engine/README.md)를 참고하십시오.
- **Analysis Result** — 하나의 Client Input에 대한 *유일한* 계산 산출물로,
  [`core/schemas/analysis_result.schema.json`](core/schemas/analysis_result.schema.json)을 따릅니다.
- **Dashboard / Report / Quotation** — 셋 다(향후 작업) Analysis Result만 읽습니다.
  **스스로 재계산하지 않습니다.** 숫자가 바뀌어야 한다면 그것은 engine 안에서 바뀌고, 모든 소비자는
  다음 Analysis Result에서 그 값을 그대로 가져갑니다 — 가격 계산이 일어나는 곳은 정확히 한 곳뿐입니다.

Analysis Result의 모든 계산값이 단순 숫자가 아니라 `{value, status, unit}`로 감싸져 있는 이유가
바로 이것입니다: 소비자는 값이 왜 없는지 몰라도 "미입력"이라고 표시할 수 있고, 알 수 없는 원가를
`0`으로 대체하는 일도 없습니다. 아래
[결과 해석: status 값](#결과-해석-status-값)을 참고하십시오.

## The five capabilities (다섯 가지 기능)

각 기능은 `docs/features/<feature>/` 아래에 자체 `SPEC.md`(개발자용 스펙) /
`METHOD.md`(컨설팅 방법론) / `CASE.md`(예제)를 가지고 있습니다 — 아래 요약은 진입점일 뿐 전체
내용이 아닙니다.

- **MODE A — current-price diagnosis** ([docs/features/mode_a_current_price/](docs/features/mode_a_current_price/SPEC.md))
  상품의 *현재 실제 가격* 기준으로, 직접원가와 변동비를 제하고 실제로 얼마가 남는지 — 공헌이익과
  공헌이익률을 계산합니다.
- **MODE B — target price** ([docs/features/mode_b_target_price/](docs/features/mode_b_target_price/SPEC.md))
  현재 원가/수수료 구조에서, *목표* 공헌이익률을 달성하려면 얼마에 팔아야 하는지 계산합니다.
- **MODE C — allowable direct cost** ([docs/features/mode_c_allowable_cost/](docs/features/mode_c_allowable_cost/SPEC.md))
  목표 시장가격과 목표 공헌이익률이 주어졌을 때, 단위당 감당할 수 있는 최대 직접원가는 얼마인지
  계산합니다.
- **BEP — break-even point** ([docs/features/bep/](docs/features/bep/SPEC.md))
  현재 가격과 공헌이익 구조에서, 기간 고정운영비를 회수하려면 몇 단위를 팔아야 하는지 계산합니다.
- **Scenario Compare** ([docs/features/scenario_compare/](docs/features/scenario_compare/SPEC.md))
  **orchestration layer이며, 여섯 번째 계산 엔진이 아닙니다**: 하나의 공유 base input에서 파생된
  여러 named scenario에 대해 MODE A/B/C와 BEP를 실행하고, 각 scenario의 절대값 결과와 선택된
  baseline scenario 대비 delta를 함께 보고합니다. 자체 가격 계산식을 정의하지 않으며 — 보여주는
  모든 숫자는 MODE A/B/C/BEP를 직접 호출한 결과입니다.

## Four content areas (네 가지 콘텐츠 영역)

| 영역 | 내용 | 공개 가능 여부 |
|---|---|---|
| `core/` | 모든 클라이언트에 공통되는 공식, 계산 로직, schema, 전략 프레임워크, 리포트 규칙. 회사명 없음. | Yes |
| `clients/` | 실제 한 회사의 실제 상품, 원가, 가격, 채널, 고객, 경쟁사 정보. | **No — gitignore 처리, 이 공개 저장소에서는 완전히 제외됨** |
| `samples/` | GitHub/워크숍용 가상 또는 익명화된 데이터. | Yes |
| `cases/` | 특정 참여(engagement)의 적용 기록 — 서사(narrative) + 생성된 산출물, 숫자를 복제하지 않고 `clients/`를 경로로 참조. | 서사는 공개 가능; 실제 수치는 클라이언트 데이터 자체가 공개/익명화된 경우에만. **이 공개 저장소에는 포함되지 않음.** |
| `curriculum/` | 위 내용들로 구성된 개념, 방법론, 교육용 예제. | Yes |

`core/schemas/examples/`는 워크숍에서 안전하게 공개하고 사용할 수 있도록 가상의 샘플 데이터만
제공합니다.

## SPEC / METHOD / CASE

이 Harness에 추가되는 모든 기능은 `docs/features/<feature>/` 아래에 세 개의 문서를 남겨야 합니다:

- **SPEC.md** — 소프트웨어 스펙: 입력, 출력, 공식, 엣지 케이스. 개발자용.
- **METHOD.md** — 컨설팅 방법론: 이 개념이 왜 중요한지, 언제 쓰는지, 클라이언트에게 어떻게
  설명하는지. 컨설턴트용.
- **CASE.md** — 실제 숫자를 사용한 예제(`cases/case_00N_.../` 참조). 영업·교육 자료용.

그 결과, 소프트웨어를 만드는 작업 자체가 컨설팅 방법론과 교육 자료를 동시에 축적합니다 — 별도의
세 가지 작업이 아닙니다.

## Purpose (목적, 네 가지 동시에)

이 프로젝트는 다음 네 가지를 동시에 지원하도록 의도적으로 운영됩니다:

1. **실제 가격 컨설팅** — 클라이언트 참여(engagement), 이 저장소 밖에서 비공개로 관리됩니다.
2. **범용 Pricing Harness 개발** — 특정 클라이언트 전용 코드가 아닌 재사용 가능한 엔진.
3. **공개 GitHub 실습 자료** — `samples/`와 `core/schemas/examples/`.
4. **3일, 9시간짜리 워크숍 커리큘럼** — `curriculum/`.
5. **축적되는 교재/사례 연구 자산** — 위의 SPEC/METHOD/CASE 3종.

## Installation (설치)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt`는 현재 다음을 고정합니다:

```
jsonschema>=4.20
pytest>=8.0
openpyxl>=3.1
```

이것만으로 Python Core, 테스트 스위트, schema validation을 실행할 수 있고, Excel Simulator
workbook을 재생성할 수 있습니다(`openpyxl`이 `.xlsx` 파일을 씁니다). 하지만 Excel QA 스크립트를
실행하기에는 **충분하지 않습니다** — 그것들은 추가로 머신에 **LibreOffice**가 설치되어 있어야
합니다(headless 수식 재계산에만 쓰이는 Python 외부 dependency); 아래
[Excel QA](#excel-qa)를 참고하십시오.

## Quick Start — Python

아직 CLI는 없습니다 — 모든 기능은 직접 import해서 쓰는 순수 Python 함수입니다. 아래 예제는
저장소 루트에서 실행하십시오(그래야 `core/`가 패키지로 resolve됩니다).

**A. 단일 분석 (MODE A + B + C + BEP를 함께)**

```python
import json
from core.engine.validation.validate_client_input import validate_client_input
from core.engine.result_builder import build_analysis_result

client_input = json.load(open("core/schemas/examples/valid/01_simple_one_time_product.json", encoding="utf-8"))

errors = validate_client_input(client_input)
assert not errors, errors  # engine을 실행하기 전에 먼저 validate

result = build_analysis_result(client_input, client_input_ref="core/schemas/examples/valid/01_simple_one_time_product.json")
print(result["mode_a"]["status"])                                      # "OK"
print(result["mode_a"]["per_component"]["main"]["contribution_margin"])  # {"value": ..., "status": "OK", "unit": "KRW"}
```

`build_analysis_result()` ([`core/engine/result_builder.py`](core/engine/result_builder.py))는
같은 Client Input에 대해 MODE A, MODE B, MODE C, BEP를 실행하고 하나의 Analysis Result로
조립합니다(`core/schemas/analysis_result.schema.json`을 따름). 단일 mode 하나만 직접 호출하려면
`core.engine.modes.mode_a`/`mode_b`/`mode_c`에서 `run_mode_a`/`run_mode_b`/`run_mode_c`를,
`core.engine.modes.bep`에서 `run_bep`를 import하십시오 — 각각 `client_input`만 받아서 해당
mode 자체의 결과 블록을 반환합니다.

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

`run_scenario_compare()` ([`core/engine/scenario_compare.py`](core/engine/scenario_compare.py))는
내부적으로 request를 `core/schemas/scenario_compare_request.schema.json`으로 검증하므로, 위
단일 분석 경로와 달리 별도의 validator를 먼저 호출할 필요가 없습니다.

## Input / Output (입력/출력)

| | Schema | 제공되는 example |
|---|---|---|
| 단일 분석 입력 | [`core/schemas/client_input.schema.json`](core/schemas/client_input.schema.json) | [`core/schemas/examples/valid/`](core/schemas/examples/valid/) (valid) / [`core/schemas/examples/invalid/`](core/schemas/examples/invalid/) (참고용, 거부되는 예시) |
| 단일 분석 출력 | [`core/schemas/analysis_result.schema.json`](core/schemas/analysis_result.schema.json) | [`core/schemas/examples/analysis_results/`](core/schemas/examples/analysis_results/) — `examples/valid/`의 모든 파일에 대해 엔진을 실행해 생성됨(수기 작성 아님, `python -m core.engine.generate_analysis_results`로 재생성) |
| Scenario Compare 입력 | [`core/schemas/scenario_compare_request.schema.json`](core/schemas/scenario_compare_request.schema.json) | [`core/schemas/examples/scenario_compare/*.request.json`](core/schemas/examples/scenario_compare/) |
| Scenario Compare 출력 | [`core/schemas/scenario_compare_result.schema.json`](core/schemas/scenario_compare_result.schema.json) | [`core/schemas/examples/scenario_compare/*.result.json`](core/schemas/examples/scenario_compare/) |

## 결과 해석: status 값

모든 계산값은 단순 숫자가 아니라 status를 함께 가집니다. 서로 다른 두 가지 status 어휘 체계가
있으므로 혼동하지 마십시오:

- **Per-metric status** (`contribution_margin` 같은 개별 숫자에 대한 것): `OK` — 모든 의존값이
  해소됨; `UNKNOWN` — 필요한 입력이 없음(null); `ESTIMATED` — 확정된 입력이 아니라 가정/기본값으로
  계산됨; `NOT_APPLICABLE` — 이 component/product 형태에서는 이 metric 자체가 의미가 없음(예:
  고정비 항목이 아예 없을 때의 손익분기 수량); `ERROR` — 입력은 있었지만 계산 자체가 실패함(예:
  모순되는 입력).
- **Module-level status** (`mode_a`/`mode_b`/`mode_c`/`bep` 전체에 대한 것): `OK`, `INCOMPLETE`
  (해당 module의 metric 중 하나 이상이 `UNKNOWN`), `ERROR`, `NOT_RUN`, `NOT_IMPLEMENTED`.
  module 레벨에는 `UNKNOWN`이나 `NOT_APPLICABLE`이 없습니다 — 이 두 값은 metric 레벨에만
  존재합니다.

**Scenario Compare와 invalid baseline**: *baseline* scenario 자체가 검증에 실패하면, 다른
유효한(valid) scenario들의 절대값 결과는 그대로 정상적으로 계산되고 표시됩니다 — 오직 그
scenario의 baseline 대비 delta만 `ERROR`가 됩니다(비교할 유효한 대상이 없기 때문입니다). 유효한
sibling scenario가 관련 없는 baseline의 실패 때문에 불이익을 받는 일은 없습니다.

## Excel Simulator

[`tools/excel_simulator/Pricing_Harness_Excel_Simulator_v0.5.xlsx`](tools/excel_simulator/Pricing_Harness_Excel_Simulator_v0.5.xlsx)는
tracked된, 바로 열어 쓸 수 있는 workbook입니다 — 사용하기 위해 무언가를 빌드할 필요가 없습니다.
이것은 **presentation/parity layer**이며, Python Core의 모든 기능을 그대로 1:1로 옮긴 UI가
아닙니다: 각 mode 입력의 단순화된 대표 슬롯(representative slot) 버전만 노출하며(
[현재 제한사항](#현재-제한사항-current-limitations) 참고), 주로 공식을 라이브로 시연하고
Python↔Excel drift를 잡아내기 위해 존재합니다.

현재 formula-generation 코드로부터 재생성하려면:

```bash
python tools/excel_simulator/build_workbook.py
```

이 명령은 현재 작업 디렉터리와 무관하게 항상
`tools/excel_simulator/Pricing_Harness_Excel_Simulator_v0.5.xlsx`(스크립트 자신의 위치 기준
상대 경로)에 저장합니다.

## Excel QA

```bash
python tools/excel_simulator/qa_check.py                     # MODE A
python tools/excel_simulator/qa_check_mode_b.py               # MODE B
python tools/excel_simulator/qa_check_mode_c.py               # MODE C
python tools/excel_simulator/qa_check_bep.py                  # BEP
python tools/excel_simulator/qa_check_scenario_compare.py     # Scenario Compare
```

각 스크립트는 tracked workbook을 **LibreOffice headless**로 재계산해(캐시된 값이 아니라 수식이
실제로 다시 평가됨) Python으로 계산한 참조값과 비교합니다. **현재 제한사항**: LibreOffice
실행 파일 경로가 현재 각 스크립트 안에 Windows 기본 설치 경로
(`C:\Program Files\LibreOffice\program\soffice.exe`)로 하드코딩되어 있습니다 — 다른 OS나
기본 설치 경로가 아닌 환경에서는 이 경로를 직접 수정하기 전까지 QA 스크립트가 실행되지 않습니다.
이것은 LibreOffice에 전혀 의존하지 않는 Python Core, 테스트 스위트, schema validation에는 영향을
주지 않습니다.

## Tests / Validation (테스트/검증)

```bash
pytest                                    # Python 단위 테스트
python core/schemas/validate_examples.py  # 제공된 모든 example의 schema validation
```

현재 이 저장소 상태 기준 audited baseline(영구적인 보장이 아니며, 실제로 체크아웃한 commit에서
다시 실행해 확인해야 합니다):

- `pytest`: 160 passed
- schema validation: ALL 13 CHECKS PASSED
- MODE A / MODE B Excel QA: PASS
- MODE C Excel QA: 20/20 PASS
- BEP Excel QA: PASS
- Scenario Compare Excel QA: 25 cases PASS
- raw Excel errors: 0

## 현재 제한사항 (Current limitations)

- Scenario Compare의 **interactive Excel UI**는 한 번에 최대 5개 scenario만 지원합니다; Python
  Core에는 이런 상한이 없습니다(최소 2개, 그 외에는 무제한).
- Excel의 cost override는 몇 개의 **대표 슬롯**(직접원가, 고정운영비, gross-payment fee rate
  하나)만 노출합니다; Python Core는 임의의 `item_id`/`component_id` override를 지원합니다.
- Scenario Compare는 **Excel에서 multi-component를 지원하지 않습니다**(Python Core의
  multi-component BEP gate를 Excel에서 실행할 입력 구조가 없습니다).
- **Structural override**(scenario 내에서 price component나 cost item을 추가/삭제하는 것)는
  Python Core와 Excel 어느 쪽에서도 지원하지 않습니다 — 기존 필드의 값을 바꾸는 것만 가능합니다.
- 실제 **shared-cost allocation engine**은 아직 어디에도 구현되어 있지 않습니다; Excel은 테스트
  전용 컨트롤로 allocation-status 상태(`none`/`unresolved`/`invalid`)만 시뮬레이션하며, Python
  Core도 아직 여러 component에 걸쳐 공유 cost item을 배분하지 않습니다.
- `build_workbook.py`는 import-time side effect를 가지고 있습니다(모듈을 import하는 것만으로
  workbook이 재생성·저장됩니다) — 항상 스크립트로 실행하십시오
  (`python tools/excel_simulator/build_workbook.py`), 다른 스크립트나 REPL에서
  `import build_workbook`으로 불러오지 마십시오.

## Version identity (버전 체계)

Pricing Harness에는 네 개의 독립적인 버전 축이 있습니다 — 각각 서로 다른 것을 추적하며, 서로
일치할 필요가 없고, 어느 하나가 다른 하나가 다루는 범위를 대신 커버한다고 읽어서는 안 됩니다.

| 축 | 현재 값 | Source of truth | 추적하는 대상 |
|---|---|---|---|
| **Product release** | `0.1.0-beta.3` | root [`VERSION`](VERSION) 파일, git tag `v0.1.0-beta.3` | 어느 시점의 Pricing Harness 전체(Python Core + schema + Excel Simulator + 문서). 이 sanitized 공개 저장소의 release identity이며 — 현재 성숙도는 **Limited/Beta**입니다. |
| Python engine marker | `0.4.0` | [`core/engine/result_builder.py`](core/engine/result_builder.py)의 `ENGINE_VERSION` | 계산 엔진 자체의 내부 iteration으로, 생성되는 모든 Analysis Result의 `source.engine_version` 필드에 기록됩니다. |
| Excel Simulator artifact | `v0.5` | workbook 파일명 자체, `Pricing_Harness_Excel_Simulator_v0.5.xlsx` | Python engine이나 product release와 무관한, 이 특정 Excel build 자체의 iteration. |
| Schema / data contract | `1.1` | 모든 Client Input / Analysis Result / Scenario Compare 문서 안의 `schema_version` 필드 | 시스템을 흐르는 JSON 문서의 *모양(shape)* — 소프트웨어 릴리스가 아니라 데이터 호환성 버전입니다. |

이 네 숫자는 설계상 시간이 지나며 서로 달라집니다: schema migration, engine 전용 공식 수정,
Excel 전용 build는 각각 다른 축을 바꾸지 않고도 일어날 수 있습니다. product release 버전은
`VERSION`(또는 일치하는 git tag)에서 읽으십시오 — Excel 파일명이나 `ENGINE_VERSION`에서
추론하지 마십시오.

## Repository map (저장소 구조)

```
core/                  모든 클라이언트가 공유하는 공식, schema, 계산 로직 — 회사명 없음
core/engine/           Pricing Engine 본체(MODE A/B/C, BEP, Scenario Compare) — core/engine/README.md 참고
core/schemas/          JSON Schema contract(Client Input, Analysis Result, Scenario Compare) + 제공되는 example
docs/features/         기능별 SPEC/METHOD/CASE 3종 세트(mode_a_current_price/, mode_b_target_price/, ...)
tests/                 기능별 pytest 단위 테스트
tools/excel_simulator/ Excel workbook 빌더 + QA 스크립트(Python↔Excel parity)
```

`clients/`, `samples/`, `cases/`, `curriculum/`은 위
[Four content areas](#four-content-areas-네-가지-콘텐츠-영역)에서 설명합니다.

## Out of scope for now (현재 범위 밖)

의도적으로 미룬 항목입니다(폴더/데이터 형태는 향후 호환되도록 유지):

- 외부 경쟁사 조사, 시장 조사, AI 기반 가격 전략 생성
- 자동 리포트 생성
- 자동 견적서 생성
- 웹 대시보드
