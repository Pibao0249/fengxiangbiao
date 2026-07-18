#!/usr/bin/env python3
"""
疯向标回测：极端情绪 → AI/存储股票后续收益
情绪代理：VIX（散户恐慌）、Crypto F&G（加密情绪）
标的：NVDA AMD MU SMH SOX
时间：2021-2026（5年+）
"""
import json, sys, os, urllib.request, ssl
from datetime import datetime, timedelta, date
import csv

PROXY = "http://127.0.0.1:7890"
ssl_ctx = ssl.create_default_context()

def fetch(url, use_proxy=True, timeout=15):
    req = urllib.request.Request(url)
    if use_proxy:
        req.set_proxy(PROXY, 'http')
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ERR: {url[:80]} -> {e}", file=sys.stderr)
        return None

# ════════════════════════════════
# 1. Yahoo Finance 历史日线
# ════════════════════════════════
def get_yahoo(symbol, period1, period2):
    """获取日线OHLCV"""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={int(period1)}&period2={int(period2)}&interval=1d"
    )
    data = fetch(url)
    if not data or 'chart' not in data:
        return None
    result = data['chart']['result'][0]
    ts = result['timestamp']
    quotes = result['indicators']['quote'][0]
    rows = []
    for i, t in enumerate(ts):
        o = quotes['open'][i]
        h = quotes['high'][i]
        l = quotes['low'][i]
        c = quotes['close'][i]
        v = quotes['volume'][i]
        if c is not None:
            rows.append({
                'date': date.fromtimestamp(t).isoformat(),
                'timestamp': t,
                'open': o, 'high': h, 'low': l, 'close': c, 'volume': v,
            })
    return rows

# ════════════════════════════════
# 2. VIX 历史 (via Yahoo ^VIX)
# ════════════════════════════════
def get_vix(period1, period2):
    """获取VIX"""
    return get_yahoo('%5EVIX', period1, period2)

# ════════════════════════════════
# 3. Crypto F&G
# ════════════════════════════════
def get_fng_history():
    """获取F&G全部历史 (2018至今, daily)"""
    url = "https://api.alternative.me/fng/?limit=0&format=json"
    data = fetch(url, use_proxy=False)
    if not data:
        return {}
    result = {}
    for item in data['data']:
        ts = int(item['timestamp'])
        result[date.fromtimestamp(ts).isoformat()] = {
            'value': int(item['value']),
            'classification': item['value_classification'],
        }
    return result

# ════════════════════════════════
# 4. 回测引擎
# ════════════════════════════════
def backtest(prices, indicator, indicator_name, extreme_high=None, extreme_low=None):
    """
    prices: [{date, close, ...}, ...]
    indicator: {date_str: value} 或 {date_str: {value: n}}
    extreme_high: 极端高阈值 (恐慌)
    extreme_low: 极端低阈值 (贪婪)
    
    返回: 极端日 → 持有N天的收益
    """
    # 对齐日期
    aligned = []
    for row in prices:
        d = row['date']
        if d in indicator:
            val = indicator[d] if isinstance(indicator[d], (int, float)) else indicator[d].get('value', indicator[d])
            aligned.append({**row, 'indicator': val})
    
    if not aligned:
        return {'error': 'no aligned data'}
    
    # 找极端日
    extreme_days = []
    if extreme_high is not None:
        # VIX > threshold = panic
        extreme_days += [a for a in aligned if a['indicator'] >= extreme_high]
    if extreme_low is not None:
        # F&G < threshold = fear
        extreme_days += [a for a in aligned if a['indicator'] <= extreme_low]
    
    # 去重
    seen = set()
    unique = []
    for d in extreme_days:
        if d['date'] not in seen:
            seen.add(d['date'])
            unique.append(d)
    unique.sort(key=lambda x: x['date'])
    
    if not unique:
        return {'error': f'no extreme days (threshold: high>{extreme_high}, low<{extreme_low})'}
    
    # 计算持有收益
    results = {7: [], 14: [], 30: [], 60: []}
    for extreme in unique:
        idx = next((i for i, r in enumerate(aligned) if r['date'] == extreme['date']), None)
        if idx is None:
            continue
        
        entry_price = aligned[idx]['close']
        for hold_days in [7, 14, 30, 60]:
            exit_idx = idx + hold_days
            if exit_idx >= len(aligned):
                continue
            exit_price = aligned[exit_idx]['close']
            ret = (exit_price - entry_price) / entry_price * 100
            results[hold_days].append({
                'entry_date': extreme['date'],
                'entry_price': entry_price,
                'exit_date': aligned[exit_idx]['date'],
                'exit_price': exit_price,
                'return': round(ret, 2),
                'indicator_value': extreme['indicator'],
            })
    
    # 统计
    th_parts = []
    if extreme_high:
        th_parts.append(f'>{extreme_high}')
    if extreme_low:
        th_parts.append(f'<{extreme_low}')
    stats = {
        'indicator': indicator_name,
        'extreme_count': len(unique),
        'threshold': ' & '.join(th_parts),
    }
    for hold, trades in results.items():
        if trades:
            returns = [t['return'] for t in trades]
            avg = sum(returns) / len(returns)
            win = sum(1 for r in returns if r > 0)
            stats[f'{hold}d'] = {
                'trades': len(trades),
                'avg_return': round(avg, 2),
                'median_return': round(sorted(returns)[len(returns)//2], 2),
                'win_rate': round(win / len(trades) * 100, 1),
                'max_return': round(max(returns), 2),
                'min_return': round(min(returns), 2),
            }
    
    return stats

# ════════════════════════════════
# MAIN
# ════════════════════════════════
if __name__ == '__main__':
    # 时间范围: 2021-01-01 到 2026-07-18
    t1 = datetime(2021, 1, 1).timestamp()
    t2 = datetime(2026, 7, 19).timestamp()
    
    symbols = {
        'NVDA': '英伟达',
        'AMD': 'AMD',
        'MU': '美光(存储)',
        'AVGO': '博通',
        'SMH': 'SOX半导体ETF',
    }
    
    print("═══════════════════════════════════════")
    print("  疯向标回测: 极端情绪 → AI/存储股  ")
    print("  2021-2026 (5年+)")
    print("═══════════════════════════════════════\n")
    
    # 获取VIX
    print("下载 VIX 数据...")
    vix = get_vix(t1, t2)
    if vix:
        vix_map = {r['date']: r['close'] for r in vix}
        print(f"  VIX: {len(vix_map)} 个交易日\n")
    
    # 获取F&G
    print("下载 Crypto F&G 数据...")
    fng = get_fng_history()
    print(f"  F&G: {len(fng)} 天\n")
    
    for sym, name in symbols.items():
        print(f"\n{'='*50}")
        print(f"  {name} ({sym})")
        print(f"{'='*50}")
        
        print(f"  下载价格...")
        prices = get_yahoo(sym, t1, t2)
        if not prices:
            print(f"  ❌ 价格数据获取失败")
            continue
        print(f"  交易日: {len(prices)}")
        
        # VIX回测: VIX>30 = 极度恐慌
        # VIX>35 = 极端恐慌
        for vix_level, label in [(25, '偏高'), (30, '极度恐慌'), (35, '极端恐慌')]:
            stats = backtest(prices, vix_map, 'VIX', extreme_high=vix_level)
            if 'error' in stats:
                continue
            print(f"\n  📊 VIX > {vix_level} ({label}): {stats['extreme_count']}次")
            for hold in ['7d', '14d', '30d', '60d']:
                if hold in stats:
                    s = stats[hold]
                    print(f"     持有{hold[:-1]}天: 均{s['avg_return']:+.2f}% | "
                          f"中{s['median_return']:+.2f}% | "
                          f"胜率{s['win_rate']:.0f}% | "
                          f"({s['trades']}笔)")
        
        # F&G回测
        for fg_level, label in [(25, '恐慌'), (15, '极度恐慌'), (10, '极端恐慌')]:
            stats = backtest(prices, fng, 'F&G', extreme_low=fg_level)
            if 'error' in stats:
                continue
            print(f"\n  📊 F&G < {fg_level} ({label}): {stats['extreme_count']}次")
            for hold in ['7d', '14d', '30d', '60d']:
                if hold in stats:
                    s = stats[hold]
                    print(f"     持有{hold[:-1]}天: 均{s['avg_return']:+.2f}% | "
                          f"中{s['median_return']:+.2f}% | "
                          f"胜率{s['win_rate']:.0f}% | "
                          f"({s['trades']}笔)")
    
    print("\n\n═══════════════════════════════════════")
    print("  回测完成")
    print("═══════════════════════════════════════")
