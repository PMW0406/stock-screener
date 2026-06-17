"""
과거 데이터 수집
1. build_ticker_list.py로 만든 kr_tickers.json 사용
2. yfinance 배치 다운로드로 가격 데이터 수집
→ 해외 IP 제한 없음
"""
import json
import os
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

def get_trading_days(start_date, end_date):
    days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            days.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    return days

def load_tickers():
    path = 'data/kr_tickers.json'
    if not os.path.exists(path):
        raise FileNotFoundError("data/kr_tickers.json 없음. build_ticker_list 먼저 실행하세요.")
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data['tickers']

def bulk_download(yf_tickers, start, end):
    closes  = {}
    opens   = {}
    volumes = {}
    BATCH   = 200

    for i in range(0, len(yf_tickers), BATCH):
        chunk = yf_tickers[i:i + BATCH]
        try:
            raw = yf.download(chunk, start=start, end=end, auto_adjust=True,
                              progress=False, threads=True)
            if raw.empty:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                c = raw['Close'];  o = raw.get('Open', pd.DataFrame()); v = raw.get('Volume', pd.DataFrame())
            else:
                c = raw[['Close']].rename(columns={'Close': chunk[0]})
                o = raw[['Open']].rename(columns={'Open': chunk[0]}) if 'Open' in raw.columns else pd.DataFrame()
                v = pd.DataFrame()

            for col in c.columns:
                closes[col]  = c[col]
                if not o.empty and col in o.columns:
                    opens[col] = o[col]
                if not v.empty and col in v.columns:
                    volumes[col] = v[col]

            print(f"  다운로드 {i+len(chunk)}/{len(yf_tickers)}")
        except Exception as e:
            print(f"  배치 오류: {e}")

    return pd.DataFrame(closes), pd.DataFrame(opens), pd.DataFrame(volumes)

def screen_from_bulk(closes, opens, volumes, date_str, ticker_map):
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
        vol = int(volumes.iloc[pos][yf_t]) if (not volumes.empty and yf_t in volumes.columns and not pd.isna(volumes.iloc[pos][yf_t])) else 0
        results.append({
            'ticker':        s['ticker'],
            'name':          s['name'],
            'market':        s['market'],
            'close':         int(price),
            'change_rate':   round(float(chg), 2),
            'volume':        vol,
            'market_cap':    s['marcap'],
            'market_cap_억': s['marcap_억'],
        })
    results.sort(key=lambda x: x['change_rate'])
    return results

def run_populate(days_back=90):
    os.makedirs('data', exist_ok=True)

    print("종목 목록 로드 중...")
    tickers    = load_tickers()
    ticker_map = {t['yf_ticker']: t for t in tickers}
    yf_tickers = list(ticker_map.keys())
    print(f"총 {len(tickers)}개 종목")

    end_date     = datetime.now() - timedelta(days=1)
    start_date   = end_date - timedelta(days=days_back)
    trading_days = get_trading_days(start_date, end_date)
    print(f"거래일: {len(trading_days)}개")

    dl_start = (start_date - timedelta(days=10)).strftime('%Y-%m-%d')
    dl_end   = (end_date   + timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"가격 데이터 다운로드: {dl_start} ~ {dl_end}")
    closes, opens, volumes = bulk_download(yf_tickers, dl_start, dl_end)
    print(f"다운로드 완료: {closes.shape[0]}일 × {closes.shape[1]}종목")

    all_backtest = []

    for i, date_str in enumerate(trading_days):
        screen_file = f'data/screening_{date_str}.json'

        if os.path.exists(screen_file):
            with open(screen_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if existing.get('count', 0) > 0:
                print(f"[{i+1}/{len(trading_days)}] {date_str} 스킵 ({existing['count']}개)")
                stocks_today = existing['stocks']
            else:
                stocks_today = screen_from_bulk(closes, opens, volumes, date_str, ticker_map)
                existing = {'date': date_str, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'count': len(stocks_today), 'stocks': stocks_today}
                with open(screen_file, 'w', encoding='utf-8') as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
                print(f"[{i+1}/{len(trading_days)}] {date_str} → {len(stocks_today)}개")
        else:
            stocks_today = screen_from_bulk(closes, opens, volumes, date_str, ticker_map)
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
                n_idx = closes.index.strftime('%Y%m%d') == next_date
                if n_idx.any():
                    n_pos = closes.index.get_loc(closes.index[n_idx][0])
                    for s in stocks_today:
                        yf_t = s['ticker'] + ('.KS' if s['market'] == 'KOSPI' else '.KQ')
                        if yf_t not in closes.columns:
                            continue
                        nc = closes.iloc[n_pos][yf_t]
                        no = opens.iloc[n_pos][yf_t] if not opens.empty and yf_t in opens.columns else nc
                        if pd.isna(nc) or s['close'] == 0:
                            continue
                        bt_results.append({
                            **s,
                            'screen_date':        date_str,
                            'next_date':          next_date,
                            'screen_change_rate': s['change_rate'],
                            'next_open':          int(no) if not pd.isna(no) else 0,
                            'next_close':         int(nc),
                            'open_return':        round((no - s['close']) / s['close'] * 100, 2) if not pd.isna(no) else 0,
                            'close_return':       round((nc - s['close']) / s['close'] * 100, 2),
                        })
                with open(bt_file, 'w', encoding='utf-8') as f:
                    json.dump({'screen_date': date_str, 'next_date': next_date, 'count': len(bt_results), 'results': bt_results}, f, ensure_ascii=False, indent=2)
                all_backtest.extend(bt_results)

    # 누적 히스토리
    history_file = 'data/backtest_history.json'
    existing_h = []
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            existing_h = json.load(f)
    keys     = {(r['ticker'], r.get('screen_date','')) for r in existing_h}
    new_recs = [r for r in all_backtest if (r['ticker'], r.get('screen_date','')) not in keys]
    combined = (existing_h + new_recs)[-2000:]
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
