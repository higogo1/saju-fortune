# 나의 운세 보기

이름과 생년월일을 입력하고 **오늘의 운 / 조심해야 할 것 / 부자되는 방법** 중 하나를 골라 운세를 보는 웹앱입니다.

**바로 사용:** https://higogo1.github.io/saju-fortune/
(처음 한 번 Firecrawl API 키를 입력하면 됩니다. 키는 그 브라우저의 localStorage에만 저장됩니다.)
운세 데이터는 [Firecrawl](https://firecrawl.dev)로 unsin.co.kr 결과 페이지를 크롤링해 가져오고, 한자를 제거한 뒤 마지막에 3줄 요약을 하이라이트로 보여줍니다.

## 로컬 실행 (키 입력 없이 .env 사용)

1. Python 3.10 이상 (외부 패키지 필요 없음)
2. `.env.example`을 `.env`로 복사하고 Firecrawl API 키 입력
3. 서버 실행

```
python app.py
```

4. 브라우저에서 http://localhost:8000 접속

## 파일

| 파일 | 설명 |
|---|---|
| `index.html` | 화면 (GitHub Pages에서는 브라우저가 Firecrawl을 직접 호출) |
| `fortune.js` | 크롤링 → 한자 제거 → 섹션 정리 → 3줄 요약 (브라우저/Worker 공용) |
| `app.py` | 로컬 웹 서버 (같은 로직의 Python 버전, `.env` 키 사용) |
| `worker/` | (선택) Cloudflare Worker. 키를 서버에 두고 누구나 키 입력 없이 쓰게 할 때 배포 |
| `crawl_saju.py` | Firecrawl 크롤러 (단독 실행 시 평생사주 결과를 md/json으로 저장) |

- 처음 조회는 20~40초 걸리며, 결과는 캐시(로컬: `cache/`, 브라우저: localStorage)에 저장되어 같은 입력은 바로 응답합니다 (오늘의 운은 날짜별).
- `.env`와 `cache/`는 저장소에 올라가지 않습니다.
