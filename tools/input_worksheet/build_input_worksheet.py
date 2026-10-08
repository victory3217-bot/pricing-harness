"""Build the course input worksheet (blank template, no data) for the web calculator.

Run: python tools/input_worksheet/build_input_worksheet.py
Writes docs/calculator/Pricing_Input_Worksheet.xlsx and tools/input_worksheet/_layout.json

Structure: first-run (initial production) based planning.
  1. assumptions  2. how-to-make activities  3. how-to-sell activities
  4. monthly fixed operating cost  5. verdict panel  6. values to type into the calculator
The verdict panel mirrors MODE A / BEP / MODE B (target rate 0) of the Python Core; parity is
checked by tools/input_worksheet/qa_check_input_worksheet.py.
"""
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "docs" / "calculator" / "Pricing_Input_Worksheet.xlsx"

INPUT = PatternFill("solid", fgColor="FFF6D6")
CALC = PatternFill("solid", fgColor="E6EEE9")
HEAD = PatternFill("solid", fgColor="1E4C40")
NOTE = Font(color="666666", size=10)
THIN = Side(style="thin", color="CCCCCC")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")

MAKE_KINDS = ["수량비례 제작비", "일회성 투자"]
K_ONCE = "런칭 전 일회성"
K_FLAT = "판매 시 정액 (개당)"
K_ORDER = "판매 시 정액 (주문당)"
K_NET = "판매 시 순매출 대비 %"
K_GROSS = "판매 시 지불액 대비 %"
SELL_KINDS = [K_ONCE, K_FLAT, K_ORDER, K_NET, K_GROSS]
N_MAKE, N_SELL, N_FIXED = 10, 10, 6

wb = Workbook()
ws = wb.active
ws.title = "입력 정리"
for col, w in zip("ABCDE", (40, 22, 20, 26, 54)):
    ws.column_dimensions[col].width = w

REF = {}  # name -> absolute cell address (also read by the QA script)


def title(r, text):
    ws.cell(r, 1, text).font = Font(bold=True, size=12, color="FFFFFF")
    for c in range(1, 6):
        ws.cell(r, c).fill = HEAD


def note(r, text):
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    c = ws.cell(r, 1, text)
    c.font, c.alignment = NOTE, WRAP
    ws.row_dimensions[r].height = 15 * (1 + len(text) // 75)


def cell(r, c, v=None, fill=None, fmt=None, bold=False):
    x = ws.cell(r, c, v)
    x.border = BOX
    if fill:
        x.fill = fill
    if fmt:
        x.number_format = fmt
    if bold:
        x.font = Font(bold=True)
    return x


def header(r, labels):
    for c, h in enumerate(labels, 1):
        cell(r, c, h, CALC, bold=True)


def hint(r, text):
    ws.cell(r, 5, text).font = NOTE
    ws.cell(r, 5).alignment = WRAP


def dropdown(options, *cells):
    dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    for c in cells:
        dv.add(c)


ws.cell(1, 1, "가격 진단 계산기 입력 정리 시트 / Input worksheet").font = Font(bold=True, size=14)
note(2, "노란 칸만 입력하세요. 회색 칸은 자동 계산입니다. 이 파일은 비어 있는 양식이며, 입력한 내용은 내려받아 연 본인의 "
        "컴퓨터에만 저장됩니다. Yellow cells are inputs; grey cells are formulas. Nothing you type leaves your computer.")
note(3, "초도생산(또는 서비스 개발) 기준으로 '만드는 활동'과 '파는 활동'의 비용을 정리하면, 초도물량으로 본전이 가능한지와 "
        "얼마나 빨리 팔아야 하는지를 5번 판정 칸에서 바로 볼 수 있습니다. 정식 계산과 목표 공헌이익률·할인율 검토는 웹 계산기에서 하세요.")

# ---------------- 1. assumptions
r = 5
title(r, "1. 가정 / Assumptions")
A = {}
rows = [
    ("biz", "업종", None, "제조 또는 서비스를 고르세요 (아래 수량 항목의 이름이 바뀝니다)"),
    ("n", None, "#,##0", "제조: 초도생산 수량. 서비스: 소진 기간 동안 받을 수 있는 고객(수용) 수"),
    ("t", "목표 소진기간 (개월)", "0.##", "초도물량을 모두 판매하려는 기간"),
    ("life", "제품/서비스 수명주기 (개월)", "0.##", "일회성 투자 회수 기준을 '수명주기'로 고를 때 사용"),
    ("basis", "일회성 투자 회수 기준", None,
     "비우면 '소진기간'. 소진기간=보수적(현금 관점), 수명주기=월 부담이 작아짐 (장치는 내용연수와 수명주기 중 짧은 쪽)"),
    ("price", "실제 판매가 (KRW)", "#,##0", "고객이 실제로 내는 가격"),
    ("vat", "부가세율 (%)", "0.0", "예: 10"),
    ("inc", "위 판매가는 VAT 포함가인가?", None, "예 / 아니오"),
]
for i, (key, lab, fmt, h) in enumerate(rows):
    rr = r + 1 + i
    A[key] = f"$B${rr}"
    if key == "n":
        cell(rr, 1, '=IF($B$6="서비스","소진 기간 동안 받을 수 있는 고객 수 (명)","초도생산 수량 (개)")', CALC)
    else:
        cell(rr, 1, lab)
    cell(rr, 2, None, INPUT, fmt)
    hint(rr, h)
dropdown(["제조", "서비스"], A["biz"].replace("$", ""))
dropdown(["소진기간", "수명주기"], A["basis"].replace("$", ""))
dropdown(["예", "아니오"], A["inc"].replace("$", ""))
r = r + 1 + len(rows) + 1

# ---------------- 2. how to make
title(r, "2. 만드는 활동 / How to make — 런칭 직전까지 (to-do list)")
note(r + 1, "제조: 재료·가공·외주 제작 등 / 서비스: 기획·개발·디자인 인건비 등. '수량비례 제작비'는 초도물량에 비례해 드는 비용, "
            "'일회성 투자'는 금형·장치·인증·개발비처럼 수량과 무관하게 한 번 드는 비용입니다.")
header(r + 2, ["활동 (to-do)", "기간 (메모)", "총 비용 (KRW)", "구분", "메모"])
m0 = r + 3
for i in range(N_MAKE):
    for c in range(1, 6):
        cell(m0 + i, c, None, INPUT, "#,##0" if c == 3 else None)
m1 = m0 + N_MAKE - 1
dropdown(MAKE_KINDS, *[f"D{x}" for x in range(m0, m1 + 1)])
rr = m1 + 1
cell(rr, 1, "수량비례 제작비 합계", CALC, bold=True)
cell(rr, 3, f'=SUMIF($D${m0}:$D${m1},"{MAKE_KINDS[0]}",$C${m0}:$C${m1})', CALC, "#,##0")
REF["make_var"] = f"$C${rr}"
rr += 1
cell(rr, 1, "일회성 투자 합계 (만들기)", CALC, bold=True)
cell(rr, 3, f'=SUMIF($D${m0}:$D${m1},"{MAKE_KINDS[1]}",$C${m0}:$C${m1})', CALC, "#,##0")
REF["make_once"] = f"$C${rr}"
rr += 1
cell(rr, 1, "구분을 고르지 않은 행 수", CALC)
cell(rr, 3, f'=COUNTIFS($C${m0}:$C${m1},"<>",$D${m0}:$D${m1},"")', CALC, "0")
hint(rr, "0이 아니면 구분을 선택하세요 (합계에 포함되지 않습니다)")
r = rr + 2

# ---------------- 3. how to sell
title(r, "3. 파는 활동 / How to sell — 런칭 전 준비와 런칭 이후")
note(r + 1, "'런칭 전 일회성'은 입점·샘플·초기 마케팅처럼 한 번 쓰는 총액입니다. '판매 시 …'는 팔 때마다 붙는 비용만 적습니다 "
            "(수수료·결제수수료·배송비·건당 광고비). 정액은 총액이 아니라 1개(또는 1주문)당 금액, %는 퍼센트 숫자로 적으세요. "
            "제작 관련 비용은 위 2번에 적습니다.")
header(r + 2, ["활동 (to-do)", "기간 (메모)", "금액 / 값", "구분", "메모"])
s0 = r + 3
for i in range(N_SELL):
    for c in range(1, 6):
        cell(s0 + i, c, None, INPUT, "#,##0.##" if c == 3 else None)
s1 = s0 + N_SELL - 1
dropdown(SELL_KINDS, *[f"D{x}" for x in range(s0, s1 + 1)])
rr = s1 + 1


def sell_sum(kind):
    return f'SUMIF($D${s0}:$D${s1},"{kind}",$C${s0}:$C${s1})'


for key, lab, f, fmt in (
    ("sell_once", "런칭 전 일회성 합계", sell_sum(K_ONCE), "#,##0"),
    ("fl", "판매 시 정액 (개당) 합계", sell_sum(K_FLAT), "#,##0.##"),
    ("po", "판매 시 정액 (주문당) 합계", sell_sum(K_ORDER), "#,##0.##"),
    ("bn", "판매 시 순매출 대비 % 합계", sell_sum(K_NET), "0.##"),
    ("bg", "판매 시 지불액 대비 % 합계", sell_sum(K_GROSS), "0.##"),
):
    cell(rr, 1, lab, CALC, bold=True)
    cell(rr, 3, "=" + f, CALC, fmt)
    REF[key] = f"$C${rr}"
    rr += 1
cell(rr, 1, "구분을 고르지 않은 행 수", CALC)
cell(rr, 3, f'=COUNTIFS($C${s0}:$C${s1},"<>",$D${s0}:$D${s1},"")', CALC, "0")
hint(rr, "0이 아니면 구분을 선택하세요 (합계에 포함되지 않습니다)")
r = rr + 2

# ---------------- 4. monthly fixed
title(r, "4. 월 고정운영비 / Monthly fixed operating cost")
note(r + 1, "물량과 무관하게 매달 나가는 비용 (임대료, 상시 인건비, 구독·툴 비용 등).")
header(r + 2, ["항목", "", "월 금액 (KRW)", "", "메모"])
f0 = r + 3
for i in range(N_FIXED):
    rr = f0 + i
    cell(rr, 1, None, INPUT)
    cell(rr, 2)
    cell(rr, 3, None, INPUT, "#,##0")
    cell(rr, 4)
    cell(rr, 5, None, INPUT)
f1 = f0 + N_FIXED - 1
rr = f1 + 1
cell(rr, 1, "월 고정운영비 합계", CALC, bold=True)
cell(rr, 3, f"=SUM($C${f0}:$C${f1})", CALC, "#,##0")
REF["fixed"] = f"$C${rr}"
r = rr + 2

# ---------------- 5. verdict
title(r, "5. 판정 / Verdict — 초도물량으로 본전이 되는가")
note(r + 1, "초도 기준 판단용 계산입니다 (재고·외상 시차와 추가 생산은 반영하지 않음). 정식 계산은 웹 계산기에서 하세요.")
header(r + 2, ["항목", "값", "", "", "설명"])
e = r + 3
P, VAT, INC, N, T = A["price"], A["vat"], A["inc"], A["n"], A["t"]
READY = f'AND(ISNUMBER({P}),ISNUMBER({VAT}),OR({INC}="예",{INC}="아니오"),ISNUMBER({N}),ISNUMBER({T}))'


def erow(key, label, formula, fmt, explain):
    global e
    cell(e, 1, label, CALC)
    cell(e, 2, formula, CALC, fmt)
    hint(e, explain)
    REF[key] = f"$B${e}"
    e += 1


def g(expr):
    return f'=IF(NOT({REF["ready"]}),"",{expr})'


erow("ready", "필수 입력 완료", f"={READY}", None, "판매가·부가세율·VAT 여부·수량·소진기간이 모두 입력되면 TRUE")
erow("net", "순매출 (VAT 제외 판매가)", g(f'IF({INC}="예",{P}/(1+{VAT}/100),{P})'), "#,##0.##", "MODE A와 같은 계산")
erow("gross", "고객 지불액 (VAT 포함)", g(f'IF({INC}="예",{P},{P}*(1+{VAT}/100))'), "#,##0.##", "")
erow("u", "개당 직접원가", g(f'IF({N}>0,{REF["make_var"]}/{N},"수량 > 0 필요")'), "#,##0.##",
     "수량비례 제작비 합계 ÷ 수량 → 계산기의 '직접원가'에 입력")
erow("s", "개당 변동비 (판매 시)",
     g(f'{REF["fl"]}+{REF["po"]}+{REF["bn"]}/100*{REF["net"]}+{REF["bg"]}/100*{REF["gross"]}'), "#,##0.##",
     "정액 + 순매출 대비 % × 순매출 + 지불액 대비 % × 지불액")
erow("cm", "개당 공헌이익", g(f'IF(AND(ISNUMBER({REF["u"]}),ISNUMBER({REF["s"]})),{REF["net"]}-{REF["u"]}-{REF["s"]},"")'),
     "#,##0.##", "순매출 − 개당 직접원가 − 개당 변동비")
erow("once", "회수 대상 일회성 투자 합계", g(f'{REF["make_once"]}+{REF["sell_once"]}'), "#,##0", "만들기 + 런칭 전 일회성")
erow("rec", "회수 기간 (개월)", g(f'IF({A["basis"]}="수명주기",{A["life"]},{T})'), "0.##", "회수 기준에 따라 소진기간 또는 수명주기")
erow("amort", "월 상각액",
     g(f'IF({REF["once"]}=0,0,IF(N({REF["rec"]})>0,{REF["once"]}/{REF["rec"]},"회수 기간 입력 필요"))'), "#,##0",
     "일회성 투자 ÷ 회수 기간")
erow("fm", "월 고정비 (상각 포함)", g(f'IF(ISNUMBER({REF["amort"]}),{REF["fixed"]}+{REF["amort"]},"")'), "#,##0",
     "월 고정운영비 + 월 상각액 → 계산기의 '월 고정운영비'에 입력")
erow("m", "목표 월 판매량", g(f'IF({T}>0,{N}/{T},"")'), "#,##0.##", "수량 ÷ 소진기간")
erow("bem", "월 손익분기 판매량",
     g(f'IF(OR(NOT(ISNUMBER({REF["fm"]})),NOT(ISNUMBER({REF["cm"]}))),"",'
       f'IF({REF["cm"]}>0,{REF["fm"]}/{REF["cm"]},IF({REF["fm"]}=0,"해당 없음","불가 (공헌이익 ≤ 0)")))'),
     "#,##0.##", "월 고정비 ÷ 개당 공헌이익 (계산기 BEP와 같은 식)")
erow("becum", "소진기간 동안 필요한 누적 판매량", g(f'IF(ISNUMBER({REF["bem"]}),{REF["bem"]}*{T},"")'), "#,##0.##",
     "월 손익분기 판매량 × 소진기간")
erow("pct", "누적 필요 판매량 ÷ 수량", g(f'IF(AND(ISNUMBER({REF["becum"]}),{N}>0),{REF["becum"]}/{N},"")'), "0.0%",
     "100% 이하여야 초도물량으로 본전 가능")
erow("pl", "초도물량 전량 판매 시 손익 (소진기간 내)",
     g(f'IF(AND(ISNUMBER({REF["fm"]}),ISNUMBER({REF["cm"]})),{N}*{REF["cm"]}-{REF["fm"]}*{T},"")'), "#,##0",
     "수량 × 개당 공헌이익 − 월 고정비 × 소진기간")
DEN = f'(1-{REF["bn"]}/100-{REF["bg"]}/100*(1+{VAT}/100))'
erow("price_be", "초도물량 전량 판매 시 본전 판매가",
     g(f'IF(OR(NOT(ISNUMBER({REF["fm"]})),NOT(ISNUMBER({REF["u"]}))),"",IF({DEN}<=0,"불가 (수수료율 합계 과다)",'
       f'IF({INC}="예",(1+{VAT}/100),1)*({REF["u"]}+{REF["fl"]}+{REF["po"]}+{REF["fm"]}*{T}/{N})/{DEN}))'),
     "#,##0.##", "이 가격(입력한 VAT 기준)이면 소진기간 안에 전량 판매 시 손익 0")
erow("payback", "투자 회수 기간 (개월)",
     g(f'IF({REF["once"]}=0,"해당 없음",IF(AND(ISNUMBER({REF["m"]}),ISNUMBER({REF["cm"]})),'
       f'IF({REF["m"]}*{REF["cm"]}-{REF["fixed"]}>0,{REF["once"]}/({REF["m"]}*{REF["cm"]}-{REF["fixed"]}),"회수 불가"),""))'),
     "#,##0.#", "일회성 투자 ÷ (목표 월 판매량 × 개당 공헌이익 − 월 고정운영비)")

cell(e, 1, "판정", CALC, bold=True)
verdict = (
    f'=IF(NOT({REF["ready"]}),"필수 입력(판매가·부가세율·VAT 여부·수량·소진기간)을 채워 주세요",'
    f'IF(NOT(ISNUMBER({REF["cm"]})),"비용 입력을 확인하세요",'
    f'IF({REF["cm"]}<=0,"개당 공헌이익이 0 이하입니다 — 팔수록 손해. 가격·원가·수수료를 다시 검토하세요",'
    f'IF(NOT(ISNUMBER({REF["pct"]})),"고정비·회수 기간 입력을 확인하세요",'
    f'IF({REF["pct"]}>1,"초도물량을 전부 팔아도 본전이 안 됩니다 — 가격 인상, 원가 절감, 고정비 축소 또는 추가 생산·기간 연장을 검토하세요",'
    f'"초도물량으로 본전 가능 — 월 "&TEXT({REF["bem"]},"#,##0.#")&"개 이상 판매 필요, 목표는 월 "&TEXT({REF["m"]},"#,##0.#")&"개")))))'
)
ws.merge_cells(start_row=e, start_column=2, end_row=e, end_column=5)
vc = cell(e, 2, verdict, CALC, bold=True)
vc.alignment = WRAP
ws.row_dimensions[e].height = 48
REF["verdict"] = f"$B${e}"
r = e + 2

# ---------------- 6. calculator values
title(r, "6. 계산기에 입력할 값 / Values to type into the calculator")
note(r + 1, "웹 계산기의 같은 이름 칸에 옮겨 적으세요. 변동비는 계산기의 '+ 변동비 항목 추가'로 유형별 합계를 항목으로 추가하면 됩니다.")
q = r + 2
OUT_ROWS = [
    ("실제 판매가 (KRW)", f'=IF({P}="","",{P})', "#,##0"),
    ("부가세율 (%)", f'=IF({VAT}="","",{VAT})', "0.0"),
    ("VAT 포함가 체크", f'=IF({INC}="","",IF({INC}="예","체크","해제"))', None),
    ("직접원가 (개당)", f'={REF["u"]}', "#,##0.##"),
    ("변동비: 정액 (개당)", f'={REF["fl"]}', "#,##0.##"),
    ("변동비: 정액 (주문당)", f'={REF["po"]}', "#,##0.##"),
    ("변동비: 순매출 대비 (%)", f'={REF["bn"]}', "0.##"),
    ("변동비: 지불액 대비 (%)", f'={REF["bg"]}', "0.##"),
    ("월 고정운영비 (상각 포함, KRW)", f'={REF["fm"]}', "#,##0"),
    ("월 계획 판매량 (개) — 목표 월 판매량", f'={REF["m"]}', "#,##0.##"),
]
for i, (lab, f, fmt) in enumerate(OUT_ROWS):
    cell(q + i, 1, lab, CALC, bold=True)
    cell(q + i, 2, f, CALC, fmt)
q += len(OUT_ROWS)
for lab, fmt, h in (
    ("목표 공헌이익률 (%)", "0.0", "MODE B에 사용 — 본전 확인 후 목표를 정해 입력"),
    ("정가 대비 할인율 (%)", "0.0", "MODE B 정가 역산"),
    ("목표 시장가격 (KRW)", "#,##0", "MODE C에 사용"),
):
    cell(q, 1, lab, bold=True)
    cell(q, 2, None, INPUT, fmt)
    hint(q, h)
    q += 1

ws.freeze_panes = "A5"
ws.sheet_view.showGridLines = False
wb.save(OUT)
(HERE / "_layout.json").write_text(
    json.dumps({"A": A, "REF": REF, "make": [m0, m1], "sell": [s0, s1], "fixed": [f0, f1]}, ensure_ascii=False),
    encoding="utf-8")
print("wrote", OUT)
