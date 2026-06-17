"""
네이버 금융 sise_fall 페이지에서 당일 하락 종목 수집
→ yfinance로 기술 지표 계산 후 점수 부여
해외 IP에서도 정상 작동
"""
import json
import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import yfinance as yf
import pandas as pd
from score import score_stock, score_label

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def get_naver_losers(market_code, market_name):
    """네이버 금융 등락률 하위 종목 (sise_fall)"""
    results = []

    for page in range(1, 6):  # 최대 5페이지 (250종목)
        url = f'https://finance.naver.com/sise/sise_fall.naver?sosok={market_code}&page={page}'
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.content, 'html.parser')
            table = soup.find('table', class_='type_2')
            if not table:
                break

            rows = table.find_all('tr')
            found = 0

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 9:
                    continue
                name_el = cols[1].find('a')
                if not name_el or 'code=' not in name_el.get('href', ''):
                    continue

                ticker = name_el['href'].split('code=')[1]
                name   = name_el.text.strip()

                try:
                    price       = int(cols[2].text.strip().replace(',', ''))
                    change_rate = float(cols[4].text.strip().replace(',', '').replace('%', ''))
                    volume      = int(cols[6].text.strip().replace(',', '') or 0)
                    marcap_text = cols[7].text.strip().replace(',', '').replace('-', '0')
                    marcap      = int(marcap_text) * 100_000_000  # 억 → 원
                except:
                    continue

                # 하락률 -5% ~ -12%, 시가총액 1000억 ~ 5조
                if not (-12 <= change_rate <= -5):
                    if change_rate > -5:
                        break  # 정렬된 페이지에서 더 이상 조건 충족 안 됨
                    continue

                if not (100_000_000_000 <= marcap <= 5_000_000_000_000):
                    continue

                results.append({
                    'ticker':        ticker,
                    'name':          name,
                    'market':        market_name,
                    'close':         price,
                    'change_rate':   change_rate,
                    'volume':        volume,
                    'market_cap':    marcap,
                    'market_cap_억': round(marcap / 100_000_000, 0),
                    'score':         0,
                    'score_label':   '',
                    'indicators':    {},
                })
                found += 1

            if found == 0:
                break
            time.sleep(0.2)

        except Exception as e:
            print(f"  {market_name} page {page} 오류: {e}")
            break

    return results

def add_scores(stocks: list) -> list:
    """yfinance로 과거 데이터를 받아 각 종목에 점수 계산"""
    print(f"  기술 지표 계산 중 ({len(stocks)}개)...")
    for s in stocks:
        suffix = '.KS' if s['market'] == 'KOSPI' else '.KQ'
        yf_t   = s['ticker'] + suffix
        try:
            hist = yf.download(yf_t, period='1y', auto_adjust=True, progress=False)
            if hist.empty or len(hist) < 20:
                continue
            closes  = hist['Close'].squeeze()
            volumes = hist['Volume'].squeeze()
            sc, det = score_stock(closes.iloc[:-1], volumes.iloc[:-1],
                                  s['volume'], s['close'], s['change_rate'])
            s['score']       = sc
            s['score_label'] = score_label(sc)
            s['indicators']  = det
        except Exception as e:
            print(f"    {s['ticker']} 지표 오류: {e}")
        time.sleep(0.1)
    return stocks


def run_screening():
    today = datetime.now().strftime('%Y%m%d')
    print(f"스크리닝 날짜: {today}")

    results = []
    for code, name in [(0, 'KOSPI'), (1, 'KOSDAQ')]:
        losers = get_naver_losers(code, name)
        print(f"  {name}: {len(losers)}개")
        results.extend(losers)

    results = add_scores(results)
    results.sort(key=lambda x: (-x['score'], x['change_rate']))

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

    print(f"완료: {len(results)}개")

if __name__ == '__main__':
    run_screening()
