import json
import os
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr

def get_kr_stocks():
    """KOSPI + KOSDAQ 종목 목록 (시가총액 필터 포함)"""
    stocks = []
    for market, suffix in [('KOSPI', '.KS'), ('KOSDAQ', '.KQ')]:
        try:
            listing = fdr.StockListing(market)
            print(f"  {market} 종목 수: {len(listing)}, 컬럼: {listing.columns.tolist()[:5]}")

            sym_col  = next((c for c in listing.columns if c in ('Symbol','Code')), None)
            cap_col  = next((c for c in listing.columns if 'Marcap' in c or 'MarketCap' in c or '시가총액' in c), None)
            name_col = next((c for c in listing.columns if c in ('Name','종목명')), None)

            if not sym_col or not cap_col or not name_col:
                print(f"  {market} 필요 컬럼 없음")
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
            print(f"  {market} 필터 후: {len([s for s in stocks if s['market'] == market])}개")
        except Exception as e:
            print(f"  {market} 리스팅 오류: {e}")
    return stocks

def screen_date(date_str, stocks):
    date  = datetime.strptime(date_str, '%Y%m%d')
    start = (date - timedelta(days=10)).strftime('%Y-%m-%d')
    end   = (date + timedelta(days=1)).strftime('%Y-%m-%d')

    results    = []
    yf_tickers = [s['yf_ticker'] for s in stocks]
    ticker_map = {s['yf_ticker']: s for s in stocks}

    BATCH = 200
    for i in range(0, len(yf_tickers), BATCH):
        chunk = yf_tickers[i:i + BATCH]
        try:
            raw = yf.download(chunk, start=start, end=end, auto_adjust=True,
                              progress=False, threads=True)
            if raw.empty:
                continue

            # MultiIndex 처리
            if isinstance(raw.columns, pd.MultiIndex):
                closes  = raw['Close']
                volumes = raw['Volume'] if 'Volume' in raw.columns.get_level_values(0) else None
            else:
                closes  = raw[['Close']].rename(columns={'Close': chunk[0]})
                volumes = None

            date_idx = closes.index.strftime('%Y%m%d') == date_str
            if not date_idx.any():
                continue

            pos = closes.index.get_loc(closes.index[date_idx][0])
            if pos == 0:
                continue

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
                s = ticker_map[yf_t]
                vol = int(volumes.iloc[pos][yf_t]) if volumes is not None and yf_t in volumes.columns else 0
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
        except Exception as e:
            print(f"  배치 오류 ({i}~{i+BATCH}): {e}")

    results.sort(key=lambda x: x['change_rate'])
    return results

def run_screening():
    today = datetime.now().strftime('%Y%m%d')
    print(f"스크리닝 날짜: {today}")

    print("종목 목록 가져오는 중...")
    stocks = get_kr_stocks()
    print(f"총 {len(stocks)}개 종목 대상")

    results = screen_date(today, stocks)

    output = {
        'date':       today,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'count':      len(results),
        'stocks':     results,
    }

    os.makedirs('data', exist_ok=True)
    with open('data/latest_screening.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(f'data/screening_{today}.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"완료: {len(results)}개 종목")

if __name__ == '__main__':
    run_screening()
