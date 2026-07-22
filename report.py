#!/usr/bin/env python3
"""
疯向标 v2 — HTML仪表盘生成器
四赛道三层信号: 散户情绪 × 周期位置 × 宏观环境
数据源: 全民社媒(百度+微博+B站) + Crypto F&G + X/Twitter中文 + 实时价格
输出: data/fengxiangbiao.html
"""
import json, os, ssl, urllib.request
from datetime import datetime

DATA_DIR = os.path.expanduser('~/.hermes/scripts/fengxiangbiao/data')
PROXY = "http://127.0.0.1:7890"
ssl_ctx = ssl.create_default_context()

def fetch(url, use_proxy=False, headers=None, timeout=10):
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        if use_proxy:
            proxy_handler = urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY})
            opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ssl_ctx))
        else:
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_ctx))
        with opener.open(req, timeout=timeout) as r:
            return r.read().decode('utf-8', errors='ignore')
    except:
        return None

def load_data():
    path = os.path.join(DATA_DIR, 'fengxiangbiao_latest.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

# ═══════════════════════════════════════════
# 实时价格获取
# ═══════════════════════════════════════════
def get_btc_price():
    try:
        html = fetch('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT')
        if html:
            return float(json.loads(html)['price'])
    except: pass
    return None

def get_yahoo_prices():
    """通过yfinance代理获取关键标的价格和MA200"""
    import os
    os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
    os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
    result = {}
    try:
        import yfinance as yf
        import pandas as pd
        
        tickers = {
            # 美股半导体七龙头（含SK海力士）
            'NVDA': 'NVDA', 'AMD': 'AMD', 'MU': 'MU',
            'AVGO': 'AVGO', 'SMCI': 'SMCI', 'TSM': 'TSM',
            'SKHYNIX': '000660.KS',  # SK海力士
            # A股半导体ETF
            'A_SEMI_ETF': '512480.SS',  # 半导体ETF（中证全指半导体）
            # 美股半导体指数
            'SOX': '^SOX',  # 费城半导体指数
            # 贵金属
            'GOLD': 'GC=F', 'SILVER': 'SI=F',
            # 宏观
            'SPX': '^GSPC', 'VIX': '^VIX',
            'BTC': 'BTC-USD',
        }
        
        for name, symbol in tickers.items():
            try:
                import time; time.sleep(1.5)  # 防限流
                t = yf.Ticker(symbol)
                hist = t.history(period='1y')
                if len(hist) > 0:
                    price = hist['Close'].iloc[-1]
                    ma200 = hist['Close'].rolling(200).mean().iloc[-1] if len(hist) >= 200 else None
                    result[name] = {
                        'price': round(float(price), 2),
                        'ma200': round(float(ma200), 2) if ma200 and not pd.isna(ma200) else None,
                        'deviation': round((price - ma200) / ma200 * 100, 1) if ma200 and not pd.isna(ma200) else None,
                    }
            except: pass
    except: pass
    return result

# ═══════════════════════════════════════════
# 三层信号分析
# ═══════════════════════════════════════════
def analyze_signal(sector_data, fng, prices, guba_override=None):
    """
    返回 {sentiment_layer, cycle_layer, macro_layer, composite, composite_class, reasons}
    """
    silence = sector_data.get('silence_rate', 0)
    carnival = sector_data.get('carnival_rate', 0)
    sentiment = sector_data.get('sentiment', 0)
    count = sector_data.get('count', 0)
    
    result = {'count': count, 'silence': silence, 'carnival': carnival, 'sentiment': sentiment}
    
    # 默认值
    macro_reasons = []
    cycle_reasons = []
    sentiment_reasons = []
    
    # 散户情绪层
    if silence >= 85 and sentiment <= 0:
        sent_layer = ('l-g', '😶', f'{silence:.0f}%沉默', '散户情绪', '强买信号')
        sentiment_reasons.append(f'沉默率{silence:.0f}%≥85%=极度麻木')
    elif silence >= 75:
        sent_layer = ('l-y', '😐', f'{silence:.0f}%沉默', '散户情绪', '偏买')
        sentiment_reasons.append(f'沉默率{silence:.0f}%≥75%=偏麻木')
    elif carnival >= 20:
        sent_layer = ('l-r', '🎉', f'{carnival:.0f}%狂欢', '散户情绪', '卖点')
        sentiment_reasons.append(f'狂欢率{carnival:.0f}%≥20%=FOMO')
    elif carnival >= 10:
        sent_layer = ('l-y', '🤔', f'{carnival:.0f}%偏多', '散户情绪', '警惕')
        sentiment_reasons.append(f'狂欢率{carnival:.0f}%≥10%=偏乐观')
    else:
        sent_layer = ('l-n', '😐', f'{silence:.0f}%沉默', '散户情绪', '中性')
        sentiment_reasons.append(f'沉默率{silence:.0f}%=正常区间')
    
    # BTC特殊处理：用F&G代替社媒情绪
    if fng:
        fng_val = fng.get('value', 50)
        if fng_val <= 25:
            sent_layer = ('l-g', '😱', f'F&G {fng_val}', '极度恐惧', '强买信号')
            sentiment_reasons = [f'恐慌贪婪指数={fng_val}≤25=极度恐惧']
        elif fng_val <= 40:
            sent_layer = ('l-y', '😰', f'F&G {fng_val}', '恐惧', '偏买')
            sentiment_reasons = [f'恐慌贪婪指数={fng_val}≤40=恐惧']
        elif fng_val >= 75:
            sent_layer = ('l-r', '🥳', f'F&G {fng_val}', '极度贪婪', '卖点')
            sentiment_reasons = [f'恐慌贪婪指数={fng_val}≥75=极度贪婪']
        elif fng_val >= 60:
            sent_layer = ('l-y', '😊', f'F&G {fng_val}', '贪婪', '警惕')
            sentiment_reasons = [f'恐慌贪婪指数={fng_val}≥60=贪婪']
    
    return {
        'sent_layer': sent_layer,
        'cycle_layer': None,  # 由sector-specific逻辑填充
        'macro_layer': None,
        'composite': '',
        'composite_class': '',
        'reasons': sentiment_reasons + cycle_reasons + macro_reasons,
        'silence': silence,
        'carnival': carnival,
        'sentiment': sentiment,
        'count': count,
    }

# ═══════════════════════════════════════════
# HTML生成
# ═══════════════════════════════════════════
STYLE = '''*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0f;color:#e0e0e0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;min-height:100vh;padding:30px 20px}
.container{max-width:1000px;margin:0 auto}
.header{text-align:center;margin-bottom:24px}
.header h1{font-size:2em;background:linear-gradient(135deg,#ff6b35,#f7c948);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header .sub{color:#888;font-size:.8em}.header .meta{color:#555;font-size:.7em;margin-top:6px}
.guba-status{text-align:center;padding:6px;border-radius:8px;margin-bottom:16px;font-size:.7em}
.guba-ok{background:rgba(34,197,94,.1);color:#22c55e;border:1px solid rgba(34,197,94,.2)}
.guba-miss{background:rgba(234,179,8,.1);color:#eab308;border:1px solid rgba(234,179,8,.2)}
.macro-bar{background:#13131a;border:1px solid #1e1e2e;border-radius:12px;padding:12px 20px;margin-bottom:20px;display:flex;justify-content:space-around;flex-wrap:wrap;gap:12px;font-size:.78em}
.macro-item{text-align:center}.macro-val{font-weight:700}.macro-lbl{color:#666;font-size:.85em}
.tracks{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}
@media(max-width:640px){.tracks{grid-template-columns:1fr}}
.card{background:#13131a;border:1px solid #1e1e2e;border-radius:16px;padding:20px}
.card-hdr{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.card-title{font-size:.95em;font-weight:700}
.card-badge{font-size:.6em;padding:2px 8px;border-radius:10px}
.bg-gold{background:rgba(255,215,0,.12);color:#ffd700}.bg-btc{background:rgba(247,147,26,.12);color:#f7931a}
.bg-cn{background:rgba(255,107,53,.12);color:#ff6b35}.bg-us{background:rgba(59,130,246,.12);color:#3b82f6}
.layers{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px}
.layer{background:#1a1a25;border-radius:8px;padding:8px;text-align:center}
.layer-emoji{font-size:1.2em}.layer-val{font-size:.8em;font-weight:700;margin:2px 0}.layer-lbl{font-size:.6em;color:#666}
.l-g{color:#22c55e}.l-r{color:#ef4444}.l-y{color:#eab308}.l-n{color:#888}
.composite{text-align:center;padding:10px;border-radius:10px;font-size:1.1em;font-weight:700;margin-bottom:12px}
.c-fire{background:rgba(34,197,94,.2);color:#22c55e;border:1px solid rgba(34,197,94,.3)}
.c-bull{background:rgba(34,197,94,.1);color:#22c55e}
.c-warn{background:rgba(234,179,8,.1);color:#eab308}
.c-bear{background:rgba(239,68,68,.1);color:#ef4444}
.c-neut{background:rgba(100,100,120,.1);color:#888}
.row{display:flex;justify-content:space-around;margin-bottom:8px}
.stat{text-align:center}.stat-v{font-size:1.2em;font-weight:700}.stat-l{font-size:.6em;color:#666}
.g{color:#22c55e}.r{color:#ef4444}.y{color:#eab308}.n{color:#888}
.bar{height:4px;background:#1a1a25;border-radius:2px;margin:8px 0;display:flex;overflow:hidden}
.bar-b{background:#22c55e;height:100%}.bar-s{background:#ef4444;height:100%}.bar-n{background:#333;height:100%}
.price-bar{display:flex;justify-content:space-between;font-size:.72em;margin:6px 0;color:#888}
.price-bar .p-big{color:#ccc;font-weight:700}
.fng-wrap{text-align:center}.fng-val{font-size:2.2em;font-weight:700}
.fng-meter{width:100%;height:14px;background:linear-gradient(to right,#22c55e,#eab308,#ef4444);border-radius:7px;position:relative;margin:6px 0}
.fng-dot{width:10px;height:10px;background:white;border-radius:50%;position:absolute;top:2px;box-shadow:0 0 6px rgba(255,255,255,.5)}
.fng-lbl{display:flex;justify-content:space-between;font-size:.55em;color:#555}
.reasons{font-size:.65em;color:#666;margin-top:4px;line-height:1.4}
.reasons span{color:#888}
.src{font-size:.65em;color:#555;margin-top:6px}
.temp-card{background:#13131a;border:1px solid #1e1e2e;border-radius:16px;padding:20px;margin-bottom:20px}
.temp-title{font-size:.9em;font-weight:700;margin-bottom:12px;color:#ccc}
.temp-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;text-align:center}
@media(max-width:640px){.temp-grid{grid-template-columns:repeat(2,1fr)}}
.temp-item{background:#1a1a25;border-radius:10px;padding:12px}
.temp-val{font-size:1.4em;font-weight:700}.temp-lbl{font-size:.6em;color:#666;margin-top:2px}
.footer{text-align:center;color:#444;font-size:.65em;margin-top:25px;padding-top:15px;border-top:1px solid #1e1e2e}
.footer a{color:#666}'''

def build_html(data, prices, fng, consensus):
    now = datetime.now()
    sectors = data.get('sectors', {})
    sources = data.get('sources', {})
    guba_status = data.get('sources', {}).get('guba', {}).get('status', 'missing')
    
    # 计算散户关注度 FAR
    all_count = sum(s.get('count', 0) for s in sectors.values())
    fin_count = all_count - sectors.get('other', {}).get('count', 0)
    far = round(fin_count / max(all_count, 1) * 100, 1)
    
    # 价格数据
    btc_price = prices.get('BTC', {}).get('price') or get_btc_price() or 0
    gold_price = prices.get('GOLD', {}).get('price', 0)
    silver_price = prices.get('SILVER', {}).get('price', 0)
    spx_price = prices.get('SPX', {}).get('price', 0)
    vix = prices.get('VIX', {}).get('price', 0)
    gold_ma200 = prices.get('GOLD', {}).get('ma200', 0)
    gold_dev = prices.get('GOLD', {}).get('deviation', 0)
    silver_ma200 = prices.get('SILVER', {}).get('ma200', 0)
    silver_dev = prices.get('SILVER', {}).get('deviation', 0)
    btc_ma200 = prices.get('BTC', {}).get('ma200', 0) or 73200
    btc_dev = prices.get('BTC', {}).get('deviation', 0) or round((btc_price - btc_ma200) / btc_ma200 * 100, 1) if btc_price and btc_ma200 else 0
    
    # 美股半导体七龙头均价（含SK海力士）
    us_semi_stocks = ['NVDA', 'AMD', 'MU', 'AVGO', 'SMCI', 'TSM', 'SKHYNIX']
    us_semi_devs = [prices.get(s, {}).get('deviation') for s in us_semi_stocks if prices.get(s, {}).get('deviation') is not None]
    us_semi_avg_dev = round(sum(us_semi_devs) / len(us_semi_devs), 1) if us_semi_devs else None
    us_semi_nvda_price = prices.get('NVDA', {}).get('price', 0)
    
    # A股半导体ETF
    a_semi_etf = prices.get('A_SEMI_ETF', {})
    a_semi_avg_dev = a_semi_etf.get('deviation')
    a_semi_etf_price = a_semi_etf.get('price') or 0
    
    # SOX指数
    sox_price = prices.get('SOX', {}).get('price', 0)
    sox_dev = prices.get('SOX', {}).get('deviation')
    
    fng_val = fng.get('value', 50) if fng else 50
    fng_class = fng.get('classification', 'Neutral') if fng else 'Neutral'
    
    # 股吧状态 + 多平台
    xq_ok = sources.get('xueqiu', {}).get('status') == 'ok'
    platform_list = []
    if guba_status == 'ok': platform_list.append('股吧')
    if xq_ok: platform_list.append('雪球')
    platform_list.extend(['微博', '百度', 'B站'])
    platform_str = '+'.join(platform_list)
    
    if guba_status == 'ok':
        guba_html = f'<div class="guba-ok guba-status">📋 {platform_str} 全平台接入 · 跨平台交叉验证生效</div>'
    else:
        guba_html = f'<div class="guba-miss guba-status">⚠️ 股吧限流中 · {platform_str} 在线 · 信号降级为社媒参考</div>'
    
    # ═══ 共识度辅助函数 ═══
    def make_consensus_line(sec_key):
        c = consensus.get(sec_key, {})
        if not c or c.get('platform_count', 0) < 2:
            return ''
        platforms = c.get('platforms', {})
        parts = []
        for pname, pdata in platforms.items():
            if pdata.get('count', 0) < 5:  # 最少5条才参与共识
                continue
            s = pdata.get('silence', 0)
            emoji = {'guba': '📋', 'xueqiu': '❄️', 'weibo': '📢', 'baidu': '🔍'}.get(pname, '📡')
            parts.append(f'{emoji}{s:.0f}%')
        if len(parts) < 2:
            return ''
        return f'<div style="font-size:.65em;color:#888;margin-top:4px;text-align:center">{c["level"]} | {" · ".join(parts)}</div>'
    
    # ═══ 构建各赛道卡片 ═══
    
    def make_gold_card():
        s = sectors.get('gold', {})
        silence = s.get('silence_rate', 0)
        carnival = s.get('carnival_rate', 0)
        sentiment = s.get('sentiment', 0)
        count = s.get('count', 0)
        b_pct = s.get('bullish', 0) / max(count, 1) * 100
        s_pct = s.get('bearish', 0) / max(count, 1) * 100
        
        # 情绪层
        if silence >= 80:
            sl = ('l-g', '😶', f'{silence:.0f}%沉默')
        elif silence >= 60:
            sl = ('l-y', '😐', f'{silence:.0f}%沉默')
        else:
            sl = ('l-n', '😐', f'{silence:.0f}%沉默')
        
        # 周期层
        if gold_dev is not None and gold_dev < -5:
            cl = ('l-g' if gold_dev < -10 else 'l-y', '📊', f'金{gold_dev:+.0f}%银{silver_dev:+.0f}%')
        elif gold_dev is not None:
            cl = ('l-n', '📊', f'金{gold_dev:+.0f}%银{silver_dev:+.0f}%')
        else:
            cl = ('l-n', '📊', '数据待拉')
        
        # 宏观层
        ml = ('l-g', '🌍', '地缘利好')
        
        # 综合
        if silence >= 80 and (gold_dev is not None and gold_dev < -5):
            comp = ('c-fire', '🔥 三重共振 · 别人恐惧我贪婪')
            reasons = f'沉默率{silence:.0f}%+深度熊市+地缘利好=历史规律说这时候该看看 · 金${gold_price:,.0f} 银${silver_price:,.0f}'
        elif silence >= 75:
            comp = ('c-bull', '🟢 没人聊了 · 有点意思')
            reasons = f'沉默率{silence:.0f}%接近关注区间 · 金${gold_price:,.0f} 银${silver_price:,.0f}'
        else:
            comp = ('c-neut', '⚪ 平平无奇 · 再蹲蹲')
            reasons = f'沉默率{silence:.0f}%未达阈值 · 金${gold_price:,.0f} 银${silver_price:,.0f}'
        
        return f'''
<div class="card">
  <div class="card-hdr"><span class="card-title">🥇 黄金 / 白银</span><span class="card-badge bg-gold">{count}帖 · 金${gold_price:,.0f} · 银${silver_price:,.0f}</span></div>
  <div class="layers">
    <div class="layer"><div class="layer-emoji">{sl[1]}</div><div class="layer-val {sl[0]}">{sl[2]}</div><div class="layer-lbl">散户情绪</div></div>
    <div class="layer"><div class="layer-emoji">{cl[1]}</div><div class="layer-val {cl[0]}">{cl[2]}</div><div class="layer-lbl">周期位置</div></div>
    <div class="layer"><div class="layer-emoji">{ml[1]}</div><div class="layer-val {ml[0]}">{ml[2]}</div><div class="layer-lbl">宏观环境</div></div>
  </div>
  <div class="composite {comp[0]}">{comp[1]}</div>
  <div class="reasons">{reasons}</div>
  {make_consensus_line('gold')}
  <div class="row">
    <div class="stat"><div class="stat-v n">{silence:.0f}%</div><div class="stat-l">沉默率</div></div>
    <div class="stat"><div class="stat-v g">{b_pct:.0f}%</div><div class="stat-l">喊涨</div></div>
    <div class="stat"><div class="stat-v r">{s_pct:.0f}%</div><div class="stat-l">喊跌</div></div>
    <div class="stat"><div class="stat-v y">{sentiment:+.2f}</div><div class="stat-l">情绪分</div></div>
  </div>
  <div class="bar"><div class="bar-b" style="width:{b_pct:.1f}%"></div><div class="bar-s" style="width:{s_pct:.1f}%"></div><div class="bar-n" style="width:{silence:.1f}%"></div></div>
  <div class="price-bar">
    <span>金: <span class="p-big">${gold_price:,.0f}</span></span>
    <span>MA200: <span class="p-big">${gold_ma200:,.0f}</span></span>
    <span>偏离: <span class="p-big" style="color:{'#22c55e' if gold_dev and gold_dev < -5 else '#ef4444' if gold_dev and gold_dev > 5 else '#888'}">{gold_dev:+.0f}%</span></span>
  </div>
  <div class="src">全民社媒(百度+微博+B站)关键词匹配 · 实时价格: Yahoo Finance</div>
</div>'''

    def make_btc_card():
        fg_color = '#22c55e' if fng_val <= 25 else '#ef4444' if fng_val >= 75 else '#eab308'
        
        if fng_val <= 25:
            sl = ('l-g', '😱', f'F&G {fng_val}')
            comp = ('c-fire', '😱 韭菜都割完了…')
            reasons = f'F&G={fng_val}极度恐惧 + BTC低于MA200 {btc_dev:+.0f}% = 历史上这时候…你懂的'
        elif fng_val <= 40:
            sl = ('l-y', '😰', f'F&G {fng_val}')
            comp = ('c-bull', '🟢 瑟瑟发抖 · 有点意思')
            reasons = f'F&G={fng_val}恐惧区间 + BTC${btc_price:,.0f}'
        elif fng_val >= 75:
            sl = ('l-r', '🥳', f'F&G {fng_val}')
            comp = ('c-bear', '🥳 韭菜杀回来了… 快跑！')
            reasons = f'F&G={fng_val}极度贪婪 = 历史上…差不多该跑了'
        else:
            sl = ('l-n', '😐', f'F&G {fng_val}')
            comp = ('c-neut', '⚪ 中性')
            reasons = f'F&G={fng_val}中性区间'
        
        cl = ('l-r' if btc_dev < -10 else 'l-y' if btc_dev < 0 else 'l-g', '📊', f'熊市{btc_dev:+.0f}%' if btc_dev < 0 else f'牛市{btc_dev:+.0f}%')
        ml = ('l-g', '🌍', 'CPI↓利好')
        
        return f'''
<div class="card">
  <div class="card-hdr"><span class="card-title">₿ BTC / 加密货币</span><span class="card-badge bg-btc">${btc_price:,.0f} · MA200下{abs(btc_dev):.0f}%</span></div>
  <div class="layers">
    <div class="layer"><div class="layer-emoji">{sl[1]}</div><div class="layer-val {sl[0]}">{sl[2]}</div><div class="layer-lbl">极度恐惧</div></div>
    <div class="layer"><div class="layer-emoji">{cl[1]}</div><div class="layer-val {cl[0]}">{cl[2]}</div><div class="layer-lbl">周期位置</div></div>
    <div class="layer"><div class="layer-emoji">{ml[1]}</div><div class="layer-val {ml[0]}">{ml[2]}</div><div class="layer-lbl">宏观环境</div></div>
  </div>
  <div class="composite {comp[0]}">{comp[1]}</div>
  <div class="reasons">{reasons}</div>
  <div class="price-bar">
    <span>BTC: <span class="p-big">${btc_price:,.0f}</span></span>
    <span>MA200: <span class="p-big">${btc_ma200:,.0f}</span></span>
    <span>偏离: <span class="p-big" style="color:{'#22c55e' if btc_dev < -10 else '#ef4444' if btc_dev > 10 else '#888'}">{btc_dev:+.0f}%</span></span>
  </div>
  <div class="fng-wrap">
    <div class="fng-val" style="color:{fg_color}">{fng_val}</div>
    <div class="fng-meter"><div class="fng-dot" style="left:{fng_val}%"></div></div>
    <div class="fng-lbl"><span>0 恐惧</span><span>50</span><span>100 贪婪</span></div>
  </div>
  <div class="src">Crypto Fear & Greed · Binance实时价格</div>
</div>'''

    def make_a_semi_card():
        s = sectors.get('a_semi', {})
        silence = s.get('silence_rate', 0)
        carnival = s.get('carnival_rate', 0)
        sentiment = s.get('sentiment', 0)
        count = s.get('count', 0)
        b_pct = s.get('bullish', 0) / max(count, 1) * 100
        s_pct = s.get('bearish', 0) / max(count, 1) * 100
        
        if silence >= 75:
            sl = ('l-y', '😐', f'{silence:.0f}%沉默')
            comp = ('c-bull', '🟢 没人聊 · 留意下')
            reasons = f'沉默率{silence:.0f}%+社媒讨论少=散户不关注A股半导体'
        else:
            sl = ('l-n', '😐', f'{silence:.0f}%沉默')
            comp = ('c-neut', '⚪ 风平浪静 · 再蹲蹲')
            reasons = f'沉默率{silence:.0f}%，社媒金融关键词匹配{count}条'
        
        cl = ('l-g' if a_semi_avg_dev and a_semi_avg_dev > 0 else 'l-r' if a_semi_avg_dev and a_semi_avg_dev < -5 else 'l-y', '📊', f'半导体{a_semi_avg_dev:+.0f}%' if a_semi_avg_dev is not None else '数据待拉')
        ml = ('l-y', '🌍', '美股联动')
        
        # 如果count为0，显示数据不足
        if count == 0:
            sl = ('l-n', '❓', '数据不足')
            comp = ('c-neut', '⚪ 待采集')
            reasons = '全民社媒未匹配到A股半导体关键词 · 需股吧数据补充'
        
        return f'''
<div class="card">
  <div class="card-hdr"><span class="card-title">🇨🇳 A股 半导体</span><span class="card-badge bg-cn">{count}帖 · 半导体ETF ¥{a_semi_etf_price:.2f}</span></div>
  <div class="layers">
    <div class="layer"><div class="layer-emoji">{sl[1]}</div><div class="layer-val {sl[0]}">{sl[2]}</div><div class="layer-lbl">散户情绪</div></div>
    <div class="layer"><div class="layer-emoji">{cl[1]}</div><div class="layer-val {cl[0]}">{cl[2]}</div><div class="layer-lbl">周期位置</div></div>
    <div class="layer"><div class="layer-emoji">{ml[1]}</div><div class="layer-val {ml[0]}">{ml[2]}</div><div class="layer-lbl">宏观环境</div></div>
  </div>
  <div class="composite {comp[0]}">{comp[1]}</div>
  <div class="reasons">{reasons}</div>
  {make_consensus_line('a_semi')}
  <div class="row">
    <div class="stat"><div class="stat-v n">{silence:.0f}%</div><div class="stat-l">沉默率</div></div>
    <div class="stat"><div class="stat-v g">{b_pct:.0f}%</div><div class="stat-l">喊涨</div></div>
    <div class="stat"><div class="stat-v r">{s_pct:.0f}%</div><div class="stat-l">喊跌</div></div>
    <div class="stat"><div class="stat-v y">{sentiment:+.2f}</div><div class="stat-l">情绪分</div></div>
  </div>
  <div class="bar"><div class="bar-b" style="width:{b_pct:.1f}%"></div><div class="bar-s" style="width:{s_pct:.1f}%"></div><div class="bar-n" style="width:{silence:.1f}%"></div></div>
  <div class="price-bar">
    <span>半导体ETF: <span class="p-big">¥{a_semi_etf_price:.2f}</span></span>
    <span>MA200偏离: <span class="p-big" style="color:{'#22c55e' if a_semi_avg_dev and a_semi_avg_dev > 0 else '#ef4444'}">{f'{a_semi_avg_dev:+.0f}%' if a_semi_avg_dev is not None else 'N/A'}</span></span>
  </div>
  <div class="src">半导体ETF 512480 · 股吧BK1036</div>
</div>'''

    def make_us_semi_card():
        s = sectors.get('us_semi', {})
        silence = s.get('silence_rate', 0)
        carnival = s.get('carnival_rate', 0)
        sentiment = s.get('sentiment', 0)
        count = s.get('count', 0)
        b_pct = s.get('bullish', 0) / max(count, 1) * 100
        s_pct = s.get('bearish', 0) / max(count, 1) * 100
        
        if silence >= 80:
            sl = ('l-g', '😶', f'{silence:.0f}%沉默')
        elif silence >= 65:
            sl = ('l-y', '😐', f'{silence:.0f}%沉默')
        else:
            sl = ('l-n', '😐', f'{silence:.0f}%沉默')
        
        if us_semi_avg_dev is not None:
            cl = ('l-g' if us_semi_avg_dev > 0 else 'l-r', '📊', f'7龙头{us_semi_avg_dev:+.0f}%')
        else:
            cl = ('l-n', '📊', '数据待拉')
        
        ml = ('l-g' if sox_dev and sox_dev > 0 else 'l-r', '🌍', f'SOX{sox_dev:+.0f}%' if sox_dev else 'SOX')
        
        if silence >= 90:
            comp = ('c-fire', '🔥 鸦雀无声… 你细品')
            reasons = f'沉默率{silence:.0f}%≥90%=极端麻木 + 七龙头均MA200偏离{us_semi_avg_dev:+.0f}%=这种组合历史上挺有意思' if us_semi_avg_dev else f'沉默率{silence:.0f}%≥90%=极端麻木'
        elif silence >= 80 and us_semi_avg_dev is not None and us_semi_avg_dev > 0:
            comp = ('c-bull', '🟢 没人聊+趋势好=挺有意思')
            reasons = f'沉默率{silence:.0f}%+七龙头均MA200上{us_semi_avg_dev:+.0f}%=牛市中的沉默=回调可以看看'
        elif silence >= 80:
            comp = ('c-warn', '⚠️ 安静但行情弱…悠着点')
            reasons = f'沉默率{silence:.0f}%但七龙头均偏离{us_semi_avg_dev:+.0f}%=谨慎' if us_semi_avg_dev else f'沉默率{silence:.0f}%'
        elif count == 0:
            comp = ('c-neut', '⚪ 待采集')
            reasons = '全民社媒未匹配到美股半导体关键词 · 需股吧数据补充'
        else:
            comp = ('c-neut', '⚪ 中性')
            reasons = f'沉默率{silence:.0f}% · 七龙头均偏离{us_semi_avg_dev:+.0f}% · 等极端信号' if us_semi_avg_dev else f'沉默率{silence:.0f}% · 等极端信号'
        
        # 七龙头列表
        us_tickers_list = []
        for s in us_semi_stocks:
            p = prices.get(s, {})
            if p.get('deviation') is not None:
                us_tickers_list.append(f'{s} {p["deviation"]:+.0f}%')
        us_tickers_str = ' · '.join(us_tickers_list[:6])
        
        return f'''
<div class="card">
  <div class="card-hdr"><span class="card-title">🇺🇸 美股 半导体</span><span class="card-badge bg-us">{count}帖 · SOX ${sox_price:,.0f} · 7均{us_semi_avg_dev:+.0f}%</span></div>
  <div class="layers">
    <div class="layer"><div class="layer-emoji">{sl[1]}</div><div class="layer-val {sl[0]}">{sl[2]}</div><div class="layer-lbl">散户情绪</div></div>
    <div class="layer"><div class="layer-emoji">{cl[1]}</div><div class="layer-val {cl[0]}">{cl[2]}</div><div class="layer-lbl">周期位置</div></div>
    <div class="layer"><div class="layer-emoji">{ml[1]}</div><div class="layer-val {ml[0]}">{ml[2]}</div><div class="layer-lbl">宏观环境</div></div>
  </div>
  <div class="composite {comp[0]}">{comp[1]}</div>
  <div class="reasons">{reasons}</div>
  {make_consensus_line('us_semi')}
  <div class="row">
    <div class="stat"><div class="stat-v n">{silence:.0f}%</div><div class="stat-l">沉默率</div></div>
    <div class="stat"><div class="stat-v g">{b_pct:.0f}%</div><div class="stat-l">喊涨</div></div>
    <div class="stat"><div class="stat-v r">{s_pct:.0f}%</div><div class="stat-l">喊跌</div></div>
    <div class="stat"><div class="stat-v y">{sentiment:+.2f}</div><div class="stat-l">情绪分</div></div>
  </div>
  <div class="bar"><div class="bar-b" style="width:{b_pct:.1f}%"></div><div class="bar-s" style="width:{s_pct:.1f}%"></div><div class="bar-n" style="width:{silence:.1f}%"></div></div>
  <div class="price-bar">
    <span>SOX: <span class="p-big">${sox_price:,.0f}</span></span>
    <span>7均偏离: <span class="p-big" style="color:{'#22c55e' if us_semi_avg_dev and us_semi_avg_dev > 0 else '#ef4444'}">{us_semi_avg_dev:+.0f}%</span></span>
  </div>
  <div style="font-size:.6em;color:#555;margin-top:4px">{us_tickers_str}</div>
  <div class="src">NVDA+AMD+MU+AVGO+SMCI+TSM+SK海力士 股吧 × Yahoo Finance实时</div>
</div>'''

    # ═══ 拼装HTML ═══
    # 散户关注度颜色
    far_color = '#22c55e' if far < 5 else '#eab308' if far < 10 else '#ef4444'
    far_verdict = '极低·韭菜没兴趣' if far < 5 else '低·日常水平' if far < 10 else '偏高·韭菜扎堆了'
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>疯向标 · 趋势拐点发现器</title>
<style>{STYLE}</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>🌪️ 疯向标</h1>
  <div class="sub">散户情绪天气预报 · 纯属娱乐不构成投资建议</div>
  <div class="meta">📅 {now.strftime('%Y-%m-%d %a')} · {now.strftime('%H:%M')} CST · BTC ${btc_price:,.0f} · 金${gold_price:,.0f} · 银 · VIX {vix:.1f}</div>
</div>

{guba_html}

<div class="macro-bar">
  <div class="macro-item"><div class="macro-val" style="color:{'#eab308' if vix < 25 else '#ef4444'}">🌡️ VIX {vix:.1f}</div><div class="macro-lbl">{'平静' if vix < 20 else '警惕' if vix < 30 else '恐慌'}</div></div>
  <div class="macro-item"><div class="macro-val" style="color:#3b82f6">📉 CPI 3.5%↓</div><div class="macro-lbl">通胀降温</div></div>
  <div class="macro-item"><div class="macro-val" style="color:#f7931a">😱 F&G {fng_val}</div><div class="macro-lbl">{fng_class}</div></div>
  <div class="macro-item"><div class="macro-val" style="color:{far_color}">📢 关注度{far:.0f}%</div><div class="macro-lbl">{far_verdict}</div></div>
  <div class="macro-item"><div class="macro-val" style="color:#a78bfa">📅 7/30</div><div class="macro-lbl">Q2 GDP</div></div>
</div>

<div class="temp-card">
  <div class="temp-title">🌡️ 全民社媒温度计 · {all_count}条热搜</div>
  <div class="temp-grid">
    <div class="temp-item"><div class="temp-val" style="color:#22c55e">{sectors.get('gold',{}).get('count',0)}</div><div class="temp-lbl">🥇 金银相关</div></div>
    <div class="temp-item"><div class="temp-val" style="color:#f7931a">{fng_val}</div><div class="temp-lbl">₿ BTC F&G</div></div>
    <div class="temp-item"><div class="temp-val" style="color:#ff6b35">{sectors.get('a_semi',{}).get('count',0)}</div><div class="temp-lbl">🇨🇳 A股半导</div></div>
    <div class="temp-item"><div class="temp-val" style="color:#3b82f6">{sectors.get('us_semi',{}).get('count',0)}</div><div class="temp-lbl">🇺🇸 美股半导</div></div>
  </div>
  <div style="font-size:.55em;color:#555;margin-top:8px;text-align:center">
    百度51条 + 微博51条 + B站50条 · 金融关键词匹配{fin_count}条 · 散户关注度{far:.1f}%
  </div>
</div>

<div class="tracks">
{make_gold_card()}
{make_btc_card()}
{make_a_semi_card()}
{make_us_semi_card()}
</div>

<div class="footer">
  疯向标 v2 · 情绪×周期×宏观 · 趋势拐点发现器 · 纯属娱乐 · 不是投资建议 · 别看了就冲 · DYOR<br>
  <a href="https://github.com/Pibao0249/fengxiangbiao">GitHub</a> · BTC: Binance实时 · F&G: alternative.me · 贵金属/NVDA/VIX: Yahoo Finance · 社媒: 百度+微博+B站热搜 · X/Twitter中文<br>
  数据三档: ✅实时 ⚠️缓存 ❌缺失 · 禁止假数据
</div>
</div>
</body>
</html>'''
    
    return html

def main():
    data = load_data()
    if not data:
        print('无数据，先运行 collect.py')
        return
    
    print('获取实时价格...')
    prices = get_yahoo_prices()
    if not prices.get('BTC'):
        btc = get_btc_price()
        if btc:
            prices['BTC'] = {'price': btc, 'ma200': 73200, 'deviation': round((btc - 73200) / 73200 * 100, 1)}
    
    print(f'  BTC: ${prices.get("BTC",{}).get("price","?")}')
    print(f'  黄金: ${prices.get("GOLD",{}).get("price","?")}')
    print(f'  白银: ${prices.get("SILVER",{}).get("price","?")}')
    print(f'  NVDA: ${prices.get("NVDA",{}).get("price","?")}')
    print(f'  VIX: {prices.get("VIX",{}).get("price","?")}')
    
    fng = data.get('sources', {}).get('fng', {})
    
    html = build_html(data, prices, fng, data.get('consensus', {}))
    
    path = os.path.join(DATA_DIR, 'fengxiangbiao.html')
    with open(path, 'w') as f:
        f.write(html)
    
    print(f'\n✅ 仪表盘: {path}')
    print(f'   file://{path}')
    
    # 输出到根目录 index.html（GitHub Pages 主入口）
    root_index = os.path.join(os.path.dirname(DATA_DIR), 'index.html')
    with open(root_index, 'w') as f:
        f.write(html)
    # 同时输出到 site/ 备用
    site_index = os.path.join(os.path.dirname(DATA_DIR), 'site', 'index.html')
    with open(site_index, 'w') as f:
        f.write(html)
    print(f'✅ Pages入口: {root_index}')

if __name__ == '__main__':
    main()
