#!/usr/bin/env python3
"""
疯向标 v1 — 全源采集器
输出: data/fengxiangbiao_daily.json
"""
import json, re, urllib.request, ssl, sys, os, time
from datetime import datetime

ssl_ctx = ssl.create_default_context()
PROXY = "http://127.0.0.1:7890"

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

def load_cookie(name):
    path = os.path.expanduser(f'~/.hermes/scripts/fengxiangbiao/data/.{name}')
    try:
        with open(path) as f:
            return f.read().strip()
    except:
        return ''

# ═══════════════════════════════════════════
# 情绪词典
# ═══════════════════════════════════════════
BULLISH = ['暴涨','起飞','新高','突破','抄底','牛回','牛市','反转','大阳线','满仓','梭哈',
           '爆拉','加仓','上车','冲','稳了','反弹','主升浪','逼空','反击','大涨','涨停',
           '吃肉','回血','all in','利好','黄金坑','起飞了']
BEARISH = ['暴跌','崩盘','归零','腰斩','割肉','清仓','跑路','完了','熊市','爆仓','血洗',
           '踩踏','恐慌','逃命','大阴线','破位','深套','亏麻','跌停','吃面','天台',
           '空仓','观望','不敢买','绝望','砸盘','出货','收割','韭菜']

def score(text):
    t = text.lower()
    b = sum(1 for w in BULLISH if w in t)
    s = sum(1 for w in BEARISH if w in t)
    if b > s: return min(b - s, 5)
    elif s > b: return max(-(s - b), -5)
    return 0

# ═══════════════════════════════════════════
# 1. 百度热搜
# ═══════════════════════════════════════════
def collect_baidu():
    html = fetch('https://top.baidu.com/board?tab=realtime', use_proxy=False)
    if not html: return None
    
    m = re.search(r'<!--s-data:(\{.*?\})-->', html)
    if not m: m = re.search(r's-data:(\{.*?\});', html)
    if not m: return None
    
    data = json.loads(m.group(1))
    items = []
    tracks = {'gold': 0, 'btc': 0, 'ai_storage': 0, 'macro': 0, 'other': 0}
    
    for card in data['data']['cards']:
        if card.get('component') != 'hotList': continue
        for item in card['content']:
            text = item.get('query','') + item.get('desc','')
            hot = int(item.get('hotScore', 0))
            
            # 赛道分类
            for kw in ['黄金','金价','白银','银价']:
                if kw in text: tracks['gold'] += 1; break
            else:
                for kw in ['BTC','比特币','加密','币']:
                    if kw in text: tracks['btc'] += 1; break
                else:
                    for kw in ['AI','芯片','存储','光模块','算力','人工智能','半导体','英伟达']:
                        if kw in text: tracks['ai_storage'] += 1; break
                    else:
                        for kw in ['A股','大盘','上证','跌停','涨停','牛市','熊市','降息']:
                            if kw in text: tracks['macro'] += 1; break
                        else:
                            tracks['other'] += 1
            
            items.append({'title': item.get('query',''), 'desc': item.get('desc','')[:150],
                         'hot': hot, 'sentiment': score(text)})
    
    return {'items': items, 'tracks': tracks}

# ═══════════════════════════════════════════
# 2. 华尔街见闻
# ═══════════════════════════════════════════
def collect_wallstreetcn():
    channels = {
        'global': 'global-channel',
        'gold': 'goldc-channel',
        'us_stock': 'us-stock-channel',
        'a_stock': 'a-stock-channel',
    }
    results = {}
    for name, ch in channels.items():
        url = f'https://api-one.wallstcn.com/apiv1/content/lives?channel={ch}&limit=20'
        html = fetch(url, headers={'User-Agent': 'Mozilla/5.0'})
        if not html: continue
        try:
            data = json.loads(html)
            items = []
            for i in data.get('data',{}).get('items',[]):
                t = i.get('content_text','') or i.get('title','')
                if t.strip():
                    items.append({'title': i.get('title',''), 'content': t[:200],
                                 'sentiment': score(t)})
            b = sum(1 for i in items if i['sentiment'] > 0)
            s = sum(1 for i in items if i['sentiment'] < 0)
            results[name] = {
                'count': len(items),
                'bullish': b, 'bearish': s,
                'sentiment': round((b - s) / max(len(items), 1), 2),
                'items': items,
            }
        except: pass
    return results

# ═══════════════════════════════════════════
# 3. 雪球 (替代股吧)
# ═══════════════════════════════════════════
def collect_xueqiu():
    cookie = load_cookie('xueqiu_cookie')
    if not cookie: return None
    
    url = 'https://xueqiu.com/v4/statuses/public_timeline_by_category.json?since_id=-1&max_id=-1&category=-1&count=20'
    html = fetch(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Cookie': cookie,
    })
    if not html: return None
    
    try:
        data = json.loads(html)
    except:
        return None
    
    posts = []
    finance_kw = ['股','A股','BTC','币','加密','黄金','降息','茅台','基金','大盘',
                  '涨停','跌停','牛市','AI','芯片','半导体','光模块','存储','算力',
                  'NVDA','英伟达','美光','MU','HBM','白银','金价','锂电','光伏']
    
    for item in data.get('list', []):
        d = json.loads(item['data'])
        title = d.get('title', '')
        desc = d.get('description', '') or ''
        text = title + ' ' + desc
        if any(k in text for k in finance_kw):
            posts.append({
                'title': title,
                'desc': desc[:150],
                'user': d.get('user', {}).get('screen_name', ''),
                'sentiment': score(text),
            })
    
    b = sum(1 for p in posts if p['sentiment'] > 0)
    s = sum(1 for p in posts if p['sentiment'] < 0)
    n = sum(1 for p in posts if p['sentiment'] == 0)
    
    return {
        'count': len(posts),
        'bullish': b, 'bearish': s, 'neutral': n,
        'silence_rate': round(n / max(len(posts), 1) * 100, 1),
        'carnival_rate': round(b / max(len(posts), 1) * 100, 1),
        'sentiment': round(sum(p['sentiment'] for p in posts) / max(len(posts), 1), 2),
        'posts': posts,
    }

# ═══════════════════════════════════════════
# 4. Crypto F&G
# ═══════════════════════════════════════════
def collect_fng():
    url = 'https://api.alternative.me/fng/?limit=1'
    html = fetch(url, use_proxy=False)
    if not html: return None
    data = json.loads(html)
    item = data['data'][0]
    return {
        'value': int(item['value']),
        'classification': item['value_classification'],
    }

# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════
if __name__ == '__main__':
    print('疯向标 v1 采集...')
    
    result = {
        'time': datetime.now().isoformat(),
        'baidu': collect_baidu(),
    }
    print(f'  百度热搜: {result["baidu"]["tracks"] if result["baidu"] else "FAIL"}')
    
    result['wallstreetcn'] = collect_wallstreetcn()
    for k, v in result['wallstreetcn'].items():
        print(f'  华尔街-{k}: {v["count"]}条 情绪{v["sentiment"]:+.2f}')
    
    result['xueqiu'] = collect_xueqiu()
    if result['xueqiu']:
        x = result['xueqiu']
        print(f'  雪球: {x["count"]}条 沉默率{x["silence_rate"]:.0f}% 情绪{x["sentiment"]:+.2f}')
    
    result['fng'] = collect_fng()
    if result['fng']:
        print(f'  Crypto F&G: {result["fng"]["value"]} ({result["fng"]["classification"]})')
    
    # 保存
    data_dir = os.path.expanduser('~/.hermes/scripts/fengxiangbiao/data')
    path = os.path.join(data_dir, f'fengxiangbiao_daily_{datetime.now().strftime("%Y%m%d")}.json')
    with open(path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    latest = os.path.join(data_dir, 'fengxiangbiao_latest.json')
    with open(latest, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f'\n✅ 保存: {path}')
