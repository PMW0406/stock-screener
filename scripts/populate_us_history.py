"""
과거 날짜별 미국 시장 데이터 수집
각 screening_YYYYMMDD.json 에 대응하는 미국 지수 데이터를 us_YYYYMMDD.json 으로 저장
"""
import json
import os
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd

US_SYMBOLS = {
    'S&P 500':   '^GSPC',
    'NASDAQ':    '^IXIC',
    '다우존스':   '^DJI',
    'VIX':       '^VIX',
    '달러인덱스': 'DX-Y.NYB',
}

def get_us_data_for_date(date_str):
    """특정 날짜(한국시간)의 미국 장 마감 데이터 (= 그날 밤)"""
    date = datetime.strptime(date_str, '%Y%m%d')
    # 미국 시장은 한국 시간 기준 전날 ~ 당일 새벽에 마감
    # date_str 날 한국 밤 = 미국 date_str 날 마감
    start = (date - timedelta(days=3)).strftime('%Y-%m-%d')
    end   = (date + timedelta(days=1)).strftime('%Y-%m-%d')

    result = {}
    for name, symbol in US_SYMBOLS.items():
        try:
            hist = yf.download(symbol, start=start, end=end,
                               auto_adjust=True, progress=False)
            if hist.empty:
                continue
            closes = hist['Close']
            # date_str 당일 데이터
            target = closes[closes.index.strftime('%Y%m%d') == date_str]
            if target.empty:
                # 미국 시장은 한국 날짜와 하루 차이날 수 있음 → 직전 거래일
                target = closes[closes.index.strftime('%Y%m%d') <= date_str]
                if target.empty:
                    continue
                target = target.iloc[[-1]]

            pos = closes.index.get_loc(target.index[0])
            curr = float(closes.iloc[pos])
            if pos == 0:
                continue
            prev = float(closes.iloc[pos - 1])
            change_pct = (curr - prev) / prev * 100

            result[name] = {
                'current':    round(curr, 2),
                'change_pct': round(change_pct, 2),
            }
        except Exception as e:
            print(f"  {name} 오류: {e}")

    return result

def run():
    os.makedirs('data', exist_ok=True)

    # 스크리닝 파일 목록
    screen_dates = sorted([
        f.replace('screening_', '').replace('.json', '')
        for f in os.listdir('data')
        if f.startswith('screening_') and 'latest' not in f
    ])

    print(f"총 {len(screen_dates)}개 날짜 처리")

    for i, date_str in enumerate(screen_dates):
        us_file = f'data/us_{date_str}.json'
        if os.path.exists(us_file):
            print(f"[{i+1}/{len(screen_dates)}] {date_str} 스킵")
            continue

        print(f"[{i+1}/{len(screen_dates)}] {date_str} 미국 데이터 수집...")
        us_data = get_us_data_for_date(date_str)

        output = {
            'date':       date_str,
            'market_data': us_data,
        }
        with open(us_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        sp = us_data.get('S&P 500', {})
        print(f"  S&P500: {sp.get('change_pct', 'N/A')}%")

    print("완료!")

if __name__ == '__main__':
    run()
