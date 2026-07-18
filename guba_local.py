#!/usr/bin/env python3
"""
疯向标 - 本地股吧采集器
登录 guba.eastmoney.com 后双击运行, 5秒完成
输出: ~/.hermes/scripts/fengxiangbiao/data/guba_local.json
"""
import json, os, subprocess, sys
from datetime import datetime

# 用AppleScript调Safari获取页面HTML（你现在打开的guba页面）
applescript = '''
tell application "Safari"
    set pageHTML to ""
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "guba.eastmoney.com" then
                set pageHTML to source of t
                exit repeat
            end if
        end repeat
        if pageHTML is not "" then exit repeat
    end repeat
    return pageHTML
end tell
'''

print("正在从Safari读取股吧页面...")
result = subprocess.run(['osascript', '-e', applescript], capture_output=True, text=True, timeout=15)
html = result.stdout

if not html or len(html) < 1000:
    print("❌ 没找到打开的股吧页面。请先在Safari打开 guba.eastmoney.com 并登录。")
    sys.exit(1)

# 提取 article_list
import re
m = re.search(r'var article_list=(\{.*?\});', html)
if not m:
    print("❌ 未找到帖子数据。请确认已登录股吧。")
    sys.exit(1)

data = json.loads(m.group(1))
posts = []
BULLISH = ['暴涨','起飞','新高','突破','抄底','牛回','牛市','反转','大阳线','满仓','梭哈',
           '爆拉','加仓','上车','冲','稳了','反弹','主升浪','逼空','反击','大涨','涨停','吃肉','回血']
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

for p in data.get('re', []):
    title = p.get('post_title', '')
    posts.append({
        'title': title,
        'user': p.get('user_nickname', ''),
        'reads': int(p.get('post_click_count', 0)),
        'comments': int(p.get('post_comment_count', 0)),
        'time': p.get('post_publish_time', ''),
        'sentiment': score(title),
    })

b = sum(1 for p in posts if p['sentiment'] > 0)
s = sum(1 for p in posts if p['sentiment'] < 0)
n = sum(1 for p in posts if p['sentiment'] == 0)

result = {
    'time': datetime.now().isoformat(),
    'count': len(posts),
    'bullish': b, 'bearish': s, 'neutral': n,
    'silence_rate': round(n / len(posts) * 100, 1),
    'carnival_rate': round(b / len(posts) * 100, 1),
    'sentiment': round(sum(p['sentiment'] for p in posts) / len(posts), 2),
    'posts': posts,
}

out_path = os.path.expanduser('~/.hermes/scripts/fengxiangbiao/data/guba_local.json')
with open(out_path, 'w') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f'\n✅ {len(posts)}条帖子')
print(f'   沉默率: {result["silence_rate"]:.0f}% | 狂欢率: {result["carnival_rate"]:.0f}%')
print(f'   看多: {b} | 看空: {s} | 中性: {n} | 情绪分: {result["sentiment"]:+.2f}')
print(f'\n   保存: {out_path}')
print(f'   现在运行: python3 ~/.hermes/scripts/fengxiangbiao/report.py')
