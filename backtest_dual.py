#!/usr/bin/env python3
"""
疯向标 双向回测: 沉默买点 + 狂欢卖点 × 全赛道
"""
import json, ssl, urllib.request
from datetime import date, timedelta
from collections import defaultdict

ssl_ctx = ssl.create_default_context()
PROXY = "http://127.0.0.1:7890"

with open('/Users/ryan/.hermes/scripts/fengxiangbiao/data/guba_history_2y.json') as f:
    history = json.load(f)
weeks = history['weeks']

def get_prices(symbol, days=730):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={days}d&interval=1d'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
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
    except:
        return None

def calc_ma200(prices, target_date):
    sorted_prices = sorted((d, p) for d, p in prices.items() if d <= target_date)
    if len(sorted_prices) < 200: return None
    return sum(p for _, p in sorted_prices[-200:]) / 200

# ═══════ 加载价格 ═══════
symbols = {'NVDA':'英伟达','MU':'美光','SMH':'SOX ETF','GLD':'黄金ETF','BTC':'比特币'}
all_prices = {}
for sym, name in symbols.items():
    ysym = 'BTC-USD' if sym == 'BTC' else sym
    p = get_prices(ysym, 800)
    if p: all_prices[sym] = {'name':name,'prices':p}

print(f'{"="*80}')
print(f'  双向验证: 沉默买点 + 狂欢卖点 × 全赛道 × 周期位置')
print(f'  {len(weeks)}周情绪数据 | {len(all_prices)}个标的')
print(f'{"="*80}')

for sym, info in all_prices.items():
    prices = info['prices']
    price_list = sorted(prices.items())
    date_to_idx = {d: i for i, (d, _) in enumerate(price_list)}
    
    print(f'\n{"─"*80}')
    print(f'  {info["name"]} ({sym})')
    print(f'{"─"*80}')
    
    # 分组: (信号类型, 周期)
    signal_buckets = defaultdict(list)
    base_returns = []
    
    for w in weeks:
        total = w['count']
        silence = round(w['neutral'] / total * 100, 1)
        carnival = round(w['bullish'] / total * 100, 1)
        sentiment = w['sentiment_score']
        
        try:
            week_date = date.fromisoformat(w['latest'][:10])
        except:
            continue
        
        entry_idx = None
        for offset in range(7):
            check = week_date + timedelta(days=offset)
            if check in date_to_idx:
                entry_idx = date_to_idx[check]
                break
        if entry_idx is None: continue
        
        entry_price = price_list[entry_idx][1]
        ma200 = calc_ma200(prices, week_date)
        if ma200 is None: continue
        cycle = 'bear' if entry_price < ma200 else 'bull'
        
        # 计算收益
        returns = {}
        for h in [7,14,30]:
            ei = entry_idx + h
            if ei < len(price_list):
                returns[h] = (price_list[ei][1] - entry_price) / entry_price * 100
        
        if 7 not in returns: continue
        
        # 沉默买点
        if silence >= 85 and sentiment < 0:
            signal_buckets[('🟢沉默买点', cycle)].append(returns)
        elif silence >= 80 and sentiment < 0:
            signal_buckets[('🟡沉默偏买', cycle)].append(returns)
        
        # 狂欢卖点（反向：做空或减仓）
        if carnival >= 25:
            signal_buckets[('🔴极端狂欢', cycle)].append({h: -v for h, v in returns.items()})  # 反向
        elif carnival >= 20:
            signal_buckets[('🟠狂欢卖点', cycle)].append({h: -v for h, v in returns.items()})
        
        # 基准
        base_returns.append(returns)
    
    # 输出
    hdr = f'  {"信号":16s} {"周期":5s} {"笔数":>4s} {"7d":>8s} {"7d胜":>6s} {"14d":>8s} {"14d胜":>6s} {"30d":>8s} {"30d胜":>6s}'
    print(hdr)
    print(f'  {"-"*len(hdr)}')
    
    key_order = [
        ('🟢沉默买点', 'bear'), ('🟢沉默买点', 'bull'),
        ('🟡沉默偏买', 'bear'), ('🟡沉默偏买', 'bull'),
        ('🔴极端狂欢', 'bear'), ('🔴极端狂欢', 'bull'),
        ('🟠狂欢卖点', 'bear'), ('🟠狂欢卖点', 'bull'),
    ]
    
    best_signal = None
    best_7d = -999
    
    for key in key_order:
        trades = signal_buckets.get(key, [])
        if not trades: continue
        
        sig, cyc = key
        n = len(trades)
        parts = [f'  {sig:14s} {cyc:5s} {n:4d}']
        
        for h in [7,14,30]:
            rets = [t[h] for t in trades if h in t]
            if rets:
                avg = sum(rets)/len(rets)
                win = sum(1 for r in rets if r>0)/len(rets)*100
                flag = '🔥' if avg > 5 and win >= 80 else '✅' if avg > 3 and win >= 60 else '⚠️' if avg > 0 else '💀'
                parts.append(f'{flag}{avg:+5.1f}% {win:4.0f}%')
                if h == 7 and avg > best_7d and n >= 3:
                    best_7d = avg
                    best_signal = f'{sig}×{cyc}'
            else:
                parts.append(f'{"":>13s}')
        print(''.join(parts))
    
    # 基准
    if base_returns:
        b7 = [t[7] for t in base_returns if 7 in t]
        b14 = [t[14] for t in base_returns if 14 in t]
        b30 = [t[30] for t in base_returns if 30 in t]
        b7_line = f'{sum(b7)/len(b7):+.1f}% {sum(1 for r in b7 if r>0)/len(b7)*100:.0f}%' if b7 else 'N/A'
        b14_line = f'{sum(b14)/len(b14):+.1f}% {sum(1 for r in b14 if r>0)/len(b14)*100:.0f}%' if b14 else 'N/A'
        b30_line = f'{sum(b30)/len(b30):+.1f}% {sum(1 for r in b30 if r>0)/len(b30)*100:.0f}%' if b30 else 'N/A'
        print(f'  {"基准买入持有":14s} {"":5s} {len(b7):4d}  {b7_line:>11s}  {b14_line:>11s}  {b30_line:>11s}')
    
    if best_signal:
        print(f'  ⭐ 最佳: {best_signal}')

print(f'\n{"="*80}')
print('  完成')
