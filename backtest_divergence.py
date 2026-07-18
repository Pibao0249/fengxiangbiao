"""
疯向标 回测 v2 — 贪婪背离逻辑
F&G 从高位拐头 + 价格滞涨 = 逃顶信号
"""
import pandas as pd
import numpy as np
import json, os, urllib.request

# ── 数据加载 ──
print("📡 加载数据...")
url = "https://api.alternative.me/fng/?limit=0&format=json"
with urllib.request.urlopen(url) as resp:
    data = json.loads(resp.read())
fng = pd.DataFrame(data["data"])
fng["date"] = pd.to_datetime(fng["timestamp"].astype(int), unit="s")
fng["value"] = fng["value"].astype(int)
fng = fng.sort_values("date").reset_index(drop=True)

os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
import yfinance as yf
btc = yf.download("BTC-USD", start="2018-02-01", end="2026-08-01", progress=False)
if isinstance(btc.columns, pd.MultiIndex):
    btc.columns = btc.columns.droplevel(1)
btc = btc.reset_index().rename(columns={"Date": "date", "Close": "close"})
btc["date"] = pd.to_datetime(btc["date"])

df = fng.merge(btc[["date","close"]], on="date").sort_values("date").reset_index(drop=True)

# ── 计算近期峰值 ──
df["fng_peak_14d"] = df["value"].rolling(14, min_periods=1).max()
df["fng_peak_30d"] = df["value"].rolling(30, min_periods=1).max()
df["price_peak_14d"] = df["close"].rolling(14, min_periods=1).max()
df["price_peak_30d"] = df["close"].rolling(30, min_periods=1).max()

# ── 未来收益 ──
for d in [7,14,30,60]:
    df[f"ret_{d}d"] = (df["close"].shift(-d) / df["close"] - 1) * 100

# ── 背离信号定义 ──
# 条件1: F&G 从高峰回落至少10点（情绪拐头）
# 条件2: 价格还在高点附近（距14日高点 <5%）
# 条件3: 之前确实过热过（30日峰值 >75）
df["greed_fading"] = (df["fng_peak_30d"] - df["value"]) >= 10
df["price_near_peak"] = (df["close"] / df["price_peak_14d"]) > 0.95
df["was_hot"] = df["fng_peak_30d"] > 75

df["divergence_sell"] = df["greed_fading"] & df["price_near_peak"] & df["was_hot"]

# ── 结果 ──
print(f"\n{'='*60}")
print("🔴 贪婪背离信号（情绪拐头 + 价格滞涨）")
print(f"{'='*60}")

signals = df[df["divergence_sell"]]
print(f"信号总次数: {len(signals)}")
if len(signals) > 0:
    for d in [7,14,30,60]:
        col = f"ret_{d}d"
        valid = signals[col].dropna()
        if len(valid) > 0:
            wr = (valid > 0).mean()*100  # 这里"赢"=正收益，但我们期望是负的
            print(f"\n  持有{d}天:")
            print(f"    平均收益: {valid.mean():+.2f}%")
            print(f"    中位数: {valid.median():+.2f}%")
            print(f"    正收益概率: {wr:.0f}%  ← 越低越好(说明多是跌的)")
            print(f"    最差: {valid.min():+.2f}%")
            print(f"    最好: {valid.max():+.2f}%")
            print(f"    n={len(valid)}")

print(f"\n{'='*60}")
print("📋 最近20个背离信号详情")
print(f"{'='*60}")
recent = signals.tail(20).copy()
for idx, r in recent.iterrows():
    dft = r["fng_peak_30d"] - r["value"]
    pct = (r["close"] / r["price_peak_14d"] - 1) * 100
    ret30 = r["ret_30d"] if not pd.isna(r["ret_30d"]) else None
    ret_str = f"→ 30d后 {ret30:+.2f}%" if ret30 is not None else ""
    print(f"  {r['date'].date()} | F&G={r['value']}(-{dft:.0f}) | BTC ${r['close']:,.0f}(距峰{pct:+.1f}%) {ret_str}")

# ── 对比：纯F&G>80（无背离筛选） ──
print(f"\n{'='*60}")
print("📊 对比：有背离 vs 无背离（贪婪>80）")
print(f"{'='*60}")
pure_greed = df[df["value"] > 80]
for label, subset in [("纯贪婪>80", pure_greed), ("贪婪背离信号", signals)]:
    col = "ret_30d"
    v = subset[col].dropna()
    if len(v) > 0:
        print(f"  {label}: 30d平均 {v.mean():+.2f}% | 胜率(涨) {(v>0).mean()*100:.0f}% | n={len(v)}")

# ── 当前 ──
print(f"\n{'='*60}")
cur = df.iloc[-1]
print(f"📍 当前: {cur['date'].date()} | F&G={cur['value']} | BTC=${cur['close']:,.0f}")
print(f"   30日F&G峰值: {cur['fng_peak_30d']} | 14日价格峰值: ${cur['price_peak_14d']:,.0f}")
fading = cur['fng_peak_30d'] - cur['value']
print(f"   背离状态: 情绪回落{fading}点 | 价格距峰{(cur['close']/cur['price_peak_14d']-1)*100:+.1f}%", end="")
if cur['divergence_sell']:
    print(" → 🔴 触发逃顶背离信号")
else:
    print(" → 无信号")
