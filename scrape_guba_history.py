#!/usr/bin/env python3
"""
疯向标 - 股吧历史采集器
从东方财富股吧翻历史2年帖子，按周抽样
输出: 每周80条帖子的情绪分
"""
import json, re, urllib.request, ssl, sys, os, time
from datetime import date, datetime, timedelta

ssl_ctx = ssl.create_default_context()

# 读取cookie
COOKIE_FILE = os.path.expanduser('~/.hermes/scripts/fengxiangbiao/data/.guba_cookie')
with open(COOKIE_FILE) as f:
    COOKIE = f.read().strip()

# 情绪词典 (增强版，含散户黑话)
BULLISH = [
    '暴涨','起飞','新高','突破','抄底','牛回','牛市','反转','大阳线',
    '满仓','梭哈','爆拉','暴力拉升','加仓','上车','冲','稳了','躺赚','利好',
    '反弹','主升浪','逼空','反击','探底回升','黄金坑','机会','起飞了',
    '看多','做多','大涨','涨停','吃肉','回血','赚',
]
BEARISH = [
    '暴跌','崩盘','归零','腰斩','割肉','清仓','跑路','完蛋','完了',
    '熊市','爆仓','血洗','踩踏','恐慌','逃命','止损','离场',
    '大阴线','破位','深套','亏麻','跌麻','亏完','没了',
    '空仓','观望','不敢买','怕了','崩溃','绝望','地狱',
    '看空','做空','空头','砸盘','出货','收割','韭菜','割韭菜',
    '爆跌','大跌','跌停','吃面','关灯吃面','天台',
]

def score(text):
    """情绪打分"""
    t = text.lower()
    bull = sum(1 for w in BULLISH if w in t)
    bear = sum(1 for w in BEARISH if w in t)
    if bull > bear:
        return min(bull - bear, 5)
    elif bear > bull:
        return max(-(bear - bull), -5)
    return 0

def fetch_page(page_num, board='zssh000001', retries=3):
    """下载股吧一页帖子"""
    url = f'https://guba.eastmoney.com/list,{board}_{page_num}.html'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
    req.add_header('Cookie', COOKIE)
    
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as r:
                html = r.read().decode('utf-8', errors='ignore')
            m = re.search(r'var article_list=(\{.*?\});', html)
            if not m:
                return None
            data = json.loads(m.group(1))
            posts = []
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
            return posts
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                print(f'  ERR page {page_num}: {e}', file=sys.stderr)
    return None

# ═══════ 主流程 ═══════
# 基于实测校准: page 1=2026-07, page 5000=2026-04, page 10000=2025-11, 
#               page 20000=2025-01, page 30000=2024-04
# 推算: ~1111页/月 ≈ 278页/周
PAGES_PER_WEEK = 278
TOTAL_WEEKS = 104  # 2年
START_PAGE = 1
END_PAGE = 30000

# 采样策略: 均匀间隔 + 关键日期加密度
sample_pages = []
# 每周一页
for i in range(TOTAL_WEEKS):
    page = START_PAGE + i * PAGES_PER_WEEK
    if page <= END_PAGE:
        sample_pages.append(page)

# 关键暴跌日加密度 (通过推算找到对应页数)
# 2024-10-08 (国庆后暴跌): 大概在28000页附近
# 2025-04-07 (关税冲击): 大概在15000页附近  
# 在这些日期前后各加2页
key_events = {
    '2024-10-08': 28000,  # A股国庆后暴跌
    '2025-04-07': 15000,  # 关税冲击
    '2025-01-02': 20000,  # 年初
    '2024-07-01': 31000,  # 起点附近
}
for label, base_page in key_events.items():
    for offset in [-3, -1, 0, 1, 3]:
        p = base_page + offset * 10  # ±30页
        if 1 <= p <= END_PAGE and p not in sample_pages:
            sample_pages.append(p)

sample_pages = sorted(set(sample_pages))
print(f'计划采集 {len(sample_pages)} 页 (~{len(sample_pages)*80}条帖子)')
print(f'范围: 第{min(sample_pages)}页 ~ 第{max(sample_pages)}页\n')

# 采集
all_weeks = []
for i, page in enumerate(sample_pages):
    posts = fetch_page(page)
    if posts:
        week_data = {
            'page': page,
            'count': len(posts),
            'bullish': sum(1 for p in posts if p['sentiment'] > 0),
            'bearish': sum(1 for p in posts if p['sentiment'] < 0),
            'neutral': sum(1 for p in posts if p['sentiment'] == 0),
            'sentiment_score': round(sum(p['sentiment'] for p in posts) / max(len(posts), 1), 2),
            'earliest': posts[-1]['time'],
            'latest': posts[0]['time'],
            'top_bullish': [p['title'][:60] for p in posts if p['sentiment'] > 1][:3],
            'top_bearish': [p['title'][:60] for p in posts if p['sentiment'] < -1][:3],
        }
        all_weeks.append(week_data)
        print(f'[{i+1}/{len(sample_pages)}] 第{page}页 | {posts[0]["time"][:10]} | '
              f'多{week_data["bullish"]}/空{week_data["bearish"]}/中{week_data["neutral"]} | '
              f'情绪分{week_data["sentiment_score"]:+.2f}', flush=True)
    else:
        print(f'[{i+1}/{len(sample_pages)}] 第{page}页: 失败', flush=True)
    time.sleep(0.3)  # 别太快

# 保存
out = {
    'collected_at': datetime.now().isoformat(),
    'board': 'zssh000001',
    'total_pages': len(all_weeks),
    'total_posts': sum(w['count'] for w in all_weeks),
    'weeks': all_weeks,
}
path = os.path.expanduser('~/.hermes/scripts/fengxiangbiao/data/guba_history_2y.json')
with open(path, 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print(f'\n✅ 保存 {path}')
print(f'   {len(all_weeks)}周 × 约80条/周 = {sum(w["count"] for w in all_weeks)}条帖子')
