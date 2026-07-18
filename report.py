#!/usr/bin/env python3
"""
疯向标 v1 — HTML 仪表盘生成器
输出: data/fengxiangbiao.html (单文件, 手机可用)
"""
import json, os
from datetime import datetime

DATA_DIR = os.path.expanduser('~/.hermes/scripts/fengxiangbiao/data')

def load_latest():
    path = os.path.join(DATA_DIR, 'fengxiangbiao_latest.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    # try today's
    today = datetime.now().strftime('%Y%m%d')
    path = os.path.join(DATA_DIR, f'fengxiangbiao_daily_{today}.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def build_html(data):
    baidu = data.get('baidu', {})
    wscn = data.get('wallstreetcn', {})
    guba = data.get('guba', {})
    fng = data.get('fng', {})
    
    # 提取各赛道情绪
    tracks = baidu.get('tracks', {})
    
    xueqiu = data.get('xueqiu', {})
    
    # 雪球信号 (替代股吧, 阈值更低因为雪球用户更理性)
    if xueqiu:
        silence = xueqiu.get('silence_rate', 0)
        carnival = xueqiu.get('carnival_rate', 0)
        xsent = xueqiu.get('sentiment', 0)
        posts = xueqiu.get('posts', [])
    else:
        silence = 0
        carnival = 0
        xsent = 0
        posts = []
    
    # 信号判断 (雪球阈值: 沉默>75%, 狂欢>15%)
    if silence >= 75 and xsent < 0:
        signal = ('🟢 买点', '#22c55e', f'雪球沉默{silence:.0f}%+偏空 → 底部')
    elif carnival >= 15:
        signal = ('🔴 卖点', '#ef4444', f'雪球狂欢{carnival:.0f}% → 见顶')
    elif silence >= 75:
        signal = ('🟡 观望', '#eab308', f'雪球沉默{silence:.0f}%')
    elif carnival >= 10:
        signal = ('🟠 警惕', '#f97316', f'雪球偏多{carnival:.0f}%')
    else:
        signal = ('⚪ 中性', '#9ca3af', '无明显极端')
    
    # F&G
    fg_val = fng.get('value', 50)
    fg_class = fng.get('classification', 'Neutral')
    if fg_val <= 25: fg_color = '#22c55e'
    elif fg_val >= 75: fg_color = '#ef4444'
    else: fg_color = '#eab308'
    
    # 华尔街情绪
    wscn_sentiments = {}
    for k, v in wscn.items():
        wscn_sentiments[k] = v.get('sentiment', 0)
    
    # 最近极端帖子
    posts = xueqiu.get('posts', []) if xueqiu else []
    extreme_posts = sorted(posts, key=lambda p: abs(p.get('sentiment', 0)), reverse=True)[:8]
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>疯向标 — 中文散户情绪仪表盘</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0f172a; color:#e2e8f0; font-family: -apple-system, "PingFang SC", sans-serif; padding:16px; max-width:480px; margin:0 auto; }}
.header {{ text-align:center; padding:20px 0; }}
.header h1 {{ font-size:28px; background:linear-gradient(135deg,#22c55e,#3b82f6); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
.header .time {{ color:#64748b; font-size:13px; margin-top:4px; }}
.signal {{ background:#1e293b; border-radius:16px; padding:20px; margin:16px 0; text-align:center; border:2px solid {signal[1]}; }}
.signal .emoji {{ font-size:48px; }}
.signal .label {{ font-size:22px; font-weight:700; margin:8px 0; }}
.signal .hint {{ color:#94a3b8; font-size:14px; }}

.row {{ display:flex; gap:12px; margin:12px 0; }}
.card {{ flex:1; background:#1e293b; border-radius:12px; padding:16px; text-align:center; }}
.card .title {{ font-size:13px; color:#64748b; margin-bottom:8px; }}
.card .value {{ font-size:24px; font-weight:700; }}
.card .sub {{ font-size:12px; color:#94a3b8; margin-top:4px; }}

.gauge {{ background:#1e293b; border-radius:12px; padding:16px; margin:12px 0; }}
.gauge .bar-track {{ height:8px; background:#334155; border-radius:4px; margin:8px 0; position:relative; }}
.gauge .bar-fill {{ height:8px; border-radius:4px; transition:width 0.5s; }}
.gauge .labels {{ display:flex; justify-content:space-between; font-size:11px; color:#64748b; }}

.posts {{ margin:16px 0; }}
.posts h3 {{ font-size:15px; margin-bottom:12px; color:#94a3b8; }}
.post {{ background:#1e293b; border-radius:10px; padding:12px; margin:8px 0; }}
.post .p-title {{ font-size:14px; margin-bottom:4px; }}
.post .p-meta {{ font-size:12px; color:#64748b; }}

.fng-bar {{ background:#1e293b; border-radius:12px; padding:16px; margin:12px 0; }}
.fng-bar .bar-outer {{ height:20px; background:#334155; border-radius:10px; overflow:hidden; }}
.fng-bar .bar-inner {{ height:20px; border-radius:10px; transition:width 0.5s; }}

.footer {{ text-align:center; color:#475569; font-size:12px; padding:20px 0; }}
</style>
</head>
<body>
<div class="header">
  <h1>疯向标</h1>
  <div class="time">{data.get('time','')[:16]}</div>
</div>

<div class="signal">
  <div class="emoji">{signal[0].split(' ')[0]}</div>
  <div class="label">{signal[0]}</div>
  <div class="hint">{signal[2]}</div>
</div>

<div class="row">
  <div class="card">
    <div class="title">😴 沉默率</div>
    <div class="value" style="color:#22c55e">{silence:.0f}%</div>
    <div class="sub">散户不说话</div>
  </div>
  <div class="card">
    <div class="title">🎉 狂欢率</div>
    <div class="value" style="color:{'#ef4444' if carnival>=15 else '#94a3b8'}">{carnival:.0f}%</div>
    <div class="sub">散户嗨了</div>
  </div>
  <div class="card">
    <div class="title">😱 恐慌贪婪</div>
    <div class="value" style="color:{fg_color}">{fg_val}</div>
    <div class="sub">{fg_class}</div>
  </div>
</div>

<div class="fng-bar">
  <div style="display:flex;justify-content:space-between;font-size:12px;color:#64748b;margin-bottom:4px">
    <span>极度恐慌 0</span><span>中性 50</span><span>极度贪婪 100</span>
  </div>
  <div class="bar-outer">
    <div class="bar-inner" style="width:{fg_val}%;background:{fg_color}"></div>
  </div>
</div>

<div class="gauge">
  <div style="font-size:14px;margin-bottom:8px">📊 雪球情绪温度计</div>
  <div class="bar-track">
    <div class="bar-fill" style="width:{max(silence,5)}%;background:linear-gradient(90deg,#22c55e,#eab308,#ef4444)"></div>
  </div>
  <div class="labels">
    <span>😴 麻木</span><span>😐 正常</span><span>🎉 狂欢</span>
  </div>
</div>

<div class="posts">
  <h3>💬 今日最极端帖子</h3>
'''
    for p in extreme_posts:
        s = p.get('sentiment', 0)
        emoji = '🟢' if s > 0 else '🔴' if s < 0 else '⚪'
        color = '#22c55e' if s > 0 else '#ef4444' if s < 0 else '#94a3b8'
        html += f'''
  <div class="post">
    <div class="p-title">{emoji} <span style="color:{color}">{s:+.0f}</span> {p.get('title','')[:80]}</div>
    <div class="p-meta">{p.get('user','')}</div>
  </div>'''
    
    html += f'''
</div>

<div class="row">
  <div class="card">
    <div class="title">🥇 黄金热搜</div>
    <div class="value">{tracks.get('gold',0)}</div>
    <div class="sub">条相关</div>
  </div>
  <div class="card">
    <div class="title">₿ BTC热搜</div>
    <div class="value">{tracks.get('btc',0)}</div>
    <div class="sub">条相关</div>
  </div>
  <div class="card">
    <div class="title">🤖 AI/存储</div>
    <div class="value">{tracks.get('ai_storage',0)}</div>
    <div class="sub">条相关</div>
  </div>
</div>

<div class="footer">
  疯向标 v1 · {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
  别人麻木我贪婪 · 别人疯狂我恐惧
</div>
</body>
</html>'''
    return html

if __name__ == '__main__':
    data = load_latest()
    if not data:
        print('无数据，先运行 collect.py')
        exit(1)
    
    html = build_html(data)
    path = os.path.join(DATA_DIR, 'fengxiangbiao.html')
    with open(path, 'w') as f:
        f.write(html)
    
    print(f'✅ 仪表盘: {path}')
    print(f'   浏览器打开: file://{path}')
