#!/usr/bin/env python3
"""
疯向标 v2 — 全民社媒情绪采集器
数据源：百度热搜 + 微博热搜 + B站热搜 + Crypto F&G + 股吧本地
输出: data/fengxiangbiao_latest.json
"""
import json, re, urllib.request, ssl, sys, os, time
from datetime import datetime

ssl_ctx = ssl.create_default_context()
PROXY = "http://127.0.0.1:7890"
DATA_DIR = os.path.expanduser('~/.hermes/scripts/fengxiangbiao/data')

def fetch(url, headers=None, use_proxy=True, timeout=10):
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    handlers = []
    if use_proxy:
        handlers.append(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))
    handlers.append(urllib.request.HTTPSHandler(context=ssl_ctx))
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return None

def fetch_direct(url, headers=None, timeout=10):
    """不带代理的请求（百度/微博直连更快）"""
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as r:
            return r.read().decode('utf-8', errors='ignore')
    except:
        return None

# ═══════════════════════════════════════════
# 情绪词典
# ═══════════════════════════════════════════
BULLISH = ['暴涨','起飞','新高','突破','抄底','牛回','牛市','反转','大阳线','满仓','梭哈',
           '爆拉','加仓','上车','冲','稳了','反弹','主升浪','逼空','反击','大涨','涨停',
           '吃肉','回血','利好','黄金坑','起飞了','all in']
BEARISH = ['暴跌','崩盘','归零','腰斩','割肉','清仓','跑路','完了','熊市','爆仓','血洗',
           '踩踏','恐慌','逃命','大阴线','破位','深套','亏麻','跌停','吃面','天台',
           '空仓','观望','不敢买','绝望','砸盘','出货','收割','韭菜']

def score(text):
    """情绪打分：正=看多，负=看空，0=中性"""
    t = text.lower()
    b = sum(1 for w in BULLISH if w in t)
    s = sum(1 for w in BEARISH if w in t)
    if b > s: return min(b - s, 5)
    elif s > b: return max(-(s - b), -5)
    return 0

# ═══════════════════════════════════════════
# 赛道关键词
# ═══════════════════════════════════════════
SECTOR_KW = {
    'gold':    ['黄金','金价','白银','银价','贵金属','现货金','期金'],
    'btc':     ['BTC','比特币','加密','币圈','以太坊','ETH','虚拟币','数字货币'],
    'a_semi':  ['半导体','芯片','A股','科创','上证','光刻','中芯','寒武纪','北方华创','新易盛','存储','HBM','算力','AI芯片'],
    'us_semi': ['美股','英伟达','NVDA','纳斯达克','AMD','美光','MU','TSM','台积电','SMCI','博通','AVGO','纳指','费城半导体'],
}

def classify_sector(text):
    """根据文本分类到赛道"""
    for sector, kws in SECTOR_KW.items():
        for kw in kws:
            if kw.lower() in text.lower():
                return sector
    return 'other'

def analyze_sector(items):
    """分析某个赛道的情绪"""
    if not items:
        return {'count': 0, 'bullish': 0, 'bearish': 0, 'neutral': 0,
                'silence_rate': 0, 'carnival_rate': 0, 'sentiment': 0}
    b = sum(1 for i in items if i['sentiment'] > 0)
    s = sum(1 for i in items if i['sentiment'] < 0)
    n = sum(1 for i in items if i['sentiment'] == 0)
    total = len(items)
    return {
        'count': total,
        'bullish': b, 'bearish': s, 'neutral': n,
        'silence_rate': round(n / total * 100, 1),
        'carnival_rate': round(b / total * 100, 1),
        'sentiment': round(sum(i['sentiment'] for i in items) / total, 2),
    }

# ═══════════════════════════════════════════
# 1. 百度热搜
# ═══════════════════════════════════════════
def collect_baidu():
    html = fetch_direct('https://top.baidu.com/board?tab=realtime')
    if not html: return None
    
    m = re.search(r'<!--s-data:(\{.*?\})-->', html)
    if not m: m = re.search(r's-data:(\{.*?\});', html)
    if not m: return None
    
    data = json.loads(m.group(1))
    items = []
    
    for card in data.get('data', {}).get('cards', []):
        if card.get('component') != 'hotList': continue
        for item in card.get('content', []):
            text = (item.get('query', '') + ' ' + item.get('desc', '')).strip()
            if not text: continue
            hot = int(item.get('hotScore', 0))
            items.append({
                'title': item.get('query', ''),
                'desc': item.get('desc', '')[:150],
                'hot': hot,
                'sentiment': score(text),
                'sector': classify_sector(text),
                'source': 'baidu',
            })
    
    return items

# ═══════════════════════════════════════════
# 2. 微博热搜
# ═══════════════════════════════════════════
def collect_weibo():
    html = fetch_direct('https://weibo.com/ajax/side/hotSearch', headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': 'https://weibo.com/',
        'Accept': 'application/json',
    })
    if not html: return None
    
    try:
        data = json.loads(html)
    except:
        return None
    
    items = []
    for item in data.get('data', {}).get('realtime', []):
        word = item.get('word', '')
        raw_hot = item.get('raw_hot', 0)
        text = word + ' ' + (item.get('label_name', '') or '')
        items.append({
            'title': word,
            'desc': '',
            'hot': int(raw_hot) if raw_hot else 0,
            'sentiment': score(text),
            'sector': classify_sector(text),
            'source': 'weibo',
        })
    
    return items

# ═══════════════════════════════════════════
# 3. B站热搜
# ═══════════════════════════════════════════
def collect_bilibili():
    html = fetch_direct('https://api.bilibili.com/x/web-interface/wbi/search/square?limit=50', headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': 'https://www.bilibili.com/',
    })
    if not html: return None
    
    try:
        data = json.loads(html)
    except:
        return None
    
    if data.get('code') != 0:
        return None
    
    items = []
    for item in data.get('data', {}).get('trending', {}).get('list', []):
        keyword = item.get('keyword', '')
        items.append({
            'title': keyword,
            'desc': '',
            'hot': 0,  # B站不提供具体热度值
            'sentiment': score(keyword),
            'sector': classify_sector(keyword),
            'source': 'bilibili',
        })
    
    return items

# ═══════════════════════════════════════════
# 4. Crypto F&G
# ═══════════════════════════════════════════
def collect_fng():
    html = fetch_direct('https://api.alternative.me/fng/?limit=1')
    if not html: return None
    data = json.loads(html)
    item = data['data'][0]
    return {
        'value': int(item['value']),
        'classification': item['value_classification'],
    }

# ═══════════════════════════════════════════
# 5. 股吧本地文件
# ═══════════════════════════════════════════
def collect_guba_local():
    """读取Ryan本地Chrome抓取的股吧数据"""
    path = os.path.join(DATA_DIR, 'guba_local.json')
    if not os.path.exists(path):
        return None
    
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None

# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════
if __name__ == '__main__':
    print('疯向标 v2 采集...')
    print()
    
    result = {
        'time': datetime.now().isoformat(),
        'sources': {},
        'sectors': {},
        'summary': {},
    }
    
    # 1. 百度
    baidu_items = collect_baidu()
    if baidu_items:
        result['sources']['baidu'] = {'count': len(baidu_items), 'status': 'ok'}
        print(f'  百度热搜: {len(baidu_items)}条')
    else:
        result['sources']['baidu'] = {'status': 'fail'}
        print('  百度热搜: FAIL')
        baidu_items = []
    
    # 2. 微博
    weibo_items = collect_weibo()
    if weibo_items:
        result['sources']['weibo'] = {'count': len(weibo_items), 'status': 'ok'}
        print(f'  微博热搜: {len(weibo_items)}条')
    else:
        result['sources']['weibo'] = {'status': 'fail'}
        print('  微博热搜: FAIL')
        weibo_items = []
    
    # 3. B站
    bili_items = collect_bilibili()
    if bili_items:
        result['sources']['bilibili'] = {'count': len(bili_items), 'status': 'ok'}
        print(f'  B站热搜: {len(bili_items)}条')
    else:
        result['sources']['bilibili'] = {'status': 'fail'}
        print('  B站热搜: FAIL')
        bili_items = []
    
    # 4. Crypto F&G
    fng = collect_fng()
    if fng:
        result['sources']['fng'] = {'status': 'ok', 'value': fng['value']}
        print(f'  Crypto F&G: {fng["value"]} ({fng["classification"]})')
    else:
        result['sources']['fng'] = {'status': 'fail'}
        print('  Crypto F&G: FAIL')
    
    # 5. 股吧本地
    guba = collect_guba_local()
    if guba:
        result['sources']['guba'] = {'status': 'ok', 'sectors': list(guba.keys())}
        print(f'  股吧本地: {len(guba)}个板块')
    else:
        result['sources']['guba'] = {'status': 'missing'}
        print('  股吧本地: 无数据')
    
    # ═══ 合并全民社媒，按赛道分析 ═══
    all_social = baidu_items + weibo_items + bili_items
    print(f'\n  全平台社媒: {len(all_social)}条')
    
    sectors = {'gold': [], 'btc': [], 'a_semi': [], 'us_semi': [], 'other': []}
    for item in all_social:
        sec = item.get('sector', 'other')
        if sec in sectors:
            sectors[sec].append(item)
        else:
            sectors['other'].append(item)
    
    for sec in ['gold', 'btc', 'a_semi', 'us_semi', 'other']:
        analysis = analyze_sector(sectors[sec])
        result['sectors'][sec] = analysis
        if sec != 'other':
            tag = {'gold': '🥇金银', 'btc': '₿BTC', 'a_semi': '🇨🇳A股半导', 'us_semi': '🇺🇸美股半导'}[sec]
            print(f'  {tag}: {analysis["count"]}条 沉默{analysis["silence_rate"]:.0f}% 狂欢{analysis["carnival_rate"]:.0f}% 情绪{analysis["sentiment"]:+.2f}')
    
    # ═══ 合并股吧数据（如果有） ═══
    if guba:
        print(f'\n  ⚠️ 股吧本地数据覆盖社媒分析')
        for sec_key, guba_data in guba.items():
            if sec_key in result['sectors']:
                # 股吧数据优先，但保留社媒作为参考
                result['sectors'][sec_key] = {
                    **result['sectors'][sec_key],
                    'guba_override': guba_data,
                }
    
    # ═══ 生成摘要 ═══
    result['summary'] = {
        'total_social': len(all_social),
        'sources_ok': sum(1 for s in result['sources'].values() if s.get('status') == 'ok'),
        'sources_total': len(result['sources']),
        'fng': fng,
    }
    
    # ═══ 保存 ═══
    os.makedirs(DATA_DIR, exist_ok=True)
    
    latest = os.path.join(DATA_DIR, 'fengxiangbiao_latest.json')
    with open(latest, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    daily = os.path.join(DATA_DIR, f'fengxiangbiao_daily_{datetime.now().strftime("%Y%m%d")}.json')
    with open(daily, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f'\n✅ {latest}')
    print(f'✅ {daily}')
