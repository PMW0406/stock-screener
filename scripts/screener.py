import json
import os
from datetime import datetime
import pandas as pd
from pykrx import stock

def screen_date(date_str):
    results = []
    for market in ['KOSPI', 'KOSDAQ']:
        try:
            ohlcv = stock.get_market_ohlcv_by_ticker(date_str, market=market)
            cap   = stock.get_market_cap_by_ticker(date_str, market=market)

            if ohlcv.empty or cap.empty:
                print(f"  {market} 데이터 없음 ({date_str})")
                continue

            # 공통 ticker만 사용 (join NaN 방지)
            common = ohlcv.index.intersection(cap.index)
            df = ohlcv.loc[common].copy()
            df['시가총액'] = cap.loc[common, '시가총액']

            print(f"  {market}: 전체 {len(df)}개 → ", end='')

            # 하락률 -5% ~ -12%
            df = df[(df['등락률'] <= -5) & (df['등락률'] >= -12)]
            # 시가총액 1000억 ~ 5조
            df = df[
                (df['시가총액'] >= 100_000_000_000) &
                (df['시가총액'] <= 5_000_000_000_000)
            ]
            print(f"필터 후 {len(df)}개")

            for ticker, row in df.iterrows():
                try:
                    name = stock.get_market_ticker_name(ticker)
                except:
                    name = ticker
                results.append({
                    'ticker': ticker,
                    'name': name,
                    'market': market,
                    'close': int(row['종가']),
                    'change_rate': round(float(row['등락률']), 2),
                    'volume': int(row['거래량']),
                    'market_cap': int(row['시가총액']),
                    'market_cap_억': round(row['시가총액'] / 100_000_000, 0),
                })
        except Exception as e:
            print(f"  {market} 오류: {e}")

    results.sort(key=lambda x: x['change_rate'])
    return results

def run_screening():
    today = datetime.now().strftime('%Y%m%d')
    print(f"스크리닝 날짜: {today}")
    results = screen_date(today)

    output = {
        'date': today,
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'count': len(results),
        'stocks': results,
    }

    os.makedirs('data', exist_ok=True)
    with open('data/latest_screening.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(f'data/screening_{today}.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"완료: {len(results)}개 종목")

if __name__ == '__main__':
    run_screening()
