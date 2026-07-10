"""Deterministic category derivation for census agents.

The census CSV has no category column. Categories are derived from
name+tagline keyword rules: buckets checked in order, keywords in order,
first match wins, no match -> "Other Services". Verified against all 272
real rows (research 2026-07-10). Methodology disclosure: "categories
derived from listing text" (surfaces on the Phase 3 methodology page).

Matching semantics:
- the two entries in REGEX_KEYWORDS compile verbatim as regex
- the two entries in SUBSTRING_KEYWORDS match as substrings: their only
  census occurrences are the plurals "cafes"/"restaurants" (row 3509,
  Crypto Shop Near Me), which the verified distribution counts in
  Lifestyle & Health and word-bounded singular matching would miss
- keywords containing a space or any non-ASCII char match as substrings
- single ASCII tokens match word-bounded (\\b...\\b)
- matched against: unicodedata.normalize("NFKC", f"{name} {tagline}").casefold()

DO NOT edit keyword contents, bucket names, or ordering without updating
the pinned distribution test - drift silently re-buckets agents and
changes Phase 2 percentiles (research Pitfall 7).
"""
from __future__ import annotations

import re
import unicodedata

REGEX_KEYWORDS = {
    r"(?<!not )astrolog",
    r"\btrading\b(?!\s+(volume|agents)\b)",
}

# Mechanics override (NOT table content): these existing table keywords match
# as substrings so their plural census occurrences are caught. Verified: only
# row 3509 contains either string, so this affects exactly one row.
SUBSTRING_KEYWORDS = {
    "cafe",
    "restaurant",
}

ORDERED_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Security & Trust", (
        "security", "安全", "audit", "audits", "审计", "scam", "rug", "rugradar",
        "honeypot", "phishing", "anti-money", "aml", "money laundering", "approval",
        "approvals", "threat", "privacy", "pii", "credit check", "creditworthiness",
        "due diligence", "尽调", "counterparty", "risk screen", "risk scan",
        "risk check", "risk assess", "risk precheck", "risk profil", "token risk",
        "wash-trade", "watchdog", "coverage", "trust layer", "verifier",
        "verification", "fact-check", "attest", "certik", "slowmist", "pre-trade",
        "guard", "guardian", "risky", "adversarial",
    )),
    ("Sports & Prediction", (
        "world cup", "世界杯", "polymarket", "prediction market", "prediction-market",
        "预测", "match outcome", "match details", "pre-match", "blackjack", "21点",
        "sports", "fan token", "hunch",
    )),
    ("Lifestyle & Health", (
        "tarot", "塔罗", "bazi", "八字", r"(?<!not )astrolog", "horoscope", "星座",
        "运势", "算命", "姻缘", "divination", "占卜", "fortune", "face reading",
        "面相", "destiny", "命理", "zodiac", "混沌梦核", "palm", "food", "饮食",
        "diet", "cook", "cuisine", "health management", "healthiness", "健康",
        "fitness", "健身", "nutrition", "travel", "旅行", "旅游", "trip",
        "itinerary", "人生", "stoic", "philosophy", "advice", "accompany", "心语",
        "cafe", "restaurant",
    )),
    ("Creative & Media", (
        "image generation", "image-to", "text-to-image", "thumbnail", "thumbnails",
        "avatar", "avatars", "video", "视频", "glitch art", "logo", "sticker",
        "wallpaper", "text-to-speech", "speech", "audio", "nft", "绘", "picture",
        "svg", "artwork", "drawing",
    )),
    ("Social & News", (
        "twitter", "推特", "tweet", "tweets", "x post", "x posts", "x api", "kol",
        "social intelligence", "social discussion", "social network",
        "social networks", "social media", "文章", "article", "viral", "爆款",
        "copywriting", "文案", "rewrite", "rewrites", "content creation",
        "content generation", "内容", "marketing", "营销", "brand", "branding",
        "品牌", "growth", "campaign", "campaigns", "go-to-market", "whatsapp",
        "instagram", "新闻", "快讯", "简报", "news retrieval",
    )),
    ("Developer Tools & Infra", (
        "code", "代码", "repo", "repository", "github", "dapp project", "prefab",
        "prefabs", "html", "css", "website", "建站", "domain", "llm", "llms",
        "model", "models", "inference", "prompt", "prompts", "agent-to-agent",
        "task delegation", "x402", "payment", "payments", "escrow", "relay",
        "registry", "registrations", "uptime", "form field", "表单", "mini-program",
        "小程序", "app", "developer", "developers", "开发", "deploy", "sdk",
        "agent brief", "agent builder", "agent builders",
    )),
    ("Trading & DeFi", (
        r"\btrading\b(?!\s+(volume|agents)\b)", "trade", "trades", "交易", "defi",
        "swap", "swaps", "bridge", "bridges", "yield", "yields", "lending", "loan",
        "loans", "borrow", "arbitrage", "套利", "futures", "quant", "量化",
        "strategy", "strategies", "策略", "copy trad", "copy-trade", "copytrade",
        "market-making", "market making", "airdrop", "airdrops", "meme coin",
        "meme token", "meme experiment", "fair-launch", "stake", "staking", "ipo",
        "打新", "market-timing", "open positions", "dca", "vault", "vaults",
    )),
    ("Market Data & Analytics", (
        "data", "数据", "analytics", "analysis", "分析", "onchain", "on-chain",
        "链上", "research", "研报", "研究", "研判", "market", "markets", "行情",
        "市场", "price", "prices", "chart", "charts", "k线", "k-line", "explorer",
        "whale", "whales", "鲸", "wallet", "wallets", "钱包", "token", "tokens",
        "tokenomics", "coin", "coins", "币", "crypto", "cryptocurrency", "stock",
        "stocks", "股", "scan", "scans", "monitor", "monitoring", "监控", "track",
        "tracking", "intel", "intelligence", "report", "reports", "index", "macro",
        "宏观", "unlock", "liquidity", "tvl", "volume", "investment", "投资",
        "watchlist", "portfolio",
    )),
)

FALLBACK = "Other Services"
CATEGORIES: tuple[str, ...] = tuple(name for name, _ in ORDERED_RULES) + (FALLBACK,)


def _compile(kw: str) -> re.Pattern[str]:
    if kw in REGEX_KEYWORDS:
        return re.compile(kw)                        # vetted regex, verbatim
    if kw in SUBSTRING_KEYWORDS or " " in kw or any(ord(c) > 127 for c in kw):
        return re.compile(re.escape(kw))             # phrase / CJK / override: substring
    return re.compile(r"\b" + re.escape(kw) + r"\b") # single ASCII token: word-bounded


_COMPILED = tuple(
    (bucket, tuple(_compile(k) for k in kws)) for bucket, kws in ORDERED_RULES
)


def derive_category(name: str, tagline: str) -> str:
    """First-match-wins over the ordered table; never returns empty."""
    text = unicodedata.normalize("NFKC", f"{name} {tagline}").casefold()
    for bucket, patterns in _COMPILED:
        for p in patterns:
            if p.search(text):
                return bucket
    return FALLBACK
