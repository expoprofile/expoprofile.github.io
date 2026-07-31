#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_events_page.py — events.json 으로부터 정적 HTML 목록 페이지를 생성한다.

  입력 : events.json      (앱이 받아가는 데이터 피드. 이 스크립트는 절대 수정하지 않는다.)
  출력 : events.html      (검색엔진이 색인할 수 있는 정적 렌더링 목록 페이지)
         sitemap.xml      (index / privacy-policy / events 3개 URL)

!!! events.json 을 수정한 뒤에는 반드시 이 스크립트를 다시 실행하고,
!!! 생성된 events.html 과 sitemap.xml 을 함께 커밋해야 한다.
!!! 그렇지 않으면 앱이 보는 데이터와 웹페이지 내용이 어긋난다.

    $ python3 build_events_page.py

Python 3 표준 라이브러리만 사용한다 (외부 패키지 설치 불필요).
JS 로 events.json 을 fetch 해서 그리지 않는 이유: 크롤러가 본문 없는 껍데기만
보게 되어 색인 목적 자체가 사라지기 때문이다. 본문은 반드시 HTML 에 들어가야 한다.

sourceUrl 외부 링크에 rel="nofollow" 를 붙이지 않는다. 광고·제휴·사용자 투고
링크가 아니라 각 행사의 공식 페이지를 편집상 판단으로 직접 고른 것이고, 이런
링크는 nofollow 대상이 아니다. 새 탭으로 열리므로 rel="noopener" 만 붙인다.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys

SITE_ORIGIN = "https://expoprofile.github.io"
PAGE_PATH = "events.html"
PAGE_URL = f"{SITE_ORIGIN}/{PAGE_PATH}"

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS_JSON = os.path.join(HERE, "events.json")
OUT_HTML = os.path.join(HERE, PAGE_PATH)
OUT_SITEMAP = os.path.join(HERE, "sitemap.xml")

PAGE_TITLE = "국내외 IT·B2B 전시회 컨퍼런스 일정 목록 (2026) - 전시회 자동입력 프로필"
PAGE_DESC = (
    "COEX·KINTEX 등에서 열리는 2026년 국내외 IT·B2B 전시회와 컨퍼런스 일정을 "
    "날짜, 장소, 분야, 공식 사이트 링크와 함께 정리했습니다. 부스 등록 폼 자동입력 앱이 "
    "사용하는 행사 목록입니다."
)

# 사이트맵에 넣을 URL. demo-form.html 은 자동입력 테스트용 임시 픽스처라 의도적으로 제외한다.
SITEMAP_PAGES = [
    ("/", "1.0", "weekly"),
    (f"/{PAGE_PATH}", "0.9", "weekly"),
    ("/privacy-policy.html", "0.3", "yearly"),
]


def esc(value) -> str:
    """HTML 텍스트 노드/속성용 이스케이프."""
    return html.escape(str(value), quote=True)


def parse_date(raw: str) -> dt.date:
    """'2026-06-10T00:00:00.000' 같은 값에서 날짜만 뽑는다."""
    return dt.date.fromisoformat(raw[:10])


def fmt_range(start: dt.date, end: dt.date) -> str:
    """한국어 기간 표기. 같은 해/달이면 뒤쪽을 줄인다."""
    if start == end:
        return f"{start.year}년 {start.month}월 {start.day}일"
    if start.year == end.year and start.month == end.month:
        return f"{start.year}년 {start.month}월 {start.day}일 ~ {end.day}일"
    if start.year == end.year:
        return f"{start.year}년 {start.month}월 {start.day}일 ~ {end.month}월 {end.day}일"
    return (
        f"{start.year}년 {start.month}월 {start.day}일 ~ "
        f"{end.year}년 {end.month}월 {end.day}일"
    )


def chips(items, css_class: str) -> str:
    if not items:
        return ""
    return "".join(
        f'<span class="{css_class}">{esc(item)}</span>' for item in items
    )


def jsonld_for(event: dict, ended: bool) -> str:
    """schema.org/Event JSON-LD 블록을 만들고, 만들자마자 다시 파싱해 검증한다."""
    start = parse_date(event["startDate"])
    end = parse_date(event["endDate"])
    description = event.get("subtitle", "")
    why = event.get("whyAutofill", "")
    if why:
        description = f"{description} {why}".strip()

    data = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": event["name"],
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        # 취소/연기/온라인 전환이 아니라 예정대로 열리는(또는 열렸던) 행사이므로
        # 종료된 행사에도 EventScheduled 를 유지한다. schema.org 에는 '종료' 상태값이 없다.
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "description": description,
        "url": event["sourceUrl"],
        "inLanguage": "ko",
        "location": {
            "@type": "Place",
            "name": event["venue"],
            "address": {
                "@type": "PostalAddress",
                "addressLocality": event["city"],
                "addressCountry": event["country"],
            },
        },
        "keywords": ", ".join(event.get("tags", [])),
        "about": event.get("focusAreas", []),
        "organizer": {
            "@type": "Organization",
            "name": event["sourceName"],
            "url": event["sourceUrl"],
        },
        "subjectOf": {
            "@type": "WebPage",
            "url": f"{PAGE_URL}#{event['id']}",
        },
    }

    payload = json.dumps(data, ensure_ascii=False, indent=2)
    # </script> 나 HTML 주석 시퀀스로 스크립트가 조기 종료되지 않도록 방어.
    payload = payload.replace("<", "\\u003C").replace(">", "\\u003E")

    # 검증: 방금 만든 JSON 을 되읽어 본다. 깨졌으면 빌드를 중단한다.
    reparsed = json.loads(payload)
    assert reparsed["name"] == event["name"], "JSON-LD 재파싱 결과가 원본과 다릅니다"
    assert reparsed["startDate"] == start.isoformat()

    return f'<script type="application/ld+json">\n{payload}\n</script>'


def render_event(event: dict, ended: bool) -> str:
    start = parse_date(event["startDate"])
    end = parse_date(event["endDate"])
    badge = (
        '<span class="badge badge-past">종료</span>'
        if ended
        else '<span class="badge badge-upcoming">예정</span>'
    )
    country = "대한민국" if event["country"] == "KR" else event["country"]
    if event["country"] == "JP":
        country = "일본"

    parts = [
        f'<article class="card event{" is-past" if ended else ""}" id="{esc(event["id"])}">',
        jsonld_for(event, ended),
        '  <div class="event-head">',
        f'    <h3 class="event-name">{esc(event["name"])}</h3>',
        f"    {badge}",
        "  </div>",
        f'  <p class="event-sub">{esc(event.get("subtitle", ""))}</p>',
        '  <dl class="meta">',
        "    <dt>기간</dt>"
        f'<dd><time datetime="{start.isoformat()}">{esc(fmt_range(start, end))}</time></dd>',
        f"    <dt>도시</dt><dd>{esc(event['city'])} ({esc(country)})</dd>",
        f"    <dt>장소</dt><dd>{esc(event['venue'])}</dd>",
        "  </dl>",
    ]

    if event.get("tags"):
        parts.append(
            '  <div class="chip-row"><span class="chip-label">분야</span>'
            f'{chips(event["tags"], "chip")}</div>'
        )
    if event.get("focusAreas"):
        parts.append(
            '  <div class="chip-row"><span class="chip-label">성격</span>'
            f'{chips(event["focusAreas"], "chip chip-soft")}</div>'
        )
    if event.get("sponsorSignals"):
        parts.append(
            '  <div class="chip-row"><span class="chip-label">부스 폼에서 자주 묻는 항목</span>'
            f'{chips(event["sponsorSignals"], "chip chip-soft")}</div>'
        )

    parts.append(
        f'  <p class="why"><strong>자동입력이 도움이 되는 이유</strong><br />{esc(event.get("whyAutofill", ""))}</p>'
    )
    parts.append(
        '  <p class="source">공식 사이트: '
        f'<a href="{esc(event["sourceUrl"])}" target="_blank" rel="noopener">'
        f'{esc(event["sourceName"])}</a></p>'
    )
    parts.append("</article>")
    return "\n".join(parts)


CSS = """
  :root {
    --blue: #2563EB;
    --blue-dark: #123A8C;
    --ink: #162033;
    --muted: #617086;
    --line: #DCE3EC;
    --bg: #F7F9FC;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
    background: var(--bg);
    color: var(--ink);
    overflow-wrap: break-word;
    word-break: break-word;
  }
  .wrap { max-width: 880px; margin: 0 auto; padding: 0 24px; }
  header.hero {
    background: linear-gradient(135deg, var(--blue-dark), var(--blue));
    color: white;
    padding: 56px 0 72px;
  }
  .hero-text h1 { font-size: 1.75em; margin: 0 0 10px; line-height: 1.35; }
  .hero-text p { margin: 0; opacity: 0.88; font-size: 1.02em; line-height: 1.6; }
  .crumb { font-size: 0.85em; opacity: 0.8; margin: 0 0 14px; }
  .crumb a { color: white; text-decoration: none; border-bottom: 1px solid rgba(255,255,255,0.5); }
  main { margin-top: -48px; padding-bottom: 8px; }
  .card {
    background: white;
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 24px 28px;
    margin-bottom: 20px;
    box-shadow: 0 8px 24px rgba(18,58,140,0.06);
  }
  .card h2 { font-size: 1.2em; margin-top: 0; }
  .intro p { color: var(--muted); line-height: 1.7; margin: 0 0 10px; font-size: 0.95em; }
  .intro p:last-child { margin-bottom: 0; }
  .toc { list-style: none; padding: 0; margin: 14px 0 0; display: grid; gap: 8px; }
  .toc a { color: var(--blue); text-decoration: none; font-size: 0.93em; font-weight: 600; }
  .toc a:hover { text-decoration: underline; }
  .toc span { color: var(--muted); font-weight: 400; font-size: 0.92em; }
  h2.section {
    font-size: 1.05em;
    margin: 32px 0 14px;
    color: var(--muted);
    letter-spacing: 0.02em;
  }
  .event { scroll-margin-top: 16px; }
  .event.is-past { background: #FCFDFE; }
  .event-head {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    flex-wrap: wrap;
  }
  .event-name { font-size: 1.12em; margin: 0; line-height: 1.4; }
  .badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.72em;
    font-weight: 700;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .badge-upcoming { background: #EAF1FF; color: var(--blue); }
  .badge-past { background: #EEF1F5; color: var(--muted); }
  .event-sub { margin: 8px 0 16px; color: var(--muted); font-size: 0.94em; line-height: 1.6; }
  dl.meta {
    margin: 0 0 14px;
    display: grid;
    grid-template-columns: 68px 1fr;
    gap: 6px 12px;
    font-size: 0.94em;
  }
  dl.meta dt { color: var(--muted); font-size: 0.9em; }
  dl.meta dd { margin: 0; }
  .chip-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    margin-bottom: 10px;
  }
  .chip-label {
    font-size: 0.8em;
    color: var(--muted);
    margin-right: 2px;
  }
  .chip {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    background: #EAF1FF;
    color: var(--blue-dark);
    font-size: 0.8em;
    font-weight: 600;
  }
  .chip-soft { background: var(--bg); color: var(--muted); border: 1px solid var(--line); }
  .why {
    margin: 14px 0 0;
    padding: 14px 16px;
    background: var(--bg);
    border-radius: 12px;
    color: var(--muted);
    font-size: 0.92em;
    line-height: 1.65;
  }
  .why strong { color: var(--ink); font-size: 0.95em; }
  .source { margin: 14px 0 0; font-size: 0.9em; color: var(--muted); }
  .source a { color: var(--blue); font-weight: 600; }
  .links { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; }
  .links a {
    display: inline-block;
    padding: 10px 18px;
    border-radius: 999px;
    text-decoration: none;
    font-weight: 600;
    font-size: 0.92em;
    background: white;
    color: var(--ink);
    border: 1px solid var(--line);
  }
  footer {
    text-align: center;
    padding: 40px 0;
    color: var(--muted);
    font-size: 0.85em;
    line-height: 1.7;
  }
  footer a { color: var(--muted); }
  @media (max-width: 520px) {
    .wrap { padding: 0 16px; }
    header.hero { padding: 44px 0 64px; }
    .hero-text h1 { font-size: 1.4em; }
    .card { padding: 20px 18px; border-radius: 14px; }
    dl.meta { grid-template-columns: 60px 1fr; font-size: 0.9em; }
  }
"""


def build_html(events: list, today: dt.date) -> str:
    decorated = []
    for event in events:
        end = parse_date(event["endDate"])
        decorated.append((parse_date(event["startDate"]), end < today, event))

    upcoming = [d for d in decorated if not d[1]]
    past = [d for d in decorated if d[1]]
    upcoming.sort(key=lambda d: d[0])
    past.sort(key=lambda d: d[0], reverse=True)

    toc_items = []
    for start, ended, event in upcoming + past:
        end = parse_date(event["endDate"])
        state = "종료" if ended else "예정"
        toc_items.append(
            f'    <li><a href="#{esc(event["id"])}">{esc(event["name"])}</a> '
            f'<span>· {esc(fmt_range(start, end))} · {esc(event["city"])} · {state}</span></li>'
        )

    sections = []
    if upcoming:
        sections.append('<h2 class="section">예정된 행사</h2>')
        sections.extend(render_event(e, ended) for _, ended, e in upcoming)
    if past:
        sections.append('<h2 class="section">종료된 행사 (기록용)</h2>')
        sections.extend(render_event(e, ended) for _, ended, e in past)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{esc(PAGE_TITLE)}</title>
<meta name="description" content="{esc(PAGE_DESC)}" />
<link rel="canonical" href="{PAGE_URL}" />
<meta name="robots" content="index, follow" />
<meta property="og:type" content="website" />
<meta property="og:site_name" content="전시회 자동입력 프로필" />
<meta property="og:locale" content="ko_KR" />
<meta property="og:title" content="{esc(PAGE_TITLE)}" />
<meta property="og:description" content="{esc(PAGE_DESC)}" />
<meta property="og:url" content="{PAGE_URL}" />
<meta property="og:image" content="{SITE_ORIGIN}/icon.png" />
<meta name="twitter:card" content="summary" />
<meta name="twitter:title" content="{esc(PAGE_TITLE)}" />
<meta name="twitter:description" content="{esc(PAGE_DESC)}" />
<meta name="twitter:image" content="{SITE_ORIGIN}/icon.png" />
<style>{CSS}</style>
</head>
<body>

<header class="hero">
  <div class="wrap hero-text">
    <p class="crumb"><a href="index.html">전시회 자동입력 프로필</a> · 행사 목록</p>
    <h1>IT·B2B 전시회 컨퍼런스 일정 ({len(events)}건)</h1>
    <p>앱이 사용하는 행사 데이터를 사람이 읽을 수 있게 정리한 페이지입니다.
    날짜, 도시, 장소, 분야와 공식 사이트 링크를 함께 제공합니다.</p>
  </div>
</header>

<main class="wrap">
  <div class="card intro">
    <h2>이 목록은 무엇인가요</h2>
    <p>COEX, KINTEX, DDP 등에서 열리는 국내 IT·B2B 전시회와 개발자 컨퍼런스를 모았습니다.
    각 행사마다 부스 등록 폼에서 반복해서 묻는 항목과, 프로필 자동입력이 도움이 되는 이유를 함께 적었습니다.</p>
    <p>이 페이지의 내용은 앱이 내려받는 데이터 피드
    <a href="events.json">events.json</a> 과 같은 원본에서 생성됩니다.
    기준일 <time datetime="{today.isoformat()}">{today.year}년 {today.month}월 {today.day}일</time> 이전에 끝난 행사는 종료로 표시하되,
    기록을 위해 목록에 그대로 남겨 둡니다.</p>
    <ul class="toc">
{chr(10).join(toc_items)}
    </ul>
  </div>

{chr(10).join(sections)}

  <div class="card">
    <h2>링크</h2>
    <div class="links">
      <a href="index.html">앱 소개</a>
      <a href="privacy-policy.html">개인정보처리방침</a>
      <a href="events.json">전시회 데이터 피드 (JSON)</a>
    </div>
  </div>
</main>

<footer>
  <div class="wrap">
    행사 정보는 각 주최 측 공식 페이지를 기준으로 정리했으며, 일정과 장소는 변경될 수 있습니다.<br />
    최종 갱신 <time datetime="{today.isoformat()}">{today.isoformat()}</time> ·
    © 2026 전시회 자동입력 프로필 · <a href="https://github.com/expoprofile">github.com/expoprofile</a>
  </div>
</footer>

</body>
</html>
"""


def build_sitemap(today: dt.date) -> str:
    entries = []
    for path, priority, changefreq in SITEMAP_PAGES:
        entries.append(
            "  <url>\n"
            f"    <loc>{SITE_ORIGIN}{path}</loc>\n"
            f"    <lastmod>{today.isoformat()}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )


def main() -> int:
    with open(EVENTS_JSON, "r", encoding="utf-8") as fh:
        events = json.load(fh)

    if not isinstance(events, list) or not events:
        print("events.json 이 비어 있거나 배열이 아닙니다.", file=sys.stderr)
        return 1

    today = dt.date.today()
    page = build_html(events, today)

    with open(OUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(OUT_SITEMAP, "w", encoding="utf-8") as fh:
        fh.write(build_sitemap(today))

    # 생성 결과 자체 점검: 모든 행사 이름이 HTML 본문에 리터럴로 들어갔는지 확인.
    missing = [e["name"] for e in events if html.escape(e["name"], quote=True) not in page]
    if missing:
        print("HTML 에 빠진 행사: " + ", ".join(missing), file=sys.stderr)
        return 1

    upcoming = sum(1 for e in events if parse_date(e["endDate"]) >= today)
    print(
        f"{PAGE_PATH} 생성 완료 — 행사 {len(events)}건 "
        f"(예정 {upcoming}, 종료 {len(events) - upcoming}), 기준일 {today.isoformat()}"
    )
    print("sitemap.xml 생성 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
