#!/usr/bin/env python3
"""
疯向标回测 v2: 股吧赛道情绪 → 对应标的价格
采样：每周翻页抓取股吧，计算沉默率 → 对应7d/14d/30d收益
"""
import json, re, subprocess, os, sys, ssl, urllib.request
from datetime import datetime, timedelta, date
from collections import defaultdict

ssl_ctx = ssl.create_default_context()
PROXY = "http://127.0.0.1:7890"
GUBA_UA = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36'

# ═══════ 情绪词典 ═══════
BULLISH = ['暴涨','起飞','新高','突破','抄底','牛回','牛市','反转','大阳线','满仓','梭哈',
           '爆拉','加仓','上车','冲','稳了','反弹','主升浪','逼空','反击','大涨','涨停',
           '吃肉','回血','利好','黄金坑']
BEARISH = ['暴跌','崩盘','归零','腰斩','割肉','清仓','跑路','完了','熊市','爆仓','血洗',
           '踩踏','恐慌','逃命','大阴线','破位','深套','亏麻','跌停','吃面','天台',
           '空仓','观望','不敢买','绝望']

def score(text):
    t = text.lower()
    b = sum(1 for w in BULLISH if w in t)
    s = sum(1 for w in BEARISH if w in t)
    if b > s: return min(b - s, 5)
    elif s > b: return max(-(s - b), -5)
    return 0

# ═══════ 抓取一周的股吧帖子 ═══════
def fetch_guba_page(code, page=1):
    url = f'https://guba.eastmoney.com/list,{code}_{page}.html' if page > 1 else f'https://guba.eastmoney.com/list,{code}.html'
    try:
        r = subprocess.run(['curl', '-s', '--max-time', '15',
            '-H', f'User-Agent: {GUBA_UA}', url],
            capture_output=True, text=True, timeout=20)
        html = r.stdout
        if len(html) < 5000: return None
        m = re.search(r'article_list\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not m: return None
        data = json.loads(m.group(1))
        return data.get('re', [])
    except:
        return None

def analyze_posts(posts):
    if not posts: return None
    b = s = n = 0
    for p in posts:
        sc = score(p.get('post_title', ''))
        if sc > 0: b += 1
        elif sc < 0: s += 1
        else: n += 1
    total = len(posts)
    return {
        'count': total,
        'bullish': b, 'bearish': s, 'neutral': n,
        'silence_rate': round(n / total * 100, 1),
        'carnival_rate': round(b / total * 100, 1),
        'sentiment': round((b - s) / total, 2),
    }

# ═══════ 获取历史价格 ═══════
def get_price_history(symbol, days=180):
    """用Yahoo v8 chart API获取历史价格"""
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={days}d&interval=1d'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        # use proxy
        proxy_handler = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
        opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ssl_ctx))
        with opener.open(req, timeout=15) as r:
            data = json.loads(r.read())
        result = data['chart']['result'][0]
        ts = result['timestamp']
        closes = result['indicators']['quote'][0]['close']
        prices = {}
        for i, t in enumerate(ts):
            if closes[i] is not None:
                d = date.fromtimestamp(t)
                prices[d] = closes[i]
        return prices
    except Exception as e:
        print(f'  价格获取失败: {e}')
        return None

# ═══════ 回测主逻辑 ═══════
def backtest(board_code, symbol, symbol_name, weeks=12):
    """采样N周，计算沉默率vs后续收益"""
    print(f'\n{"="*60}')
    print(f'回测: {symbol_name} ({board_code}) → {symbol}')
    print(f'采样{weeks}周')
    print(f'{"="*60}')
    
    # 获取价格
    print('获取价格...')
    prices = get_price_history(symbol, days=weeks*7+60)
    if not prices:
        print('❌ 价格获取失败')
        return None
    
    print(f'  价格范围: {min(prices.keys())} ~ {max(prices.keys())} ({len(prices)}天)')
    
    # 每周采样股吧（取该周第1页作为代表）
    # 页面估算: p278=1周前, p556=2周前, p834=3周前...
    PAGES_PER_WEEK = 278
    
    weekly_data = []
    for w in range(weeks):
        page = 1 + w * PAGES_PER_WEEK
        
        # 确定该周的日期
        week_date = date.today() - timedelta(weeks=w+1)
        
        posts = fetch_guba_page(board_code, page)
        if not posts:
            print(f'  W{w+1:2d} (p{page}): ❌ 抓取失败')
            continue
        
        analysis = analyze_posts(posts)
        analysis['week'] = w + 1
        analysis['date'] = week_date.isoformat()
        weekly_data.append(analysis)
        
        print(f'  W{w+1:2d} ({week_date}): {analysis["count"]}条 沉默{analysis["silence_rate"]:.0f}% 狂欢{analysis["carnival_rate"]:.0f}% 情绪{analysis["sentiment"]:+.2f}')
    
    if len(weekly_data) < 5:
        print('❌ 有效数据不足')
        return None
    
    # ═══ 计算收益 ═══
    price_list = sorted(prices.items())
    date_to_idx = {d: i for i, (d, _) in enumerate(price_list)}
    
    print(f'\n{"="*60}')
    print(f'  回测结果')
    print(f'{"="*60}')
    
    # 按沉默率分组
    results = {
        'high_silence': [],  # silence >= 85%
        'mid_silence': [],   # 75-85%
        'low_silence': [],   # < 75%
    }
    
    for wd in weekly_data:
        sr = wd['silence_rate']
        week_date = date.fromisoformat(wd['date'])
        
        # 找该周后的第一个价格日
        entry_idx = None
        for offset in range(7):
            check = week_date + timedelta(days=offset)
            if check in date_to_idx:
                entry_idx = date_to_idx[check]
                break
        
        if entry_idx is None:
            continue
        
        entry_price = price_list[entry_idx][1]
        
        bucket = 'high_silence' if sr >= 85 else 'mid_silence' if sr >= 75 else 'low_silence'
        
        for hold_days in [7, 14, 30]:
            exit_idx = entry_idx + hold_days
            if exit_idx >= len(price_list):
                continue
            ret = (price_list[exit_idx][1] - entry_price) / entry_price * 100
            results[bucket].append({
                'date': wd['date'],
                'silence': sr,
                'hold': hold_days,
                'return': round(ret, 2),
            })
    
    # 汇总
    for bucket, trades in results.items():
        if not trades:
            continue
        label = {'high_silence': '沉默≥85%', 'mid_silence': '沉默75-85%', 'low_silence': '沉默<75%'}[bucket]
        print(f'\n📊 {label} ({len(trades)}笔)')
        
        for h in [7, 14, 30]:
            subset = [t for t in trades if t['hold'] == h]
            if not subset:
                continue
            rets = [t['return'] for t in subset]
            avg = sum(rets) / len(rets)
            win = sum(1 for r in rets if r > 0) / len(rets) * 100
            median = sorted(rets)[len(rets)//2]
            print(f'  持有{h:2d}d: 均{avg:+.2f}% 中{median:+.2f}% 胜率{win:.0f}% ({len(subset)}笔)')
            # 列出具体交易
            for t in subset:
                emoji = '✅' if t['return'] > 0 else '❌'
                print(f'    {emoji} {t["date"]} 沉默{t["silence"]:.0f}% → {h}d {t["return"]:+.2f}%')
    
    return results

if __name__ == '__main__':
    # 回测美股半导体
    backtest('us_NVDA', 'NVDA', '英伟达NVDA', weeks=12)
    
    # 回测黄金
    backtest('BK0731', 'GC=F', '黄金期货', weeks=12)
    
    # 回测A股半导体
    backtest('BK1036', '688981.SS', '中芯国际', weeks=12)
