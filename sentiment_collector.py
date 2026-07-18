"""
疯向标 - Google News 情绪采集器 v1
采集 BTC 和半导体相关新闻标题 → VADER 情绪打分 → 每日情绪指数
"""
import sys, os
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
import json, urllib.request

# ── 配置 ──
TOPICS = {
    "BTC": "BTC+bitcoin+crypto",
    "AI_SEMI": "semiconductor+AI+chip+HBM+NVDA+MU+storage+memory",
}

os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"

def fetch_news(topic, query):
    """拉 Google News RSS"""
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            root = ET.fromstring(resp.read())
    except Exception as e:
        print(f"  拉取 {topic} 失败: {e}")
        return []

    items = root.findall('.//item')
    headlines = []
    for item in items:
        title = item.find('title').text if item.find('title') is not None else ''
        pubdate = item.find('pubDate').text if item.find('pubDate') is not None else ''
        source = item.find('source').text if item.find('source') is not None else ''
        headlines.append({
            'topic': topic,
            'title': title,
            'date': pubdate,
            'source': source
        })
    return headlines

# ── VADER 情绪分析 ──
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
analyzer = SentimentIntensityAnalyzer()

# 添加金融领域自定义词
financial_words = {
    "crash": -4.0, "plunge": -3.5, "collapse": -4.0, "panic": -3.5,
    "dump": -3.0, "bear": -2.5, "correction": -2.0, "slump": -3.0,
    "fear": -3.0, "bloodbath": -4.0, "carnage": -4.0, "meltdown": -4.0,
    "surge": 3.5, "rally": 3.0, "moon": 4.0, "bullish": 3.0,
    "breakout": 2.5, "rocket": 3.5, "explode": 3.0, "skyrocket": 4.0,
    "accumulate": 2.0, "bottom": -0.5, "top": -0.5,
}
analyzer.lexicon.update(financial_words)

def score_headlines(headlines):
    """给一组标题打分，返回平均情绪"""
    scores = []
    for h in headlines:
        score = analyzer.polarity_scores(h['title'])
        h['sentiment'] = score['compound']
        scores.append(score['compound'])
    avg = sum(scores) / len(scores) if scores else 0
    return avg, headlines

# ── 执行 ──
print(f"\n{'='*60}")
print(f"📊 疯向标情绪采集 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"{'='*60}")

all_data = {}
for topic, query in TOPICS.items():
    print(f"\n🔍 采集: {topic}")
    headlines = fetch_news(topic, query)
    avg_score, scored = score_headlines(headlines)

    print(f"   标题数: {len(headlines)}")
    print(f"   平均情绪: {avg_score:+.3f}")

    # 分类
    if avg_score > 0.2:
        mood = "😀 乐观"
    elif avg_score > -0.2:
        mood = "😐 中性"
    else:
        mood = "😟 悲观"
    print(f"   情绪判断: {mood}")

    # 显示最极端的几条
    scored.sort(key=lambda x: x['sentiment'])
    print(f"   🔴 最负面: {scored[0]['title'][:70]}" if scored else "")
    print(f"   🟢 最正面: {scored[-1]['title'][:70]}" if scored else "")

    all_data[topic] = {
        'count': len(headlines),
        'avg_sentiment': round(avg_score, 3),
        'mood': mood,
        'headlines': scored[:20],  # 只保留前20条
    }

# ── 保存 ──
outdir = os.path.expanduser("~/.hermes/scripts/fengxiangbiao/data")
os.makedirs(outdir, exist_ok=True)
today = datetime.now().strftime("%Y-%m-%d")
with open(f"{outdir}/sentiment_{today}.json", "w") as f:
    json.dump(all_data, f, indent=2, ensure_ascii=False)

print(f"\n✅ 已保存: {outdir}/sentiment_{today}.json")
