#!/usr/bin/env python3
"""
疯向标 X API 采集器
四赛道中文讨论量监控 + 异常情绪分析

成本控制：
- Counts 接口：每2小时4次调用（Basic 套餐约48次/天，免费额度够）
- Search 接口：仅异常时触发，每天最多2次，每次最多5条
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone, timedelta

BEARER = "AAAAAAAAAAAAAAAAAAAAABj7%2BgEAAAAANbf7V687aLDxotqkIl5iOdn56Mg%3Dlvk90PcvcspHHfISvkdhB2hpB2cOLfajoPaKCSC1YL7sTY7mQ6"
PROXY = "http://127.0.0.1:7890"
DATA_DIR = os.path.expanduser("~/.hermes/scripts/fengxiangbiao/data")
HISTORY_FILE = os.path.join(DATA_DIR, "x_history.json")
RESULT_FILE = os.path.join(DATA_DIR, "x_latest.json")
SEARCH_LOG = os.path.join(DATA_DIR, "x_search_log.json")
os.makedirs(DATA_DIR, exist_ok=True)

CST = timezone(timedelta(hours=8))

# ═══ 四大板块查询 ═══
SECTORS = {
    "gold": {
        "name": "黄金白银",
        "query": "(gold OR silver OR 黄金 OR 白银 OR 金价 OR $XAUUSD OR $XAGUSD OR $GLD OR $SLV) lang:zh",
        "search_query": "(gold OR silver OR 黄金 OR 白银 OR 金价) lang:zh -is:retweet",
    },
    "btc": {
        "name": "BTC",
        "query": "($BTC OR $ETH OR 比特币 OR 以太坊 OR 加密货币 OR 币圈) lang:zh",
        "search_query": "($BTC OR $ETH OR 比特币 OR 以太坊 OR 加密货币) lang:zh -is:retweet",
    },
    "a_semi": {
        "name": "A股半导体",
        "query": "(半导体 OR 芯片 OR 中芯国际 OR 寒武纪 OR 北方华创 OR 光刻 OR 算力 OR AI芯片 OR 科创板 OR 688981 OR 688256 OR 002371 OR 688012 OR 688008 OR 603501 OR 603986 OR 600703 OR 300782 OR 中微 OR 澜起 OR 华虹 OR 韦尔 OR 兆易 OR 长电 OR 龙芯) lang:zh",
        "search_query": "(半导体 OR 芯片 OR 中芯国际 OR 寒武纪 OR 算力 OR AI芯片 OR 688981 OR 688256 OR 002371 OR 中微 OR 澜起) lang:zh -is:retweet",
    },
    "us_semi": {
        "name": "美股半导体",
        "query": "($NVDA OR $AVGO OR $MU OR $TSMC OR $SMCI OR 英伟达 OR 美光 OR 台积电 OR HBM OR Blackwell OR $SKHY OR 海力士) lang:zh",
        "search_query": "($NVDA OR $AVGO OR $MU OR 英伟达 OR 美光 OR 台积电 OR HBM) lang:zh -is:retweet",
    },
}


def api(url):
    """X API v2 请求"""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {BEARER}"})
    proxy_handler = urllib.request.ProxyHandler({"https": PROXY, "http": PROXY})
    opener = urllib.request.build_opener(proxy_handler)
    with opener.open(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def get_counts(sector_key):
    """获取最近7天小时级讨论量"""
    q = urllib.parse.quote(SECTORS[sector_key]["query"])
    url = f"https://api.twitter.com/2/tweets/counts/recent?query={q}&granularity=hour"
    return api(url)


def get_tweets(sector_key, max_results=5):
    """抓取样本帖子（仅在异常时使用）"""
    q = urllib.parse.quote(SECTORS[sector_key]["search_query"])
    url = f"https://api.twitter.com/2/tweets/search/recent?query={q}&max_results={max_results}&tweet.fields=created_at,public_metrics,lang"
    return api(url)


def load_history():
    """加载历史计数数据"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {}


def save_history(history):
    """保存历史数据，每板块保留最近14天"""
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def load_search_log():
    """加载今日搜索触发记录"""
    if os.path.exists(SEARCH_LOG):
        with open(SEARCH_LOG) as f:
            log = json.load(f)
    else:
        log = {"date": "", "triggered": 0, "sectors": []}
    today = datetime.now(CST).strftime("%Y-%m-%d")
    if log.get("date") != today:
        log = {"date": today, "triggered": 0, "sectors": []}
    return log


def save_search_log(log):
    with open(SEARCH_LOG, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def simple_sentiment(text):
    """
    简易中文情绪判断（不调 LLM，省钱）
    正负词库 → 粗略多空分类
    """
    bullish = ["暴涨", "突破", "起飞", "抄底", "利好", "牛市", "看涨", "做多",
               "大涨", "暴涨", "新高", "拉升", "涨停", "赚", "翻倍", "猛",
               "起飞", "爆发", "疯涨", "强势", "买入", "all in", "加仓",
               "不错", "看好", "机会", "底部", "反弹", "利好", "起飞"]
    bearish = ["暴跌", "崩盘", "割肉", "腰斩", "清仓", "做空", "看跌", "熊市",
               "大跌", "暴跌", "新低", "砸盘", "跌停", "亏", "套牢", "完了",
               "不行", "泡沫", "危险", "利空", "跑路", "恐慌", "危机",
               "凉了", "废了", "归零", "认输", "止损", "踏空"]

    text_lower = text.lower()
    b_score = sum(1 for w in bullish if w in text_lower)
    s_score = sum(1 for w in bearish if w in text_lower)

    if b_score > s_score:
        return "看涨"
    elif s_score > b_score:
        return "看跌"
    return "中性"


def classify_emotion(tweets_data):
    """对样本帖子做情绪分类"""
    if "data" not in tweets_data:
        return {"sentiment": "未知", "sample_count": 0}

    sentiments = {"看涨": 0, "看跌": 0, "中性": 0}
    for tw in tweets_data["data"]:
        s = simple_sentiment(tw["text"])
        sentiments[s] += 1

    total = sum(sentiments.values())
    dominant = max(sentiments, key=sentiments.get)

    if sentiments["看涨"] > total * 0.6:
        emotion = "狂欢"
    elif sentiments["看跌"] > total * 0.6:
        emotion = "绝望"
    else:
        emotion = "调整"

    return {
        "sentiment": f"{dominant}/{emotion}",
        "sample_count": total,
        "breakdown": sentiments,
    }


def detect_anomaly(counts, history, sector_key):
    """
    检测异常：当前小时 vs 过去7天同时段均值
    返回: (is_anomaly, direction, ratio)
    """
    now = datetime.now(CST)
    current_hour = now.hour

    if not counts.get("data"):
        return False, "normal", 1.0

    # 最新一小时count
    latest = counts["data"][-1]
    current_count = latest["tweet_count"]

    # 从历史中提取过去7天同时段数据
    past = history.get(sector_key, [])
    same_hour_counts = []
    for entry in past:
        ts = entry.get("hour", "")
        if ts:
            try:
                entry_hour = ts.split("T")[1]  # "2026-07-22T13" → "13"
                if int(entry_hour) == current_hour:
                    same_hour_counts.append(entry["count"])
            except (IndexError, ValueError):
                pass

    if len(same_hour_counts) < 2:  # 数据不足，不算异常
        return False, "normal", 1.0

    avg = sum(same_hour_counts) / len(same_hour_counts)
    if avg == 0:
        return False, "normal", 1.0

    ratio = current_count / avg

    if ratio > 1.35:
        return True, "high", ratio
    elif ratio < 0.65:
        return True, "low", ratio
    return False, "normal", ratio


def main():
    result = {
        "collected_at": datetime.now(CST).isoformat(),
        "sectors": {},
    }

    history = load_history()
    search_log = load_search_log()

    for sector_key, cfg in SECTORS.items():
        print(f"[{cfg['name']}] 获取 counts...", file=sys.stderr)

        try:
            counts = get_counts(sector_key)
        except Exception as e:
            print(f"  ❌ 失败: {e}", file=sys.stderr)
            result["sectors"][sector_key] = {
                "name": cfg["name"],
                "error": str(e),
            }
            continue

        if "data" not in counts:
            result["sectors"][sector_key] = {
                "name": cfg["name"],
                "count": 0,
                "status": "no_data",
            }
            continue

        # 解析最新数据和汇总
        data = counts["data"]
        latest = data[-1]["tweet_count"]
        total = counts["meta"]["total_tweet_count"]
        hourly_avg = total / max(len(data), 1)

        # 异常检测
        is_anomaly, direction, ratio = detect_anomaly(counts, history, sector_key)

        sector_result = {
            "name": cfg["name"],
            "latest_hour": latest,
            "total_7d": total,
            "hourly_avg": round(hourly_avg, 1),
            "anomaly": is_anomaly,
            "anomaly_direction": direction,
            "anomaly_ratio": round(ratio, 2),
            "emotion": None,
        }

        # 异常时触发搜索
        if is_anomaly and search_log["triggered"] < 2:
            print(f"  🚨 异常! direction={direction} ratio={ratio:.1f}x, 抓样本...", file=sys.stderr)
            try:
                tweets = get_tweets(sector_key, max_results=5)
                emotion = classify_emotion(tweets)
                sector_result["emotion"] = emotion
                sector_result["sample_tweets"] = [
                    {"text": t["text"][:100], "sentiment": simple_sentiment(t["text"]),
                     "created_at": t.get("created_at", "")}
                    for t in tweets.get("data", [])[:5]
                ]
                search_log["triggered"] += 1
                search_log["sectors"].append(sector_key)
                print(f"  → {emotion['sentiment']} ({emotion['sample_count']}条样本)", file=sys.stderr)
            except Exception as e:
                print(f"  ⚠️ 抓样本失败: {e}", file=sys.stderr)

        result["sectors"][sector_key] = sector_result

        # 更新历史
        sector_history = history.get(sector_key, [])
        now_str = datetime.now(CST).strftime("%Y-%m-%dT%H")
        sector_history.append({"hour": now_str, "count": latest})

        # 只保留14天
        cutoff = (datetime.now(CST) - timedelta(days=14)).strftime("%Y-%m-%dT%H")
        sector_history = [e for e in sector_history if e["hour"] >= cutoff]
        history[sector_key] = sector_history

    # 保存
    save_history(history)
    save_search_log(search_log)

    with open(RESULT_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 输出摘要
    print(f"\n📊 X采集完成 {datetime.now(CST).strftime('%m/%d %H:%M')}", file=sys.stderr)
    for key, sec in result["sectors"].items():
        if "error" in sec:
            print(f"  {sec['name']}: ❌ {sec['error']}", file=sys.stderr)
            continue
        anomaly = "🚨" if sec.get("anomaly") else "  "
        emotion = f" [{sec['emotion']['sentiment']}]" if sec.get("emotion") else ""
        print(f"  {anomaly} {sec['name']}: {sec.get('latest_hour','?')}条/小时 (7日均{sec.get('hourly_avg','?')}){emotion}",
              file=sys.stderr)

    return result


if __name__ == "__main__":
    main()
