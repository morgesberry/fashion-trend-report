import os
import re
import json
from datetime import datetime, timezone
from collections import Counter
import feedparser
from jinja2 import Template

RSS_SOURCES = [
    "https://www.vogue.com/feed/rss",
    "https://wwd.com/feed/",
    "https://www.businessoffashion.com/feed/",
]

TREND_KEYWORDS = [
    "2026春夏", "静奢", "可持续", "薄纱", "复古", "运动时尚",
    "极简", "Y2K", "廓形西装", "功能面料", "针织", "牛仔",
    "秀场", "联名", "环保", "剪裁", "高定", "成衣"
]

TAG_GROUPS = {
    "材质": ["牛仔", "皮革", "针织", "薄纱", "羊毛", "丝绸", "功能面料"],
    "风格": ["极简", "复古", "Y2K", "静奢", "运动时尚", "街头"],
    "单品": ["西装", "风衣", "连衣裙", "半身裙", "外套", "衬衫", "包袋", "球鞋"],
    "色彩": ["黑色", "白色", "灰色", "棕色", "蓝色", "红色", "绿色", "粉色", "金属色"],
}

BRANDS = [
    "Chanel", "Dior", "Gucci", "Prada", "Louis Vuitton", "Saint Laurent",
    "Bottega Veneta", "Miu Miu", "Balenciaga", "Valentino", "Versace",
    "Burberry", "Loewe", "Fendi", "Celine", "Givenchy"
]

HTML_TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>时尚趋势日报 v2</title>
  <style>
    body { font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin: 32px auto; max-width: 1100px; padding: 0 16px; line-height: 1.65; color:#222; }
    h1,h2,h3 { margin: 0 0 10px; }
    .meta { color:#666; margin-bottom: 18px; }
    .grid { display:grid; grid-template-columns: 1fr; gap: 12px; }
    .card { border:1px solid #eee; border-radius:14px; padding:14px 16px; background:#fff; }
    .small { color:#666; font-size:13px; }
    .tags { margin-top:8px; }
    .tag { display:inline-block; border:1px solid #ddd; border-radius:999px; padding:2px 10px; margin:0 6px 6px 0; font-size:12px; color:#444; }
    .lead { background:#fafafa; border:1px solid #eee; border-radius:12px; padding:12px 14px; margin: 10px 0 20px; }
    .section { margin-top:22px; }
    a { color:#111; text-decoration:none; }
    a:hover { text-decoration:underline; }
  </style>
</head>
<body>
  <h1>时尚趋势日报 v2</h1>
  <div class="meta">生成时间：{{ generated_at }}</div>

  <div class="lead">
    <strong>编辑部导语：</strong>{{ lead_text }}
  </div>

  <div class="section">
    <h2>今日趋势关键词</h2>
    {% for k, c in top_keywords %}
      <span class="tag">{{ k }} × {{ c }}</span>
    {% endfor %}
  </div>

  <div class="section">
    <h2>本周趋势榜（近7天累计）</h2>
    {% if weekly_keywords %}
      {% for k, c in weekly_keywords %}
        <span class="tag">{{ k }} × {{ c }}</span>
      {% endfor %}
    {% else %}
      <div class="small">暂无历史数据，持续运行后将自动形成。</div>
    {% endif %}
  </div>

  <div class="section">
    <h2>手动置顶选题池</h2>
    {% set manual_items = items | selectattr("manual_pick") | list %}
    {% if manual_items %}
      <div class="grid">
        {% for item in manual_items %}
          <div class="card">
            <div><a href="{{ item.link }}" target="_blank">{{ item.title }}</a></div>
            <div class="small">{{ item.source }}</div>
            <div style="margin-top:6px;">{{ item.cn_summary }}</div>
            <div class="tags">
              {% for t in item.tags %}
                <span class="tag">{{ t }}</span>
              {% endfor %}
            </div>
          </div>
        {% endfor %}
      </div>
    {% else %}
      <div class="small">暂无手动置顶选题。</div>
    {% endif %}
  </div>

  <div class="section">
    <h2>热点报道</h2>
    <div class="grid">
    {% for item in items %}
      {% if not item.manual_pick %}
      <div class="card">
        <div><a href="{{ item.link }}" target="_blank">{{ item.title }}</a></div>
        <div class="small">{{ item.source }} · {{ item.published }}</div>
        <div style="margin-top:6px;">{{ item.cn_summary }}</div>
        <div class="tags">
          {% for t in item.tags %}
            <span class="tag">{{ t }}</span>
          {% endfor %}
        </div>
      </div>
      {% endif %}
    {% endfor %}
    </div>
  </div>

  <div class="section">
    <h3>说明</h3>
    <div class="small">
      当前为免费版工作流（RSS 优先 + 公开信号），社媒深度抓取将根据平台合规策略逐步接入。
    </div>
  </div>
</body>
</html>
"""

def norm_text(s: str) -> str:
    s = s or ""
    s = re.sub(r"<[^>]+>", "", s)
    return " ".join(s.strip().split())

def fake_cn_summary(title: str, summary: str) -> str:
    text = f"{title}。{summary}".strip("。")
    text = text[:180]
    return f"关注点：{text}。该议题可能对未来两周的单品企划与视觉风格产生外溢影响。"

def extract_tags(text: str):
    tags = []
    lower_text = text.lower()

    for kw in TREND_KEYWORDS:
        if kw.lower() in lower_text:
            tags.append(f"趋势:{kw}")

    for group, words in TAG_GROUPS.items():
        for w in words:
            if w.lower() in lower_text:
                tags.append(f"{group}:{w}")

    for b in BRANDS:
        if b.lower() in lower_text:
            tags.append(f"品牌:{b}")

    seen = set()
    out = []
    for t in tags:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out[:12]

def fetch_items():
    rows, seen = [], set()
    for url in RSS_SOURCES:
        feed = feedparser.parse(url)
        source = feed.feed.get("title", url)
        for e in feed.entries[:40]:
            title = norm_text(e.get("title", ""))
            link = e.get("link", "")
            if not title or not link:
                continue
            key = (title.lower(), link)
            if key in seen:
                continue
            seen.add(key)
            summary = norm_text(e.get("summary", ""))[:260]
            published = e.get("published", "")[:30]
            raw_text = f"{title} {summary}"
            tags = extract_tags(raw_text)
            rows.append({
                "title": title,
                "link": link,
                "summary": summary,
                "published": published,
                "source": source,
                "tags": tags
            })
    return rows

def score_items(items):
    scored = []
    counter = Counter()
    for it in items:
        raw = f"{it['title']} {it['summary']}".lower()
        score = 0
        hit = []
        for kw in TREND_KEYWORDS:
            if kw.lower() in raw:
                score += 2
                hit.append(kw)
        score += min(len(it["tags"]), 6)
        counter.update(hit)
        item = dict(it)
        item["score"] = score
        item["cn_summary"] = fake_cn_summary(it["title"], it["summary"])
        scored.append(item)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:30], counter

def load_history():
    path = "data/history.json"
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []

def save_history(history):
    with open("data/history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def weekly_top_keywords(history):
    last_7 = history[-7:]
    c = Counter()
    for d in last_7:
        for k, v in d.get("top_keywords", []):
            c[k] += v
    return c.most_common(12)

def make_lead_text(top_keywords):
    if not top_keywords:
        return "今日样本中趋势分布较为分散，建议关注高频词与高分报道的交叉区域。"
    keys = [k for k, _ in top_keywords[:4]]
    return f"从今日样本看，{'、'.join(keys)}热度靠前；建议优先跟踪相关品牌动作、秀场叙事与商业转化信号。"

def load_manual_picks():
    path = "data/manual_picks.json"
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            items = json.load(f)
            if not isinstance(items, list):
                return []
            normalized = []
            for x in items:
                title = norm_text(x.get("title", ""))
                link = x.get("link", "")
                if not title or not link:
                    continue
                normalized.append({
                    "title": title,
                    "link": link,
                    "summary": norm_text(x.get("summary", ""))[:260],
                    "published": x.get("published", ""),
                    "source": x.get("source", "编辑部手动选题"),
                    "tags": x.get("tags", []),
                    "manual_pick": True,
                    "score": 10_000,
                    "cn_summary": fake_cn_summary(title, norm_text(x.get("summary", "")))
                })
            return normalized
        except Exception:
            return []

def main():
    os.makedirs("data", exist_ok=True)
    os.makedirs("site", exist_ok=True)

    items = fetch_items()
    top_items, today_counter = score_items(items)
    top_keywords = today_counter.most_common(12)

    manual_picks = load_manual_picks()
    manual_links = {x["link"] for x in manual_picks}
    top_items = [x for x in top_items if x["link"] not in manual_links]
    top_items = (manual_picks + top_items)[:30]

    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    lead_text = make_lead_text(top_keywords)

    latest = {
        "date": today,
        "generated_at": now,
        "lead_text": lead_text,
        "top_keywords": top_keywords,
        "items": top_items,
    }
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    history = load_history()
    history = [x for x in history if x.get("date") != today]
    history.append({
        "date": today,
        "top_keywords": top_keywords
    })
    history.sort(key=lambda x: x["date"])
    history = history[-60:]
    save_history(history)

    weekly_keywords = weekly_top_keywords(history)

    html = Template(HTML_TEMPLATE).render(
        generated_at=now,
        lead_text=lead_text,
        top_keywords=top_keywords,
        weekly_keywords=weekly_keywords,
        items=top_items
    )
    with open("site/index.html", "w", encoding="utf-8") as f:
        f.write(html)

if __name__ == "__main__":
    main()
