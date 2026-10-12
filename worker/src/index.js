// 운세 API (Cloudflare Worker, 선택 사항). 키를 서버에 두고 누구나 키 입력 없이 쓰게 하고 싶을 때 배포한다.
// POST /api/fortune  {option, name, sex, year, month, day, hour, solunar}
// 비밀값: FIRECRAWL_API_KEY (wrangler secret), KV: CACHE
import { OPTIONS, UserError, buildResult, kstDate, parsePerson } from "../../fortune.js";

const ALLOWED_ORIGINS = ["https://higogo1.github.io", "http://localhost:8000", "http://127.0.0.1:8000"];
const DAILY_LIMIT_PER_IP = 30; // 캐시에 없는 새 조회(=크레딧 사용)만 센다

function context(env, ip) {
  return {
    apiKey: env.FIRECRAWL_API_KEY,
    cache: {
      get: (k) => env.CACHE.get(k),
      put: (k, v, ttl) => env.CACHE.put(k, v, { expirationTtl: ttl }),
    },
    async beforeScrape() {
      const quotaKey = `quota:${kstDate()}:${ip}`;
      const used = Number(await env.CACHE.get(quotaKey)) || 0;
      if (used >= DAILY_LIMIT_PER_IP) throw new UserError("오늘 조회 가능 횟수를 모두 사용했습니다. 내일 다시 시도해 주세요.");
      await env.CACHE.put(quotaKey, String(used + 1), { expirationTtl: 86400 });
    },
  };
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const cors = ALLOWED_ORIGINS.includes(origin) ? {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Vary": "Origin",
    } : {};
    const reply = (status, obj) => new Response(JSON.stringify(obj), {
      status, headers: { "Content-Type": "application/json; charset=utf-8", ...cors },
    });

    const url = new URL(request.url);
    if (url.pathname !== "/api/fortune") return reply(404, { error: "not found" });
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (request.method !== "POST") return reply(405, { error: "method not allowed" });
    if (!cors["Access-Control-Allow-Origin"]) return reply(403, { error: "허용되지 않은 출처입니다." });

    try {
      const data = await request.json().catch(() => ({}));
      if (!OPTIONS[data.option]) throw new UserError("보고 싶은 운세를 선택해 주세요.");
      const ip = request.headers.get("CF-Connecting-IP") || "unknown";
      return reply(200, await buildResult(context(env, ip), data.option, parsePerson(data)));
    } catch (e) {
      if (e instanceof UserError) return reply(400, { error: e.message });
      return reply(502, { error: `운세 정보를 가져오는 중 오류가 발생했습니다: ${e.message}` });
    }
  },
};
