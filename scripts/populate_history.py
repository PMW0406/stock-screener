"""
과거 데이터 수집 스크립트
- 최근 90일치 하락 종목 스크리닝 + 다음날 수익률 백테스트 데이터를 한번에 생성
- GitHub Actions에서 최초 1회 실행하거나 수동으로 실행
"""
import json
import os
import time
from datetime import datetime, timedelta
import pandas as pd
from pykrx import stock

def get_trading_days(start_date, end_date):
    """거래일 목록 반환"""
    days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:  # 월~금
            days.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)
    return days

def screen_date(date_str):
    """특정 날짜의 하락 종목 스크리닝"""
    results = []
    for market in ['KOSPI', 'KOSDAQ']:
        try:
            ohlcv = stock.get_market_ohlcv_by_ticker(date_str, market=market)
            if ohlcv.empty:
                continue
            cap = stock.get_market_cap_by_ticker(date_str, market=market)
            df = ohlcv.join(cap[['시가총액']])
            df = df[(df['등락률'] <= -5) & (df['등락률'] >= -12)]
            df = df[
                (df['시가총액'] >= 100_000_000_000) &
                (df['시가총액'] <= 5_000_000_000_000)
            ]
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

def get_next_day_returns(stocks, next_date_str):
    """다음 거래일 수익률 계산"""
    results = []
    for s in stocks:
        try:
            ohlcv = stock.get_market_ohlcv(next_date_str, next_date_str, s['ticker'])
            if ohlcv.empty:
                continue
            next_open = int(ohlcv.iloc[0]['시가'])
            next_close = int(ohlcv.iloc[0]['종가'])
            prev_close = s['close']
            results.append({
                **s,
                'screen_date': s.get('date', ''),
                'next_date': next_date_str,
                'next_open': next_open,
                'next_close': next_close,
                'open_return': round((next_open - prev_close) / prev_close * 100, 2),
                'close_return': round((next_close - prev_close) / prev_close * 100, 2),
            })
        except:
            pass
    return results

def run_populate(days_back=90):
    os.makedirs('data', exist_ok=True)

    end_date = datetime.now() - timedelta(days=1)
    start_date = end_date - timedelta(days=days_back)
    trading_days = get_trading_days(start_date, end_date)

    print(f"총 {len(trading_days)}개 거래일 처리 중...")

    all_backtest = []

    for i, date_str in enumerate(trading_days):
        screen_file = f'data/screening_{date_str}.json'

        # 이미 있으면 스킵
        if os.path.exists(screen_file):
            print(f"[{i+1}/{len(trading_days)}] {date_str} 이미 존재, 스킵")
            with open(screen_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            stocks = data.get('stocks', [])
        else:
            print(f"[{i+1}/{len(trading_days)}] {date_str} 스크리닝 중...")
            stocks = screen_date(date_str)
            output = {
                'date': date_str,
                'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'count': len(stocks),
                'stocks': stocks,
            }
            with open(screen_file, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"  → {len(stocks)}개 종목")
            time.sleep(0.5)  # API 과부하 방지

        # 다음 거래일 수익률
        if stocks and i + 1 < len(trading_days):
            next_date = trading_days[i + 1]
            bt_file = f'data/backtest_{date_str}.json'
            if not os.path.exists(bt_file):
                print(f"  백테스트: {date_str} → {next_date}")
                for s in stocks:
                    s['date'] = date_str
                bt_results = get_next_day_returns(stocks, next_date)
                with open(bt_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'screen_date': date_str,
                        'next_date': next_date,
                        'count': len(bt_results),
                        'results': bt_results,
                    }, f, ensure_ascii=False, indent=2)
                all_backtest.extend(bt_results)
                time.sleep(0.5)

    # 전체 히스토리 저장
    history_file = 'data/backtest_history.json'
    existing = []
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    existing_keys = {(r['ticker'], r.get('screen_date', '')) for r in existing}
    new_records = [r for r in all_backtest if (r['ticker'], r.get('screen_date', '')) not in existing_keys]
    combined = existing + new_records
    combined = combined[-2000:]

    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    # 날짜 목록 저장 (프론트엔드용)
    date_list = sorted([
        f.replace('screening_', '').replace('.json', '')
        for f in os.listdir('data')
        if f.startswith('screening_') and f != 'screening_latest.json'
    ], reverse=True)

    with open('data/date_list.json', 'w', encoding='utf-8') as f:
        json.dump(date_list, f)

    print(f"\n완료! 총 {len(combined)}개 백테스트 레코드")

if __name__ == '__main__':
    run_populate(days_back=90)
