# MODE B — Target Price — METHOD (DRAFT)

```
Methodology source status:
- Pricing Harness Internal Specification: ACTIVE (design draft, not yet coded)
- Master Note derived methodology reference: ACTIVE (via MASTER_NOTE_PRICING_REFERENCE.md)
- Direct Master Note source access in this repository: NOT AVAILABLE
- External academic/reference validation: PENDING
```

This repository does not hold the Startup Master Note original. Every claim below attributed
to the Master Note is sourced only through
[`docs/reference/MASTER_NOTE_PRICING_REFERENCE.md`](../../reference/MASTER_NOTE_PRICING_REFERENCE.md)
§13 and its cross-references — never quoted or paraphrased as if from the original text. See
`docs/methodology/MASTER_NOTE_MAPPING.md` item 2 for the full cross-Harness mapping.

> **Corrigendum (v0.2)**: an earlier draft of `SPEC.md` assumed that a VAT-exclusive display
> price makes VAT rate irrelevant even when a gross-payment-based fee exists. That was wrong —
> gross payment is always net sales × (1+VAT), regardless of display convention. `SPEC.md` now
> uses one unified formula instead of two VAT branches. This correction also revealed the same
> error, already shipped in MODE A's code at the time (`core/engine/modes/mode_a.py`) — that
> defect is documented as a historical note in `SPEC.md` §7 and was fixed in commit `e503b5a`
> ("fix: correct VAT gross payment handling in mode A") before MODE B implementation begins.
> MODE B is designed against the corrected MODE A semantics.

## Business Purpose

MODE A answers "at the current price, what's left?" MODE B answers the inverse question a
consultant hits immediately after: *if the current price doesn't leave enough, what price
would?* Rather than guessing at a new number and re-running MODE A repeatedly, MODE B solves
directly for the price that hits a stated target.

Business question:

> "현재 원가·수수료 구조에서 목표 Contribution Margin Rate를 확보하려면 얼마에 팔아야 하는가?"

This only becomes a meaningful question once MODE A has already established what the current
cost/fee structure actually is — MODE B does not replace MODE A, it is built on top of it.

## Master Note Supported Concept

> Source: MASTER_NOTE_PRICING_REFERENCE §13
> Underlying Master Note: MN06 (primary), MN04 (secondary, via §3.5)

Four ideas the Reference attributes to the Master Note, and that MODE B is a direct application
of (paraphrased from the Reference, not the original text):

1. 원가는 가격의 현실적 제약조건이다 — the cost/fee structure MODE B solves against is exactly
   this constraint made numeric.
2. 고객이 지불하는 것은 원가가 아니라 가치다 — MODE B computes what price the *business* needs,
   which is a separate question from what a customer will actually *accept*; MODE B does not
   claim to answer the latter.
3. 고객가치 기반 가격은 지불의사를 확인한 뒤 원가·상품구성을 역으로 검토한다 — MODE B is one
   half of that reverse-check (the arithmetic half); the value/willingness-to-pay half is a
   human judgment this mode does not make.
4. 가격은 경쟁·포지셔닝과 연결된다 — a MODE B output that lands far outside the competitive
   band is a signal to revisit cost, positioning, or the target rate itself, not a number to
   accept uncritically.

## Internal Specification Boundary

The Reference is explicit (§13) that Master Note does **not** define:

- a concrete formula for inverting a target Contribution Margin Rate into a price, or
- how to fold VAT and multiple rate-based fees into that inversion algebraically.

Everything in `SPEC.md` — the terminology (N/G/C/b/a/t), the unified target-price formula, the
discount inversion, and every ERROR/UNKNOWN rule — is **Category B, Pricing Harness Internal
Specification**. None of it may be presented to a client or in training material as "Master
Note에서 정의한 공식." When teaching or writing a consulting report, the correct framing is:
*"이 계산식은 Pricing Harness가 MN06의 문제의식을 수식화한 것이며, Master Note 원문이 확정한
공식이 아니다."*

## 사용 시점 (When to use)

- MODE A를 이미 실행해 현재 가격의 Contribution Margin Rate를 확인한 **이후**.
- 현재 CM Rate가 목표(내부 기준, 투자자 요구, 업종 벤치마크 등)에 못 미칠 때 "그럼 얼마여야
  하는가"를 물을 때.
- 원가·수수료 구조가 바뀌는 시나리오(채널 변경, PG사 교체, 수수료율 협상)에서 그 변화가
  필요한 가격에 미치는 영향을 즉시 확인하고 싶을 때.
- **사용하지 말아야 할 때**: 목표 CM Rate 자체가 근거 없이 정해진 경우(예: "그냥 30%로 하자") —
  MODE B는 그 숫자가 옳은지 검증하지 않는다. 목표율의 타당성은 컨설턴트의 판단 영역이다.

## 컨설팅 해석 (Consulting interpretation)

- **결과가 시장가와 크게 다를 때**: 계산이 틀린 게 아니라, 현재 원가·수수료 구조로는 목표
  수익성과 시장가가 양립하지 않는다는 신호다. 다음 중 하나를 선택해야 한다 — 원가를 낮춘다,
  목표율을 낮춘다, 채널/수수료 구조를 바꾼다, 상품을 재설계한다. MODE B는 이 선택지를
  제시하지 않는다 — MODE C(허용원가)와 컨설턴트 판단의 영역이다.
- **ERROR(분모 ≤ 0)가 나올 때**: "계산 불가"가 아니라 "이 목표율은 현재 구조에서 어떤 가격을
  매겨도 달성 불가능하다"는 확정적 진단이다. 이는 그 자체로 강한 컨설팅 시그널이다 — 목표
  자체를 재검토해야 한다.
- **UNKNOWN이 나올 때**: 계산이 실패한 게 아니라 아직 데이터가 없는 것이다. "지금은 답할 수
  없다"와 "이 가격으로는 안 된다"를 혼동하지 않는다.
- **목표 CM Rate의 출처를 항상 기록한다**: 내부 기준인지, 투자자 요구인지, 업종 평균인지 —
  이 문서와 Client Input의 `evidence` 필드(있다면)에 남긴다. MODE B 결과를 재사용할 때 "왜
  이 목표율이었는지"를 추적할 수 있어야 한다.

## 교육 포인트

1. **역산은 정산과 다르다** — MODE A(정산: 가격→이익)와 MODE B(역산: 목표이익→가격)는 같은
   대수식을 반대 방향으로 푸는 것이다. 학생에게는 "N = C/(1-t-b-a...)" 자체보다 "왜 이 방향
   전개가 항상 유일해(단조증가함수)를 갖는지"를 먼저 이해시킨다.
2. **분모가 0 이하가 될 수 있다는 사실 자체가 교훈이다** — 비율형 비용(b, a)과 목표율(t)의
   합이 1을 넘으면 어떤 가격을 매겨도 목표에 도달할 수 없다. 이것은 "계산기가 고장난 것"이
   아니라 "사업 구조 자체의 한계"를 수식이 보여주는 사례로 가르친다.
3. **rate_of_net_sales vs rate_of_gross_payment의 차이가 여기서 더 분명해진다** — MODE A에서는
   둘 다 그냥 "변동비"였지만, MODE B에서는 이 둘이 공식의 서로 다른 자리(b는 N에, a는 G에)에
   들어가 계수 구조 자체를 바꾼다. `a` 항에만 `(1+v)`가 곱해지는 이유 — gross payment는 항상
   `N×(1+v)`이기 때문 — 를 여기서 가르친다.
4. **표시가격 방식(VAT 포함/제외)과 VAT율이 실제로 필요한지는 별개의 질문이며, 이 질문은
   지표(metric)마다 따로 답해야 한다** — "VAT율이 필요한가"는 "계산 전체"에 대한 하나의
   답이 아니라 N, G, `required_selling_price` 각각에 대해 따로 판단해야 한다:
   - `required_net_sales`(N): `a=0`이면 `v` 없이 계산 가능, `a>0`이면 `v` 필수 (표시방식과
     무관).
   - `required_gross_payment`(G): `G=N×(1+v)`이므로 `a`와 무관하게 항상 `v` 필수.
   - `required_selling_price`: `price_includes_vat=false`면 N 기준(위 N의 조건부 규칙을
     그대로 물려받음), `price_includes_vat=true`면 G 기준(항상 `v` 필수).

   이 프로젝트에서 실제로 있었던 사례로 가르친다: 초안은 "VAT 제외 표시 = VAT율 불필요"라고
   전체를 뭉뚱그려 잘못 가정했다가, gross-payment 기준 수수료가 있으면 표시방식과 무관하게
   VAT율이 여전히 필요하다는 것을 리뷰에서 지적받아 수정했다(TC11 vs TC12 비교 참고).
   "하나의 원칙이 여러 곳에 일관 적용되어야 한다"는 Harness 설계 원칙이, 그 원칙 자체가
   처음에 지표 구분 없이 잘못 적용됐던 사례로 뒤집어 보여주는 교육포인트다.
5. **할인율은 별도 레이어다** — 목표가격 계산(N, G)과 정가 역산(list price)은 서로 다른 문제다.
   할인이 커질수록(1에 가까워질수록) 필요한 정가가 발산한다는 것을 직접 계산해 보여준다.
6. **UNKNOWN과 ERROR는 다른 종류의 "못 함"이다** — MODE A에서 배운 원칙(null≠0)이 MODE B에서는
   한 걸음 더 나아가 "데이터가 없어서 못 푼다(UNKNOWN)"와 "데이터는 있지만 답이 없다(ERROR)"를
   구분하도록 확장된다.
7. **N과 G는 서로 다른 지표이고, 서로 다르게 UNKNOWN이 될 수 있다** — `a=0`(gross-payment 기준
   수수료가 아예 없음)이면 VAT율을 몰라도 `required_net_sales`는 계산되지만
   `required_gross_payment`는 여전히 UNKNOWN이다(SPEC.md TC12). 하나의 컴포넌트 안에서도
   "이 지표는 알고 저 지표는 모른다"가 동시에 참일 수 있다는 것을 보여주는 사례다.
8. **shared 비용을 0처럼 무시하면 목표가격이 실제보다 낮게 나온다** — `applies_to_component
   = "shared"`이고 아직 배부(allocation)할 수 없는 비용(`by_component_revenue`/`fixed_share`,
   또는 규칙 누락)을 만나면, MODE B는 그 비용을 조용히 빼고 계산하지 않는다. 그렇게 하면 `C`,
   `b`, `a`가 실제보다 작게 계산되어 "목표를 달성하려면 이 가격이면 된다"는 잘못된 확신을 주는
   숫자가 나온다 — null≠0 원칙이 금지하는 바로 그 실패 유형이다. 대신 그 비용에 의존하는 지표
   전체(`denominator` 이하 전부 또는 그 지표만, 어떤 집계에 걸렸는지에 따라)가 UNKNOWN이
   되고, warning code `UNSUPPORTED_SHARED_COST_ALLOCATION`로 "데이터가 없어서"가 아니라
   "아직 배부 엔진이 없어서" 못 푼다는 것을 구분해서 알린다. `"blended_only"`(애초에 컴포넌트
   단위에 절대 나타나지 않음)는 이 문제에 해당하지 않는다 — 정상 제외. `allocation_rule="direct"`는
   전혀 다른, 더 심각한 케이스다 — "shared"(특정 컴포넌트에 귀속되지 않음)와 "direct"(이미
   귀속됨)는 의미적으로 모순이므로 MODE A/MODE B 공통 canonical rule로 `ERROR`
   (`INVALID_ALLOCATION_CONFIGURATION`) 처리한다 — dependency_rules.md §4 참고.
9. **`target_contribution_margin_rate`는 현재 global이다** — 한 Client Input 안에 여러
   `price_component`(예: 하드웨어+SaaS 하이브리드)가 있어도, 지금 버전은 모든 컴포넌트에
   동일한 목표 CM율을 적용한다. 컴포넌트마다 다른 목표율이 실제로 필요한 사례가 나오면
   별도 Internal Specification addendum과 스키마 변경이 필요하다 — 이번 구현 범위에는
   포함되지 않는다.

## Not covered here

Whether the specific algebraic form in `SPEC.md` is the "correct" or only possible way to invert
a target Contribution Margin Rate (vs. alternative formulations) is not addressed by the
Reference and is not claimed to be settled — this is Category B, open to revision as the Harness
is used on real cases.
