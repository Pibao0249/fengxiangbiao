#!/usr/bin/env python3
"""
疯向标 - 中文散户情绪采集器
数据源：百度热搜 + 华尔街见闻 + 雪球 + 东方财富股吧
输出：统一JSON，含情绪打分
"""
import json, re, urllib.request, ssl, sys, os
from datetime import datetime, timezone, timedelta

# 代理
PROXY = "http://127.0.0.1:7890"
ssl_ctx = ssl.create_default_context()

def fetch(url, headers=None, use_proxy=True, timeout=10):
    """发起HTTP请求"""
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        handlers = []
        if use_proxy:
            handlers.append(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))
        handlers.append(urllib.request.HTTPSHandler(context=ssl_ctx))
        opener = urllib.request.build_opener(*handlers)
        with opener.open(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  [ERROR] {url[:60]}: {e}", file=sys.stderr)
        return None

# ─── 情绪词典 ───
BULLISH_WORDS = [
    '暴涨','起飞','新高','突破','抄底','牛回','牛市','反转','大阳线',
    '满仓','All in','all in','梭哈','起飞了','爆拉','暴力拉升',
    '加仓','上车','冲','起飞吧','稳了','稳赢','躺赚','利好',
    '反弹','主升浪','逼空','反击','探底回升','黄金坑','机会',
    'to the moon','moon','pump','long','看多','做多',
]
BEARISH_WORDS = [
    '暴跌','崩盘','归零','腰斩','割肉','清仓','跑路','完蛋',
    '熊市','爆仓','血洗','踩踏','恐慌','逃命','止损','离场',
    '大阴线','破位','深套','亏麻','跌麻','亏完','没了',
    '空仓','观望','不敢买','怕了','崩溃','绝望','地狱',
    '看空','做空','空头','砸盘','出货','收割','韭菜',
]
NEUTRAL_SIGNAL = [
    '又涨见识','无语','服了','懵了','没想到','居然',
]

def score_sentiment(text):
    """简单情绪打分：+1看多, -1看空, 0中性"""
    text_lower = text.lower()
    bull = sum(1 for w in BULLISH_WORDS if w.lower() in text_lower)
    bear = sum(1 for w in BEARISH_WORDS if w.lower() in text_lower)
    if bull > bear:
        return min(bull - bear, 5)  # cap at 5
    elif bear > bull:
        return max(-(bear - bull), -5)
    return 0

# ═══════════════════════════════════════════
# 百度热搜
# ═══════════════════════════════════════════
def collect_baidu():
    """采集百度热搜Top50，过滤财经相关"""
    html = fetch('https://top.baidu.com/board?tab=realtime', use_proxy=False)
    if not html:
        return []
    
    m = re.search(r's-data:(\{.*?\});', html)
    if not m:
        # try alternative pattern
        m = re.search(r'<!--s-data:(\{.*?\})-->', html)
    if not m:
        return []
    
    data = json.loads(m.group(1))
    items = []
    finance_kw = ['股','A股','大盘','基金','比特币','BTC','加密','币','黄金',
                  '降息','加息','美联储','央行','楼市','房价','涨停','跌停',
                  '牛市','熊市','爆仓','韭菜','割肉','锂电','芯片','AI',
                  '茅台','光伏','新能源','量化','回购','期货']
    
    for card in data['data']['cards']:
        if card.get('component') != 'hotList':
            continue
        for item in card['content']:
            query = item.get('query', '')
            desc = item.get('desc', '')
            text = query + ' ' + desc
            if any(k in text for k in finance_kw):
                items.append({
                    'source': 'baidu',
                    'title': query,
                    'desc': desc[:200],
                    'hot_score': int(item.get('hotScore', 0)),
                    'sentiment': score_sentiment(text),
                    'time': datetime.now().isoformat(),
                })
    return items

# ═══════════════════════════════════════════
# 华尔街见闻
# ═══════════════════════════════════════════
def collect_wallstreetcn():
    """采集华尔街见闻24h快讯"""
    items = []
    for channel in ['global-channel', 'us-stock-channel', 'a-stock-channel']:
        url = f'https://api-one.wallstcn.com/apiv1/content/lives?channel={channel}&limit=30'
        html = fetch(url, headers={'User-Agent': 'Mozilla/5.0'})
        if not html:
            continue
        try:
            data = json.loads(html)
            for item in data.get('data', {}).get('items', []):
                text = item.get('content_text', '') or item.get('title', '')
                if not text.strip():
                    continue
                items.append({
                    'source': 'wallstreetcn',
                    'channel': channel,
                    'title': item.get('title', ''),
                    'content': text[:300],
                    'sentiment': score_sentiment(text),
                    'time': datetime.fromtimestamp(item.get('display_time', 0)).isoformat(),
                })
        except:
            pass
    return items

# ═══════════════════════════════════════════
# 雪球
# ═══════════════════════════════════════════
def collect_xueqiu():
    """采集雪球热门讨论"""
    cookie = os.environ.get('XUEQIU_COOKIE', '')
    if not cookie:
        try:
            with open(os.path.expanduser('~/.hermes/scripts/fengxiangbiao/data/.xueqiu_cookie'), 'r') as f:
                cookie = f.read().strip()
        except:
            pass
    
    if not cookie:
        return [{'source': 'xueqiu', 'error': 'no cookie'}]
    
    url = 'https://xueqiu.com/v4/statuses/public_timeline_by_category.json?since_id=-1&max_id=-1&category=-1&count=10'
    html = fetch(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Cookie': cookie,
    })
    if not html:
        return []
    
    items = []
    finance_kw = ['股','A股','BTC','币','加密','黄金','降息','茅台','基金',
                  '大盘','涨停','跌停','牛市','爆仓','锂电','AI','芯片',
                  '半导体','光伏','新能源','量化','存储','AI','算力']
    try:
        data = json.loads(html)
        for post in data.get('list', []):
            d = json.loads(post['data'])
            title = d.get('title', '')
            desc = d.get('description', '') or ''
            text = title + ' ' + desc
            if any(k in text for k in finance_kw):
                items.append({
                    'source': 'xueqiu',
                    'title': title[:120],
                    'desc': desc[:200],
                    'user': d.get('user', {}).get('screen_name', ''),
                    'sentiment': score_sentiment(text),
                    'time': datetime.now().isoformat(),
                })
    except:
        pass
    return items

# ═══════════════════════════════════════════
# 东方财富股吧
# ═══════════════════════════════════════════
GUBA_COOKIE = None

def get_guba_cookie():
    global GUBA_COOKIE
    if GUBA_COOKIE:
        return GUBA_COOKIE
    try:
        with open(os.path.expanduser('~/.hermes/scripts/fengxiangbiao/data/.guba_cookie'), 'r') as f:
            GUBA_COOKIE = f.read().strip()
    except:
        pass
    return GUBA_COOKIE

def collect_guba(code='zssh000001', name='上证指数'):
    """采集东方财富股吧帖子"""
    cookie = get_guba_cookie()
    if not cookie:
        return [{'source': 'guba', 'error': 'no cookie'}]
    
    url = f'https://guba.eastmoney.com/list,{code}.html'
    html = fetch(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Cookie': cookie,
    }, use_proxy=False)
    if not html:
        return []
    
    m = re.search(r'var article_list=(\{.*?\});', html)
    if not m:
        return []
    
    items = []
    try:
        data = json.loads(m.group(1))
        for post in data.get('re', []):
            title = post.get('post_title', '')
            items.append({
                'source': 'guba',
                'board': name,
                'title': title,
                'user': post.get('user_nickname', ''),
                'reads': int(post.get('post_click_count', 0)),
                'comments': int(post.get('post_comment_count', 0)),
                'sentiment': score_sentiment(title),
                'time': post.get('post_publish_time', ''),
            })
    except:
        pass
    return items

# ═══════════════════════════════════════════
# 汇总 & 分析
# ═══════════════════════════════════════════
def collect_all():
    """采集所有数据源，返回统一格式"""
    all_items = []
    
    print("采集百度热搜...")
    all_items.extend(collect_baidu())
    
    print("采集华尔街见闻...")
    all_items.extend(collect_wallstreetcn())
    
    print("采集雪球...")
    all_items.extend(collect_xueqiu())
    
    print("采集东方财富股吧...")
    all_items.extend(collect_guba())
    
    # 按来源统计情绪
    stats = {}
    for item in all_items:
        src = item['source']
        if src not in stats:
            stats[src] = {'total': 0, 'bullish': 0, 'bearish': 0, 'neutral': 0}
        stats[src]['total'] += 1
        s = item.get('sentiment', 0)
        if s > 0:
            stats[src]['bullish'] += 1
        elif s < 0:
            stats[src]['bearish'] += 1
        else:
            stats[src]['neutral'] += 1
    
    # 整体情绪指数
    total = sum(v['total'] for v in stats.values())
    bull = sum(v['bullish'] for v in stats.values())
    bear = sum(v['bearish'] for v in stats.values())
    neutral = sum(v['neutral'] for v in stats.values())
    
    sentiment_index = 0
    if total > 0:
        sentiment_index = round((bull - bear) / total * 100, 1)
    
    result = {
        'time': datetime.now().isoformat(),
        'total_items': total,
        'sentiment_index': sentiment_index,
        'breakdown': {
            'bullish': bull,
            'bearish': bear,
            'neutral': neutral,
        },
        'by_source': stats,
        'items': all_items,
    }
    return result

# ─── 保存 ───
def save_result(result):
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    path = os.path.expanduser(f'~/.hermes/scripts/fengxiangbiao/data/chinese_sentiment_{ts}.json')
    with open(path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    # 也保存latest
    latest = os.path.expanduser('~/.hermes/scripts/fengxiangbiao/data/chinese_sentiment_latest.json')
    with open(latest, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return path

if __name__ == '__main__':
    result = collect_all()
    path = save_result(result)
    
    print(f"\n╔══════════════════════════════╗")
    print(f"║   疯向标 · 中文情绪采集    ║")
    print(f"╠══════════════════════════════╣")
    print(f"║ 总条目: {result['total_items']:>4}               ║")
    print(f"║ 情绪指数: {result['sentiment_index']:>+5.1f}%          ║")
    print(f"║ 看多: {result['breakdown']['bullish']:>3}  看空: {result['breakdown']['bearish']:>3}  中性: {result['breakdown']['neutral']:>3} ║")
    print(f"╠══════════════════════════════╣")
    for src, s in result['by_source'].items():
        print(f"║ {src:<12}: {s['total']:>3}条 (多{s['bullish']}/空{s['bearish']}/中{s['neutral']}) ║")
    print(f"╚══════════════════════════════╝")
    print(f"\n保存: {path}")
    
    # 列出情绪最极端的条目
    by_sent = sorted(result['items'], key=lambda x: abs(x.get('sentiment', 0)), reverse=True)
    print("\n── 情绪最极端条目 ──")
    for item in by_sent[:10]:
        s = item.get('sentiment', 0)
        emoji = '🟢' if s > 0 else '🔴' if s < 0 else '⚪'
        print(f"  {emoji} [{item['source']}] {item.get('title','')[:80]}")
