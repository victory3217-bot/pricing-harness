# MASTER_NOTE_MAPPING

> Status: Working mapping, v0.1
> Purpose: track which Pricing Harness function connects to which part of
> `docs/reference/MASTER_NOTE_PRICING_REFERENCE.md`, and to what degree
> Source of all Master-Note-derived claims: **MASTER_NOTE_PRICING_REFERENCE.md only.**
> This repository does not hold the Startup Master Note original — nothing here is a direct
> quotation of it. Citations point at Reference sections, never at the original.

Citation format used throughout this file:

```
Source: MASTER_NOTE_PRICING_REFERENCE §N
Underlying Master Note: MNxx
```

## Category legend

| Code | Meaning |
|---|---|
| **A** | Master Note directly supports this (per the Reference) |
| **B** | Pricing Harness Internal Specification — the Reference explicitly does *not* confirm a formula/standard here |
| **C** | `PENDING METHODOLOGY SOURCE` — no Reference section covers this; do not attribute to Master Note |

Per-function fields: Harness Function · Business Question · Reference Section · Underlying
Master Note · Master Note Supported Concept (A) · Internal Specification Needed (B) · Current
Implementation Status · Future Validation Needed.

---

## 1. MODE A — Current Price Diagnosis

- **Business Question**: 현재 이 가격으로 판매하면 한 단위의 거래에서 실제로 얼마가 남는가?
- **Reference Section**: §12 (primary), §5.1, §5.2, §5.4, §11
- **Underlying Master Note**: MN06 (Primary), MN05 (Secondary) — per Reference §11/§18
- **[A] Master Note Supported Concept**: 원가를 모르고 가격을 정할 수 없다; 생산뿐 아니라 판매·유통 활동에서도 비용이 발생한다; 채널비용이 가격구조를 바꾼다; 현재 가격·비용구조의 지속가능성을 확인해야 한다.
- **[B] Internal Specification Needed**: `actual_price_ex_vat`/`direct_cost_total`/`gross_profit`/`gross_profit_rate`/`variable_cost_total`/`contribution_margin`/`contribution_margin_rate`의 구체 계산식 전체 — Reference §5.4가 "Master Note 원문에서 직접 확정된 정의가 아니다"라고 명시.
- **Current Implementation Status**: Implemented — `core/engine/modes/mode_a.py`, `tests/test_mode_a.py` 8/8 PASS, Excel Simulator v0.1 parity 28/28 + QA 56/56 PASS.
- **Future Validation Needed**: 매출총이익·공헌이익 등 마진 개념의 통일된 관리수준 (§16).

---

## 2. MODE B — Target Price

- **Business Question**: 목표 경제성을 확보하려면 판매가격이 얼마여야 하는가?
- **Reference Section**: §13 (MODE B), §3.2, §11
- **Underlying Master Note**: MN06 (Primary), MN04·MN07 (Secondary)
- **[A] Master Note Supported Concept**: 원가는 가격의 현실적 제약조건이다; 고객이 지불하는 것은 원가가 아니라 가치다; 고객가치 기반 가격은 지불의사를 확인한 뒤 원가·상품구성을 역으로 검토한다; 가격은 경쟁·포지셔닝과 연결된다.
- **[B] Internal Specification Needed**: 목표 Contribution Margin Rate 기반 역산 공식, VAT·복수 비율수수료를 포함한 대수적 계산식 — §13이 "Master Note가 아직 확정하지 않은 범위"로 명시.
- **Current Implementation Status**: Not implemented.
- **Future Validation Needed**: 업종별/B2C·B2B·B2G별 Target Price 공식의 표준화 가능성 (§16).

---

## 3. MODE C — Allowable Cost

- **Business Question**: 시장가격이 정해져 있을 때 목표 경제성을 확보하려면 상품원가는 최대 얼마여야 하는가?
- **Reference Section**: §13 (MODE C), §11
- **Underlying Master Note**: MN06 (Primary), MN07 (Secondary)
- **[A] Master Note Supported Concept**: 받아들일 수 있는 가격에서 사업성이 성립하도록 원가·상품구성을 역으로 검토한다; 비용이 감당되지 않으면 상품기능·고객군·채널을 재설계할 수 있다; 사업타당성은 비용·가격·자원·고객을 반복 조정하는 과정이다.
- **[B] Internal Specification Needed**: Allowable Cost 표준공식, 어떤 비용까지 allowable product cost에 포함할지의 세부 회계정책 — §13이 명시적으로 미확정 영역으로 구분.
- **Current Implementation Status**: Not implemented.
- **Future Validation Needed**: Allowable Cost의 범용 정의 (§16).

---

## 4. Customer/Buyer Pricing Context

- **Business Question**: 누가 문제를 겪고, 누가 구매를 결정하고, 누가 비용을 지불하는가?
- **Reference Section**: §2.1–2.3, §11
- **Underlying Master Note**: MN03 (Primary), MN07 (Secondary)
- **[A] Master Note Supported Concept**: User(문제 경험자)·구매결정자·지불주체를 구분한다; 문제의 존재보다 심각성과 구매이유(KBF)가 중요하다; B2C/B2B/B2G에 따라 구매구조가 달라진다.
- **[B] Internal Specification Needed**: 이 개념을 Client Input 스키마나 Analysis Result에 어떻게 데이터로 담을지는 아직 설계되지 않음 — 현재 스키마(`client_input.schema.json`)에는 대응 필드 없음.
- **Current Implementation Status**: Not implemented (코드/스키마 없음).
- **Future Validation Needed**: 고객 지불의사를 측정하는 표준 검증방법과 임계값 (§16).

---

## 5. Value Pricing

- **Business Question**: 고객이 어떤 가치 때문에 이 가격을 받아들이는가?
- **Reference Section**: §3.1, §3.2, §11
- **Underlying Master Note**: MN06 (Primary), MN03·MN04 (Secondary)
- **[A] Master Note Supported Concept**: 고객이 지불하는 것은 원가가 아니라 가치다; 고객가치 기반 가격결정은 세그먼트의 지불의사를 먼저 확인하고 원가·상품구성을 역으로 검토하는 접근이다.
- **[B] Internal Specification Needed**: 가격 하한·상한을 실제 숫자로 산정하는 절차 — §3.2가 "Master Note는 표준 공식까지 확정하지 않았다"고 명시.
- **Current Implementation Status**: Not implemented.
- **Future Validation Needed**: 가격 하한선과 상한선을 실제 숫자로 산정하는 표준 절차 (§16).

---

## 6. Competitive Pricing

- **Business Question**: 고객이 실제로 비교하는 대안과 비교지표는 무엇인가?
- **Reference Section**: §3.3, §3.4, §11
- **Underlying Master Note**: MN04 (Primary), MN06 (Secondary)
- **[A] Master Note Supported Concept**: 경쟁자는 같은 제품을 파는 기업만이 아니라 같은 문제를 해결하는 경쟁재·대체재다; 비교지표는 기업이 자랑하고 싶은 사양이 아니라 고객의 구매결정 기준이어야 한다.
- **[B] Internal Specification Needed**: 비교지표를 정량화·가중치화하는 방법 — Reference에 구체 방법론 없음, 프로젝트가 별도 설계해야 함.
- **Current Implementation Status**: Not implemented in Core. (Case 001의 구 Competitive Benchmark 시트는 Phase 1 범위에서 제외되어 별도 보관 중이며 Core 기능이 아님.)
- **Future Validation Needed**: Reference §16에 이 항목 전용 문구는 없음 — 일반 항목인 "검증 데이터의 충분성을 판정하는 공통 임계값"과 연결 가능.

---

## 7. Channel Analysis

- **Business Question**: 채널 변화가 가격·판매비용·고객경험을 어떻게 바꾸는가?
- **Reference Section**: §6.1, §11
- **Underlying Master Note**: MN06 (Primary), MN05 (Secondary)
- **[A] Master Note Supported Concept**: 간접채널은 시장접근성을 높이지만 유통마진·수수료가 발생하고, 직접채널은 유통비용을 줄이지만 고객획득·배송·서비스를 직접 부담한다; 채널이 달라지면 적정가격과 비용·마진 구조가 달라진다.
- **[B] Internal Specification Needed**: 채널별 비용 표준 배부 방식 — §16이 미확정 항목으로 명시. (현재 `cost_item.applies_to_component`/`allocation_rule` 필드는 존재하나 채널 단위 분석 기능 자체는 없음.)
- **Current Implementation Status**: Schema-level partial (배부 규칙 필드만 존재), 분석 기능 미구현.
- **Future Validation Needed**: 채널비용·고객관계 비용의 표준 배부 방식 (§16).

---

## 8. Revenue Model

- **Business Question**: 누가, 무엇에 대해, 한 번 또는 반복해서 지불하는가?
- **Reference Section**: §7.1, §7.2, §7.3, §11
- **Underlying Master Note**: MN06 (Primary), MN05 (Secondary)
- **[A] Master Note Supported Concept**: 가격을 정했다고 수익모델이 완성되는 것은 아니다; 하나의 사업이 복수 수익원을 가질 수 있다; 단발성 수익과 반복적 수익은 경제성이 다르다. §7.2는 Harness의 `price_components[]` 구조가 이 복수 수익원 개념과 정합적이라고 직접 언급.
- **[B] Internal Specification Needed**: `pricing_model`(one_time/recurring/hybrid) 유형별 구체 분석 로직 — 현재는 MODE A가 per-component 계산만 수행, revenue-model 전용 분석 기능은 없음.
- **Current Implementation Status**: Schema 구조 반영됨(`product.price_components[]`), 전용 분석 기능 미구현.
- **Future Validation Needed**: 복합 수익원(HW+SaaS 등)의 blended economics 표준 (§16) — 아래 11번 항목 참조.

---

## 9. BEP / Feasibility

- **Business Question**: 이 가격·비용구조와 판매수량에서 사업이 성립하는가?
- **Reference Section**: §8.1–8.4, §11
- **Underlying Master Note**: MN07 (Primary), MN06 (Secondary)
- **[A] Master Note Supported Concept**: MN06→MN07로 넘어가는 입력은 가격 P, 비용·마진 구조, 수익모델 세 가지다; 비즈니스모델은 정성에서 정량으로 넘어가야 하며, 특정 가격·수량에서 매출·비용·잔여이익·실행가능성까지 이어져야 한다.
- **[B] Internal Specification Needed**: BEP 계산식(고정비÷Contribution Margin 단가 등 구체 공식) — Reference에 표준 공식 없음.
- **Current Implementation Status**: Not implemented — `analysis_result.schema.json`에 `bep` 블록이 `NOT_IMPLEMENTED` 상태로만 예약되어 있음.
- **Future Validation Needed**: 검증 데이터의 충분성을 판정하는 공통 임계값 (§16).

---

## 10. Scenario Compare

- **Business Question**: 고객·채널·비용·가격의 변화가 경제성을 어떻게 바꾸는가?
- **Reference Section**: §8.4, §11
- **Underlying Master Note**: MN07 (Primary), MN05·MN06 (Secondary)
- **[A] Master Note Supported Concept**: 사업타당성은 반복 설계다 — 자원이 부족하면 고객·채널을 바꾸고, 비용이 감당 안 되면 상품·가격을 바꾸는 과정을 반복한다; Harness는 "정답 가격 하나"보다 시나리오 비교·수정가능성을 보여주는 시스템으로 설계하는 것이 Master Note 흐름과 맞다(§8.4).
- **[B] Internal Specification Needed**: 시나리오 비교 데이터 구조·UI — Gap Analysis 단계에서 `03_SCENARIO_COMPARE`로 이미 요구되었으나 아직 미설계.
- **Current Implementation Status**: Not implemented.
- **Future Validation Needed**: Reference §16에 전용 문구 없음.

---

## 11. blended economics

> **주의**: 이 항목은 Reference §11의 Harness 기능 매핑 표에 별도 행으로 존재하지 않는다. 아래는 §7.2·§16에서 간접적으로만 다뤄지는 내용이며, 전용 섹션이 없다는 점을 그대로 기록한다.

- **Business Question**: 복수 price_component(예: HW+SaaS)를 합쳐서 본 전체 계약 단위경제성은 어떤 상태인가?
- **Reference Section**: §7.2 (간접), §16 (미확정 항목으로 명시적 언급) — §11 표에는 없음
- **Underlying Master Note**: MN06 (§7.2가 인용하는 "수익원은 여러 형태를 가진다" 관련) — 단, blended 계산 자체에 대한 MN06 언급은 없음
- **[A] Master Note Supported Concept**: 하나의 사업이 복수 수익원을 가질 수 있다는 일반 원칙(§7.2)뿐. blended 계산방법론 자체는 Master Note 지지 범위 밖.
- **[C] PENDING METHODOLOGY SOURCE**: 복합 수익원의 blended economics 표준 방식 — §16이 명시적으로 "아직 확정하지 않는다"고 나열.
- **Current Implementation Status**: Not implemented — `analysis_result.schema.json`의 `blended` 블록은 `NOT_IMPLEMENTED` 스텁만 존재. MODE A 실행 시 shared-cost allocation이 필요한 경우(예: `03_hybrid_hw_saas.json`) 정직하게 UNKNOWN 처리됨(구현 확인됨).
- **Future Validation Needed**: 복합 수익원(HW+SaaS 등)의 blended economics 표준 (§16, 원문 그대로 나열된 항목).

---

## 12. Pricing Strategy AI

- **Business Question**: 원가·가치·경쟁·채널을 어떤 논리로 종합해 가격전략을 제안할 것인가?
- **Reference Section**: §10, §11
- **Underlying Master Note**: MN06 (Primary), MN03~MN05 (Secondary)
- **[A] Master Note Supported Concept**: AI는 별도의 사업개발 단계가 아니라 자료요약·비교분석·가설과 반증 비교·초안 작성 등을 가속하는 역할이다; 위험 감수·데이터 우선순위·현장데이터 vs AI추론 충돌 시 판단은 사업가·기획자 몫이다; Harness에서 AI는 계산값을 임의 수정하지 않고, UNKNOWN을 추론으로 채우지 않으며, Fact/Estimate/Assumption을 구분한다.
- **[B] Internal Specification Needed**: "최종 Pricing Strategy는 사람의 검토·승인을 거친다"는 운영규칙 — §10이 이것을 "Master Note의 AI 역할에서 직접 파생되는 것이 아니라 그 원칙을 구현하기 위한 Harness의 내부 통제 규칙"이라고 명시적으로 구분.
- **Current Implementation Status**: Not implemented (지시에 따라 착수하지 않음).
- **Future Validation Needed**: Reference §16에 전용 문구 없음.

---

## 13. Validation / Feedback

- **Business Question**: 실제 시장 데이터가 어떤 가격가설을 수정하게 만드는가?
- **Reference Section**: §9.1–9.3, §11
- **Underlying Master Note**: MN08 (Primary), MN03~MN07 (Secondary)
- **[A] Master Note Supported Concept**: 가격은 확정된 진리가 아니라 검증 대상 가설이다; 검증은 조사검증대상·측정지표·방법및계획·피드백데이터로 구조화되어야 한다; 피보팅은 데이터가 가설을 수정한 결과다.
- **[B] Internal Specification Needed**: 검증 데이터를 어떤 구조로 저장·추적할지 — Reference에 구체 스키마 없음.
- **Current Implementation Status**: Not implemented.
- **Future Validation Needed**: 검증 데이터의 충분성을 판정하는 공통 임계값 (§16).

---

## 14. Dashboard

- **Business Question**: 현재 판단과 그 근거를 어떻게 보여줄 것인가?
- **Reference Section**: §14, §11 (Dashboard/Report가 §11에서 같은 행)
- **Underlying Master Note**: MN07·MN08 (Primary), MN05·MN06 (Secondary)
- **[A] Master Note Supported Concept**: 대시보드는 숫자만 제시하지 않고 현재가격↔고객/원가/채널/경쟁/가치/Qty 등의 관계를 보여줄 수 있어야 한다; 확보되지 않은 데이터는 UNKNOWN으로 표시하고 AI가 임의 보충하지 않는다.
- **[B] Internal Specification Needed**: "Dashboard는 analysis_result만 읽고 재계산하지 않는다"는 규칙 — §14가 이를 "Master Note 내용이 아니라 Pricing Harness 내부 아키텍처 규칙"이라고 명시적으로 구분.
- **Current Implementation Status**: Partial — MODE A 범위의 Dashboard Card는 `01_SIMULATOR`(Excel) 안에 구현됨. 별도 Executive Dashboard는 미구현(사용자 지시로 MODE B/C/BEP/Scenario Compare 이후로 연기).
- **Future Validation Needed**: Reference §16에 전용 문구 없음.

---

## 15. Consulting Report

- **Business Question**: (14번과 동일 축) 현재 판단과 근거를 문서로 어떻게 설명할 것인가?
- **Reference Section**: §14, §11 (Dashboard/Report가 §11에서 같은 행)
- **Underlying Master Note**: MN07·MN08 (Primary), MN05·MN06 (Secondary)
- **[A] Master Note Supported Concept**: 14번과 동일 — 관계 표시, UNKNOWN 명시, AI 임의보충 금지.
- **[B] Internal Specification Needed**: Report 생성 규칙·템플릿 구조 — Reference에 구체 형식 없음.
- **Current Implementation Status**: Not implemented.
- **Future Validation Needed**: Reference §16에 전용 문구 없음.

---

## 16. Quotation

> **주의**: 이 항목은 Reference 문서 전체에서 별도로 다뤄지지 않는다. §11 매핑 표에도 없고, §14(Dashboard/Report)에도 포함되지 않는다.

- **Business Question**: (Reference에 정의되어 있지 않음 — 이 프로젝트의 최종 목적(§ "컨설팅 종료 후 고객사에 Dashboard/Report/Quotation 납품")에서 나온 요구사항이며, Master Note Reference 자체의 주제가 아님)
- **Reference Section**: 없음 — 해당 없음
- **Underlying Master Note**: 명시된 바 없음
- **[C] PENDING METHODOLOGY SOURCE**: 견적서(Quotation) 생성 방법론 전체 — Reference에 근거가 전혀 없으므로 Master Note 관련 내용으로 서술하지 않는다. Analysis Result를 소스로 사용한다는 아키텍처 원칙(§14의 일반 원칙 연장)만 차용 가능하고, 그 외 가격 제시 로직·조건 문구 등은 순수 Harness/프로젝트 설계 영역.
- **Current Implementation Status**: Not implemented.
- **Future Validation Needed**: N/A (근거 문서 없음).

---

## 요약 — Category 분포

| Category | 해당 항목 |
|---|---|
| **A 비중이 큰 항목** (Master Note가 문제의식/원칙을 직접 지지) | MODE A, MODE B, MODE C, Customer/Buyer, Value Pricing, Competitive Pricing, Channel Analysis, Revenue Model, BEP/Feasibility, Scenario Compare, Pricing Strategy AI, Validation/Feedback, Dashboard, Consulting Report |
| **B로 명확히 구분되어야 하는 항목** (Reference가 "미확정"이라고 직접 명시) | MODE A의 GP/CM 공식, MODE B 역산식, MODE C 표준식, blended economics |
| **C — 근거 문서 없음** | Quotation (완전), blended economics의 표준 계산방식(부분) |

---

## 다음 단계에서 반드시 지킬 것

1. 위 표의 **[A]** 문구를 확장할 때도 Reference 섹션 번호를 반드시 함께 적는다.
2. **[B]/[C]** 항목을 구현할 때 SPEC.md/METHOD.md에 "Master Note가 확정함"이라고 쓰지 않는다.
3. 이 매핑 자체도 v0.1이며, Reference가 갱신되면 이 파일도 함께 갱신되어야 한다.
