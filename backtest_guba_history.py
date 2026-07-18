#!/usr/bin/env python3
"""
疯向标回测 v3: 股吧历史情绪 → AI/存储美股
用已采集的股吧2年周情绪数据，回测情绪极端 vs 后续股价
"""
import json, sys
from datetime import date, datetime, timedelta
from collections import defaultdict

# ═══════ 加载数据 ═══════
HISTORY_FILE = '/Users/ryan/.hermes/scripts/fengxiangbiao/data/guba_history_2y.json'
with open(HISTORY_FILE) as f:
    history = json.load(f)

weeks = history['weeks']
print(f'加载 {len(weeks)} 周 × ~{history["total_posts"]//max(len(weeks),1)}条/周')
print(f'时间范围: {weeks[-1]["earliest"][:10]} ~ {weeks[0]["latest"][:10]}')

# ═══════ 加载美股价格 ═══════
def load_yahoo(path):
    with open(path) as f:
        data = json.load(f)
    result = data['chart']['result'][0]
    ts = result['timestamp']
    q = result['indicators']['quote'][0]
    rows = {}
    for i, t in enumerate(ts):
        c = q['close'][i]
        if c is not None:
            rows[date.fromtimestamp(t)] = c
    return rows

stocks = {}
for sym, name in [('NVDA','英伟达'),('MU','美光存储'),('SMH','SOX半导体')]:
    stocks[sym] = {'name': name, 'prices': load_yahoo(f'/tmp/{sym}_data.json')}

# ═══════ 回测 ═══════
def backtest_sentiment(weeks, prices, percentiles=[80, 90, 95]):
    """情绪极端百分位 → 后续N天收益"""
    price_list = sorted(prices.items())
    date_to_idx = {d: i for i, (d, _) in enumerate(price_list)}
    
    # 计算情绪分分布
    scores = [w['sentiment_score'] for w in weeks]
    
    results = {}
    for pct in percentiles:
        # 双向极端: 看多极端和看空极端
        bullish_cutoff = sorted(scores)[int(len(scores) * pct / 100)]
        bearish_cutoff = sorted(scores)[int(len(scores) * (100 - pct) / 100)]
        
        # 找极端周
        extreme_weeks = []
        for w in weeks:
            if w['sentiment_score'] >= bullish_cutoff:
                extreme_weeks.append({**w, 'type': 'bullish_extreme'})
            elif w['sentiment_score'] <= bearish_cutoff:
                extreme_weeks.append({**w, 'type': 'bearish_extreme'})
        
        if len(extreme_weeks) < 5:
            continue
        
        # 计算持有收益
        hold_results = {7:[], 14:[], 30:[], 60:[]}
        for ew in extreme_weeks:
            # 取该周最后一天的日期
            try:
                week_date = date.fromisoformat(ew['latest'][:10])
            except:
                continue
            
            # 找之后第一个美股交易日
            for offset in range(7):
                check = week_date + timedelta(days=offset)
                if check in date_to_idx:
                    entry_idx = date_to_idx[check]
                    entry_price = price_list[entry_idx][1]
                    break
            else:
                continue
            
            for hold in [7,14,30,60]:
                exit_idx = entry_idx + hold
                if exit_idx >= len(price_list):
                    continue
                ret = (price_list[exit_idx][1] - entry_price) / entry_price * 100
                hold_results[hold].append(ret)
        
        stats = {'pctile': pct, 'bullish_cutoff': round(bullish_cutoff, 2), 
                 'bearish_cutoff': round(bearish_cutoff, 2),
                 'total_extreme_weeks': len(extreme_weeks)}
        
        for hold, returns in hold_results.items():
            if returns:
                avg = sum(returns)/len(returns)
                median = sorted(returns)[len(returns)//2]
                win = sum(1 for r in returns if r > 0) / len(returns) * 100
                stats[hold] = {
                    'avg': round(avg, 2), 'median': round(median, 2),
                    'win_rate': round(win, 1), 'count': len(returns),
                }
        
        results[pct] = stats
    
    return results

# ═══════ 执行 ═══════
print('\n' + '='*60)
print('  回测: 股吧历史情绪 → AI/存储股')
print('  逻辑: 情绪极端(高/低百分位) → 后续是否反转')
print('='*60)

for sym, info in stocks.items():
    print(f'\n── {info["name"]} ({sym}) ──')
    r = backtest_sentiment(weeks, info['prices'])
    
    for pct in sorted(r.keys()):
        s = r[pct]
        print(f'  📊 极端{pct}分位 (多>{s["bullish_cutoff"]:+.1f} / 空<{s["bearish_cutoff"]:+.1f}): {s["total_extreme_weeks"]}周触发')
        for h in [7,14,30,60]:
            if h in s:
                d = s[h]
                print(f'      持有{h}d: 均{d["avg"]:+.2f}% | 中{d["median"]:+.2f}% | 胜率{d["win_rate"]:.0f}% | {d["count"]}笔')

# ═══════ 展示极端情绪周详情 ═══════
print('\n' + '='*60)
print('  情绪最极端的10周')
print('='*60)
sorted_weeks = sorted(weeks, key=lambda w: abs(w['sentiment_score']), reverse=True)
for w in sorted_weeks[:10]:
    emoji = '🟢' if w['sentiment_score'] > 0 else '🔴'
    print(f'\n  {emoji} {w["latest"][:10]} | 情绪分{w["sentiment_score"]:+.2f} | 多{w["bullish"]}/空{w["bearish"]}')
    if w['top_bullish']:
        print(f'      看多: {w["top_bullish"][0][:60]}')
    if w['top_bearish']:
        print(f'      看空: {w["top_bearish"][0][:60]}')

print('\n═══ 完成 ═══')
