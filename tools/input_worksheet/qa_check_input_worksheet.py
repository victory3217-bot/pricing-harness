"""QA for the input worksheet (초도 / 양산 / 비교 tabs).

Fills the blank template with scenario inputs, recalculates it headless with LibreOffice, and
compares the panels against the Python Core:
  - 초도: 판매 1개당 남는 금액 and cumulative break-even quantity <-> core/engine/modes/bep.py
          (direct cost 0, fixed = total to recover), break-even price <-> mode_b.py (target rate 0)
  - 양산: cm and monthly break-even <-> bep.py, break-even price <-> mode_b.py
plus the panels' own arithmetic, the 비교 tab, and the verdict text branches.

Run: python tools/input_worksheet/qa_check_input_worksheet.py
"""
import json
import re
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
S1, S2, S3 = "초도", "양산", "비교"
A1, R1 = LAY[S1]["A"], LAY[S1]["REF"]
R2 = LAY[S2]["REF"]
CR = LAY[S3]["rows"]

K_ONCE, K_FLAT = "런칭 전 총액", "판매 시 정액 (판매 단위당)"
K_NET, K_GROSS = "판매 시 순매출 대비 %", "판매 시 지불액 대비 %"


def sc(name, **kw):
    base = dict(biz="제조", unit="낱개 1개", n=200, t=6, price=35000, vat=10, inc="예", make=[], sell=[], fixed=[],
                q=None, m=None, o_price=None, rep=[], invest=[], life=None,
                o_fl=None, o_bn=None, o_bg=None, o_fixed=None)
    base.update(kw)
    base["name"] = name
    return base


SCENARIOS = [
    sc("base: cannot break even", make=[("재료", 4_000_000), ("금형", 5_000_000)],
       sell=[("PG", 2.5, K_GROSS), ("입점", 800_000, K_ONCE)], fixed=[("임대", 300_000)],
       q=1000, m=150, rep=[("재료", 15_000_000)]),
    sc("feasible", n=500, make=[("재료", 5_000_000)], sell=[("PG", 2.5, K_GROSS), ("배송", 3000, K_FLAT)],
       fixed=[("임대", 300_000)], q=2000, m=300, rep=[("재료", 16_000_000)], invest=[("증설", 6_000_000)], life=24),
    sc("price excl VAT + overrides", inc="아니오", price=31818.18, make=[("재료", 4_000_000)],
       sell=[("플랫폼", 8, K_NET), ("PG", 3, K_GROSS), ("택배", 2500, K_FLAT)], fixed=[("임대", 500_000)],
       q=800, m=120, o_price=29000, rep=[("재료", 8_000_000)], o_fl=1800, o_bn=6, o_bg=2, o_fixed=700_000),
    sc("cm <= 0", make=[("재료", 9_000_000)], fixed=[("임대", 300_000)], q=500, m=100, rep=[("재료", 20_000_000)]),
    sc("whole numbers (no trailing dot)", t=2, price=11, make=[("재료", 20)], fixed=[("고정", 30)],
       q=100, m=50, rep=[("재료", 100)]),
    sc("service", biz="서비스", n=30, t=3, make=[("개발 인건비", 15_000_000)], fixed=[("툴", 200_000)],
       q=100, m=25, rep=[("건당 인건비", 1_000_000)]),
]


def expected(s):
    v = s["vat"] / 100
    f = (1 + v) if s["inc"] == "예" else 1
    P = s["price"]
    net = P / (1 + v) if s["inc"] == "예" else P
    gross = P if s["inc"] == "예" else P * (1 + v)
    make = sum(a for _, a in s["make"])
    once = sum(x for _, x, k in s["sell"] if k == K_ONCE)
    fl = sum(x for _, x, k in s["sell"] if k == K_FLAT)
    po = 0.0  # per-order is no longer a separate kind
    bn = sum(x for _, x, k in s["sell"] if k == K_NET) / 100
    bg = sum(x for _, x, k in s["sell"] if k == K_GROSS) / 100
    F = sum(a for _, a in s["fixed"])
    sv = fl + po + bn * net + bg * gross
    w = net - sv
    tot = make + once + F * s["t"]
    out = {"net": net, "s": sv, "w": w, "tot": tot}
    out["beq"] = tot / w if w > 0 else None
    out["pct"] = out["beq"] / s["n"] if out["beq"] is not None else None
    out["bem"] = out["beq"] / s["t"] if out["beq"] is not None else None
    out["pl"] = s["n"] * w - tot
    D = 1 - bn - bg * (1 + v)
    out["price_be"] = f * ((tot / s["n"]) + fl + po) / D
    out["u_all"] = make / s["n"]
    out["fm1"] = F + once / s["t"]
    out["cm1"] = net - out["u_all"] - sv
    out["bem1"] = out["fm1"] / out["cm1"] if out["cm1"] > 0 else None
    # --- scale
    P2 = s["o_price"] if s["o_price"] is not None else P
    net2 = P2 / (1 + v) if s["inc"] == "예" else P2
    gross2 = P2 if s["inc"] == "예" else P2 * (1 + v)
    rep = sum(a for _, a in s["rep"])
    inv = sum(a for _, a in s["invest"])
    fl2 = s["o_fl"] if s["o_fl"] is not None else fl + po
    bn2 = (s["o_bn"] if s["o_bn"] is not None else bn * 100) / 100
    bg2 = (s["o_bg"] if s["o_bg"] is not None else bg * 100) / 100
    F2 = s["o_fixed"] if s["o_fixed"] is not None else F
    u2 = rep / s["q"]
    sv2 = fl2 + bn2 * net2 + bg2 * gross2
    cm2 = net2 - u2 - sv2
    fm2 = F2 + (inv / s["life"] if inv else 0)
    out.update(u2=u2, s2=sv2, cm2=cm2, fm2=fm2, net2=net2, f2=fl2)
    out["bem2"] = fm2 / cm2 if cm2 > 0 else None
    D2 = 1 - bn2 - bg2 * (1 + v)
    out["price_be2"] = f * (u2 + fl2 + fm2 / s["m"]) / D2
    out["fl"], out["po"], out["bn"], out["bg"] = fl, po, bn, bg
    out["bn2"], out["bg2"] = bn2, bg2
    out["saving"] = 1 - u2 / out["u_all"]
    return out


def engine(s, ex):
    out = {}
    v, inc = s["vat"] / 100, s["inc"] == "예"
    # 초도: direct 0, flat variable, rates, fixed = total to recover
    ci = make_client_input_bep(actual_price=s["price"], includes_vat=inc, vat_rate=v, direct_cost=0,
                               variable_fixed_cost=ex["fl"] + ex["po"], net_sales_fee_rate=ex["bn"],
                               gross_payment_fee_rate=ex["bg"], fixed_operating_cost=ex["tot"])
    m = run_bep(ci)["per_component"]["main"]
    out["w"] = m["contribution_margin_per_unit"]["value"]
    st = m["break_even_quantity_exact"]
    out["beq"] = st["value"] if st["status"] == "OK" else None
    cb = make_client_input_b(target_cm_rate=0.0, direct_cost=ex["tot"] / s["n"] + ex["fl"] + ex["po"],
                             net_sales_fee_rate=ex["bn"], gross_payment_fee_rate=ex["bg"], vat_rate=v, includes_vat=inc)
    rb = run_mode_b(cb)["per_component"]["main"]["required_selling_price"]
    out["price_be"] = rb["value"] if rb["status"] == "OK" else None
    # 양산
    P2 = s["o_price"] if s["o_price"] is not None else s["price"]
    ci2 = make_client_input_bep(actual_price=P2, includes_vat=inc, vat_rate=v, direct_cost=ex["u2"],
                                variable_fixed_cost=ex["f2"], net_sales_fee_rate=ex["bn2"],
                                gross_payment_fee_rate=ex["bg2"], fixed_operating_cost=ex["fm2"])
    m2 = run_bep(ci2)["per_component"]["main"]
    out["cm2"] = m2["contribution_margin_per_unit"]["value"]
    st2 = m2["break_even_quantity_exact"]
    out["bem2"] = st2["value"] if st2["status"] == "OK" else None
    cb2 = make_client_input_b(target_cm_rate=0.0, direct_cost=ex["u2"] + ex["f2"] + ex["fm2"] / s["m"],
                              net_sales_fee_rate=ex["bn2"], gross_payment_fee_rate=ex["bg2"], vat_rate=v, includes_vat=inc)
    rb2 = run_mode_b(cb2)["per_component"]["main"]["required_selling_price"]
    out["price_be2"] = rb2["value"] if rb2["status"] == "OK" else None
    return out


def fill(s, path):
    wb = openpyxl.load_workbook(TEMPLATE)
    w1, w2 = wb[S1], wb[S2]
    for k in ("biz", "unit", "n", "t", "price", "vat", "inc"):
        w1[A1[k].replace("$", "")] = s[k]
    for i, (a, amt) in enumerate(s["make"]):
        r = LAY[S1]["make"][0] + i
        w1.cell(r, 1, a), w1.cell(r, 2, amt)
    for i, (a, amt, kind) in enumerate(s["sell"]):
        r = LAY[S1]["sell"][0] + i
        w1.cell(r, 1, a), w1.cell(r, 2, amt), w1.cell(r, 3, kind)
    for i, (a, amt) in enumerate(s["fixed"]):
        r = LAY[S1]["fixed"][0] + i
        w1.cell(r, 1, a), w1.cell(r, 2, amt)
    for k in ("q", "m", "o_price", "life", "o_fl", "o_bn", "o_bg", "o_fixed"):
        if s[k] is not None:
            w2[R2[k].replace("$", "")] = s[k]
    for i, (a, amt) in enumerate(s["rep"]):
        r = LAY[S2]["repeat"][0] + i
        w2.cell(r, 1, a), w2.cell(r, 2, amt)
    for i, (a, amt) in enumerate(s["invest"]):
        r = LAY[S2]["invest"][0] + i
        w2.cell(r, 1, a), w2.cell(r, 2, amt)
    wb.save(path)


def recalc(path):
    out = SCRATCH / "out"
    out.mkdir(exist_ok=True)
    subprocess.run([SOFFICE, "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(out), str(path)],
                   check=True, capture_output=True)
    return openpyxl.load_workbook(out / path.name, data_only=True)


def val(wb, sheet, ref):
    return wb[sheet][ref.replace("$", "")].value


def close(a, b, tol=1e-6):
    return isinstance(a, (int, float)) and b is not None and abs(a - b) <= tol * max(1.0, abs(b))


def clipboard_text(ws, title_prefix):
    """The calculator-values table as it would arrive from a spreadsheet copy: label TAB displayed value."""
    start = next(r for r in range(1, ws.max_row + 1) if str(ws.cell(r, 1).value or "").startswith(title_prefix))
    lines, r = [], start + 2
    while ws.cell(r, 2).fill.fgColor.rgb[-6:] == "E6EEE9" and ws.cell(r, 1).value:
        v, fmt = ws.cell(r, 2).value, ws.cell(r, 2).number_format
        if v is None or v == "":
            shown = ""
        elif isinstance(v, (int, float)):
            shown = f"{v:,.0f}" if fmt == "#,##0" else f"{v:,.1f}" if fmt in ("#,##0.0", "0.0") else f"{v:g}"
        else:
            shown = str(v)
        lines.append(f"{ws.cell(r, 1).value}\t{shown}")
        r += 1
    return "\n".join(lines)


def parse_paste(text):
    out = subprocess.run(["node", str(HERE / "paste_parse_runner.js")], input=text, capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    return json.loads(out)


def main():
    shutil.rmtree(SCRATCH, ignore_errors=True)
    SCRATCH.mkdir()
    fails = 0
    for i, s in enumerate(SCENARIOS):
        p = SCRATCH / f"s{i}.xlsx"
        fill(s, p)
        wb = recalc(p)
        ex = expected(s)
        en = engine(s, ex)
        bad = []
        g1 = lambda k: val(wb, S1, R1[k])  # noqa: E731
        g2 = lambda k: val(wb, S2, R2[k])  # noqa: E731
        c1 = [("net", "net"), ("s", "s"), ("w", "w"), ("tot", "tot"), ("pl", "pl"), ("price_be", "price_be")]
        if ex["beq"] is not None:
            c1 += [("beq", "beq"), ("pct", "pct"), ("bem", "bem")]
        for k, e_ in c1:
            if not close(g1(k), ex[e_]):
                bad.append(f"초도:{k} got={g1(k)} want={ex[e_]}")
        if not close(g1("w"), en["w"]):
            bad.append("engine:w")
        if ex["beq"] is not None and not close(g1("beq"), en["beq"]):
            bad.append("engine:beq")
        if not close(g1("price_be"), en["price_be"]):
            bad.append("engine:price_be")
        c2 = [("u", "u2"), ("s", "s2"), ("cm", "cm2"), ("fm", "fm2"), ("price_be", "price_be2")]
        if ex["bem2"] is not None:
            c2.append(("bem", "bem2"))
        for k, e_ in c2:
            if not close(g2(k), ex[e_]):
                bad.append(f"양산:{k} got={g2(k)} want={ex[e_]}")
        if not close(g2("cm"), en["cm2"]):
            bad.append("engine:cm2")
        if ex["bem2"] is not None and not close(g2("bem"), en["bem2"]):
            bad.append("engine:bem2")
        if not close(g2("price_be"), en["price_be2"]):
            bad.append("engine:price_be2")
        # 비교 탭
        cmpv = lambda key, col: wb[S3][f"{col}{CR[key]}"].value  # noqa: E731
        for key, e1, e2 in (("u", ex["u_all"], ex["u2"]), ("cm", ex["cm1"], ex["cm2"]), ("fm", ex["fm1"], ex["fm2"])):
            if not close(cmpv(key, "B"), e1) or not close(cmpv(key, "C"), e2):
                bad.append(f"비교:{key} {cmpv(key, 'B')}/{cmpv(key, 'C')} want {e1}/{e2}")
        if ex["bem1"] is not None and not close(cmpv("bem", "B"), ex["bem1"]):
            bad.append("비교:bem1")
        if not close(cmpv("saving", "C"), ex["saving"]):
            bad.append("비교:saving")
        # the calculator's paste parser reads each sheet's calculator-values table back to the same numbers
        v1p = parse_paste(clipboard_text(wb[S1], "5. 계산기에 입력할 값"))
        want = {"price": s["price"], "vat": s["vat"], "inc": s["inc"] == "예", "direct": ex["u_all"],
                "flat": ex["fl"], "net": ex["bn"] * 100, "gross": ex["bg"] * 100, "fixed": ex["fm1"], "qty": s["n"] / s["t"]}
        for k, w_ in want.items():
            got = v1p["values"].get(k)
            ok = got is w_ if isinstance(w_, bool) else (got is not None and abs(got - w_) <= max(0.5, abs(w_) * 1e-3))
            if not ok:
                bad.append(f"paste(초도):{k} got={got} want={w_}")
        if v1p["unmatched"] or v1p["skipped"]:
            bad.append(f"paste(초도) unmatched={v1p['unmatched']} skipped={v1p['skipped']}")
        v2p = parse_paste(clipboard_text(wb[S2], "6. 계산기에 입력할 값"))
        want2 = {"price": s["o_price"] if s["o_price"] is not None else s["price"], "vat": s["vat"],
                 "inc": s["inc"] == "예", "direct": ex["u2"], "flat": ex["f2"], "net": ex["bn2"] * 100,
                 "gross": ex["bg2"] * 100, "fixed": ex["fm2"], "qty": s["m"]}
        for k, w_ in want2.items():
            got = v2p["values"].get(k)
            ok = got is w_ if isinstance(w_, bool) else (got is not None and abs(got - w_) <= max(0.5, abs(w_) * 1e-3))
            if not ok:
                bad.append(f"paste(양산):{k} got={got} want={w_}")
        # verdict text branches
        v1 = str(g1("verdict"))
        want1 = ("판매 단위당 남는 금액이 0 이하" if ex["w"] <= 0 else
                 "본전이 안 됩니다" if ex["pct"] > 1 else "초도물량으로 본전 가능")
        if want1 not in v1:
            bad.append("초도 verdict text")
        v2 = str(g2("verdict"))
        want2 = ("판매 단위당 공헌이익이 0 이하" if ex["cm2"] <= 0 else
                 "본전이 안 됩니다" if ex["bem2"] / s["m"] > 1 else "본전 가능")
        if want2 not in v2:
            bad.append("양산 verdict text")
        cmp_text = str(wb[S3]["B" + LAY[S3]["REF"]["verdict"].split("$")[-1]].value)
        for label, txt in (("초도", v1), ("양산", v2), ("비교", cmp_text)):
            if re.search(r"\d\.(?!\d)", txt):
                bad.append(f"{label} text has a trailing dot after a number: {txt[:60]}")
        if s["name"].startswith("whole numbers") and "누적 8단위(월 4단위)" not in v1:
            bad.append("whole-number text should read 누적 8단위(월 4단위)")
        errs = [(sh.title, c.coordinate) for sh in wb.worksheets for row in sh.iter_rows() for c in row
                if isinstance(c.value, str) and c.value.startswith("#")]
        if errs:
            bad.append(f"excel errors {errs[:3]}")
        fails += bool(bad)
        print(f"[{'PASS' if not bad else 'FAIL ' + '; '.join(bad)}] {s['name']}")
        print(f"        초도: {v1}")
        print(f"        양산: {v2}")
        print(f"        비교: {wb[S3]['B' + LAY[S3]['REF']['verdict'].split('$')[-1]].value}")
    # blank template: prompts, no errors, no filled input cells
    p = SCRATCH / "blank.xlsx"
    shutil.copy(TEMPLATE, p)
    wb = recalc(p)
    ok = ("필수 입력" in str(val(wb, S1, R1["verdict"])) and "필수 입력" in str(val(wb, S2, R2["verdict"]))
          and "채우면" in str(val(wb, S3, LAY[S3]["REF"]["verdict"])))
    errs = [(sh.title, c.coordinate) for sh in wb.worksheets for row in sh.iter_rows() for c in row
            if isinstance(c.value, str) and c.value.startswith("#")]
    tmpl = openpyxl.load_workbook(TEMPLATE)
    filled = [(sh.title, c.coordinate) for sh in tmpl.worksheets for row in sh.iter_rows() for c in row
              if c.fill.fgColor.rgb == "00FFF6D6" and c.value is not None]
    blank_ok = ok and not errs and not filled
    print(f"[{'PASS' if blank_ok else 'FAIL'}] blank template: prompts={ok} errors={errs[:3]} filled_inputs={filled[:3]}")
    fails += not blank_ok
    shutil.rmtree(SCRATCH, ignore_errors=True)
    print("ALL PASS" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
