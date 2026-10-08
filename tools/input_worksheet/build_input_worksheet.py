"""Build the course input worksheet (blank template, no data) for the web calculator.

Run: python tools/input_worksheet/build_input_worksheet.py
Writes docs/calculator/Pricing_Input_Worksheet.xlsx and tools/input_worksheet/_layout.json

Tabs
  초도   first-run planning: every cost is a lump sum for the first batch; verdict = can the first
         batch recover its total cost, and how fast must it sell
  양산   planning at scale: unit cost when re-producing at a larger quantity (equipment already
         owned), optional new investment amortized over the product life
  비교   side by side, same definitions on both sides
  사용법 how to use
The verdict panels mirror MODE A / BEP / MODE B (target rate 0) of the Python Core; parity is checked
by tools/input_worksheet/qa_check_input_worksheet.py.
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

K_ONCE = "런칭 전 총액"
K_FLAT = "판매 시 정액 (판매 단위당)"
K_NET = "판매 시 순매출 대비 %"
K_GROSS = "판매 시 지불액 대비 %"
SELL_KINDS = [K_ONCE, K_FLAT, K_NET, K_GROSS]
S1, S2, S3, SG = "초도", "양산", "비교", "사용법"

wb = Workbook()
LAYOUT = {}


class Sheet:
    def __init__(self, ws):
        self.ws = ws
        self.ref = {}
        for col, w in zip("ABCDE", (42, 22, 26, 28, 56)):
            ws.column_dimensions[col].width = w
        ws.sheet_view.showGridLines = False

    def title(self, r, text):
        self.ws.cell(r, 1, text).font = Font(bold=True, size=12, color="FFFFFF")
        for c in range(1, 6):
            self.ws.cell(r, c).fill = HEAD

    def note(self, r, text):
        self.ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        c = self.ws.cell(r, 1, text)
        c.font, c.alignment = NOTE, WRAP
        self.ws.row_dimensions[r].height = 15 * (1 + len(text) // 75)

    def cell(self, r, c, v=None, fill=None, fmt=None, bold=False):
        x = self.ws.cell(r, c, v)
        x.border = BOX
        if fill:
            x.fill = fill
        if fmt:
            x.number_format = fmt
        if bold:
            x.font = Font(bold=True)
        return x

    def header(self, r, labels):
        for c, h in enumerate(labels, 1):
            self.cell(r, c, h, CALC, bold=True)

    def hint(self, r, text):
        self.ws.cell(r, 5, text).font = NOTE
        self.ws.cell(r, 5).alignment = WRAP

    def dropdown(self, options, *cells):
        dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
        self.ws.add_data_validation(dv)
        for c in cells:
            dv.add(c)

    def inputs(self, r, rows):
        """rows: (key, label, fmt, hint). Returns next free row. Label None -> caller writes it."""
        for i, (key, lab, fmt, h) in enumerate(rows):
            rr = r + i
            self.ref[key] = f"$B${rr}"
            if lab is not None:
                self.cell(rr, 1, lab)
            self.cell(rr, 2, None, INPUT, fmt)
            self.hint(rr, h)
        return r + len(rows)

    def table(self, r, labels, nrows, money_col, money_fmt="#,##0"):
        self.header(r, labels)
        first = r + 1
        for i in range(nrows):
            for c in range(1, len(labels) + 1):
                self.cell(first + i, c, None, INPUT, money_fmt if c == money_col else None)
        return first, first + nrows - 1

    def calc(self, r, key, label, formula, fmt, explain=""):
        self.cell(r, 1, label, CALC)
        self.cell(r, 2, formula, CALC, fmt)
        if explain:
            self.hint(r, explain)
        self.ref[key] = f"$B${r}"
        return r + 1


def q(sheet, ref):
    return f"'{sheet}'!{ref}"


# =====================================================================  초도 (first run)
w1 = wb.active
w1.title = S1
a = Sheet(w1)
w1.cell(1, 1, "초도 기준 정리 / First-run planning").font = Font(bold=True, size=14)
a.note(2, "노란 칸만 입력하세요. 회색 칸은 자동 계산입니다. 입력한 내용은 내려받아 연 본인의 컴퓨터에만 저장됩니다. "
          "작성 방법은 '사용법' 탭을 보세요. Yellow cells are inputs; grey cells are formulas. Nothing you type leaves your computer.")
a.note(3, "처음 만드는 물량(초도생산) 기준으로 만들고 파는 데 드는 총비용을 적고, 초도물량으로 본전이 되는지와 얼마나 빨리 팔아야 하는지를 "
          "4번 판정에서 봅니다. 규모를 키웠을 때는 '양산' 탭, 둘의 차이는 '비교' 탭에서 봅니다.")
r = 5
a.title(r, "1. 가정 / Assumptions")
r = a.inputs(r + 1, [
    ("biz", "업종", None, "제조 또는 서비스 (아래 수량·기간 항목의 이름이 바뀝니다)"),
    ("unit", "판매 단위 (예: 낱개 1개, 6개입 세트, 1건)", None,
     "판매가·수량·비용 모두 이 단위를 기준으로 적습니다. 한 번에 한 가지 판매 단위만 정리하세요"),
    ("n", None, "#,##0", "제조: 초도생산 수량 (판매 단위 수). 서비스: 이 기간 안에 팔려는 목표 판매 수 — 수용 한도가 아니라 목표로 적으세요"),
    ("t", None, "General", "초도물량(서비스는 목표 판매 수)을 모두 판매하려는 기간"),
    ("price", "실제 판매가 (KRW)", "#,##0", "고객이 실제로 내는 가격"),
    ("vat", "부가세율 (%)", "0.0", "예: 10"),
    ("inc", "위 판매가는 VAT 포함가인가?", None, "예 / 아니오"),
])
a.cell(8, 1, '=IF($B$6="서비스","목표 판매 수","초도생산 수량")&" (판매 단위 수"&IF($B$7<>""," · 1단위 = "&$B$7,"")&")"', CALC)
a.cell(9, 1, '=IF($B$6="서비스","목표 판매 기간 (개월)","목표 소진기간 (개월)")', CALC)
for _r in (7, 8, 9):
    a.ws.cell(_r, 1).alignment = Alignment(wrap_text=True, vertical="center")
    a.ws.row_dimensions[_r].height = 32
a.dropdown(["제조", "서비스"], "B6")
a.dropdown(["예", "아니오"], a.ref["inc"].replace("$", ""))
A1 = dict(a.ref)

r += 1
a.title(r, "2. 만드는 활동 / How to make — 런칭 직전까지")
a.note(r + 1, "초도물량을 만드는 데 드는 일(to-do)을 한 줄씩 적고, 그 일에 드는 총비용을 적으세요. "
              "제조: 재료·가공·금형·장치·포장 등 / 서비스: 기획·개발·디자인 인건비 등. 구분 없이 총액만 적습니다.")
m0, m1 = a.table(r + 2, ["활동 (to-do)", "총 비용 (KRW)", "메모"], 10, 2)
rr = m1 + 1
a.cell(rr, 1, "만드는 총비용 합계", CALC, bold=True)
a.cell(rr, 2, f"=SUM($B${m0}:$B${m1})", CALC, "#,##0")
a.ref["make"] = f"$B${rr}"
r = rr + 1

a.title(r, "3. 파는 활동 / How to sell — 런칭 전 준비와 판매 시 비용")
a.note(r + 1, "'런칭 전 총액'은 입점·샘플·초기 마케팅처럼 팔기 전에 쓰는 총비용입니다. '판매 시 …'는 팔 때마다 붙는 비용만 적습니다 "
              "(수수료·결제수수료·배송비·건당 광고비). 정액은 총액이 아니라 판매 단위 1개당 금액(판매 단위가 주문 1건이면 주문당 택배비도 여기), %는 퍼센트 숫자(예: 10)로 적으세요.")
s0, s1 = a.table(r + 2, ["활동 (to-do)", "금액 / 값", "구분", "메모"], 10, 2, "[>=1000]#,##0;General")
a.dropdown(SELL_KINDS, *[f"C{x}" for x in range(s0, s1 + 1)])
rr = s1 + 1


def ssum(kind):
    return f'=SUMIF($C${s0}:$C${s1},"{kind}",$B${s0}:$B${s1})'


for key, lab, kind, fmt in (("sell_once", "런칭 전 총액 합계", K_ONCE, "#,##0"),
                            ("fl", "판매 시 정액 (판매 단위당) 합계", K_FLAT, "#,##0"),
                            ("bn", "판매 시 순매출 대비 % 합계", K_NET, "General"),
                            ("bg", "판매 시 지불액 대비 % 합계", K_GROSS, "General")):
    a.cell(rr, 1, lab, CALC, bold=True)
    a.cell(rr, 2, ssum(kind), CALC, fmt)
    a.ref[key] = f"$B${rr}"
    rr += 1
a.cell(rr, 1, "구분을 고르지 않은 행 수", CALC)
a.cell(rr, 2, f'=COUNTIFS($B${s0}:$B${s1},"<>",$C${s0}:$C${s1},"")', CALC, "0")
a.hint(rr, "0이 아니면 구분을 선택하세요 (구분이 없는 행은 합계에 포함되지 않습니다)")
r = rr + 2

a.title(r, "3-2. 월 고정운영비 / Monthly fixed operating cost")
a.note(r + 1, "물량과 무관하게 매달 나가는 비용 (임대료, 상시 인건비, 구독·툴 비용 등).")
f0, f1 = a.table(r + 2, ["항목", "월 금액 (KRW)", "메모"], 6, 2)
rr = f1 + 1
a.cell(rr, 1, "월 고정운영비 합계", CALC, bold=True)
a.cell(rr, 2, f"=SUM($B${f0}:$B${f1})", CALC, "#,##0")
a.ref["fixed"] = f"$B${rr}"
r = rr + 2

a.title(r, "4. 판정 / Verdict — 초도물량으로 본전이 되는가")
a.note(r + 1, "초도 기준 판단용 계산입니다 (재고·외상 시차와 추가 생산은 반영하지 않음). 정식 계산은 웹 계산기에서 하세요.")
a.header(r + 2, ["항목", "값", "", "", "설명"])
e = r + 3
P, VAT, INC, N, T = A1["price"], A1["vat"], A1["inc"], A1["n"], A1["t"]
R1 = a.ref
READY1 = f'AND(ISNUMBER({P}),ISNUMBER({VAT}),OR({INC}="예",{INC}="아니오"),ISNUMBER({N}),ISNUMBER({T}))'


def g1(expr):
    return f'=IF(NOT({R1["ready"]}),"",{expr})'


e = a.calc(e, "ready", "필수 입력 완료", f"={READY1}", None, "판매가·부가세율·VAT 여부·수량·소진기간이 모두 입력되면 TRUE")
e = a.calc(e, "net", "판매 단위당 순매출 (VAT 제외 판매가)", g1(f'IF({INC}="예",{P}/(1+{VAT}/100),{P})'), "#,##0")
e = a.calc(e, "gross", "판매 단위당 고객 지불액 (VAT 포함)", g1(f'IF({INC}="예",{P},{P}*(1+{VAT}/100))'), "#,##0")
e = a.calc(e, "s", "판매 단위당 변동비 (판매 시)",
           g1(f'{R1["fl"]}+{R1["bn"]}/100*{R1["net"]}+{R1["bg"]}/100*{R1["gross"]}'), "#,##0",
           "정액 + 순매출 대비 % × 순매출 + 지불액 대비 % × 지불액")
e = a.calc(e, "w", "판매 단위당 남는 금액", g1(f'{R1["net"]}-{R1["s"]}'), "#,##0", "순매출 − 판매 단위당 변동비 (제작비·고정비 회수 전)")
e = a.calc(e, "c0", "초도 총비용", g1(f'{R1["make"]}+{R1["sell_once"]}'), "#,##0", "만드는 총비용 + 런칭 전 총액")
e = a.calc(e, "tot", "회수해야 할 총액", g1(f'{R1["c0"]}+{R1["fixed"]}*{T}'), "#,##0", "초도 총비용 + 월 고정운영비 × 소진기간")
e = a.calc(e, "beq", "본전에 필요한 누적 판매량",
           g1(f'IF({R1["w"]}>0,{R1["tot"]}/{R1["w"]},"불가 (판매 단위당 남는 금액 ≤ 0)")'), "#,##0.0",
           "회수해야 할 총액 ÷ 판매 단위당 남는 금액")
e = a.calc(e, "pct", "필요 판매량 ÷ 수량", g1(f'IF(AND(ISNUMBER({R1["beq"]}),{N}>0),{R1["beq"]}/{N},"")'), "0.0%",
           "100% 이하여야 초도물량으로 본전 가능")
e = a.calc(e, "bem", "필요 월 판매량 (소진기간 내 본전)", g1(f'IF(AND(ISNUMBER({R1["beq"]}),{T}>0),{R1["beq"]}/{T},"")'), "#,##0.0",
           "누적 필요 판매량 ÷ 소진기간")
e = a.calc(e, "m", "목표 월 판매량", g1(f'IF({T}>0,{N}/{T},"")'), "#,##0.0", "수량 ÷ 소진기간")
e = a.calc(e, "pl", "초도물량 전량 판매 시 손익", g1(f'{N}*{R1["w"]}-{R1["tot"]}'), "#,##0", "수량 × 판매 단위당 남는 금액 − 회수해야 할 총액")
DEN1 = f'(1-{R1["bn"]}/100-{R1["bg"]}/100*(1+{VAT}/100))'
e = a.calc(e, "price_be", "초도물량 전량 판매 시 본전 판매가",
           g1(f'IF({DEN1}<=0,"불가 (수수료율 합계 과다)",IF({INC}="예",(1+{VAT}/100),1)*'
              f'(({R1["tot"]}/{N})+{R1["fl"]})/{DEN1})'),
           "#,##0", "이 가격(입력한 VAT 기준)이면 소진기간 안에 전량 판매 시 손익 0")
a.cell(e, 1, "판정", CALC, bold=True)
a.ws.merge_cells(start_row=e, start_column=2, end_row=e, end_column=5)
vc = a.cell(e, 2, (
    f'=IF(NOT({R1["ready"]}),"필수 입력(판매가·부가세율·VAT 여부·수량·소진기간)을 채워 주세요",'
    f'IF({R1["w"]}<=0,"판매 단위당 남는 금액이 0 이하입니다 — 팔수록 손해. 가격·수수료를 다시 검토하세요",'
    f'IF({R1["pct"]}>1,"초도물량을 전부 팔아도 본전이 안 됩니다 — 가격 인상, 비용 절감, 고정비 축소 또는 기간·물량 조정을 검토하세요",'
    f'"초도물량으로 본전 가능 — 소진기간 안에 누적 "&IF(ROUND({R1["beq"]},1)=INT(ROUND({R1["beq"]},1)),TEXT(ROUND({R1["beq"]},1),"#,##0"),TEXT(ROUND({R1["beq"]},1),"#,##0.0"))&"단위(월 "&IF(ROUND({R1["bem"]},1)=INT(ROUND({R1["bem"]},1)),TEXT(ROUND({R1["bem"]},1),"#,##0"),TEXT(ROUND({R1["bem"]},1),"#,##0.0"))&"단위) 이상 판매 필요, 목표는 월 "&IF(ROUND({R1["m"]},1)=INT(ROUND({R1["m"]},1)),TEXT(ROUND({R1["m"]},1),"#,##0"),TEXT(ROUND({R1["m"]},1),"#,##0.0"))&"단위")))'
), CALC, bold=True)
vc.alignment = WRAP
w1.row_dimensions[e].height = 48
a.ref["verdict"] = f"$B${e}"
r = e + 2

a.title(r, "5. 계산기에 입력할 값 / Values to type into the calculator")
a.note(r + 1, "이 표(라벨과 값 두 열)를 복사해 웹 계산기의 '시트 값 붙여넣기'에 붙여넣으면 자동으로 채워집니다. 직접 옮겨 적어도 됩니다. 판매 단위당 직접원가는 초도 총비용으로 환산한 '초도 완전원가'라 양산 때보다 높게 나옵니다. "
              "월 고정운영비에는 런칭 전 총액을 소진기간으로 나눈 월 상각이 포함됩니다 (계산기 결과는 이 시트의 판정과 근사치로만 같습니다).")
q0 = r + 2
a.ref["u_all"] = f"$B${q0 + 3}"
a.ref["fm1"] = f"$B${q0 + 7}"
rows5 = [
    ("실제 판매가 (KRW)", f'=IF({P}="","",{P})', "#,##0"),
    ("부가세율 (%)", f'=IF({VAT}="","",{VAT})', "0.0"),
    ("VAT 포함가 체크", f'=IF({INC}="","",IF({INC}="예","체크","해제"))', None),
    ("직접원가 (판매 단위당, 초도 완전원가)", g1(f'IF({N}>0,{R1["make"]}/{N},"")'), "#,##0"),
    ("변동비: 정액 (판매 단위당)", f'={R1["fl"]}', "#,##0"),
    ("변동비: 순매출 대비 (%)", f'={R1["bn"]}', "General"),
    ("변동비: 지불액 대비 (%)", f'={R1["bg"]}', "General"),
    ("월 고정운영비 (런칭 전 총액 상각 포함, KRW)",
     g1(f'IF({T}>0,{R1["fixed"]}+{R1["sell_once"]}/{T},"")'), "#,##0"),
    ("월 계획 판매량 (판매 단위 수) — 목표 월 판매량", f'={R1["m"]}', "#,##0.0"),
]
for i, (lab, f, fmt) in enumerate(rows5):
    a.cell(q0 + i, 1, lab, CALC, bold=True)
    a.cell(q0 + i, 2, f, CALC, fmt)
qq = q0 + len(rows5)
a.note(qq, "목표 공헌이익률·정가 대비 할인율·목표 시장가격은 이 시트에서 입력하지 않습니다. 위 값을 계산기에 넣은 뒤 계산기에서 정하며, "
           "각각 MODE B(목표 가격 역산), MODE C(허용 직접원가)에서 쓰입니다.")
w1.freeze_panes = "A5"
LAYOUT[S1] = {"A": A1, "REF": dict(a.ref), "make": [m0, m1], "sell": [s0, s1], "fixed": [f0, f1]}

# =====================================================================  양산 (scale)
w2 = wb.create_sheet(S2)
b = Sheet(w2)
w2.cell(1, 1, "양산 기준 정리 / Planning at scale").font = Font(bold=True, size=14)
b.note(2, "규모를 키워 다시 만들 때를 정리합니다. 이 탭의 값은 견적서나 근거 있는 가정으로 채우세요 (근거 없이 낙관적으로 쓰면 비교가 무의미합니다). "
          "업종·부가세·VAT 포함 여부는 '초도' 탭 값을 그대로 씁니다.")
b.note(3, "판매가·변동비·월 고정운영비는 비워 두면 '초도' 탭 값을 그대로 씁니다. 바뀌는 항목만 입력하세요.")
r = 5
b.title(r, "1. 양산 가정 / Assumptions at scale")
r = b.inputs(r + 1, [
    ("q", "양산 수량 (한 번에 만드는 수량, 판매 단위 수)", "#,##0", "이 수량을 다시 만들 때의 반복 비용을 아래 2번에 적습니다"),
    ("m", "양산 시 월 목표 판매량 (판매 단위 수)", "#,##0.0", "본전 판매가와 판정에 사용"),
    ("o_price", "양산 시 판매가 (KRW)", "#,##0", "비우면 초도 판매가와 같음 (초도와 같은 VAT 기준)"),
])
r += 1
b.title(r, "2. 양산 시 만드는 비용 / Repeat production cost")
b.note(r + 1, "같은 설비를 이미 갖고 있다고 보고, 양산 수량을 다시 만들 때 또 드는 비용(재료·가공·외주 제작·포장·건당 인건비)의 총비용을 적으세요. "
              "초도 때 산 금형·장치는 여기에 다시 적지 않습니다.")
rp0, rp1 = b.table(r + 2, ["활동 (to-do)", "총 비용 (KRW, 양산 수량 기준)", "메모"], 8, 2)
rr = rp1 + 1
rr = b.calc(rr, "c_rep", "양산 시 만드는 총비용 합계", f"=SUM($B${rp0}:$B${rp1})", "#,##0")
r = rr + 1
b.title(r, "3. 새로 드는 투자 / New investment")
b.note(r + 1, "양산을 위해 새로 사는 설비나 증설 비용이 있으면 적으세요. 제품·서비스 수명주기(개월)로 나눠 월 고정비에 더합니다. 없으면 비워 두세요.")
iv0, iv1 = b.table(r + 2, ["항목", "총 비용 (KRW)", "메모"], 4, 2)
rr = iv1 + 1
rr = b.calc(rr, "invest", "새 투자 합계", f"=SUM($B${iv0}:$B${iv1})", "#,##0")
rr = b.inputs(rr, [("life", "제품/서비스 수명주기 (개월)", "General", "새 투자가 있으면 입력 (장치는 내용연수와 수명주기 중 짧은 쪽)")])
r = rr + 1
b.title(r, "4. 판매·고정비 변경분 / Overrides (비우면 초도 값)")
r = b.inputs(r + 1, [
    ("o_fl", "판매 시 정액 (판매 단위당 합계, KRW)", "[>=1000]#,##0;General", "비우면 초도의 판매 시 정액 합계"),
    ("o_bn", "판매 시 순매출 대비 % 합계", "General", "비우면 초도 값"),
    ("o_bg", "판매 시 지불액 대비 % 합계", "General", "비우면 초도 값"),
    ("o_fixed", "월 고정운영비 (KRW)", "#,##0", "비우면 초도의 월 고정운영비 합계"),
])
for k in ("o_fl", "o_bn", "o_bg", "o_fixed"):
    pass
r += 1
b.title(r, "5. 판정 / Verdict at scale")
b.note(r + 1, "양산 기준 판단용 계산입니다. 정식 계산은 웹 계산기에서 하세요.")
b.header(r + 2, ["항목", "값", "", "", "설명"])
e = r + 3
R2 = b.ref
X = lambda k: q(S1, A1[k]) if k in A1 else q(S1, LAYOUT[S1]["REF"][k])  # noqa: E731
VAT2, INC2 = q(S1, A1["vat"]), q(S1, A1["inc"])
def g2(expr):
    return f'=IF(NOT({R2["ready"]}),"",{expr})'


e = b.calc(e, "price", "적용 판매가 (KRW)",
           f'=IF(ISNUMBER({R2["o_price"]}),{R2["o_price"]},IF(ISNUMBER({X("price")}),{X("price")},""))', "#,##0", "양산 판매가, 비었으면 초도 판매가")
READY2 = (f'AND(ISNUMBER({R2["price"]}),ISNUMBER({VAT2}),OR({INC2}="예",{INC2}="아니오"),'
          f'ISNUMBER({R2["q"]}),ISNUMBER({R2["m"]}))')
e = b.calc(e, "ready", "필수 입력 완료", f"={READY2}", None, "적용 판매가·'초도' 탭의 부가세율·VAT 여부·양산 수량·월 목표 판매량이 입력되면 TRUE")
e = b.calc(e, "net", "판매 단위당 순매출 (VAT 제외 판매가)", g2(f'IF({INC2}="예",{R2["price"]}/(1+{VAT2}/100),{R2["price"]})'), "#,##0")
e = b.calc(e, "gross", "판매 단위당 고객 지불액 (VAT 포함)", g2(f'IF({INC2}="예",{R2["price"]},{R2["price"]}*(1+{VAT2}/100))'), "#,##0")
e = b.calc(e, "u", "판매 단위당 직접원가 (양산)", g2(f'IF({R2["q"]}>0,{R2["c_rep"]}/{R2["q"]},"수량 > 0 필요")'), "#,##0", "양산 시 만드는 총비용 ÷ 양산 수량")
e = b.calc(e, "fl", "적용 판매 시 정액 합계", g2(f'IF(ISNUMBER({R2["o_fl"]}),{R2["o_fl"]},{X("fl")})'), "#,##0")
e = b.calc(e, "bn", "적용 순매출 대비 % 합계", g2(f'IF(ISNUMBER({R2["o_bn"]}),{R2["o_bn"]},{X("bn")})'), "General")
e = b.calc(e, "bg", "적용 지불액 대비 % 합계", g2(f'IF(ISNUMBER({R2["o_bg"]}),{R2["o_bg"]},{X("bg")})'), "General")
e = b.calc(e, "s", "판매 단위당 변동비 (판매 시)", g2(f'{R2["fl"]}+{R2["bn"]}/100*{R2["net"]}+{R2["bg"]}/100*{R2["gross"]}'), "#,##0")
e = b.calc(e, "cm", "판매 단위당 공헌이익", g2(f'IF(ISNUMBER({R2["u"]}),{R2["net"]}-{R2["u"]}-{R2["s"]},"")'), "#,##0",
           "순매출 − 판매 단위당 직접원가 − 판매 단위당 변동비")
e = b.calc(e, "fixed", "적용 월 고정운영비", g2(f'IF(ISNUMBER({R2["o_fixed"]}),{R2["o_fixed"]},{X("fixed")})'), "#,##0")
e = b.calc(e, "amort", "월 상각액 (새 투자)", g2(f'IF({R2["invest"]}=0,0,IF(N({R2["life"]})>0,{R2["invest"]}/{R2["life"]},"수명주기 입력 필요"))'),
           "#,##0", "새 투자 ÷ 수명주기")
e = b.calc(e, "fm", "월 고정비 (상각 포함)", g2(f'IF(ISNUMBER({R2["amort"]}),{R2["fixed"]}+{R2["amort"]},"")'), "#,##0",
           "→ 계산기의 '월 고정운영비'에 입력")
e = b.calc(e, "bem", "월 손익분기 판매량",
           g2(f'IF(OR(NOT(ISNUMBER({R2["fm"]})),NOT(ISNUMBER({R2["cm"]}))),"",'
              f'IF({R2["cm"]}>0,{R2["fm"]}/{R2["cm"]},IF({R2["fm"]}=0,"해당 없음","불가 (공헌이익 ≤ 0)")))'),
           "#,##0.0", "월 고정비 ÷ 판매 단위당 공헌이익 (계산기 BEP와 같은 식)")
e = b.calc(e, "pct", "월 손익분기 ÷ 월 목표 판매량", g2(f'IF(AND(ISNUMBER({R2["bem"]}),{R2["m"]}>0),{R2["bem"]}/{R2["m"]},"")'), "0.0%",
           "100% 이하여야 목표 판매 속도로 본전")
e = b.calc(e, "pl", "월 손익 (목표 월 판매량 기준)",
           g2(f'IF(AND(ISNUMBER({R2["fm"]}),ISNUMBER({R2["cm"]})),{R2["m"]}*{R2["cm"]}-{R2["fm"]},"")'), "#,##0")
DEN2 = f'(1-{R2["bn"]}/100-{R2["bg"]}/100*(1+{VAT2}/100))'
e = b.calc(e, "price_be", "월 목표 판매량에서 본전 판매가",
           g2(f'IF(OR(NOT(ISNUMBER({R2["fm"]})),NOT(ISNUMBER({R2["u"]}))),"",IF({DEN2}<=0,"불가 (수수료율 합계 과다)",'
              f'IF({INC2}="예",(1+{VAT2}/100),1)*({R2["u"]}+{R2["fl"]}+{R2["fm"]}/{R2["m"]})/{DEN2}))'),
           "#,##0", "이 가격이면 월 목표 판매량에서 월 손익 0")
b.cell(e, 1, "판정", CALC, bold=True)
b.ws.merge_cells(start_row=e, start_column=2, end_row=e, end_column=5)
vc = b.cell(e, 2, (
    f'=IF(NOT({R2["ready"]}),"필수 입력(양산 수량·월 목표 판매량, 판매가, 초도 탭의 부가세율·VAT 여부)을 채워 주세요",'
    f'IF(NOT(ISNUMBER({R2["cm"]})),"비용 입력을 확인하세요",'
    f'IF({R2["cm"]}<=0,"판매 단위당 공헌이익이 0 이하입니다 — 팔수록 손해. 가격·원가·수수료를 다시 검토하세요",'
    f'IF(NOT(ISNUMBER({R2["pct"]})),"고정비·수명주기 입력을 확인하세요",'
    f'IF({R2["pct"]}>1,"목표 월 판매량으로는 본전이 안 됩니다 — 월 손익분기 "&IF(ROUND({R2["bem"]},1)=INT(ROUND({R2["bem"]},1)),TEXT(ROUND({R2["bem"]},1),"#,##0"),TEXT(ROUND({R2["bem"]},1),"#,##0.0"))&"단위가 필요합니다",'
    f'"목표 월 판매량으로 본전 가능 — 월 "&IF(ROUND({R2["bem"]},1)=INT(ROUND({R2["bem"]},1)),TEXT(ROUND({R2["bem"]},1),"#,##0"),TEXT(ROUND({R2["bem"]},1),"#,##0.0"))&"단위 이상 판매 필요")))))'
), CALC, bold=True)
vc.alignment = WRAP
w2.row_dimensions[e].height = 48
b.ref["verdict"] = f"$B${e}"
r = e + 2
b.title(r, "6. 계산기에 입력할 값 / Values to type into the calculator")
b.note(r + 1, "이 표(라벨과 값 두 열)를 복사해 웹 계산기의 '시트 값 붙여넣기'에 붙여넣으면 자동으로 채워집니다 (양산 기준). 직접 옮겨 적어도 됩니다.")
q0 = r + 2
rows6 = [
    ("실제 판매가 (KRW)", f'={R2["price"]}', "#,##0"),
    ("부가세율 (%)", f'=IF({VAT2}="","",{VAT2})', "0.0"),
    ("VAT 포함가 체크", f'=IF({INC2}="","",IF({INC2}="예","체크","해제"))', None),
    ("직접원가 (판매 단위당, 양산)", f'={R2["u"]}', "#,##0"),
    ("변동비: 정액 (판매 단위당)", f'={R2["fl"]}', "#,##0"),
    ("변동비: 순매출 대비 (%)", f'={R2["bn"]}', "General"),
    ("변동비: 지불액 대비 (%)", f'={R2["bg"]}', "General"),
    ("월 고정운영비 (상각 포함, KRW)", f'={R2["fm"]}', "#,##0"),
    ("월 계획 판매량 (판매 단위 수) — 월 목표 판매량", f'=IF(ISNUMBER({R2["m"]}),{R2["m"]},"")', "#,##0.0"),
]
for i, (lab, f, fmt) in enumerate(rows6):
    b.cell(q0 + i, 1, lab, CALC, bold=True)
    b.cell(q0 + i, 2, f, CALC, fmt)
w2.freeze_panes = "A5"
LAYOUT[S2] = {"REF": dict(b.ref), "repeat": [rp0, rp1], "invest": [iv0, iv1]}

# =====================================================================  비교
w3 = wb.create_sheet(S3)
c = Sheet(w3)
w3.cell(1, 1, "초도 vs 양산 비교 / Comparison").font = Font(bold=True, size=14)
c.note(2, "두 탭의 값을 같은 정의로 나란히 보여줍니다. 양산 탭 값은 견적·가정이므로 '얼마나 개선되는가'의 방향을 보는 용도로 쓰세요.")
c.note(3, "월 손익분기는 계산기의 BEP와 같은 식(월 고정비 ÷ 판매 단위당 공헌이익)으로 양쪽을 맞췄습니다. 초도 쪽 직접원가는 초도 총비용으로 환산한 '초도 완전원가'입니다.")
for col, w in zip("ABCDE", (44, 22, 22, 22, 50)):
    w3.column_dimensions[col].width = w
c.header(5, ["항목", "초도", "양산", "차이 (양산 − 초도)", "설명"])
R1x, R2x = LAYOUT[S1]["REF"], LAYOUT[S2]["REF"]
T1 = q(S1, A1["t"])
cmp_rows = [
    ("price", "판매 단위당 판매가 (KRW)", q(S1, A1["price"]), q(S2, R2x["price"]), "#,##0", "양산 탭의 적용 판매가"),
    ("net", "판매 단위당 순매출 (VAT 제외)", q(S1, R1x["net"]), q(S2, R2x["net"]), "#,##0", ""),
    ("u", "판매 단위당 직접원가", q(S1, LAYOUT[S1]["REF"]["u_all"]), q(S2, R2x["u"]), "#,##0", "초도: 만드는 총비용 ÷ 초도수량 / 양산: 반복 비용 ÷ 양산 수량"),
    ("s", "판매 단위당 변동비 (판매 시)", q(S1, R1x["s"]), q(S2, R2x["s"]), "#,##0", ""),
    ("cm", "판매 단위당 공헌이익", None, q(S2, R2x["cm"]), "#,##0", "순매출 − 판매 단위당 직접원가 − 판매 단위당 변동비"),
    ("fm", "월 고정비 (상각 포함)", q(S1, LAYOUT[S1]["REF"]["fm1"]), q(S2, R2x["fm"]), "#,##0", "초도: 월 고정운영비 + 런칭 전 총액 ÷ 소진기간 / 양산: 월 고정운영비 + 새 투자 상각"),
    ("bem", "월 손익분기 판매량", None, q(S2, R2x["bem"]), "#,##0.0", "월 고정비 ÷ 판매 단위당 공헌이익"),
]
rr = 6
CR = {}
for key, lab, f1, f2, fmt, h in cmp_rows:
    c.cell(rr, 1, lab, CALC, bold=True)
    CR[key] = rr
    if key == "cm":
        v1 = f'=IF(AND(ISNUMBER(B{CR["net"]}),ISNUMBER(B{CR["u"]}),ISNUMBER(B{CR["s"]})),B{CR["net"]}-B{CR["u"]}-B{CR["s"]},"")'
    elif key == "bem":
        v1 = (f'=IF(AND(ISNUMBER(B{CR["fm"]}),ISNUMBER(B{CR["cm"]})),IF(B{CR["cm"]}>0,B{CR["fm"]}/B{CR["cm"]},'
              f'IF(B{CR["fm"]}=0,"해당 없음","불가 (공헌이익 ≤ 0)")),"")')
    else:
        v1 = f"={f1}"
    c.cell(rr, 2, v1, CALC, fmt)
    c.cell(rr, 3, f"={f2}", CALC, fmt)
    c.cell(rr, 4, f'=IF(AND(ISNUMBER(B{rr}),ISNUMBER(C{rr})),C{rr}-B{rr},"")', CALC, fmt)
    c.hint(rr, h)
    rr += 1
c.cell(rr, 1, "본전 판매가 (VAT 기준은 초도 탭과 같음)", CALC, bold=True)
c.cell(rr, 2, f"={q(S1, R1x['price_be'])}", CALC, "#,##0")
c.cell(rr, 3, f"={q(S2, R2x['price_be'])}", CALC, "#,##0")
c.cell(rr, 4, f'=IF(AND(ISNUMBER(B{rr}),ISNUMBER(C{rr})),C{rr}-B{rr},"")', CALC, "#,##0")
c.hint(rr, "초도: 전량 판매·소진기간 기준 / 양산: 월 목표 판매량 기준 (기준 물량이 다릅니다)")
CR["price_be"] = rr
rr += 1
c.cell(rr, 1, "판매 단위당 직접원가 절감률", CALC, bold=True)
c.cell(rr, 2, "", CALC)
c.cell(rr, 3, f'=IF(AND(ISNUMBER(B{CR["u"]}),ISNUMBER(C{CR["u"]}),B{CR["u"]}>0),1-C{CR["u"]}/B{CR["u"]},"")', CALC, "0.0%")
c.cell(rr, 4, "", CALC)
c.hint(rr, "양산 시 판매 단위당 직접원가가 초도 대비 얼마나 줄었는지")
CR["saving"] = rr
rr += 2
c.cell(rr, 1, "해석", CALC, bold=True)
c.ws.merge_cells(start_row=rr, start_column=2, end_row=rr, end_column=5)
vc = c.cell(rr, 2, (
    f'=IF(NOT(AND(ISNUMBER(B{CR["cm"]}),ISNUMBER(C{CR["cm"]}))),"두 탭의 필수 입력을 채우면 비교가 표시됩니다",'
    f'"양산하면 판매 단위당 직접원가가 "&TEXT(ABS(C{CR["saving"]}),"0%")&IF(C{CR["saving"]}>=0," 낮아지고"," 높아지고")&", 판매 단위당 공헌이익은 "&TEXT(B{CR["cm"]},"#,##0")&"원에서 "&TEXT(C{CR["cm"]},"#,##0")&"원이 됩니다. '
    f'월 손익분기는 "&IF(AND(ISNUMBER(B{CR["bem"]}),ISNUMBER(C{CR["bem"]})),IF(ROUND(B{CR["bem"]},1)=INT(ROUND(B{CR["bem"]},1)),TEXT(ROUND(B{CR["bem"]},1),"#,##0"),TEXT(ROUND(B{CR["bem"]},1),"#,##0.0"))&"단위에서 "&IF(ROUND(C{CR["bem"]},1)=INT(ROUND(C{CR["bem"]},1)),TEXT(ROUND(C{CR["bem"]},1),"#,##0"),TEXT(ROUND(C{CR["bem"]},1),"#,##0.0"))&"단위로 바뀝니다.","확인이 필요합니다."))'
), CALC, bold=True)
vc.alignment = WRAP
w3.row_dimensions[rr].height = 48
c.ref["verdict"] = f"$B${rr}"
LAYOUT[S3] = {"REF": dict(c.ref), "rows": CR}
w3.freeze_panes = "A6"

# =====================================================================  사용법
GUIDE = [
    ("h", "입력 정리 시트 사용법"),
    ("p", "이 시트는 웹 계산기에 넣을 값을 미리 정리하고, 처음 만드는 물량(초도)으로 본전이 되는지와 규모를 키웠을 때(양산)의 차이를 가늠해 보는 양식입니다. "
          "입력한 내용은 이 파일(내 컴퓨터)에만 저장되며 어디로도 전송되지 않습니다. 노란 칸만 입력하고, 회색 칸은 자동 계산입니다."),
    ("h", "탭 구성"),
    ("p", "· 초도: 처음 만드는 물량 기준. 만드는 활동·파는 활동의 총비용을 적고 판정을 봅니다.\n"
          "· 양산: 규모를 키워 다시 만들 때 기준. 반복 비용, 새 투자, 바뀌는 변동비·고정비를 적습니다.\n"
          "· 비교: 초도와 양산을 같은 정의로 나란히 보여줍니다 (입력 없음).\n"
          "· 사용법: 지금 보는 탭입니다."),
    ("h", "초도 탭 작성 순서"),
    ("p", "① 1. 가정: 업종, 판매 단위(낱개 1개, 6개입 세트, 1건처럼 한 번 팔 때의 단위. 판매가·수량·모든 비용이 이 단위 기준입니다), 초도생산 수량(판매 단위 수. 서비스는 수용 한도가 아니라 이 기간 안에 팔려는 목표 판매 수), 목표 소진기간(서비스는 목표 판매 기간, 개월), 판매가, 부가세, VAT 포함 여부를 입력합니다.\n"
          "② 2. 만드는 활동: 런칭 직전까지 만드는 데 드는 일(to-do)을 한 줄씩 적고 그 일에 드는 총비용을 적습니다. 구분은 필요 없습니다. "
          "제조는 재료·가공·금형·장치·포장, 서비스는 기획·개발·디자인 인건비 등입니다.\n"
          "③ 3. 파는 활동: 런칭 전에 쓰는 총비용은 '런칭 전 총액'으로, 팔 때마다 붙는 비용은 '판매 시 …'로 구분을 고릅니다. 구분을 고르지 않은 행은 합계에서 빠지며, "
          "표 아래 '구분을 고르지 않은 행 수'가 0이 아니면 선택하라는 뜻입니다.\n"
          "④ 3-2. 월 고정운영비: 물량과 무관하게 매달 나가는 비용을 적습니다.\n"
          "⑤ 4. 판정에서 본전 가능 여부를 읽고, 5. 계산기에 입력할 값 표(라벨과 값 두 열)를 복사해 웹 계산기의 '시트 값 붙여넣기'에 붙여넣습니다(직접 옮겨 적어도 됩니다)."),
    ("h", "판매 단위"),
    ("p", "이 시트는 판매 품목 하나, 판매 단위 하나를 기준으로 정리합니다. 판매 단위가 낱개 1개이면 모든 금액이 낱개당, 6개입 세트이면 세트당, 주문 1건이면 주문당입니다. "
          "단위가 다르면 환산해서 적으세요(낱개 원가 1,000원인 6개입 세트는 6,000원). 낱개와 묶음을 모두 판다면 주력 판매 단위로 한 번, 다른 단위로 한 번 따로 정리합니다."),
    ("h", "판매 시 비용을 적는 법"),
    ("p", "· 판매 시 정액(판매 단위당): 판매 단위 1개를 팔 때마다 붙는 고정 금액(배송비 등). 총액이 아니라 판매 단위 1개당 금액을 적습니다. 판매 단위가 주문 1건이면 주문당 택배비가 그대로 해당합니다.\n"
          "· 판매 시 순매출 대비 %: VAT를 뺀 판매가의 몇 %가 붙는 비용(플랫폼 수수료 등). 퍼센트 숫자만 적습니다(예: 10).\n"
          "· 판매 시 지불액 대비 %: VAT를 포함한 고객 결제액의 몇 %가 붙는 비용(결제수수료 등).\n"
          "제작 관련 비용은 2번에, 판매·배송 비용은 3번에만 적으세요. 같은 비용을 두 곳에 넣으면 두 번 차감됩니다."),
    ("h", "양산 탭 작성 순서"),
    ("p", "① 양산 수량(한 번에 만드는 수량)과 양산 시 월 목표 판매량을 입력합니다.\n"
          "② 같은 설비를 이미 갖고 있다고 보고, 양산 수량을 다시 만들 때 또 드는 비용의 총비용을 적습니다. 초도 때 산 금형·장치는 다시 적지 않습니다.\n"
          "③ 양산을 위해 새로 사는 설비가 있으면 적고, 수명주기(개월)를 입력합니다.\n"
          "④ 판매가·변동비·월 고정운영비가 초도와 다르면 4번 칸에 적습니다. 비워 두면 초도 값을 그대로 씁니다.\n"
          "이 탭의 값은 견적서나 근거 있는 가정으로 채우세요. 근거 없이 낙관적으로 쓰면 비교가 의미가 없습니다."),
    ("h", "판정 읽는 법"),
    ("p", "· 초도 판정: 초도 총비용과 소진기간 동안의 월 고정운영비를 합한 '회수해야 할 총액'을, 판매 단위당 남는 금액(순매출 − 판매 단위당 변동비)으로 나눈 것이 "
          "본전에 필요한 누적 판매량입니다. 이 수량이 초도수량의 100%를 넘으면 초도물량을 모두 팔아도 본전이 안 됩니다.\n"
          "· 본전 판매가: 초도물량을 소진기간 안에 모두 팔았을 때 손익이 0이 되는 가격입니다(입력한 VAT 기준).\n"
          "· 양산 판정: 판매 단위당 공헌이익(순매출 − 판매 단위당 직접원가 − 판매 단위당 변동비), 월 손익분기 판매량(월 고정비 ÷ 판매 단위당 공헌이익), 월 목표 판매량과의 비교를 봅니다.\n"
          "· 비교 탭: 판매 단위당 직접원가 절감률, 판매 단위당 공헌이익, 월 손익분기가 초도에서 양산으로 어떻게 바뀌는지 봅니다."),
    ("h", "계산기에 옮길 때 주의"),
    ("p", "· 초도 탭의 '직접원가(판매 단위당)'는 초도 총비용으로 환산한 초도 완전원가라 양산 때보다 높습니다. 지금 당장의 생존 판단에는 초도 값을, "
          "규모를 키운 뒤의 가격 판단에는 양산 값을 쓰세요.\n"
          "· 계산기는 판매 단위당 직접원가와 월 고정비로 계산하므로 이 시트의 판정과 결과가 근사치로만 같습니다.\n"
          "· 판정은 재고·외상 같은 시차와 추가 생산을 반영하지 않는 간이 판단이며, 세법상 감가상각과 다를 수 있는 가격 판단용 관리 계산입니다."),
    ("h", "작은 예시 (가상의 숫자)"),
    ("p", "초도 200개(판매 단위: 낱개 1개), 소진기간 6개월, 판매가 35,000원(VAT 포함 10%), 만드는 총비용 900만 원, 결제수수료 2.5%(판매 시 지불액 대비 %), "
          "월 고정운영비 30만 원이면 → 회수해야 할 총액 1,080만 원, 판매 단위당 남는 금액 약 30,943원이라 본전에 약 349개가 필요합니다. "
          "초도 200개를 모두 팔아도 본전이 안 된다는 판정이 나옵니다. 양산 탭에서 1,000개를 다시 만드는 반복 비용이 총 1,500만 원(판매 단위당 15,000원)이라면 "
          "판매 단위당 직접원가가 초도 45,000원에서 15,000원으로 줄어드는 것을 비교 탭에서 볼 수 있습니다."),
]
gs = wb.create_sheet(SG)
gs.column_dimensions["A"].width = 120
gs.sheet_view.showGridLines = False
for i, (kind, text) in enumerate(GUIDE, 1):
    cc = gs.cell(i, 1, text)
    cc.alignment = WRAP
    if kind == "h":
        cc.font = Font(bold=True, size=13 if i == 1 else 12, color="1E4C40")
    else:
        gs.row_dimensions[i].height = 16 * sum(len(line) // 55 + 1 for line in text.split("\n"))
wb.active = 0
wb.save(OUT)
(HERE / "_layout.json").write_text(json.dumps(LAYOUT, ensure_ascii=False), encoding="utf-8")
print("wrote", OUT)
