# MODE B — Target Price — CASE (DRAFT v0.2)

Fictional data only (`client_id: sample_co_delta`) — not based on any real client. Numbers
match `SPEC.md` v0.2's TC3/TC4/TC6/TC7/TC11/TC12 so the two documents stay traceable to each
other. No engine code exists yet — every number below is hand-calculated per the corrected
formulas in `SPEC.md`, for review. (v0.1 of this CASE used an ambiguous `S`/"actual price" term
and an incorrect VAT-exclusive shortcut — see `SPEC.md`'s "Correction note" for what changed.)

## Scenario

**Sample Co. Delta** sells a subscription-based service. A MODE A run on the current price
showed a Contribution Margin Rate below what the company's investors expect. Management sets a
**target Contribution Margin Rate of 30%** and asks: *what price actually gets us there?*

Known cost/fee structure (already collected for a MODE A run, so nothing here is new data
entry):

- Fixed-amount costs (direct + amount-type variable, combined into `C`): **10,000** (KRW)
- Channel commission: **10% of net sales** → `b = 0.10` (`rate_of_net_sales`)
- PG fee: **3% of gross payment** → `a = 0.03` (`rate_of_gross_payment`)
- VAT: **10%**, and the price will be quoted **VAT-inclusive** (`price_includes_vat = true`)
- Target Contribution Margin Rate: **t = 0.30**

## Step-by-step (matches SPEC.md TC4)

```
D = 1 − t − b − a(1+v) = 1 − 0.30 − 0.10 − 0.03×1.10 = 0.567
N = C / D = 10,000 / 0.567 = 17,636.68            (required net sales, ex VAT)
G = N × (1+v) = 17,636.68 × 1.10 = 19,400.35      (required gross payment, VAT-inclusive)
```

Since `price_includes_vat = true` for this component, the headline quoted price
(`required_selling_price`) is **G**, not N.

**Cross-check** (this is exactly what MODE A would compute if fed this price back in):

```
CM = N − C − bN − aG = 17,636.68 − 10,000 − 1,763.67 − 582.01 = 5,291.01
CM / N = 5,291.01 / 17,636.68 = 0.30   ✓ matches target exactly
```

**MODE B output for this component:**

| Metric | Value |
|---|---|
| `required_net_sales` | 17,636.68 |
| `required_gross_payment` | 19,400.35 |
| `required_selling_price` ("목표 실판매가") | 19,400.35 (= `required_gross_payment`, since `price_includes_vat = true`) |
| `required_list_price` ("목표 정가") | 19,400.35 (no discount configured) |
| `expected_contribution_margin` | 5,291.01 |
| `expected_contribution_margin_rate` | 0.30 |

## Extension — with a discount (matches SPEC.md TC6)

Sample Co. Delta actually always runs a **10% promotional discount** off list price. The
19,400.35 above is the *actual selling price after discount* — the number that must appear on
the price tag (list price) is higher, on the **same** VAT-inclusive basis:

```
required_list_price = required_selling_price / (1 − discount_rate)
                     = 19,400.35 / 0.90
                     = 21,555.95
```

**컨설팅 해석**: 카탈로그/정가표에는 21,555.95를 게시하고, 10% 할인 적용 시 실제 청구액이
19,400.35가 되어야 목표 30% Contribution Margin Rate가 달성된다. 정가만 보고 "비싸다"고
판단하면 안 되고, 실제 청구액 기준으로 목표 달성 여부를 확인해야 한다.

## Extension — when the target is unreachable (matches SPEC.md TC7)

같은 회사가 채널 수수료 협상에 실패해 `b = 0.30`, `a = 0.30`으로 구조가 악화되고, 목표를
`t = 0.50`으로 올려 잡았다면 (VAT 10%는 그대로):

```
D = 1 − t − b − a(1+v) = 1 − 0.50 − 0.30 − 0.30×1.10 = −0.13   ≤ 0   →   ERROR
```

**컨설팅 해석**: 이건 "계산이 안 됐다"가 아니라 **"이 원가·수수료 구조로는 어떤 가격을 매겨도
목표 50% Contribution Margin Rate에 도달할 수 없다"**는 확정적 진단이다. 이 시점에서 필요한
것은 다른 가격이 아니라 다른 구조다 — 채널 재협상, 목표율 재검토, 또는 상품 자체의 재설계
(MODE C·컨설턴트 판단 영역).

## Extension — missing data (matches SPEC.md TC8)

동일 시나리오에서 직접원가(고정금액형 비용, `C`)가 아직 확정되지 않아 `amount = null`인 상태로
MODE B를 실행하면:

| Metric | Status |
|---|---|
| `required_net_sales` | **UNKNOWN** |
| `required_gross_payment` | **UNKNOWN** |
| `required_selling_price` | **UNKNOWN** |
| `required_list_price` | **UNKNOWN** |

**컨설팅 해석**: 목표가격을 "대략 얼마일 것"이라고 추정해 보고서에 넣지 않는다. 원가가
확정되기 전까지 이 값은 존재하지 않는 것으로 취급한다 (MODE A의 null≠0 원칙을 그대로 계승).

## Extension — VAT rate unknown: same setup, opposite outcome (matches SPEC.md TC11 vs TC12)

이번엔 다른 사업부(같은 가상 회사, `sample_co_delta_b2`)를 가정한다. VAT율이 아직 확정되지
않았고(`vat_rate = null`), 가격은 VAT 제외로 표시할 계획이다(`price_includes_vat = false`).
`C=10000, t=0.3`은 동일.

**시나리오 A — gross-payment 기준 수수료가 있는 경우 (`a=0.05, b=0`)**

VAT율을 몰라도 표시가격(N 기준)은 계산할 수 있을 것 같지만, **아니다** — `a>0`이면 CM 방정식
자체에 `a(1+v)` 항이 들어가므로 VAT율이 필요하다:

| Metric | Status |
|---|---|
| `required_net_sales` | **UNKNOWN** |
| `required_gross_payment` | **UNKNOWN** |
| `required_selling_price` | **UNKNOWN** |

**시나리오 B — net-sales 기준 수수료만 있는 경우 (`a=0, b=0.10`)**

이번엔 `a=0`이라 `a(1+v)` 항이 통째로 사라진다 — VAT율을 몰라도 N은 계산된다:

```
N = C / (1-t-b) = 10,000 / (1-0.3-0.1) = 16,666.67   →  OK (v 불필요, a=0)
```

| Metric | Status | Value |
|---|---|---|
| `required_net_sales` | **OK** | 16,666.67 |
| `required_gross_payment` | **UNKNOWN** | — (G는 VAT율 없이 절대 계산 불가) |
| `required_selling_price` | **OK** | 16,666.67 (표시기준이 N이므로 G가 없어도 됨) |
| `required_list_price` | **OK** | 16,666.67 (할인 없음) |

**컨설팅 해석**: 두 시나리오 모두 "VAT율 모름"은 같지만 결과가 다르다. 실무적으로 중요한
질문은 "VAT율을 아는가"가 아니라 **"이 상품에 gross-payment 기준 수수료가 걸려 있는가"**다.
PG사·카드사 수수료처럼 실제 결제금액에 붙는 비용이 하나라도 있으면 VAT율 확정이 선행되어야
하고, 그런 비용이 없다면 표시가격(N 기준) 산정에는 VAT율이 당장 급하지 않다 — 다만
`required_gross_payment`("고객이 실제로 내는 돈")는 이 경우에도 여전히 UNKNOWN으로 남는다는
점은 놓치지 말아야 한다.

**일반화**: VAT율 필요 여부는 "계산 전체"가 아니라 지표별로 판단한다 — `required_net_sales`는
`a=0`일 때만 `v` 없이 가능, `required_gross_payment`는 항상 `v` 필요, `required_selling_price`는
`price_includes_vat`가 `false`면 N 기준(따라서 N의 조건부 규칙을 물려받음), `true`면 G 기준
(따라서 항상 `v` 필요)이다. 이 CASE의 시나리오 A/B는 그 중 `price_includes_vat=false`,
`required_selling_price=N` 분기만 보여준다.
