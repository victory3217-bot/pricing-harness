# MODE A — Current Price Diagnosis — METHOD

```
Methodology source status:
- Pricing Harness Internal Specification: ACTIVE
- Master Note derived methodology reference: ACTIVE (via MASTER_NOTE_PRICING_REFERENCE.md)
- Direct Master Note source access in this repository: NOT AVAILABLE
- External academic/reference validation: PENDING
```

This repository does not hold the Startup Master Note original. Every claim below that is
attributed to the Master Note is sourced **only** through
[`docs/reference/MASTER_NOTE_PRICING_REFERENCE.md`](../../reference/MASTER_NOTE_PRICING_REFERENCE.md)
(itself a derived reference, not the original) — never quoted or paraphrased as if from the
original text. Citations use that document's own format:

> Source: MASTER_NOTE_PRICING_REFERENCE §N
> Underlying Master Note: MNxx

Everything else below (the calculation definitions, the engineering rationale) is this
Harness's own internal reasoning, fixed in `core/schemas/dependency_rules.md` and implemented
in `core/engine/modes/mode_a.py`. Section "Source boundary" below states exactly which parts
are which — see also
[`docs/methodology/MASTER_NOTE_MAPPING.md`](../../methodology/MASTER_NOTE_MAPPING.md) for the
full cross-Harness mapping.

## Business purpose

MODE A's question is not an engineering-invented starting point — it sits directly on a
problem framing the Reference attributes to the Master Note:

> Source: MASTER_NOTE_PRICING_REFERENCE §12
> Underlying Master Note: MN06

The Reference states that MODE A systematizes four MN06 problem points (paraphrased from the
Reference, not the original): pricing cannot be set without knowing cost; cost arises not only
from producing the thing but from selling and delivering it; channel-type costs (commissions,
fees) change the price structure itself; and a business must be able to confirm whether its
current price and cost structure are sustainable at all. MODE A's core question —

> "현재 이 가격과 비용구조로 판매할 때 한 단위 거래가 경제적으로 어떤 상태인가?"
> ("At the current price and cost structure, what economic state is one unit of this
> transaction in?")

— is this Harness's operationalization of that framing. The Reference is explicit, however,
that this attribution covers only the *problem MODE A addresses*, not its *specific formulas*
— see "Source boundary" below.

## Why this mode exists (engineering framing)

Before talking about strategy, discounts, or competitors, a pricing engagement needs one
settled fact: at the price actually being charged today, what does one transaction leave
behind, after the costs that are unambiguously tied to it? MODE A answers only that — it is
deliberately the smallest, least controversial question in the whole Harness, because every
other mode (target pricing, allowable cost, BEP, strategy) is built on top of it and inherits
its errors if it's wrong.

## Source boundary

| | Category | Basis |
|---|---|---|
| MODE A exists to answer "what does one unit leave behind at the current price" | **A — Master Note supported** | MASTER_NOTE_PRICING_REFERENCE §12, underlying MN06 |
| Cost must be known before price can be set; selling/delivery activity itself carries cost; channel-type costs change price structure | **A — Master Note supported** | MASTER_NOTE_PRICING_REFERENCE §12, §5.1, §5.2, §6.1, underlying MN06 |
| The exact definitions `Gross Profit = actual_price_ex_vat − direct_cost_total`, `Contribution Margin = Gross Profit − variable_cost_total`, `Contribution Margin Rate = Contribution Margin / actual_price_ex_vat` | **B — Pricing Harness Internal Specification** | The Reference states these are *not* a Master Note–confirmed formula — MASTER_NOTE_PRICING_REFERENCE §5.4 explicitly leaves "어느 수준까지 마진 개념을 구분할지" as an open MN06 follow-up question, not a settled definition |
| `fixed_operating_cost` excluded from Contribution Margin, reserved for BEP | **B — Pricing Harness Internal Specification** | Same boundary as above (§5.4); the Reference does not itself state this exclusion rule — this Harness derived it |
| `null ≠ 0`, dependency propagation, `{value, status}`, Analysis Result as sole computed artifact, parity test | **B — Pricing Harness Internal Specification** | MASTER_NOTE_PRICING_REFERENCE §15 states these engineering concepts "Master Note 원문에서 나온 개념이 아니라 Pricing Harness 개발 과정에서 만든 내부 설계 자산" |
| `gross_payment_incl_vat = net_sales_ex_vat × (1+v)` always, independent of display basis; VAT-rate dependency decided per metric, not per component | **B — Pricing Harness Internal Specification** | The Reference does not address VAT/gross-payment mechanics at all — this is a pure internal math correction (teaching point 2.1 above), not a Master Note claim |

Anything not in this table that reads as a Master Note claim elsewhere in this document should
be treated as unsupported until traced to a Reference section — flag it rather than assume it.

## Teaching points

The engineering points below (1–7) are, per the table above, **Category B — Pricing Harness
Internal Specification**, not Master Note concepts. They explain *why this Harness is built the
way it is*, which is a different question from *why MODE A's business question matters*
(covered in "Business purpose" above).

**1. Why `null` and `0` are different, not just "no data"**

A spreadsheet that treats a blank cell as `0` is making a silent decision: *this cost doesn't
exist*. That decision is invisible to whoever reads the output — a Gross Profit of "81.5%"
looks identical whether it's real or whether three cost lines were simply never filled in.
This Harness forces the distinction into the data model itself: `null` means "we don't know
yet," `0` means "we checked, and it's genuinely zero" (e.g. `channel_fee.rate = 0` because a
client sells direct with no channel partner). Only the second one is safe to compute with.

**2. VAT-inclusive vs. VAT-exclusive pricing**

A price tag and a transaction's real revenue are not the same number the moment VAT is in the
picture. `price_includes_vat = true` means the number in `actual_price` already has VAT baked
in, so it must be divided down (`÷ (1 + vat_rate)`) before it means anything for profitability.
`price_includes_vat = false` means the number is already net — and, for *that specific number*,
that state doesn't need the VAT rate to be usable. Conflating the two is a common, easy mistake
with outsized consequences: every downstream metric that depends on it is wrong by the VAT rate
if this one flag is wrong. (What "that specific number" excludes is its own lesson — see below.)

**2.1 Display basis vs. economic basis — a mistake this Harness itself made once**
*(Pricing Harness Internal Specification — the Master Note does not define VAT/gross-payment
mechanics; nothing here should be presented as Master-Note-confirmed.)*

It's tempting to read "price excludes VAT" as "VAT doesn't matter here" and stop. That's wrong,
and this project shipped that exact mistake before catching it: `price_includes_vat` only says
which of two numbers — `net_sales_ex_vat` or `gross_payment_incl_vat` — the raw price directly
equals. It does not change the underlying economic fact that, in a standard taxable transaction,
`gross_payment_incl_vat = net_sales_ex_vat × (1 + vat_rate)` **regardless of how the price is
displayed**. A `rate_of_gross_payment` fee (a PG/card processor fee, say) is charged on the real
money changing hands — if the quoted price happens to exclude VAT, that fee still needs the VAT
rate to gross the price back up, even though the *displayed* net-sales number didn't need it.
The lesson generalizes: **VAT-rate dependency is a per-metric question, never a per-component
one.** Two metrics on the same component can disagree about whether they need `vat_rate` at
all, and disagree about which direction (up or down) they'd apply it if they did.

**3. Gross Profit vs. Contribution Margin — not the same number**

Gross Profit only subtracts the cost of making/delivering the thing itself
(`product_service_direct_cost`). Contribution Margin goes one step further and also subtracts
the variable cost of *selling* it (channel commission, PG fees, shipping, per-visit service
cost — `variable_selling_delivery`). A product can look healthy on Gross Profit and be thin or
negative on Contribution Margin once selling costs are counted — which is the number that
actually tells you whether *this specific unit, sold through this specific channel*, was worth
selling. Calling both of these "마진"/"margin" without distinguishing them is exactly the kind
of ambiguity this Harness's terminology rules exist to prevent.

*(These two definitions are Category B — Pricing Harness Internal Specification, not a Master
Note–confirmed formula. See "Source boundary" above, MASTER_NOTE_PRICING_REFERENCE §5.4.)*

**4. Why fixed cost is excluded from Contribution Margin**

`fixed_operating_cost` (rent, salaries, fixed SG&A) doesn't scale with any single transaction —
it's a cost of *existing*, not a cost of *this sale*. Folding it into a per-unit margin produces
a number that changes depending on volume assumptions baked in silently, and conflates two
different questions: "is this unit worth selling?" (Contribution Margin) vs. "how many units do
we need to sell to cover the business?" (BEP — a separate, not-yet-built module that uses fixed
cost directly against Contribution Margin, not against Gross Profit).

**5. Why dependency propagation matters**

If Contribution Margin is computed as `Gross Profit − variable_cost_total` and either side is
missing, printing a number anyway means printing a guess dressed up as a fact. This Harness's
rule — any `UNKNOWN` dependency makes the metric `UNKNOWN`, with the exact missing field(s)
recorded — means a consultant (or a client reading a dashboard) can trust that every number
shown either is real or is honestly marked as not yet available. This is the direct fix for a
concrete failure observed in this project's own prior prototype: a spreadsheet that quietly
treated blank cost cells as `0` and reported an 81.5% margin that had no basis in confirmed
data.

**6. Spreadsheet vs. Harness**

A spreadsheet computes and displays in the same place — every cell is both storage and
presentation, which is exactly why it's so easy for a missing input to silently become a `0`
and for a formula tweak in one tab to quietly diverge from the "same" formula in another tab.
This Harness separates those concerns on purpose: `core/engine/` is the only place calculation
happens, `Analysis Result` is the only thing produced, and anything downstream (a future Excel
Simulator, dashboard, report) is a renderer of that one document, not an independent calculator.

**7. Why Analysis Result exists as its own artifact**

If a dashboard and a report each recomputed pricing math from the same Client Input, they could
drift — different rounding, a formula fixed in one place but not the other, or simply an update
to the engine that only one consumer picked up. Analysis Result exists to make that structurally
impossible: it is the *only* computed output, versioned (`source.engine_version`), traceable
back to its input (`source.client_input_ref`), and every consumer — Excel, Dashboard, Report,
Quotation — reads it, never recomputes it.

## Not covered here

Whether the Category B definitions above (Gross Profit / Contribution Margin / Contribution
Margin Rate, fixed-cost exclusion, the engineering concepts in "Teaching points") match a
particular textbook, external accounting standard, or the Startup Master Note *original text*
remains open — MASTER_NOTE_PRICING_REFERENCE §16 lists the unified margin-management level as
one of its own unresolved items, and this repository has no direct access to the Master Note
original to check further. See the status block at the top of this file and
`docs/methodology/MASTER_NOTE_MAPPING.md` for how this connects to the rest of the Harness.
