"""
Momentum Engine — computes RSI, moving averages, returns, signals, and
investor emotion from DailyPrice history. Pure functions, no ORM.
"""
from decimal import Decimal, InvalidOperation
from typing import Optional
import math


# ── CORE CALCULATIONS ────────────────────────────────────

def compute_returns(closes: list) -> dict:
    """
    Given a list of close prices (oldest → newest),
    return 1M, 3M, 6M, 12M % returns.
    Assumes weekly data (~52 weeks per year).
    """
    n = len(closes)
    if n < 2:
        return {}

    def ret(weeks_back):
        idx = max(0, n - 1 - weeks_back)
        try:
            return round((closes[-1] / closes[idx] - 1) * 100, 2)
        except (ZeroDivisionError, TypeError):
            return None

    return {
        'return_1m':  ret(4),
        'return_3m':  ret(13),
        'return_6m':  ret(26),
        'return_12m': ret(52),
    }


def compute_rsi(closes: list, period: int = 14) -> Optional[float]:
    """Compute 14-day RSI from a close price list."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i - 1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0.001
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def compute_moving_averages(closes: list) -> dict:
    """Compute 20, 50, 200 day moving averages."""
    n = len(closes)
    result = {}
    for period, key in [(20, 'ma_20'), (50, 'ma_50'), (200, 'ma_200')]:
        if n >= period:
            result[key] = round(sum(closes[-period:]) / period, 2)
    return result


def compute_52w_range(closes: list) -> dict:
    """52-week high and low."""
    window = closes[-52:] if len(closes) >= 52 else closes
    if not window:
        return {}
    return {
        'high_52w': max(window),
        'low_52w':  min(window),
    }


def get_signal(primary_return: float, rsi: float) -> tuple:
    """
    Return (signal_code, emotion_code, emotion_icon) based on
    return over chosen period and RSI.
    """
    if primary_return > 15 and rsi > 60:
        signal = 'STRONG_BULL'
    elif primary_return > 8 and rsi > 50:
        signal = 'BULLISH'
    elif primary_return > 3:
        signal = 'MILD_UPTREND'
    elif primary_return > -3:
        signal = 'SIDEWAYS'
    elif primary_return > -8:
        signal = 'MILD_DOWNTREND'
    elif primary_return > -15:
        signal = 'BEARISH'
    else:
        signal = 'STRONG_BEAR'

    if rsi > 75:
        emotion, icon = 'EXTREME_GREED', '🔥'
    elif rsi > 65:
        emotion, icon = 'GREED', '😤'
    elif rsi > 55:
        emotion, icon = 'OPTIMISM', '😊'
    elif rsi > 45:
        emotion, icon = 'NEUTRAL', '😐'
    elif rsi > 35:
        emotion, icon = 'ANXIETY', '😟'
    elif rsi > 25:
        emotion, icon = 'FEAR', '😨'
    else:
        emotion, icon = 'PANIC', '😱'

    return signal, emotion, icon


def compute_all(closes: list, period: str = '6m') -> dict:
    """
    Main entry point. Takes a list of close prices and period code.
    Returns a flat dict matching MomentumSnapshot fields.
    """
    if not closes or len(closes) < 5:
        return {}

    returns   = compute_returns(closes)
    rsi       = compute_rsi(closes)
    mas       = compute_moving_averages(closes)
    rng       = compute_52w_range(closes)

    primary = {
        '3m': returns.get('return_3m'),
        '6m': returns.get('return_6m'),
        '12m': returns.get('return_12m'),
    }.get(period, returns.get('return_6m'))

    signal = emotion = icon = ''
    if primary is not None and rsi is not None:
        signal, emotion, icon = get_signal(primary, rsi)

    result = {
        **returns,
        'rsi_14':       rsi,
        'current_price': closes[-1],
        'signal':        signal,
        'emotion':       emotion,
        'emotion_icon':  icon,
        **mas,
        **rng,
    }
    return {k: v for k, v in result.items() if v is not None}


# ── SHAREHOLDING TREND HELPER ────────────────────────────

def compute_sh_trend(statements: list) -> dict:
    """
    Given FinancialStatement queryset (ordered newest first),
    return current + 6-quarter trend for promoter/FII/DII.
    """
    if not statements:
        return {}

    latest  = statements[0]
    oldest  = statements[-1] if len(statements) > 1 else latest

    def trend(attr):
        cur = float(getattr(latest, attr) or 0)
        old = float(getattr(oldest, attr) or 0)
        return round(cur - old, 2)

    return {
        'promoter_current':  float(latest.promoter_holding or 0),
        'promoter_trend_6q': trend('promoter_holding'),
        'fii_current':       float(latest.fii_holding     or 0),
        'fii_trend_6q':      trend('fii_holding'),
        'dii_current':       float(latest.dii_holding     or 0),
        'dii_trend_6q':      trend('dii_holding'),
        'pledging':          float(latest.promoter_pledged or 0),
    }
