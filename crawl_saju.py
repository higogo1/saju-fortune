"""unsin.co.kr 평생사주(total) 결과를 Firecrawl로 크롤링.

사용 예:
  python crawl_saju.py --name 홍길동 --sex 남 --year 1990 --month 1 --day 1 --hour 0 --solunar S_C
  hour: 0=모름, 01 子, 02 丑, 04 寅, 06 卯, 08 辰, 10 巳, 12 午, 14 未, 16 申, 18 酉, 20 戌, 22 亥
  solunar: S_C 양력, L_C 음력(평달), L_L 음력(윤달)
"""
import argparse
import json
import os
import re
from pathlib import Path

import urllib.request

FORM_URL = "https://www.unsin.co.kr/unse/saju/total/form"
API_URL = "https://api.firecrawl.dev/v2/scrape"
# 사이트 이미지 번호(a1~a10, b1~b12) -> 천간/지지
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "寅卯辰巳午未申酉戌亥子丑"
SECTIONS = [
    "평생에 걸친 운세 총평입니다.", "초년운", "중년운", "말년운", "건강운", "체질운",
    "사회운", "사회적성격", "성격운", "타고난 성향", "타고난 인품", "이성운",
    "애정운", "재물운", "재물모으는법", "재물손실 막는법", "재테크비법",
]


def load_api_key():
    key = os.environ.get("FIRECRAWL_API_KEY")
    env = Path(__file__).with_name(".env")
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("FIRECRAWL_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"\'')
    if not key:
        raise SystemExit("FIRECRAWL_API_KEY not found")
    return key


def build_js(a):
    fields = {
        "user_name": a.name, "sex": a.sex, "birth_yyyy": str(a.year),
        "birth_mm": f"{a.month:02d}", "birth_dd": f"{a.day:02d}",
        "birth_hh": a.hour, "birth_solunar": a.solunar,
    }
    return (
        f"const v={json.dumps(fields, ensure_ascii=False)};"
        "const f=document.getElementById('frm');"
        "for(const [k,val] of Object.entries(v)){const el=f.elements[k];"
        "if(el.tagName==='SELECT'&&![...el.options].some(o=>o.value===val)){"
        "const o=document.createElement('option');o.value=val;el.appendChild(o);}"
        "el.value=val;}"
        "HTMLFormElement.prototype.submit.call(f);"
    )


def scrape(key, a, form_url=FORM_URL):
    body = {
        "url": form_url,
        "formats": ["markdown"],
        "onlyMainContent": True,
        "actions": [
            {"type": "wait", "milliseconds": 1500},
            {"type": "executeJavascript", "script": build_js(a)},
            {"type": "wait", "milliseconds": 4000},
        ],
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        res = json.load(r)
    if not res.get("success"):
        raise SystemExit(f"Firecrawl error: {res}")
    return res["data"]["markdown"]


def parse(md):
    out = {}
    table = {}
    for row, label in (("天干천간", "천간"), ("地支지지", "지지")):
        for cell in re.findall(r"!\[([^\]]*)\]\([^)]*/([ab])(\d+)\.gif\)([^|]*)",
                               (re.search(r"\| " + row + r" \|(.*)", md) or [None, ""])[1]):
            pos, kind, idx, sipsung = cell
            chars = STEMS if kind == "a" else BRANCHES
            table.setdefault(pos, {})[label] = chars[int(idx) - 1]
            table[pos][label + "_십성"] = sipsung.strip()
    if table:
        out["사주명식"] = table
    for i, name in enumerate(SECTIONS):
        pat = r"## " + re.escape(name) + r"\s*\n(.*?)(?=\n## |\n- 카카오|\Z)"
        s = re.search(pat, md, re.S)
        if s:
            out[name.rstrip(".")] = s.group(1).strip()
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", default="홍길동")
    p.add_argument("--sex", default="남", choices=["남", "여"])
    p.add_argument("--year", type=int, default=1990)
    p.add_argument("--month", type=int, default=1)
    p.add_argument("--day", type=int, default=1)
    p.add_argument("--hour", default="0")
    p.add_argument("--solunar", default="S_C", choices=["S_C", "L_C", "L_L"])
    p.add_argument("--out", default="saju_result")
    a = p.parse_args()

    md = scrape(load_api_key(), a)
    Path(f"{a.out}.md").write_text(md, encoding="utf-8")
    data = {"input": vars(a), "result": parse(md)}
    Path(f"{a.out}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {a.out}.md / {a.out}.json ({len(data['result'])} sections)")


if __name__ == "__main__":
    main()
