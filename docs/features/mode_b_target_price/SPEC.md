# MODE B — Target Price — SPEC (v0.2, implemented)

Status: **implemented** — `core/engine/modes/mode_b.py`, `tests/test_mode_b.py`. v0.2 corrects a
modeling error found in v0.1's VAT handling (see "Correction note" below); implementation follows
v0.2 exactly, including the per-metric VAT dependency rules and the shared-cost-allocation
limitation documented in §9.

## Correction note (v0.1 → v0.2)

v0.1 assumed that when a price is quoted VAT-exclusive (`price_includes_vat = false`), the
customer's actual gross payment equals net sales (`S = N`), and built two separate formulas
(`D1` for VAT-inclusive, `D2` for VAT-exclusive) on that basis. **This was wrong.** Whether a
price is *displayed/quoted* VAT-inclusive or VAT-exclusive is an input/presentation convention;
it does not change the economic fact that, in a standard taxable transaction, the customer's
gross payment is always `net sales × (1 + VAT rate)`. v0.2 uses a single unified formula and
removes the false premise that VAT-exclusive display makes VAT rate irrelevant whenever a
gross-payment-based fee exists. See §3 for the corrected derivation and §7 for the history of
this same error in MODE A (already fixed in `e503b5a`).

## Question answered

> 현재 원가·수수료 구조에서 목표 Contribution Margin Rate를 확보하려면 얼마에 팔아야 하는가?

## Source boundary (Master Note vs. Internal Specification)

Unchanged from v0.1 — see `docs/reference/MASTER_NOTE_PRICING_REFERENCE.md` §13. The four
Master-Note-supported ideas (원가=제약조건, 고객은 가치 때문에 지불, 지불의사 확인 후 역검토,
가격-경쟁/포지셔닝 연결) are Category A. **Every formula in this document, including the
correction, is Category B — Pricing Harness Internal Specification.** The Reference does not
address VAT/gross-payment mechanics at all; this correction is not a Master-Note-derived fix,
it is an internal math correction.

## 1. Terminology (redefined, v0.2)

The v0.1 draft used an ambiguous `S` ("actual price") that conflated two different things.
v0.2 uses six explicit terms:

| Term | Meaning | Symbol |
|---|---|---|
| `selling_price` | The number actually entered/quoted for a price. Corresponds to the Client Input schema's `price_component.actual_price` field — that field name is not changed here, `selling_price` is just the clearer term used in this document's prose. | — |
| `price_includes_vat` | Whether `selling_price` (and, by the same convention, `list_price`) already has VAT folded in. | boolean/null |
| `net_sales_ex_vat` | The VAT tax base — what MODE A calls `actual_price_ex_vat`. | N |
| `gross_payment_incl_vat` | What the customer actually pays, in a standard taxable transaction. **Always** `= net_sales_ex_vat × (1 + v)`, independent of how the price happens to be quoted. | G |
| `list_price` | Pre-discount quoted price, on the **same** VAT basis as `selling_price` (see §5). | — |
| `discount_rate` | Fraction knocked off `list_price` to reach `selling_price`. | — |

### Resolving `selling_price` into N and G

```
price_includes_vat = null   →  N UNKNOWN, G UNKNOWN
price_includes_vat = true   →  G = selling_price ;  N = G / (1 + v)   [N needs v]
price_includes_vat = false  →  N = selling_price ;  G = N × (1 + v)   [G needs v]
```

This table is symmetric by construction: whichever of {N, G} is *not* the display basis
requires `v` to derive; the one that *is* the display basis is immediate. This generalizes (and
corrects) MODE A's existing conditional-VAT rule, which today only applies the "needs v"
branch to N and incorrectly treats G as always immediate — see §7.

## 2. Rate basis (redefined, v0.2)

```
rate_of_net_sales      →  net_sales_ex_vat (N) × rate
rate_of_gross_payment  →  gross_payment_incl_vat (G) × rate
```

**`price_includes_vat = false` does not make `rate_of_gross_payment` use N.** G is still
`N × (1+v)` and still requires `v` to be known, regardless of display basis. If a fee is
contractually defined against a VAT-exclusive *contract* price rather than the true gross
payment, that fee should be classified `rate_of_net_sales`, not `rate_of_gross_payment` — the
`basis` field describes the fee's real contractual base, not the display convention of the
headline price.

## 3. Corrected general formula

Contribution Margin, in full:

```
CM = N − C − bN − aG
```

Since `G = N(1+v)` always:

```
CM = N − C − bN − aN(1+v) = N·[1 − b − a(1+v)] − C
```

Setting `CM/N = t` and solving:

```
N = C / [1 − t − b − a(1+v)]

G = N × (1 + v)
```

**This is now a single formula, used regardless of `price_includes_vat`.** The v0.1 `D1`/`D2`
branch is gone — display basis no longer changes which formula applies, only which of {N, G} is
reported as the headline `selling_price`-equivalent output (§4).

Denominator `D = 1 − t − b − a(1+v)`. `D ≤ 0` → **ERROR** (target unreachable at any price).

### When is `v` actually required? (per metric — not a single blanket answer)

`v`-dependency is not one fact about "the calculation" — it differs by which output metric you
ask about. **"`v` is needed only when `a > 0`" applies specifically to the N inversion formula,
not to every metric.** Per metric:

- **`required_net_sales` (N)**: `v` only appears multiplied by `a` in the denominator. **If `a =
  0` (no gross-payment-based fee at all), `v` is not needed to compute N**, regardless of
  `price_includes_vat`. If `a > 0`, `v` is required to compute N, *also regardless of
  `price_includes_vat`* — this is the specific point v0.1 got wrong (v0.1 assumed
  `price_includes_vat = false` made `v` unnecessary whenever there was a gross-payment fee; it
  does not).
- **`required_gross_payment` (G)**: `G = N(1+v)` always — `v` is **always** required to compute
  G, independent of `a` and independent of `price_includes_vat`.
- **`required_selling_price`**: which of {N, G} it reads from depends on `price_includes_vat` —
  `= N` if `price_includes_vat = false` (so it inherits N's conditional `v`-dependency above),
  `= G` if `price_includes_vat = true` (so it always needs `v`), UNKNOWN if `price_includes_vat`
  itself is null.

**Rule of thumb: always answer "does this need `v`?" per metric, never as one global yes/no for
"the computation."** N, G, and `required_selling_price` can each have a different answer, and
`required_selling_price`'s answer additionally depends on `price_includes_vat`, not just on `a`.

## 4. Outputs — per component

| Metric | Formula | Depends on |
|---|---|---|
| `required_net_sales` | `N = C/[1−t−b−a(1+v)]` | C, b, a, t always; v only if a>0 |
| `required_gross_payment` | `G = N(1+v)` | `required_net_sales`, and v (always) |
| `required_selling_price` | `= required_net_sales` if `price_includes_vat=false`; `= required_gross_payment` if `true`; UNKNOWN if `price_includes_vat=null` | `price_includes_vat`, plus whichever of N/G it selects |
| `required_list_price` | `required_selling_price / (1 − discount_rate)`, or `= required_selling_price` if no discount | `required_selling_price`, discount_rate |
| `expected_contribution_margin` | `t × required_net_sales` | `required_net_sales` |
| `expected_contribution_margin_rate` | should equal input `t` exactly when OK (self-check) | `expected_contribution_margin`, `required_net_sales` |

All wrapped `{value, status, unit}` per `analysis_result.schema.json`, same enum as MODE A.
Note that `required_net_sales` and `required_gross_payment` can have **different statuses** —
e.g. N can be `OK` while G is `UNKNOWN` if `v` is missing and `a = 0` (see TC12).

## 5. Discount and list price basis

**Generalization used here** (per the review request to pick one rule rather than two parallel
VAT cases): `list_price` and `selling_price` share the **same** `price_includes_vat` basis —
there is no separate "is list_price VAT-inclusive" flag. Discounting moves you from `list_price`
to `selling_price` within that one shared basis:

```
selling_price = list_price × (1 − discount_rate)
⇒ list_price  = selling_price / (1 − discount_rate)
```

Applied to MODE B's output: `required_list_price = required_selling_price / (1 −
discount_rate)`, where `required_selling_price` is already on whichever basis
`price_includes_vat` specifies. `discount_rate ≥ 1` → **ERROR**.

**Schema**: `discount_rate` is implemented on `price_component` in `client_input.schema.json`,
intentionally left unbounded (unlike `cost_item.rate`) so an out-of-range value reaches MODE B
as a diagnosable ERROR on `required_list_price` rather than being rejected at the input-validation
layer.

## 6. Scope limitation — tax-exempt / zero-rated transactions

**PENDING — not addressed by this SPEC.** The model assumes one uniform, standard VAT rate
applies to the transaction (`v = 0` is a valid, explicit input and degenerates the formulas
correctly to `G = N`, covering a zero-rated case *numerically*). It does **not** address:

- Transactions genuinely exempt from VAT (as distinct from zero-rated — an accounting
  distinction affecting the seller's own input-VAT recovery, not modeled here)
- Mixed-rate or multi-jurisdiction transactions
- Any case where `v` is not a single uniform rate

Neither `MASTER_NOTE_PRICING_REFERENCE.md` nor the current schema gives grounds to resolve
these, so they are out of scope until a concrete need and data model are defined. Do not
implement exemption-specific logic without a separate SPEC addendum.

## 7. MODE A history note (resolved — no longer an open issue)

**Historical note**: MODE B 설계 과정에서 MODE A의 VAT/gross-payment 의미체계 결함이
발견되었으며, MODE B 구현 전에 commit `e503b5a`("fix: correct VAT gross payment handling in
mode A")에서 수정되었다. MODE B는 수정된 MODE A 의미체계를 기준으로 한다.

The defect (now fixed): `gross_payment` was previously set equal to the raw currency-converted
`actual_price` unconditionally, never branching on `price_includes_vat` and never multiplying by
`(1+v)`. Confirmed by re-reading the current `core/engine/modes/mode_a.py`:
`_gross_payment_incl_vat` (lines 91–109) is now a deliberate mirror of `_actual_price_ex_vat` —
it returns the raw value only when `price_includes_vat = true`, returns `UNKNOWN` when
`price_includes_vat` or `vat_rate` is null, and otherwise returns `value * (1 + vat_rate)`. This
matches the N/G model in §1 above.

Current verified state: pytest 13/13 PASS, Excel parity PASS.

## 8. Minimum test cases (design only — no test code yet)

All fictional, single component. `v = 0.10` where used.

**TC1 — no rate-based cost at all (a=0, b=0)**
`C=10000, t=0.4` → `N = 10000/(1-0.4) = 16666.67`. N needs no `v` (a=0). If `v=0.10` known,
`G = 18333.33`; if `v` unknown, `G` is UNKNOWN but **N stays OK**.

**TC2 — net-sales fee only (b>0, a=0)**
`C=10000, b=0.1, t=0.3, v=0.10` → `N = 10000/(1-0.3-0.1) = 16666.67` (v not needed for N since
a=0). `G = 16666.67×1.1 = 18333.33`.

**TC3 — gross-payment fee only (a>0, b=0), v KNOWN, display VAT-exclusive** *(corrected; also
satisfies the review's requested case "VAT 제외 표시가격 + VAT 10% + gross-payment fee")*
`C=10000, a=0.05, v=0.10, t=0.3, price_includes_vat=false`
`D = 1-0.3-0-0.05×1.1 = 0.645` → `N = 10000/0.645 = 15503.88`
`G = 15503.88×1.1 = 17054.26`
Check: `CM = N - C - aG = 15503.88-10000-852.71 = 4651.16`; `CM/N = 0.30` ✓
`required_selling_price = N = 15503.88` (display basis is N since `price_includes_vat=false`)

**TC4 — VAT-inclusive display, both fee types** *(unchanged from v0.1 — old D1 already matched
the corrected formula since it already used `a(1+v)`)*
`C=10000, b=0.1, a=0.03, v=0.10, t=0.3` → `N=17636.68`, `G=19400.35`.
`required_selling_price = G = 19400.35` (display basis is G since `price_includes_vat=true`).

**TC5 — VAT-exclusive display, both fee types, v known** *(corrected)*
`C=8000, b=0.05, a=0.02, v=0.10, t=0.25`
`D = 1-0.25-0.05-0.02×1.1 = 0.678` → `N = 8000/0.678 = 11799.41`
`G = 11799.41×1.1 = 12979.35`
Check: `CM = 11799.41-8000-589.97-259.59 = 2949.85`; `CM/N = 0.25` ✓

**TC6 — discount applied on top of TC4**
`required_selling_price (G) = 19400.35`, `discount_rate=0.10`
`required_list_price = 19400.35/0.9 = 21555.95`

**TC7 — denominator ≤ 0 (ERROR)**
`t=0.5, b=0.3, a=0.3, v=0.10` → `D = 1-0.5-0.3-0.3×1.1 = -0.13 ≤ 0` → **ERROR**

**TC8 — UNKNOWN cost (C null)**
Same shape as TC1, direct-cost `amount=null` → `required_net_sales`, `required_gross_payment`,
`required_selling_price`, `required_list_price` all **UNKNOWN**.

**TC9 — explicit zero rate**
Same shape as TC3 but `channel_fee.rate = 0` (explicit) alongside `pg_fee.rate = 0.05` (known)
→ identical arithmetic to TC3; confirms confirmed-zero does not block computation (contrast
with TC8's `null`).

**TC10 — alias of TC3**, listed separately because it directly answers the review's first
requested case: *VAT 제외 표시가격 + VAT 10% + gross-payment fee* → see TC3, `N` and `G` both
`OK`.

**TC11 — VAT-exclusive display, `v` UNKNOWN, gross-payment fee present (a>0)** *(new, per
review)*
`C=10000, a=0.05, b=0, t=0.3, v=null, price_includes_vat=false`
`D` cannot be evaluated (`a>0` needs `v`) → `required_net_sales` **UNKNOWN**,
`required_gross_payment` **UNKNOWN**, `required_selling_price` **UNKNOWN** (even though the
display basis is N, which would not normally need `v`, the presence of the gross-payment fee
makes `v` necessary to solve the CM equation itself — this is exactly the case v0.1 got wrong).

**TC12 — VAT-exclusive display, `v` UNKNOWN, net-sales fee only (a=0, b>0)** *(new, per review)*
`C=10000, b=0.1, t=0.3, a=0, v=null, price_includes_vat=false`
`N = 10000/(1-0.3-0.1) = 16666.67` — **OK** (a=0, so v is never needed for N)
`G` — **UNKNOWN** (v missing; G always needs v)
`required_selling_price = N = 16666.67` — **OK** (display basis is N, doesn't need G)
`required_list_price` (no discount) `= 16666.67` — **OK**

TC11 vs. TC12 together are the key regression pair: same "VAT-exclusive display + v unknown"
setup, opposite outcome, depending only on whether a gross-payment fee (`a`) is present. This
is the exact distinction v0.1 collapsed incorrectly.

## 9. Implementation status and current limitations (post-implementation update)

`core/engine/modes/mode_b.py` is now implemented (`tests/test_mode_b.py`, 23 tests, all TC1–TC12
above verified numerically). Two limitations from the original draft are now load-bearing enough
to call out explicitly here rather than leave as a single out-of-scope bullet:

**Shared-cost allocation is not implemented, and is never silently treated as 0.** If a cost
item has `applies_to_component = "shared"` and an `allocation_rule` of `"by_component_revenue"`,
`"fixed_share"`, or a missing/unrecognized rule, MODE B cannot compute this component's share of
it without the (not-yet-built) blended engine. The affected aggregate — `C`, `b`, or `a` —
becomes **UNKNOWN**, and every metric downstream of it (`denominator`, `required_net_sales_ex_vat`,
`required_gross_payment_incl_vat`, `required_selling_price`, `required_list_price`,
`expected_contribution_margin[_rate]`) becomes UNKNOWN too, with warning code
`UNSUPPORTED_SHARED_COST_ALLOCATION` and a dependency path of `blended.allocation[<item_id>]`.
Ignoring the shared cost (treating it as 0) was considered and rejected: it would silently
understate `C`/`b`/`a` and report a target price **lower than the business actually needs** — a
direct violation of the Harness's `null != 0` / "never substitute a plausible-looking number for
UNKNOWN" principle. `allocation_rule = "direct"` on a `"shared"` item is a *different* case —
per `dependency_rules.md` section 4's canonical rule, `"shared"` + `"direct"` is a semantic
contradiction and is `ERROR` (code `INVALID_ALLOCATION_CONFIGURATION`), the same in MODE A and
MODE B. `"blended_only"` never appears at component level, by schema design, and is unaffected
(excluded, no warning). Resolving `by_component_revenue`/`fixed_share` allocation is explicitly
deferred to the future `blended` (whole-contract) Internal Specification, not MODE B.

**`target_contribution_margin_rate` is global, not per-component.** `client_input.targets` holds
one target rate for the whole Client Input; every `price_component` MODE B solves for uses that
same `t`. A product with multiple components that legitimately need different target margins
(e.g. hardware vs. SaaS in a hybrid product) is not supported yet — this would require either a
per-component override field or a redesign of `targets`, neither of which is implemented in this
step. Not addressed here; a future Internal Specification addendum if a real case needs it.

## Explicitly out of scope for this draft

- No MODE A code changes needed here (§7 documents the fix already applied in `e503b5a`)
- Tax-exempt/zero-rated/multi-rate handling (§6, PENDING)
- `blended` allocation resolution (§9 — cost items needing it are UNKNOWN, never dropped as 0)
- Per-component target Contribution Margin Rate (§9 — target rate is global for now)
- MODE C, BEP, Scenario Compare, Pricing Strategy AI — untouched
