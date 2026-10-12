"""운세 웹앱: 이름/생년월일 입력 후 옵션(오늘의 운, 조심해야 할 것, 부자되는 방법)을 골라 보는 로컬 서버.

실행: python app.py  ->  http://localhost:8000
데이터는 crawl_saju.py의 Firecrawl 크롤러로 unsin.co.kr에서 가져온다.
"""
import argparse
import datetime
import hashlib
import json
import re
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import crawl_saju

TODAY_FORM = "https://www.unsin.co.kr/unse/free/todayline/form?linenum=01&sid=tunse"
TOTAL_FORM = crawl_saju.FORM_URL
INDEX = Path(__file__).with_name("index.html")
CACHE = Path(__file__).with_name("cache")

HANJA = re.compile(r"[㐀-䶿一-鿿豈-﫿]+")
# 요약 문장 고를 때 가산점을 주는 표현 (많이 걸릴수록 우선)
CAUTION_WORDS = r"조심|주의|금물|피하|삼가|않도록|멀리|위험|손해|잃을|소홀|게을리|성급|해야|좋겠|좋습니다|좋으며"
RICH_WORDS = r"모을|모으|저축|투자|재테크|관리|큰 돈|부자|재물|금전|해야|좋겠|좋습니다|좋으며"

# 옵션별: 어느 페이지에서, 어떤 섹션을 보여주고, 요약은 어디서 뽑는지
OPTIONS = {
    "today": {
        "form": TODAY_FORM,
        "sections": ["한마디 운세", "애정운", "소망운", "사업운", "금전운", "오늘 이 방향으로 가보세요"],
        "summary": [("금전운", None), ("사업운", None), ("오늘 이 방향으로 가보세요", r"길하|좋")],
    },
    "caution": {
        "form": TOTAL_FORM,
        "sections": ["건강운", "체질운", "재물손실 막는법"],
        "summary": [("건강운", CAUTION_WORDS), ("체질운", CAUTION_WORDS), ("재물손실 막는법", CAUTION_WORDS)],
    },
    "rich": {
        "form": TOTAL_FORM,
        "sections": ["재물운", "재물모으는법", "재테크비법"],
        "summary": [("재물운", RICH_WORDS), ("재물모으는법", RICH_WORDS), ("재테크비법", RICH_WORDS)],
    },
}

def strip_hanja(text):
    text = HANJA.sub("", text)
    text = re.sub(r"\(\s*\)|（\s*）", "", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def split_sections(md):
    """'## 제목' 단위로 본문을 나눈다."""
    out = {}
    for m in re.finditer(r"^## (.+?)\s*\n(.*?)(?=^## |^- 카카오|^- 어제의 운세|\Z)", md, re.M | re.S):
        out[m.group(1).strip().rstrip(".")] = m.group(2).strip()
    return out


def sentences(text):
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 8]


def pick_sentence(text, pattern, exclude=()):
    """pattern 표현이 가장 많이 들어간 문장(동점이면 앞 문장)을 고른다."""
    sents = [s for s in sentences(text) if s not in exclude]
    if not sents:
        return ""
    if not pattern:
        return sents[0]
    return max(sents, key=lambda s: (len(re.findall(pattern, s)), -sents.index(s)))


def fetch(option, person):
    """크롤링 결과를 cache/ 에 저장해 같은 입력은 크레딧을 다시 쓰지 않는다 (오늘의 운은 날짜별)."""
    form = OPTIONS[option]["form"]
    day = datetime.date.today().isoformat() if form == TODAY_FORM else ""
    raw = json.dumps([form, day, sorted(person.items())], ensure_ascii=False)
    path = CACHE / (hashlib.sha1(raw.encode()).hexdigest() + ".md")
    if path.exists():
        return path.read_text(encoding="utf-8")
    key = crawl_saju.load_api_key()
    for attempt in range(3):
        try:
            md = crawl_saju.scrape(key, argparse.Namespace(**person), form_url=form)
            break
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 2:
                raise
    CACHE.mkdir(exist_ok=True)
    path.write_text(md, encoding="utf-8")
    return md


def build_result(option, person):
    conf = OPTIONS[option]
    md = strip_hanja(fetch(option, person))
    secs = split_sections(md)
    result = {"option": option, "name": person["name"], "sections": [], "summary": [], "score": None}

    if option == "today":
        m = re.search(r"(\d{1,3})%", md.split("## ", 1)[0])
        result["score"] = int(m.group(1)) if m else None

    for title in conf["sections"]:
        body = secs.get(title)
        if not body:
            continue
        headline = None
        h = re.match(r"###\s*(.+)\n", body)
        if h:
            headline, body = h.group(1).strip(), body[h.end():].strip()
        paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        result["sections"].append({"title": title, "headline": headline, "paragraphs": paras})

    if option == "today":
        first = next((s for s in result["sections"] if s["title"] == "한마디 운세"), None)
        if first and first["headline"]:
            score = f"총운 {result['score']}점 · " if result["score"] is not None else ""
            result["summary"].append(score + first["headline"])
    for title, pattern in conf["summary"]:
        if len(result["summary"]) >= 3:
            break
        if secs.get(title):
            s = pick_sentence(secs[title], pattern, exclude=result["summary"])
            if s:
                result["summary"].append(s)

    if not result["sections"]:
        raise ValueError("결과를 가져오지 못했습니다. 입력값을 확인하거나 잠시 후 다시 시도해 주세요.")
    return result


def parse_person(data):
    name = str(data.get("name", "")).strip()[:20]
    if not name:
        raise ValueError("이름을 입력해 주세요.")
    person = {
        "name": name,
        "sex": data.get("sex"),
        "year": int(data.get("year")),
        "month": int(data.get("month")),
        "day": int(data.get("day")),
        "hour": str(data.get("hour") or "0"),
        "solunar": data.get("solunar") or "S_C",
    }
    if person["sex"] not in ("남", "여"):
        raise ValueError("성별을 선택해 주세요.")
    if person["solunar"] not in ("S_C", "L_C", "L_L"):
        raise ValueError("양/음력 값이 올바르지 않습니다.")
    if not (1930 <= person["year"] <= datetime.date.today().year and 1 <= person["month"] <= 12 and 1 <= person["day"] <= 31):
        raise ValueError("생년월일을 확인해 주세요.")
    return person


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/fortune.js":
            self._send(200, INDEX.with_name("fortune.js").read_bytes(), "text/javascript; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path != "/api/fortune":
            return self._send(404, "not found", "text/plain; charset=utf-8")
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            option = data.get("option")
            if option not in OPTIONS:
                raise ValueError("보고 싶은 운세를 선택해 주세요.")
            res = build_result(option, parse_person(data))
            self._send(200, json.dumps(res, ensure_ascii=False), "application/json; charset=utf-8")
        except (ValueError, TypeError) as e:
            self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8")
        except Exception as e:  # 크롤링 실패 등
            self._send(502, json.dumps({"error": f"운세 정보를 가져오는 중 오류가 발생했습니다: {e}"}, ensure_ascii=False),
                       "application/json; charset=utf-8")


if __name__ == "__main__":
    port = 8000
    print(f"http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
