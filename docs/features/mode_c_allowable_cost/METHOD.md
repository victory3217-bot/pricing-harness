# MODE C — Allowable Direct Cost — METHOD (DRAFT)

```
Methodology source status:
- Pricing Harness Internal Specification: ACTIVE (design draft, not yet coded)
- Master Note derived methodology reference: ACTIVE (via MASTER_NOTE_PRICING_REFERENCE.md)
- Direct Master Note source access in this repository: NOT AVAILABLE
- External academic/reference validation: PENDING
```

This repository does not hold the Startup Master Note original. Every claim below attributed to
the Master Note is sourced only through
[`docs/reference/MASTER_NOTE_PRICING_REFERENCE.md`](../../reference/MASTER_NOTE_PRICING_REFERENCE.md)
and its cross-references — never quoted or paraphrased as if from the original text.

## Business Purpose

A client rarely gets to set price from a blank page. Far more often, the market already tells
them what a customer will pay — a competitor's price, an existing price point, a price the
client is unwilling to raise. MODE A tells them what that price is currently earning. MODE B
tells them what price they would need if they insist on today's cost structure and profitability
target. **MODE C answers the question that comes up when neither of those is the actual
constraint**: *"The price is fixed. My margin target is fixed. Given that, how much can this
product actually cost to make?"*

This is the classic **target costing** move: instead of building a product and discovering
afterward whether it can be priced profitably (cost-plus thinking), you start from the price the
market will bear and the margin the business needs, and derive the cost ceiling the product
design must live inside. MODE C is the Pricing Harness's numeric implementation of that
direction of reasoning.

Business question:

> "시장가격과 목표 Contribution Margin Rate가 주어졌을 때, 허용 가능한 최대 product/service
> direct cost는 얼마인가?"

## Master Note Supported Concept

> Source: consistent with the concepts MODE A/B already cite from
> MASTER_NOTE_PRICING_REFERENCE §13 (MN06 primary, MN04 secondary via §3.5)

Ideas the Reference attributes to the Master Note that MODE C is a direct application of
(paraphrased from the Reference, not the original text):

1. 고객이 지불하는 것은 원가가 아니라 가치다 — MODE C's very premise is that the price is set by
   the market/customer, not derived from cost; cost only enters afterward, as a constraint the
   *product design* must satisfy.
2. 원가는 가격의 현실적 제약조건이다 — MODE A/B already apply this in the "cost limits what
   price can achieve a margin" direction; MODE C applies the same idea in reverse: **price
   limits what cost can be afforded**. Same constraint relationship, opposite unknown.
3. 고객가치 기반 가격은 지불의사를 확인한 뒤 원가·상품구성을 역으로 검토한다 — MODE C is the
   "원가·상품구성을 역으로 검토" half made numeric: once willingness-to-pay (the market price) is
   known, MODE C tells you exactly how far product cost/sourcing/design decisions can go before
   they break the required margin.
4. 가격은 경쟁·포지셔닝과 연결된다 — a MODE C result that yields an uncomfortably low (or
   negative — see §8 of SPEC.md) allowable cost is a signal to revisit sourcing, product scope,
   the target margin itself, or whether this price point is even the right one to compete at —
   not a number to force through regardless.

## Internal Specification Boundary

As with MODE A and MODE B, the Reference does **not** define:

- a concrete formula for inverting a target Contribution Margin Rate into an allowable direct
  cost, or
- how VAT, channel/PG fees, and non-product variable costs combine algebraically in that
  inversion.

Everything in `SPEC.md` — the terminology (N/G/t/b/a/F/ADC), the derivation, the VAT-dependency
table, the negative-ADC treatment, and every UNKNOWN/ERROR rule — is **Category B, Pricing
Harness Internal Specification**. When teaching or writing a consulting report, the correct
framing is the same one MODE B already established: *"이 계산식은 Pricing Harness가 target
costing 개념을 수식화한 것이며, Master Note 원문이 확정한 공식이 아니다."*

## MODE A / B / C relationship — how they compose

```
MODE A: price (given)         + cost (given)   -> CM (diagnosis)
MODE B: cost (given)          + target CM      -> price (the unknown)
MODE C: price (given, market) + target CM      -> allowable direct cost (the unknown)
```

All three solve the same underlying Contribution Margin identity
(`CM = N − direct_cost − F − bN − aG`) for a different unknown. In a full engagement, the three
modes are typically used in sequence:

1. **MODE A** establishes where the client actually stands today.
2. If the current margin is below target, **MODE B** asks "what price would fix this, holding
   cost fixed?"
3. If the answer to (2) is not realistic (the market won't bear that price), **MODE C** flips the
   question: "holding the *market* price fixed instead, what does the *cost* need to look like?"

MODE C does not replace MODE B — it is the mirror-image question for the (very common) case
where price is the constraint, not cost.

**Where MODE C's "market price" actually comes from (SPEC.md §1a-§1c, revised)**: MODE C does
**not** reuse MODE A's `actual_price` — an earlier draft of this document proposed that, and it
was withdrawn, because a real engagement often needs *both* numbers at once: "we currently charge
90,000, but the market has moved to 100,000" is exactly the situation MODE C exists to analyze,
and one field cannot hold two different values. MODE C instead reads a new field,
`product.price_components[].target_market_price` (a schema addition, not yet applied — SPEC.md
§1a), placed alongside `actual_price` in the same component so it automatically shares that
component's `price_includes_vat`/`currency` without needing its own copy of either. `actual_price`
stays exclusively MODE A's number; MODE C never reads it. The existing global
`targets.target_market_price` field (already in schema, unused by every mode today) was
considered and rejected as the home for this — it has no VAT basis of its own and, being global,
cannot hold a different market price per component the way a hardware+SaaS hybrid product would
need (SPEC.md §1b).

**`targets.target_market_price`'s final status: legacy, scheduled for removal.** This is not
just "unused for now" — no engine has ever read it, and keeping two same-purpose price fields
(one global, one per-component) around indefinitely would invite exactly the "which one does
MODE C actually read" confusion this whole decision exists to prevent, and would tempt a future
implementer into writing fallback logic between them. MODE C is designed from the start to read
`price_components[].target_market_price` **only**, with no fallback to the global field. The
global field's removal from `client_input.schema.json` happens at MODE C's implementation step,
not in this documentation-only round.

**`target_market_price` is an effective price, not a list price (SPEC.md §1d).** It is the
number the customer actually pays — discount, if any, already applied. `100,000` list price at
an expected `10%` discount means `target_market_price = 90,000`, not `100,000`.
`price_includes_vat` only says whether that 90,000 is VAT-inclusive or not; it says nothing
about discounting, which has already happened by the time MODE C sees the number. This mirrors
how MODE A's `actual_price` and MODE B's `required_selling_price` are also effective prices —
only MODE B additionally computes a *list*-price view (`required_list_price`), because only
MODE B's question ("what should the price tag say") needs one. MODE C has no such output and
does not read `discount_rate` — see SPEC.md §1e for the full A/B/C price-field comparison.

## 사용 시점 (When to use)

- 시장가격이 사실상 고정되어 있거나(경쟁 구조, 기존 가격 포지셔닝, 고객 저항) MODE B가 제시한
  필요 가격이 현실적으로 받아들여지지 않을 때.
- 신제품/신규 소싱 결정 전, "이 가격대에서 원가를 얼마까지 쓸 수 있는가"를 먼저 확정하고 싶을 때.
- 기존 제품의 실제 원가가 허용원가를 넘어서고 있는지 점검하고 싶을 때(`direct_cost_gap`).
- **사용하지 말아야 할 때**: 목표 CM Rate 자체가 근거 없이 정해진 경우 — MODE B와 동일하게, 목표율의
  타당성은 컨설턴트의 판단 영역이며 MODE C는 이를 검증하지 않는다.

## 컨설팅 해석 (Consulting interpretation)

- **`allowable_direct_cost`가 충분히 큰 양수일 때**: 원가 여유가 있다는 뜻이며, 이 여유를
  어디에 쓸지(마진 확대, 상품 고도화, 마케팅 투자)는 컨설턴트/클라이언트의 판단 영역이다.
- **`allowable_direct_cost`가 작은 양수이거나 0에 가까울 때**: 원가 여유가 거의 없다 — 소싱
  단가가 조금만 올라도 목표 달성이 무너지는 구조라는 조기 경고다.
- **`allowable_direct_cost`가 음수일 때 (SPEC.md §8)**: "계산이 잘못됐다"가 아니라 **"이 시장
  가격과 이 비용구조로는 direct cost를 0으로 잡아도 목표 마진에 도달할 수 없다"**는 확정적
  진단이다. 다음 선택지 중 하나가 필요하다 — 목표율을 낮춘다, 채널/PG 수수료 구조를 재협상한다,
  이 가격대에서의 경쟁을 재고한다, 비직접 변동비(F/b/a) 자체를 줄인다. MODE C는 이 선택을
  대신하지 않는다.
- **`direct_cost_gap` (SPEC.md §9)**: 현재 실제 원가가 이미 존재하는 제품/서비스라면, gap이
  목표와 현실의 거리를 바로 보여준다 — "지금 원가를 얼마나 낮춰야 목표 마진에 도달하는가"에
  대한 즉답이다.
- **UNKNOWN이 나올 때**: MODE A/B와 동일한 원칙 — "지금은 답할 수 없다"와 "이 가격/비용
  구조로는 안 된다"를 혼동하지 않는다.

## 교육 포인트

1. **MODE B와 MODE C는 같은 항등식을 반대 방향으로 푼다** — `CM = N − direct_cost − F − bN −
   aG`라는 하나의 식에서, MODE B는 `direct_cost`(=C)를 알고 `N`(가격)을 풀고, MODE C는 `N`을
   알고 `direct_cost`(=ADC)를 푼다. 학생에게는 "왜 같은 식이 정반대 도구가 되는가"를 먼저
   이해시킨다.
2. **나눗셈이 아니라 곱셈이라는 것의 실무적 의미** — MODE B의 `N = C/D`는 나눗셈이라 `D≤0`이면
   계산이 아예 불가능해진다(ERROR). MODE C의 `ADC = N·D − F`는 곱셈이라 `D`가 무엇이든(0이든
   음수든) 항상 계산된다 — 대신 결과가 "말이 안 되는 숫자"(음수 원가)로 나타날 수 있다.
   "계산이 안 되는 것"과 "계산은 되지만 답이 불리한 것"은 다른 종류의 신호라는 것을 이 대비로
   가르친다(SPEC.md §3, §8).
3. **VAT dependency는 여전히 metric별로 판단한다** — MODE A/B에서 확립된 원칙이 MODE C에서도
   그대로 적용된다: `a=0`이면 표시가격 방식과 무관하게 `v` 없이 ADC 계산 가능, `a>0`이면 `v`
   필요. 이 원칙이 세 번째 Mode에서도 깨지지 않고 재사용된다는 것 자체가, 이 원칙이 "MODE B의
   특수 규칙"이 아니라 이 Harness 전체의 경제적 사실이라는 것을 보여주는 교육포인트다.
4. **direct cost와 allowable direct cost는 다른 metric이다** — SPEC.md §5/§9에서 강조하듯,
   실제 원가를 허용원가 계산식에 넣으면 순환논리가 된다. 둘을 완전히 독립적으로 계산한 뒤 마지막에
   `gap`으로만 비교하는 구조가, "지금 얼마 쓰고 있는가"와 "얼마까지 쓸 수 있는가"를 섞지 않는
   Harness의 원칙을 보여준다.
5. **음수 ADC를 0으로 clamp하지 않는다** — null≠0 원칙의 또 다른 얼굴이다. "달성 불가능한 목표"를
   "원가 0이면 된다"는 그럴듯한 숫자로 덮어버리면, 그 목표 자체가 비현실적이라는 신호를 컨설턴트가
   놓치게 된다.
6. **"항목이 아예 없음"과 "항목은 있는데 값이 null"은 다른 상태다** — MODE A/B에서 이미 확립된
   원칙이지만 F/b/a 세 집계가 동시에 등장하는 MODE C에서 특히 헷갈리기 쉽다. 해당 종류의
   비용 항목이 하나도 없으면 그 합계는 확정된 0(`OK`)이고, 항목은 존재하는데 `amount`/`rate`가
   아직 입력되지 않았으면 UNKNOWN이다(SPEC.md §5, CASE.md TC17 vs TC18). "필요한 비용이 없어서
   UNKNOWN"이라는 뭉뚱그린 표현은 이 둘을 섞어버리므로 쓰지 않는다.
7. **`allowable_direct_cost`는 `actual_direct_cost`를 전혀 모른다** — ADC 공식(§3)은
   `product_service_direct_cost` 항목을 한 번도 읽지 않는다. 그래서 실제 원가 데이터가 아직
   없거나(그 자체로 UNKNOWN), 심지어 그 실제 원가가 shared 항목이라 배부조차 안 되는
   상황이라도(CASE.md TC19, TC20), `allowable_direct_cost`는 전혀 흔들리지 않고 정상 계산된다.
   반대로 변동비(F/b/a) 쪽 shared 항목이 미해결이면 `allowable_direct_cost` 자체가 UNKNOWN이
   된다(CASE.md TC14) — 두 종류의 "shared 미해결"이 서로 다른 지표에만 영향을 준다는 것을
   구분해서 가르친다(SPEC.md §9의 Case A/B/C).
8. **`target_market_price`는 effective price이지 list price가 아니다** — 할인이 있다면 이미
   반영된, 고객이 실제로 지불하는 금액이다. `price_includes_vat`는 이 실거래가가 VAT
   포함/제외인지만 나타낸다. MODE B의 `required_selling_price`(effective)/`required_list_price`
   (할인 전 정가) 구분과 정확히 대응하는 개념이지만, MODE C는 list price에 해당하는 출력이
   없으므로 `discount_rate`를 아예 읽지 않는다(SPEC.md §1d, §1e).

## Not covered here

Whether `ADC = N[1−t−b−a(1+v)] − F`의 대수 형태가 target costing 문제를 표현하는 유일한 방식인지는
Reference가 다루지 않으며 확정된 것으로 주장하지 않는다 — 이는 Category B이며, 실제 사례에 적용되며
계속 검토될 수 있다.
