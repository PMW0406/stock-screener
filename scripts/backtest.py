import json
import os
from datetime import datetime, timedelta
from pykrx import stock

def find_latest_screening():
    for days_back in range(1, 6):
        date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
        path = f'data/screening_{date}.json'
        if os.path.exists(path):
            return path, date
    return None, None

def run_backtest():
    today = datetime.now().strftime('%Y%m%d')

    prev_file, prev_date = find_latest_screening()
    if not prev_file:
        print("이전 스크리닝 데이터 없음")
        return

    with open(prev_file, 'r', encoding='utf-8') as f:
        prev_data = json.load(f)

    if not prev_data['stocks']:
        print("이전 스크리닝 종목 없음")
        return

    results = []
    for s in prev_data['stocks']:
        ticker = s['ticker']
        try:
            ohlcv = stock.get_market_ohlcv(today, today, ticker)
            if ohlcv.empty:
                continue
            today_open = int(ohlcv.iloc[0]['시가'])
            today_close = int(ohlcv.iloc[0]['종가'])
            prev_close = s['close']

            results.append({
                'ticker': ticker,
                'name': s['name'],
                'market': s['market'],
                'screen_date': prev_date,
                'screen_close': prev_close,
                'screen_change_rate': s['change_rate'],
                'next_open': today_open,
                'next_close': today_close,
                'open_return': round((today_open - prev_close) / prev_close * 100, 2),
                'close_return': round((today_close - prev_close) / prev_close * 100, 2),
            })
        except Exception as e:
            print(f"{ticker} 오류: {e}")

    # 누적 히스토리 업데이트
    history_file = 'data/backtest_history.json'
    history = []
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)

    history.extend(results)
    history = history[-1000:]  # 최근 1000건 유지

    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    with open('data/latest_backtest.json', 'w', encoding='utf-8') as f:
        json.dump({
            'date': today,
            'screen_date': prev_date,
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'count': len(results),
            'results': results,
        }, f, ensure_ascii=False, indent=2)

    if results:
        avg_open = sum(r['open_return'] for r in results) / len(results)
        avg_close = sum(r['close_return'] for r in results) / len(results)
        win_rate = sum(1 for r in results if r['close_return'] > 0) / len(results) * 100
        print(f"백테스트 완료: {len(results)}개 | 평균 시가수익률 {avg_open:.2f}% | 평균 종가수익률 {avg_close:.2f}% | 승률 {win_rate:.1f}%")

if __name__ == '__main__':
    run_backtest()
