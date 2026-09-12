# MODE C — Allowable Direct Cost — CASE (DRAFT v0.1)

Fictional data only (`client_id: sample_co_epsilon`) — not any real client. No engine code
exists yet — every number below is hand-calculated per the formulas in `SPEC.md`, for review.
All cases use a single component named `main` unless noted. `v = 0.10` where a VAT rate is
known.

Every `N`/`target_market_price` value in these cases is, per `SPEC.md` §1d, the **effective
(post-discount) transaction selling price** the input field `product.price_components[].
target_market_price` would hold — not a pre-discount list price. None of these cases involve a
discount step; `discount_rate` is not read by MODE C v0.1 (§1d, §11).

## Scenario

**Sample Co. Epsilon** is deciding whether to enter a product category where the market price is
effectively fixed by competition. Management wants to know: *given that price and our required
30% Contribution Margin Rate, how much can we actually afford to spend on the product itself?*

---

**TC1 — simple, no fee at all (a=0, b=0, F=0)**
`N=100000, t=0.3, b=0, a=0, F=0`
`ADC = N(1−t−b) − aG − F = 100000×0.7 − 0 − 0 = 70000`
Check: `CM = N−ADC−F−bN−aG = 100000−70000−0−0−0 = 30000`; `CMR = 30000/100000 = 0.30` ✓

**TC2 — fixed-amount non-product variable cost (F>0)**
`N=100000, t=0.3, b=0, a=0, F=5000`
`ADC = 100000×0.7 − 0 − 5000 = 65000`
Check: `CM = 100000−65000−5000−0−0 = 30000`; `CMR = 0.30` ✓

**TC3 — net-sales fee only (b>0)**
`N=100000, t=0.3, b=0.1, a=0, F=0`
`ADC = 100000×(1−0.3−0.1) − 0 − 0 = 100000×0.6 = 60000`
Check: `CM = 100000−60000−0−10000−0 = 30000`; `CMR = 0.30` ✓

**TC4 — gross-payment fee, v known, VAT-exclusive display**
`price_includes_vat=false, target_market_price=100000 (=N), v=0.10, t=0.3, b=0, a=0.05, F=0`
`G = 100000×1.1 = 110000`
`ADC = 100000×(1−0.3−0) − 0.05×110000 − 0 = 70000 − 5500 = 64500`
Check: `CM = 100000−64500−0−0−5500 = 30000`; `CMR = 0.30` ✓

**TC5 — VAT-inclusive display, both fee types**
`price_includes_vat=true, target_market_price=110000 (=G), v=0.10 → N=100000, t=0.3, b=0.1, a=0.03, F=1000`
`D = 1−0.3−0.1−0.03×1.1 = 0.567`
`ADC = 100000×0.567 − 1000 = 56700 − 1000 = 55700`
Check: `aG = 0.03×110000 = 3300`; `CM = 100000−55700−1000−10000−3300 = 30000`; `CMR = 0.30` ✓

**TC6 — VAT-exclusive display, same underlying economics as TC5**
`price_includes_vat=false, target_market_price=100000 (=N), v=0.10, t=0.3, b=0.1, a=0.03, F=1000`
`G = 100000×1.1 = 110000` (derived, needs `v`) — same `D=0.567`, same `ADC = 55700`.
**컨설팅 해석**: TC5와 TC6은 표시가격 방식만 다르고 실제 경제 구조(N=100000, G=110000)는
동일하므로 `ADC`가 정확히 같다 — 표시방식이 허용원가를 바꾸지 않는다는 것을 직접 보여준다
(MODE A/B에서 확립된 원칙의 재확인).

**TC7 — VAT-exclusive display, `v` UNKNOWN, `a=0` (no gross-payment fee)**
`price_includes_vat=false, target_market_price=100000 (=N), v=null, t=0.3, b=0.1, a=0, F=1000`
`D = 1−0.3−0.1−0 = 0.6` (no `a(1+v)` term since `a=0` — `v` never touched)
`ADC = 100000×0.6 − 1000 = 60000 − 1000 = 59000` — **OK** despite `v` unknown.
`market_gross_payment_incl_vat` (G) — **UNKNOWN** (`v` missing) but not needed for `ADC`.

**TC8 — VAT-exclusive display, `v` UNKNOWN, `a>0` (gross-payment fee present)**
`price_includes_vat=false, target_market_price=100000 (=N), v=null, t=0.3, b=0, a=0.05, F=0`
`a>0` → `ADC` needs `G` → `G` needs `v`, which is missing.
`allowable_direct_cost` — **UNKNOWN**, dependency `tax.vat_rate`.
**컨설팅 해석**: TC7과 TC8은 "`v` 모름"이라는 조건은 같지만 결과가 다르다 — 실무적으로 중요한
질문은 "gross-payment 기준 수수료(PG사·카드사 수수료 등)가 있는가"이지 "VAT율을 아는가"가
아니다. MODE B의 TC11/TC12와 동일한 구조의 교훈이다.

**TC9 — target CM rate UNKNOWN**
`N=100000 (known), t=null, b=0, a=0, F=0`
`allowable_direct_cost` — **UNKNOWN**, dependency `targets.target_contribution_margin_rate`.

**TC10 — target CM rate invalid (t >= 1)**
`N=100000, t=1.0, b=0, a=0, F=0`
`t >= 1` → **ERROR** (explicit validity gate, SPEC.md §7 — not derived from the algebra itself;
the raw formula would compute `ADC = 100000×(1−1−0) = 0`, but a target of "100% Contribution
Margin Rate" is treated as an invalid input, not a valid answer of "ADC must be 0").
`allowable_direct_cost` — **ERROR**.

**TC11 — negative allowable direct cost (valid computation, confirmed infeasible)**
`N=10000, t=0.5, b=0.3, a=0.3, v=0.10, F=0`
`D = 1−0.5−0.3−0.3×1.1 = 1−0.5−0.3−0.33 = −0.13`
`G = 10000×1.1 = 11000`
`ADC = 10000×(−0.13) − 0 = −1300`
Check: `CM = 10000−(−1300)−0−3000−0.3×11000 = 10000+1300−3000−3300 = 5000`; `CMR = 5000/10000 =
0.50 = t` ✓ (self-check still holds exactly even though `ADC` is negative)
`allowable_direct_cost` — **OK**, `value = −1300`, with a non-blocking warning
`NEGATIVE_ALLOWABLE_COST`.
**컨설팅 해석**: "계산 불가"가 아니라 **"이 시장가격·수수료 구조로는 direct cost를 0으로
잡아도 목표 50% Contribution Margin Rate를 달성할 수 없다"**는 확정적 진단이다. 목표율을
낮추거나, 채널·PG 수수료를 재협상하거나, 이 가격대 자체를 재검토해야 한다.

**TC12 — actual direct cost below allowable (gap > 0)**
Same as TC1: `ADC = 70000`. `actual_direct_cost = 50000` (entered).
`direct_cost_gap = 70000 − 50000 = 20000` — 현재 원가에 20,000만큼 여유가 있음.

**TC13 — actual direct cost above allowable (gap < 0)**
Same as TC1: `ADC = 70000`. `actual_direct_cost = 90000` (entered).
`direct_cost_gap = 70000 − 90000 = −20000` — 현재 원가가 목표 마진이 허용하는 한도를
20,000 초과.

**TC14 — unresolved shared cost (F item)**
동일 시나리오, 단 F를 이루는 비용 중 하나가 `applies_to_component: "shared"`,
`allocation_rule: "by_component_revenue"`로 설정되어 아직 배부 불가.
`F` — **UNKNOWN**, code `UNSUPPORTED_SHARED_COST_ALLOCATION`, dependency
`blended.allocation[<item_id>]`.
`allowable_direct_cost` — **UNKNOWN** (F가 UNKNOWN이므로 downstream 전파).

**TC15 — shared + direct invalid configuration**
동일 시나리오, 단 `b`를 이루는 비용 항목 하나가 `applies_to_component: "shared"`,
`allocation_rule: "direct"`로 설정(의미적 모순).
`b` — **ERROR**, code `INVALID_ALLOCATION_CONFIGURATION`, dependency
`costs.items[<item_id>].allocation_rule`.
`allowable_direct_cost` — **ERROR** (b가 ERROR이므로 downstream 전파).

**TC16 — explicit zero rate does not block computation**
`N=100000, t=0.3, b=0 (explicit), a=0.05, v=0.10, F=0`
`b=0`은 명시적 확정값이지 미입력이 아니므로 TC4와 산술적으로 동일한 결과:
`G=110000`; `ADC = 100000×(1−0.3−0) − 0.05×110000 − 0 = 70000−5500 = 64500` — **OK**.
Confirms `b=0` (explicit) is treated identically to "no net-sales fee item at all," not as
UNKNOWN — contrast with TC9's `t=null`.

**TC17 — no variable-cost items at all (confirmed 0, not UNKNOWN)**
`N=100000, t=0.3`. No `variable_selling_delivery` cost item exists for this component at all —
not F, not b, not a.
Per SPEC.md §5's no-item-vs-null table (row 1): `F=0, b=0, a=0`, all **confirmed, status OK**
(nothing to sum is not missing data).
`ADC = 100000×(1−0.3−0) − 0×G − 0 = 70000` — **OK**. Numerically identical to TC1, but TC1 never
actually specified whether the zero fees came from confirmed-absent items or explicit `0`
entries — TC17 pins down the "no item at all" branch specifically.

**TC18 — a matching variable-cost item exists but its value is null (UNKNOWN, not 0)**
`N=100000, t=0.3, F=0, a=0`. One `variable_selling_delivery` item exists with
`basis=rate_of_net_sales`, `applies_to_component=main`, but `rate=null` (not yet entered).
Contrast with TC17: here an item **does** match — it is simply incomplete.
`b` — **UNKNOWN**, dependency `costs.items[<item_id>].rate`.
`allowable_direct_cost` — **UNKNOWN** (inherits `b`'s UNKNOWN). This is the row-2 case from
SPEC.md §5's table — must not be confused with TC17's row-1 case, even though both eventually
show `allowable_direct_cost` as something other than a clean positive `OK` number in isolation
(TC17 is `OK`; TC18 is `UNKNOWN` — the distinction matters).

**TC19 — `actual_direct_cost` UNKNOWN, `allowable_direct_cost` unaffected (dependency isolation, Case A)**
Same base numbers as TC1: `N=100000, t=0.3, b=0, a=0, F=0` → `ADC = 70000` — **OK**, exactly as
in TC1. Separately, a `product_service_direct_cost` item **exists** for this component but its
`amount` is `null` (not yet entered) — per SPEC.md §5's no-item-vs-null table (row 2), this is
the "item present, value missing" case, not "no item at all" (row 1, which would instead give a
confirmed `0`, `OK` — the same distinction TC17 vs. TC18 pins down for F/b/a).
`actual_direct_cost` — **UNKNOWN**.
`direct_cost_gap` — **UNKNOWN** (needs `actual_direct_cost`).
`allowable_direct_cost`, `expected_contribution_margin`, `expected_contribution_margin_rate` —
all **OK**, completely unaffected. This is SPEC.md §9's Case A: a problem finding direct-cost
data must never UNKNOWN the core `ADC` metric, which never reads direct-cost items at all.

**TC20 — shared `product_service_direct_cost` allocation unresolved (dependency isolation, Case B)**
Same base numbers as TC1 again: `N=100000, t=0.3, b=0, a=0, F=0` → `ADC = 70000` — **OK**. This
time a `product_service_direct_cost` item **does** exist, but with `applies_to_component:
"shared"` and `allocation_rule: "by_component_revenue"` (unresolved — needs the not-yet-built
blended engine).
`actual_direct_cost` — **UNKNOWN**, code `UNSUPPORTED_SHARED_COST_ALLOCATION`, dependency
`blended.allocation[<item_id>]`.
`direct_cost_gap` — **UNKNOWN**.
`allowable_direct_cost` — **OK**, `= 70000`, completely unaffected — SPEC.md §9's Case B:
even a *shared-allocation* problem on the direct-cost side must not touch `ADC`, because `ADC`
never reads `product_service_direct_cost` items, shared or not. Contrast directly with TC14,
where the unresolved shared item is instead a `variable_selling_delivery` item feeding `F` —
there, `ADC` *does* go UNKNOWN, because F/b/a are exactly what `ADC`'s formula depends on
(SPEC.md §9's Case C).

---

## Summary table

| TC | Scenario | ADC | Status |
|---|---|---|---|
| 1 | no fee | 70000 | OK |
| 2 | + fixed F | 65000 | OK |
| 3 | + net-sales fee | 60000 | OK |
| 4 | + gross-payment fee, VAT-excl, v known | 64500 | OK |
| 5 | VAT-incl display, both fees | 55700 | OK |
| 6 | VAT-excl display, same economics as 5 | 55700 | OK |
| 7 | VAT-excl, v unknown, a=0 | 59000 | OK |
| 8 | VAT-excl, v unknown, a>0 | — | UNKNOWN |
| 9 | target CM null | — | UNKNOWN |
| 10 | target CM = 1.0 | — | ERROR |
| 11 | negative ADC | −1300 | OK (+ warning) |
| 12 | gap > 0 | 70000 (gap +20000) | OK |
| 13 | gap < 0 | 70000 (gap −20000) | OK |
| 14 | shared (F) unresolved | — | UNKNOWN |
| 15 | shared+direct invalid | — | ERROR |
| 16 | explicit zero rate | 64500 | OK |
| 17 | no variable-cost items at all | 70000 | OK (confirmed 0s) |
| 18 | variable-cost item exists, value null | — | UNKNOWN |
| 19 | actual_direct_cost UNKNOWN, ADC unaffected | 70000 (gap UNKNOWN) | ADC OK |
| 20 | shared actual direct cost unresolved, ADC unaffected | 70000 (gap UNKNOWN) | ADC OK |
