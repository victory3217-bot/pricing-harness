"""QA for the input worksheet's verdict panel.

Fills the blank template with scenario inputs, recalculates it headless with LibreOffice, and
compares the panel against the Python Core:
  - cm (개당 공헌이익) and monthly break-even quantity  <-> core/engine/modes/bep.py (run_bep)
  - break-even selling price (target rate 0)            <-> core/engine/modes/mode_b.py (run_mode_b)
plus the panel's own arithmetic (totals, amortization, verdict text branches).

Run: python tools/input_worksheet/qa_check_input_worksheet.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import openpyxl

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "excel_simulator"))

from core.engine.modes.bep import run_bep  # noqa: E402
from core.engine.modes.mode_b import run_mode_b  # noqa: E402
from scenario_helpers import make_client_input_b, make_client_input_bep  # noqa: E402

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
SCRATCH = HERE / "_qa_scratch"
TEMPLATE = ROOT / "docs" / "calculator" / "Pricing_Input_Worksheet.xlsx"

subprocess.run([sys.executable, str(HERE / "build_input_worksheet.py")], check=True, capture_output=True)
LAY = json.loads((HERE / "_layout.json").read_text(encoding="utf-8"))
A, REF = LAY["A"], LAY["REF"]


def cellv(ws, addr):
    return ws[addr.replace("$", "")].value


def scenario(name, **kw):
    base = dict(biz="제조", n=200, t=6, life=24, basis=None, price=35000, vat=10, inc="예",
                make=[], sell=[], fixed=[])
    base.update(kw)
    base["name"] = name
    return base


VAR, ONE = "수량비례 제작비", "일회성 투자"
SCENARIOS = [
    scenario("base: unit costs only", make=[("재료", 3_000_000, VAR), ("가공", 1_000_000, VAR)],
             sell=[("결제수수료", 2.5, "판매 시 지불액 대비 %"), ("배송", 3000, "판매 시 정액 (개당)")],
             fixed=[("임대", 300_000)]),
    scenario("with investment, basis=소진기간", make=[("재료", 3_000_000, VAR), ("금형", 6_000_000, ONE)],
             sell=[("입점", 1_200_000, "런칭 전 일회성"), ("수수료", 10, "판매 시 순매출 대비 %")],
             fixed=[("임대", 300_000), ("툴", 100_000)]),
    scenario("with investment, basis=수명주기", basis="수명주기", make=[("재료", 3_000_000, VAR), ("금형", 6_000_000, ONE)],
             sell=[("입점", 1_200_000, "런칭 전 일회성"), ("수수료", 10, "판매 시 순매출 대비 %"),
                   ("택배", 2500, "판매 시 정액 (주문당)")], fixed=[("임대", 300_000)]),
    scenario("price excl VAT", inc="아니오", price=31818.18, make=[("재료", 4_000_000, VAR)],
             sell=[("PG", 3, "판매 시 지불액 대비 %"), ("플랫폼", 8, "판매 시 순매출 대비 %")], fixed=[("임대", 500_000)]),
    scenario("cm <= 0", make=[("재료", 9_000_000, VAR)], fixed=[("임대", 300_000)]),
    scenario("cannot break even within N", n=20, make=[("재료", 400_000, VAR), ("금형", 8_000_000, ONE)], fixed=[("임대", 500_000)]),
    scenario("feasible within N", n=500, make=[("재료", 5_000_000, VAR)], fixed=[("임대", 300_000)],
             sell=[("결제수수료", 2.5, "판매 시 지불액 대비 %")]),
    scenario("service", biz="서비스", n=30, t=3, make=[("개발 인건비", 15_000_000, ONE)], fixed=[("툴", 200_000)]),
]


def expected(sc):
    """Independent re-statement of the panel arithmetic (no engine)."""
    v = sc["vat"] / 100
    net = sc["price"] / (1 + v) if sc["inc"] == "예" else sc["price"]
    gross = sc["price"] if sc["inc"] == "예" else sc["price"] * (1 + v)
    make_var = sum(a for _, a, k in sc["make"] if k == VAR)
    once = sum(a for _, a, k in sc["make"] if k == ONE) + sum(a for _, a, k in sc["sell"] if k == "런칭 전 일회성")
    fl = sum(a for _, a, k in sc["sell"] if k in ("판매 시 정액 (개당)", "판매 시 정액 (주문당)"))
    bn = sum(a for _, a, k in sc["sell"] if k == "판매 시 순매출 대비 %") / 100
    bg = sum(a for _, a, k in sc["sell"] if k == "판매 시 지불액 대비 %") / 100
    fixed = sum(a for _, a in sc["fixed"])
    u = make_var / sc["n"]
    cm = net - u - fl - bn * net - bg * gross
    rec = sc["life"] if sc["basis"] == "수명주기" else sc["t"]
    fm = fixed + once / rec
    bem = fm / cm if cm > 0 else None
    D = 1 - bn - bg * (1 + v)
    net_be = (u + fl + fm * sc["t"] / sc["n"]) / D
    price_be = net_be * (1 + v) if sc["inc"] == "예" else net_be
    return dict(u=u, cm=cm, fm=fm, bem=bem, becum=None if bem is None else bem * sc["t"],
                pl=sc["n"] * cm - fm * sc["t"], price_be=price_be, fl=fl, bn=bn, bg=bg, net=net, gross=gross)


def engine(sc, ex):
    """Run the Python Core on the same economics (direct cost = u, flat variable, rates, fixed = fm)."""
    out = {}
    ci = make_client_input_bep(
        actual_price=sc["price"], includes_vat=(sc["inc"] == "예"), vat_rate=sc["vat"] / 100, direct_cost=ex["u"],
        variable_fixed_cost=ex["fl"], net_sales_fee_rate=ex["bn"], gross_payment_fee_rate=ex["bg"],
        fixed_operating_cost=ex["fm"])
    m = run_bep(ci)["per_component"]["main"]
    out["cm"] = m["contribution_margin_per_unit"]["value"]
    out["bem"] = m["break_even_quantity_exact"]["value"] if m["break_even_quantity_exact"]["status"] == "OK" else None
    try:
        cb = make_client_input_b(
            target_cm_rate=0.0, direct_cost=ex["u"] + ex["fm"] * sc["t"] / sc["n"], net_sales_fee_rate=ex["bn"],
            gross_payment_fee_rate=ex["bg"], vat_rate=sc["vat"] / 100, includes_vat=(sc["inc"] == "예"))
        # direct_cost above folds the per-unit flat variable amount in through the same slot
        cb["costs"]["items"][0]["amount"] += ex["fl"]
        rb = run_mode_b(cb)["per_component"]["main"]
        k = "required_selling_price"
        out["price_be"] = rb[k]["value"] if rb[k]["status"] == "OK" else None
    except Exception as exc:  # engine may reject a 0 target rate; reported, not hidden
        out["price_be_error"] = repr(exc)
    return out


def fill(sc, path):
    wb = openpyxl.load_workbook(TEMPLATE)
    ws = wb.active
    for k in ("biz", "n", "t", "life", "basis", "price", "vat", "inc"):
        if sc[k] is not None:
            ws[A[k].replace("$", "")] = sc[k]
    for i, (a, amt, kind) in enumerate(sc["make"]):
        r = LAY["make"][0] + i
        ws.cell(r, 1, a), ws.cell(r, 3, amt), ws.cell(r, 4, kind)
    for i, (a, amt, kind) in enumerate(sc["sell"]):
        r = LAY["sell"][0] + i
        ws.cell(r, 1, a), ws.cell(r, 3, amt), ws.cell(r, 4, kind)
    for i, (a, amt) in enumerate(sc["fixed"]):
        r = LAY["fixed"][0] + i
        ws.cell(r, 1, a), ws.cell(r, 3, amt)
    wb.save(path)


def recalc(path):
    out = SCRATCH / "out"
    out.mkdir(exist_ok=True)
    subprocess.run([SOFFICE, "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(out), str(path)],
                   check=True, capture_output=True)
    return openpyxl.load_workbook(out / path.name, data_only=True).active


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def main():
    shutil.rmtree(SCRATCH, ignore_errors=True)
    SCRATCH.mkdir()
    fails = 0
    for i, sc in enumerate(SCENARIOS):
        p = SCRATCH / f"s{i}.xlsx"
        fill(sc, p)
        ws = recalc(p)
        ex = expected(sc)
        en = engine(sc, ex)
        got = {k: cellv(ws, REF[k]) for k in ("u", "cm", "fm", "bem", "becum", "pl", "price_be", "verdict")}
        checks = [("u", ex["u"]), ("cm", ex["cm"]), ("fm", ex["fm"]), ("pl", ex["pl"]), ("price_be", ex["price_be"])]
        if ex["bem"] is not None:
            checks += [("bem", ex["bem"]), ("becum", ex["becum"])]
        bad = [k for k, want in checks if not close(got[k], want)]
        if not close(got["cm"], en["cm"]):
            bad.append("engine:cm")
        if ex["bem"] is not None and not close(got["bem"], en["bem"]):
            bad.append("engine:bem")
        if "price_be" in en and not close(got["price_be"], en["price_be"]):
            bad.append("engine:price_be")
        notes = []
        if "price_be_error" in en:
            notes.append("engine MODE B price skipped: " + en["price_be_error"])
        want_text = ("개당 공헌이익이 0 이하" if ex["cm"] <= 0 else
                     "본전이 안 됩니다" if ex["becum"] > sc["n"] else "초도물량으로 본전 가능")
        if want_text not in str(got["verdict"]):
            bad.append("verdict text")
        errs = [c.coordinate for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("#")]
        if errs:
            bad.append(f"excel errors {errs}")
        status = "PASS" if not bad else "FAIL " + ",".join(bad)
        fails += bool(bad)
        print(f"[{status}] {sc['name']}: cm={got['cm']:.2f} bem={got['bem']} price_be={got['price_be']}")
        print(f"        verdict: {got['verdict']}")
        for n in notes:
            print("        note:", n)
    # blank template must show the prompt, not errors
    ws = recalc_blank()
    blank_ok = "필수 입력" in str(cellv(ws, REF["verdict"]))
    print(f"[{'PASS' if blank_ok else 'FAIL'}] blank template shows the fill-in prompt")
    fails += not blank_ok
    shutil.rmtree(SCRATCH, ignore_errors=True)
    print("ALL PASS" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


def recalc_blank():
    p = SCRATCH / "blank.xlsx"
    shutil.copy(TEMPLATE, p)
    return recalc(p)


if __name__ == "__main__":
    sys.exit(main())
