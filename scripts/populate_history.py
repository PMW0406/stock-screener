"""
과거 데이터 수집 — yfinance + FinanceDataReader 사용 (해외 IP 제한 없음)
"""
import json
import os
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr

def get_trading_days(start_date, end_date):
    days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            days.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    return days

def get_kr_stocks():
    stocks = []
    for market, suffix in [('KOSPI', '.KS'), ('KOSDAQ', '.KQ')]:
        try:
            listing = fdr.StockListing(market)
            sym_col  = next((c for c in listing.columns if c in ('Symbol','Code')), None)
            cap_col  = next((c for c in listing.columns if 'Marcap' in c or 'MarketCap' in c or '시가총액' in c), None)
            name_col = next((c for c in listing.columns if c in ('Name','종목명')), None)
            if not sym_col or not cap_col or not name_col:
                continue
            listing = listing[listing[cap_col].notna()]
            listing = listing[
                (listing[cap_col] >= 100_000_000_000) &
                (listing[cap_col] <= 5_000_000_000_000)
            ]
            for _, row in listing.iterrows():
                ticker = str(row[sym_col]).zfill(6)
                stocks.append({
                    'ticker':    ticker,
                    'name':      str(row[name_col]),
                    'market':    market,
                    'yf_ticker': ticker + suffix,
                    'marcap':    int(row[cap_col]),
                    'marcap_억': round(row[cap_col] / 100_000_000, 0),
                })
        except Exception as e:
            print(f"  {market} 리스팅 오류: {e}")
    return stocks

def bulk_download(yf_tickers, start, end):
    """날짜 범위 전체를 한 번에 다운로드"""
    all_closes  = {}
    all_volumes = {}
    BATCH = 200
    for i in range(0, len(yf_tickers), BATCH):
        chunk = yf_tickers[i:i + BATCH]
        try:
            raw = yf.download(chunk, start=start, end=end, auto_adjust=True,
                              progress=False, threads=True)
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                closes  = raw['Close']
                volumes = raw.get('Volume', pd.DataFrame())
            else:
                closes  = raw[['Close']].rename(columns={'Close': chunk[0]})
                volumes = pd.DataFrame()
            for col in closes.columns:
                all_closes[col]  = closes[col]
                if col in (volumes.columns if not volumes.empty else []):
                    all_volumes[col] = volumes[col]
        except Exception as e:
            print(f"  다운로드 오류: {e}")
    return pd.DataFrame(all_closes), pd.DataFrame(all_volumes)

def screen_from_bulk(closes, volumes, date_str, ticker_map):
    results = []
    date_idx = closes.index.strftime('%Y%m%d') == date_str
    if not date_idx.any():
        return results
    pos = closes.index.get_loc(closes.index[date_idx][0])
    if pos == 0:
        return results
    curr   = closes.iloc[pos]
    prev   = closes.iloc[pos - 1]
    change = (curr - prev) / prev * 100
    mask   = (change <= -5) & (change >= -12)
    hits   = change[mask].dropna()
    for yf_t, chg in hits.items():
        if yf_t not in ticker_map:
            continue
        price = curr[yf_t]
        if pd.isna(price) or price == 0:
            continue
        s   = ticker_map[yf_t]
        vol = int(volumes.iloc[pos][yf_t]) if (not volumes.empty and yf_t in volumes.columns) else 0
        results.append({
            'ticker':      s['ticker'],
            'name':        s['name'],
            'market':      s['market'],
            'close':       int(price),
            'change_rate': round(float(chg), 2),
            'volume':      vol,
            'market_cap':  s['marcap'],
            'market_cap_억': s['marcap_억'],
        })
    results.sort(key=lambda x: x['change_rate'])
    return results

def run_populate(days_back=90):
    os.makedirs('data', exist_ok=True)
    end_date     = datetime.now() - timedelta(days=1)
    start_date   = end_date - timedelta(days=days_back)
    trading_days = get_trading_days(start_date, end_date)
    print(f"총 {len(trading_days)}개 거래일")

    print("종목 목록 가져오는 중...")
    stocks     = get_kr_stocks()
    ticker_map = {s['yf_ticker']: s for s in stocks}
    yf_tickers = list(ticker_map.keys())
    print(f"총 {len(stocks)}개 종목")

    # 전체 기간 데이터를 한 번에 다운로드
    dl_start = (start_date - timedelta(days=10)).strftime('%Y-%m-%d')
    dl_end   = (end_date   + timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"가격 데이터 다운로드 중: {dl_start} ~ {dl_end}")
    closes, volumes = bulk_download(yf_tickers, dl_start, dl_end)
    print(f"다운로드 완료: {closes.shape}")

    all_backtest = []

    for i, date_str in enumerate(trading_days):
        screen_file = f'data/screening_{date_str}.json'

        # 기존 데이터가 있고 종목이 있으면 스킵
        if os.path.exists(screen_file):
            with open(screen_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if existing.get('count', 0) > 0:
                print(f"[{i+1}/{len(trading_days)}] {date_str} 스킵 ({existing['count']}개)")
                stocks_today = existing['stocks']
            else:
                stocks_today = screen_from_bulk(closes, volumes, date_str, ticker_map)
                data = {'date': date_str, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'count': len(stocks_today), 'stocks': stocks_today}
                with open(screen_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"[{i+1}/{len(trading_days)}] {date_str} → {len(stocks_today)}개")
        else:
            stocks_today = screen_from_bulk(closes, volumes, date_str, ticker_map)
            data = {'date': date_str, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'count': len(stocks_today), 'stocks': stocks_today}
            with open(screen_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[{i+1}/{len(trading_days)}] {date_str} → {len(stocks_today)}개")

        # 다음날 수익률
        if stocks_today and i + 1 < len(trading_days):
            next_date = trading_days[i + 1]
            bt_file   = f'data/backtest_{date_str}.json'
            if not os.path.exists(bt_file):
                bt_results = []
                for s in stocks_today:
                    yf_t  = s['ticker'] + ('.KS' if s['market'] == 'KOSPI' else '.KQ')
                    d_idx = closes.index.strftime('%Y%m%d') == next_date
                    if not d_idx.any() or yf_t not in closes.columns:
                        continue
                    pos       = closes.index.get_loc(closes.index[d_idx][0])
                    next_open_val  = closes.iloc[pos][yf_t]   # yfinance auto_adjust: open ≈ close proxy
                    next_close_val = closes.iloc[pos][yf_t]
                    # 시가/종가를 따로 가져오기
                    bt_results.append({
                        **s,
                        'screen_date':  date_str,
                        'next_date':    next_date,
                        'screen_change_rate': s['change_rate'],
                        'next_close':   int(next_close_val) if not pd.isna(next_close_val) else 0,
                        'close_return': round((next_close_val - s['close']) / s['close'] * 100, 2) if not pd.isna(next_close_val) and s['close'] > 0 else 0,
                        'open_return':  0,
                    })
                with open(bt_file, 'w', encoding='utf-8') as f:
                    json.dump({'screen_date': date_str, 'next_date': next_date, 'count': len(bt_results), 'results': bt_results}, f, ensure_ascii=False, indent=2)
                all_backtest.extend(bt_results)

    # 히스토리 저장
    history_file = 'data/backtest_history.json'
    existing_h = []
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            existing_h = json.load(f)
    keys = {(r['ticker'], r.get('screen_date','')) for r in existing_h}
    new  = [r for r in all_backtest if (r['ticker'], r.get('screen_date','')) not in keys]
    combined = (existing_h + new)[-2000:]
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    # 날짜 목록
    date_list = sorted([
        f.replace('screening_','').replace('.json','')
        for f in os.listdir('data')
        if f.startswith('screening_') and 'latest' not in f
    ], reverse=True)
    with open('data/date_list.json', 'w', encoding='utf-8') as f:
        json.dump(date_list, f)

    print(f"\n완료! 백테스트 {len(combined)}개 레코드")

if __name__ == '__main__':
    run_populate(days_back=90)
