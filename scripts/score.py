"""
하락 종목 반등 가능성 채점 로직
최대 12점 — 점수가 높을수록 반등 확률 높음
"""
import pandas as pd


def calc_rsi(closes: pd.Series, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff().dropna()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float('nan'))
    rsi   = 100 - (100 / (1 + rs))
    val   = rsi.iloc[-1]
    return float(val) if not pd.isna(val) else 50.0


def score_stock(hist_closes: pd.Series, hist_volumes: pd.Series,
                today_volume: int, today_close: float,
                today_change_pct: float) -> tuple[int, dict]:
    """
    hist_closes / hist_volumes : 오늘 제외한 과거 데이터 (최소 20일 권장)
    반환 → (score 0~12, details dict)
    """
    details = {
        'rsi':              None,
        'vol_ratio':        None,
        'pct_from_52w_low': None,
        'pct_from_52w_high':None,
        'above_ma20':       None,
        'above_ma60':       None,
    }

    if len(hist_closes) < 20:
        return 0, details

    score = 0

    # ── RSI ──────────────────────────────────────────
    rsi = calc_rsi(hist_closes)
    details['rsi'] = round(rsi, 1)
    if rsi < 25:
        score += 3
    elif rsi < 30:
        score += 2
    elif rsi < 35:
        score += 1

    # ── 거래량 비율 (20일 평균 대비) ──────────────────
    avg_vol = float(hist_volumes.tail(20).mean()) if len(hist_volumes) >= 20 else 0
    vol_ratio = today_volume / avg_vol if avg_vol > 0 else 1.0
    details['vol_ratio'] = round(vol_ratio, 2)
    if vol_ratio >= 3.0:
        score += 4
    elif vol_ratio >= 2.0:
        score += 3
    elif vol_ratio >= 1.5:
        score += 2
    elif vol_ratio >= 1.2:
        score += 1
    # 거래량 실종 = 패닉셀 없음 → 추가 하락 위험
    elif vol_ratio < 0.8:
        score -= 1

    # ── 52주 고/저 대비 위치 ───────────────────────────
    window = hist_closes.tail(252)
    high52 = float(window.max())
    low52  = float(window.min())
    pct_from_low  = (today_close - low52)  / low52  * 100 if low52  > 0 else 0
    pct_from_high = (today_close - high52) / high52 * 100 if high52 > 0 else 0
    details['pct_from_52w_low']  = round(pct_from_low,  1)
    details['pct_from_52w_high'] = round(pct_from_high, 1)

    if pct_from_low > 30:
        score += 2          # 최저가에서 충분히 올라온 상태 → 지지 있음
    elif pct_from_low > 15:
        score += 1
    elif pct_from_low < 5:
        score -= 2          # 신저점 근처 → 추세 붕괴 위험

    # ── 이동평균선 ────────────────────────────────────
    ma20 = float(hist_closes.tail(20).mean())
    ma60 = float(hist_closes.tail(60).mean()) if len(hist_closes) >= 60 else ma20
    details['above_ma20'] = today_close > ma20
    details['above_ma60'] = today_close > ma60

    if today_close > ma60:
        score += 2          # 중기 상승 추세 유지
    if today_close > ma20:
        score += 1

    # ── 하락 폭 스위트스팟 ────────────────────────────
    drop = abs(today_change_pct)
    if 7 <= drop <= 10:
        score += 1          # 과도하지 않은 하락 = 반등 여지

    return max(score, 0), details


def score_label(score: int) -> str:
    if score >= 9:  return '⭐⭐⭐ 강력 반등 후보'
    if score >= 6:  return '⭐⭐ 반등 가능'
    if score >= 3:  return '⭐ 주의 관찰'
    return '❌ 반등 신호 약함'
