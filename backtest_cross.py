#!/usr/bin/env python3
"""
疯向标 交叉验证回测
上证指数吧2年104周情绪 → 全赛道(NVDA/MU/GLD/BTC/SMH) × 周期位置过滤
"""
import json, ssl, urllib.request
from datetime import date, timedelta
from collections import defaultdict

ssl_ctx = ssl.create_default_context()
PROXY = "http://127.0.0.1:7890"

# ═══════ 加载情绪数据 ═══════
with open('/Users/ryan/.hermes/scripts/fengxiangbiao/data/guba_history_2y.json') as f:
    history = json.load(f)
weeks = history['weeks']
print(f'情绪数据: {len(weeks)}周 | {weeks[-1]["earliest"][:10]} ~ {weeks[0]["latest"][:10]}')

# ═══════ 获取价格+MA200 ═══════
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
    except Exception as e:
        print(f'  {symbol}: {e}')
        return None

def calc_ma200(prices, target_date):
    """计算target_date当天的MA200"""
    sorted_prices = sorted((d, p) for d, p in prices.items() if d <= target_date)
    if len(sorted_prices) < 200:
        return None
    recent = sorted_prices[-200:]
    return sum(p for _, p in recent) / 200

# ═══════ 获取所有标的价格 ═══════
symbols = {
    'NVDA': '英伟达',
    'MU': '美光存储', 
    'SMH': 'SOX半导体ETF',
    'GLD': '黄金ETF',
    'BTC': '比特币',
}

print('\n获取价格数据...')
all_prices = {}
for sym, name in symbols.items():
    ysym = 'BTC-USD' if sym == 'BTC' else sym
    prices = get_prices(ysym, days=800)
    if prices:
        all_prices[sym] = {'name': name, 'prices': prices}
        print(f'  {sym}: {min(prices.keys())} ~ {max(prices.keys())} ({len(prices)}天)')

# ═══════ 交叉验证 ═══════
print(f'\n{"="*70}')
print(f'  交叉验证: 上证情绪 → 全赛道 × 周期位置')
print(f'{"="*70}')

for sym, info in all_prices.items():
    prices = info['prices']
    price_list = sorted(prices.items())
    date_to_idx = {d: i for i, (d, _) in enumerate(price_list)}
    
    print(f'\n── {info["name"]} ({sym}) ──')
    
    # 按沉默率+周期分组
    buckets = defaultdict(list)  # (silence_bucket, cycle) -> [(return_7d, return_14d, return_30d)]
    
    for w in weeks:
        # 沉默率
        silence = round(w['neutral'] / w['count'] * 100, 1)
        sentiment = w['sentiment_score']
        
        # 找周日期
        try:
            week_date = date.fromisoformat(w['latest'][:10])
        except:
            continue
        
        # 找入场价格
        entry_idx = None
        for offset in range(7):
            check = week_date + timedelta(days=offset)
            if check in date_to_idx:
                entry_idx = date_to_idx[check]
                break
        if entry_idx is None:
            continue
        
        entry_price = price_list[entry_idx][1]
        
        # MA200
        ma200 = calc_ma200(prices, week_date)
        if ma200 is None:
            continue
        
        cycle = 'bear' if entry_price < ma200 else 'bull'
        
        # 沉默率分档
        if silence >= 85:
            sil_bucket = '😶 ≥85%'
        elif silence >= 75:
            sil_bucket = '😐 75-85%'
        else:
            sil_bucket = '😊 <75%'
        
        # 计算持有收益
        returns = []
        for hold in [7, 14, 30]:
            exit_idx = entry_idx + hold
            if exit_idx < len(price_list):
                ret = (price_list[exit_idx][1] - entry_price) / entry_price * 100
                returns.append(ret)
            else:
                returns.append(None)
        
        if returns[0] is not None:
            buckets[(sil_bucket, cycle)].append(returns)
    
    # 输出
    print(f'  {"":20s} {"笔数":>4s} {"7d均":>7s} {"7d胜率":>7s} {"14d均":>7s} {"14d胜率":>7s} {"30d均":>7s} {"30d胜率":>7s}')
    print(f'  {"-"*70}')
    
    key_order = [
        ('😶 ≥85%', 'bear'),
        ('😶 ≥85%', 'bull'),
        ('😐 75-85%', 'bear'),
        ('😐 75-85%', 'bull'),
        ('😊 <75%', 'bear'),
        ('😊 <75%', 'bull'),
    ]
    
    for key in key_order:
        trades = buckets.get(key, [])
        if not trades:
            continue
        
        sil, cyc = key
        n = len(trades)
        
        parts = [f'  {sil}×{cyc:4s}  {n:4d}']
        for h_idx, h in enumerate([7, 14, 30]):
            rets = [t[h_idx] for t in trades if t[h_idx] is not None]
            if rets:
                avg = sum(rets) / len(rets)
                win = sum(1 for r in rets if r > 0) / len(rets) * 100
                color_flag = '🔥' if avg > 5 and win >= 60 else '⚠️' if avg > 0 else '💀'
                parts.append(f'{color_flag}{avg:+6.1f}%')
                parts.append(f'{win:5.0f}%')
            else:
                parts.append(f'{"":>7s}')
                parts.append(f'{"":>7s}')
        
        print(''.join(parts))
    
    # 汇总：沉默买点总体 vs 基准
    all_silence_bear = []
    all_other = []
    for (sil, cyc), trades in buckets.items():
        for t in trades:
            if sil == '😶 ≥85%' and cyc == 'bear':
                all_silence_bear.append(t)
            else:
                all_other.append(t)
    
    if all_silence_bear:
        print(f'\n  📊 沉默≥85%+熊市 vs 其余:')
        for h_idx, h in enumerate([7, 14, 30]):
            sb_rets = [t[h_idx] for t in all_silence_bear if t[h_idx] is not None]
            o_rets = [t[h_idx] for t in all_other if t[h_idx] is not None]
            if sb_rets and o_rets:
                sb_avg = sum(sb_rets)/len(sb_rets)
                sb_win = sum(1 for r in sb_rets if r>0)/len(sb_rets)*100
                o_avg = sum(o_rets)/len(o_rets)
                o_win = sum(1 for r in o_rets if r>0)/len(o_rets)*100
                diff = sb_avg - o_avg
                print(f'    持有{h:2d}d: 信号{sb_avg:+.1f}%({sb_win:.0f}%胜) vs 基准{o_avg:+.1f}%({o_win:.0f}%胜) 超额{diff:+.1f}%')

print(f'\n{"="*70}')
print('  完成')
