// 운세 결과 만들기 (Firecrawl 크롤링 → 한자 제거 → 섹션 정리 → 3줄 요약).
// 브라우저(index.html, GitHub Pages)와 Cloudflare Worker(worker/)가 함께 쓴다. 로컬 python app.py 와 같은 로직.

const TOTAL_FORM = "https://www.unsin.co.kr/unse/saju/total/form";
const TODAY_FORM = "https://www.unsin.co.kr/unse/free/todayline/form?linenum=01&sid=tunse";

const HANJA = /[㐀-䶿一-鿿豈-﫿]+/g;
// 요약 문장 고를 때 가산점을 주는 표현 (많이 걸릴수록 우선)
const CAUTION_WORDS = /조심|주의|금물|피하|삼가|않도록|멀리|위험|손해|잃을|소홀|게을리|성급|해야|좋겠|좋습니다|좋으며/g;
const RICH_WORDS = /모을|모으|저축|투자|재테크|관리|큰 돈|부자|재물|금전|해야|좋겠|좋습니다|좋으며/g;

// 옵션별: 어느 페이지에서, 어떤 섹션을 보여주고, 요약은 어디서 뽑는지
export const OPTIONS = {
  today: {
    form: TODAY_FORM,
    sections: ["한마디 운세", "애정운", "소망운", "사업운", "금전운", "오늘 이 방향으로 가보세요"],
    summary: [["금전운", null], ["사업운", null], ["오늘 이 방향으로 가보세요", /길하|좋/g]],
  },
  caution: {
    form: TOTAL_FORM,
    sections: ["건강운", "체질운", "재물손실 막는법"],
    summary: [["건강운", CAUTION_WORDS], ["체질운", CAUTION_WORDS], ["재물손실 막는법", CAUTION_WORDS]],
  },
  rich: {
    form: TOTAL_FORM,
    sections: ["재물운", "재물모으는법", "재테크비법"],
    summary: [["재물운", RICH_WORDS], ["재물모으는법", RICH_WORDS], ["재테크비법", RICH_WORDS]],
  },
};

export class UserError extends Error {}

export const kstDate = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);

function stripHanja(text) {
  return text.replace(HANJA, "").replace(/\(\s*\)|（\s*）/g, "").replace(/[ \t]{2,}/g, " ").trim();
}

// '## 제목' 단위로 본문을 나눈다.
function splitSections(md) {
  const out = {};
  for (const chunk of md.split(/^## /m).slice(1)) {
    const nl = chunk.indexOf("\n");
    const title = (nl < 0 ? chunk : chunk.slice(0, nl)).trim().replace(/\.$/, "");
    let body = nl < 0 ? "" : chunk.slice(nl + 1);
    body = body.split(/^- (?:카카오|어제의 운세)/m)[0];
    out[title] = body.trim();
  }
  return out;
}

function sentences(text) {
  return text.replace(/^#+\s*/gm, "").split(/(?<=[.!?])\s+|\n+/).map(s => s.trim()).filter(s => s.length > 8);
}

// pattern 표현이 가장 많이 들어간 문장(동점이면 앞 문장)을 고른다.
function pickSentence(text, pattern, exclude) {
  const sents = sentences(text).filter(s => !exclude.includes(s));
  if (!sents.length) return "";
  if (!pattern) return sents[0];
  let best = sents[0], bestN = -1;
  for (const s of sents) {
    const n = (s.match(pattern) || []).length;
    if (n > bestN) { best = s; bestN = n; }
  }
  return best;
}

function fillFormScript(p) {
  const fields = {
    user_name: p.name, sex: p.sex, birth_yyyy: String(p.year),
    birth_mm: String(p.month).padStart(2, "0"), birth_dd: String(p.day).padStart(2, "0"),
    birth_hh: p.hour, birth_solunar: p.solunar,
  };
  return `const v=${JSON.stringify(fields)};const f=document.getElementById('frm');` +
    "for(const [k,val] of Object.entries(v)){const el=f.elements[k];" +
    "if(el.tagName==='SELECT'&&![...el.options].some(o=>o.value===val)){" +
    "const o=document.createElement('option');o.value=val;el.appendChild(o);}" +
    "el.value=val;}HTMLFormElement.prototype.submit.call(f);";
}

async function scrape(apiKey, form, person) {
  const body = JSON.stringify({
    url: form, formats: ["markdown"], onlyMainContent: true,
    actions: [
      { type: "wait", milliseconds: 1500 },
      { type: "executeJavascript", script: fillFormScript(person) },
      { type: "wait", milliseconds: 4000 },
    ],
  });
  for (let attempt = 0; ; attempt++) {
    const res = await fetch("https://api.firecrawl.dev/v2/scrape", {
      method: "POST", body,
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    });
    if (res.status >= 500 && attempt < 2) continue;
    const json = await res.json().catch(() => ({}));
    if (!res.ok || !json.success) throw new Error(`Firecrawl ${res.status}`);
    return json.data.markdown;
  }
}

async function sha1(s) {
  const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
}

// 크롤링 결과를 cache에 저장해 같은 입력은 크레딧을 다시 쓰지 않는다 (오늘의 운은 날짜별).
// cache: { get(key) -> string|null, put(key, value, ttlSeconds) }, beforeScrape: 크레딧 쓰기 직전 호출 (쿼터 확인용)
async function fetchMarkdown(ctx, option, person) {
  const form = OPTIONS[option].form;
  const today = form === TODAY_FORM;
  const key = "md:" + await sha1(JSON.stringify([form, today ? kstDate() : "", person]));
  const cached = await ctx.cache.get(key);
  if (cached) return cached;
  if (ctx.beforeScrape) await ctx.beforeScrape();
  const md = await scrape(ctx.apiKey, form, person);
  await ctx.cache.put(key, md, today ? 86400 : 60 * 86400);
  return md;
}

export async function buildResult(ctx, option, person) {
  const conf = OPTIONS[option];
  const md = stripHanja(await fetchMarkdown(ctx, option, person));
  const secs = splitSections(md);
  const result = { option, name: person.name, sections: [], summary: [], score: null };

  if (option === "today") {
    const m = md.split("## ")[0].match(/(\d{1,3})%/);
    result.score = m ? Number(m[1]) : null;
  }
  for (const title of conf.sections) {
    let body = secs[title];
    if (!body) continue;
    let headline = null;
    const h = body.match(/^###\s*(.+)\n/);
    if (h) { headline = h[1].trim(); body = body.slice(h[0].length).trim(); }
    const paragraphs = body.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
    result.sections.push({ title, headline, paragraphs });
  }

  if (option === "today") {
    const first = result.sections.find(s => s.title === "한마디 운세");
    if (first && first.headline) {
      result.summary.push((result.score != null ? `총운 ${result.score}점 · ` : "") + first.headline);
    }
  }
  for (const [title, pattern] of conf.summary) {
    if (result.summary.length >= 3) break;
    if (secs[title]) {
      const s = pickSentence(secs[title], pattern, result.summary);
      if (s) result.summary.push(s);
    }
  }
  if (!result.sections.length) throw new UserError("결과를 가져오지 못했습니다. 입력값을 확인하거나 잠시 후 다시 시도해 주세요.");
  return result;
}

export function parsePerson(d) {
  const name = String(d.name || "").trim().slice(0, 20);
  if (!name) throw new UserError("이름을 입력해 주세요.");
  const p = {
    name, sex: d.sex, year: parseInt(d.year), month: parseInt(d.month), day: parseInt(d.day),
    hour: String(d.hour || "0"), solunar: d.solunar || "S_C",
  };
  if (!["남", "여"].includes(p.sex)) throw new UserError("성별을 선택해 주세요.");
  if (!["S_C", "L_C", "L_L"].includes(p.solunar)) throw new UserError("양/음력 값이 올바르지 않습니다.");
  if (!/^(0|0[1-9]|1\d|2[0-2])$/.test(p.hour)) throw new UserError("태어난 시간 값이 올바르지 않습니다.");
  const year = new Date().getFullYear();
  if (!(p.year >= 1930 && p.year <= year && p.month >= 1 && p.month <= 12 && p.day >= 1 && p.day <= 31)) {
    throw new UserError("생년월일을 확인해 주세요.");
  }
  return p;
}
