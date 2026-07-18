"""
疯向标 - 加密恐慌指数 vs BTC 价格回测
核心假设：极端情绪 + 价格背离 = 趋势拐点
"""
import pandas as pd
import numpy as np
import json
import urllib.request
from datetime import datetime, timedelta

# ── 1. 拉取 Crypto Fear & Greed 历史数据 ──
print("📡 获取 Fear & Greed 历史数据...")
url = "https://api.alternative.me/fng/?limit=0&format=json"
with urllib.request.urlopen(url) as resp:
    data = json.loads(resp.read())
fng_df = pd.DataFrame(data["data"])
fng_df["date"] = pd.to_datetime(fng_df["timestamp"].astype(int), unit="s")
fng_df["value"] = fng_df["value"].astype(int)
fng_df["classification"] = fng_df["value_classification"]
fng_df = fng_df.sort_values("date").reset_index(drop=True)
print(f"✅ 获取 {len(fng_df)} 条 F&G 数据 ({fng_df['date'].min().date()} ~ {fng_df['date'].max().date()})")

# ── 2. 拉取 BTC 价格 ──
print("\n📡 获取 BTC 历史价格...")
import os
os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"
os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
import yfinance as yf

btc = yf.download("BTC-USD", start="2018-02-01", end="2026-08-01", progress=False)
if btc.empty:
    # 代理不行就直连重试
    del os.environ["HTTP_PROXY"]
    del os.environ["HTTPS_PROXY"]
    btc = yf.download("BTC-USD", start="2018-02-01", end="2026-08-01", progress=False)

# flatten multi-level columns
if isinstance(btc.columns, pd.MultiIndex):
    btc.columns = btc.columns.droplevel(1)
btc = btc.reset_index()
btc = btc.rename(columns={"Date": "date", "Close": "close"})
btc["date"] = pd.to_datetime(btc["date"])
btc = btc[["date", "close"]]
print(f"✅ 获取 {len(btc)} 条 BTC 价格数据 ({btc['date'].min().date()} ~ {btc['date'].max().date()})")

# ── 3. 合并数据，计算未来收益率 ──
df = fng_df.merge(btc, on="date", how="inner")
df["return_7d"] = (df["close"].shift(-7) / df["close"] - 1) * 100
df["return_14d"] = (df["close"].shift(-14) / df["close"] - 1) * 100
df["return_30d"] = (df["close"].shift(-30) / df["close"] - 1) * 100
df["return_60d"] = (df["close"].shift(-60) / df["close"] - 1) * 100

# ── 4. 定义情绪区间 ──
extreme_fear = df[df["value"] <= 20]    # 极度恐慌
fear = df[(df["value"] > 20) & (df["value"] <= 40)]
neutral = df[(df["value"] > 40) & (df["value"] <= 60)]
greed = df[(df["value"] > 60) & (df["value"] <= 80)]
extreme_greed = df[df["value"] > 80]    # 极度贪婪

# ── 5. 计算各区间的未来平均收益 ──
print("\n" + "="*70)
print("📊 不同情绪区间后的 BTC 未来收益")
print("="*70)

def show_stats(label, subset, price_col="close"):
    n = len(subset)
    if n == 0:
        return
    avg_price = subset[price_col].mean()
    print(f"\n{label}  (n={n} 天)")
    for period, col in [("7日", "return_7d"), ("14日", "return_14d"), 
                         ("30日", "return_30d"), ("60日", "return_60d")]:
        valid = subset[col].dropna()
        if len(valid) > 0:
            win_rate = (valid > 0).mean() * 100
            avg_ret = valid.mean()
            median_ret = valid.median()
            print(f"  {period}: 平均 {avg_ret:+.2f}% | 中位数 {median_ret:+.2f}% | 胜率 {win_rate:.0f}% | n={len(valid)}")

show_stats("😱 极度恐慌 (0-20)", extreme_fear)
show_stats("😟 恐慌 (21-40)", fear)
show_stats("😐 中性 (41-60)", neutral)
show_stats("😀 贪婪 (61-80)", greed)
show_stats("🤩 极度贪婪 (81-100)", extreme_greed)

# ── 6. 简单策略回测 ──
print("\n" + "="*70)
print("📈 策略回测")
print("="*70)

# 策略：恐慌<20买入 持有30天 vs 贪婪>80卖出
fear_buy_signals = extreme_fear.copy()
if len(fear_buy_signals) > 0:
    fear_returns = fear_buy_signals["return_30d"].dropna()
    print(f"\n😱 恐慌<20 买入 BTC 持有30天:")
    print(f"  信号次数: {len(fear_returns)}")
    print(f"  平均收益: {fear_returns.mean():+.2f}%")
    print(f"  中位数收益: {fear_returns.median():+.2f}%")
    print(f"  胜率: {(fear_returns > 0).mean()*100:.0f}%")
    print(f"  最大亏损: {fear_returns.min():+.2f}%")
    print(f"  最大盈利: {fear_returns.max():+.2f}%")

greed_sell_signals = extreme_greed.copy()
if len(greed_sell_signals) > 0:
    greed_returns = greed_sell_signals["return_30d"].dropna()
    print(f"\n🤩 贪婪>80 时买入 BTC 持有30天（应为负）:")
    print(f"  信号次数: {len(greed_returns)}")
    print(f"  平均收益: {greed_returns.mean():+.2f}%")
    print(f"  中位数收益: {greed_returns.median():+.2f}%")
    print(f"  胜率: {(greed_returns > 0).mean()*100:.0f}%")

# ── 7. 恐慌程度 vs 未来收益散点 ──
print("\n" + "="*70)
print("🔍 极端情绪后30日收益明细（最近10次）")
print("="*70)

recent_fear = extreme_fear.dropna(subset=["return_30d"]).tail(10)
print("\n😱 极度恐慌 <20 后30日:")
for _, row in recent_fear.iterrows():
    print(f"  {row['date'].date()} | F&G={row['value']:2d} | BTC ${row['close']:,.0f} | 30日后 {row['return_30d']:+.2f}%")

recent_greed = extreme_greed.dropna(subset=["return_30d"]).tail(10)
print("\n🤩 极度贪婪 >80 后30日:")
for _, row in recent_greed.iterrows():
    print(f"  {row['date'].date()} | F&G={row['value']:2d} | BTC ${row['close']:,.0f} | 30日后 {row['return_30d']:+.2f}%")

# ── 8. 当前状态 ──
current = fng_df.iloc[-1]
print("\n" + "="*70)
print(f"📍 当前状态: {current['date'].date()} | F&G = {current['value']} ({current['classification']})")
print("="*70)
