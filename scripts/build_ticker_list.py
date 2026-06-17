"""
네이버 금융에서 KOSPI/KOSDAQ 전체 종목 목록 수집
→ data/kr_tickers.json 저장
해외 IP에서도 접속 가능
"""
import json
import os
import time
import requests
from bs4 import BeautifulSoup

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def get_naver_tickers(market_code, market_name, suffix):
    """네이버 금융 시가총액 순 전체 종목 수집"""
    tickers = []
    page = 1

    while True:
        url = f'https://finance.naver.com/sise/sise_market_sum.naver?sosok={market_code}&page={page}'
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

                # 시가총액: 8번째 열, 억원 단위
                try:
                    marcap_text = cols[7].text.strip().replace(',', '').replace('-', '0')
                    marcap = int(marcap_text) * 100_000_000
                except:
                    marcap = 0

                tickers.append({
                    'ticker':    ticker,
                    'name':      name,
                    'market':    market_name,
                    'yf_ticker': ticker + suffix,
                    'marcap':    marcap,
                    'marcap_억': round(marcap / 100_000_000, 0),
                })
                found += 1

            print(f"  {market_name} page {page}: {found}개")
            if found == 0:
                break
            page += 1
            time.sleep(0.3)

        except Exception as e:
            print(f"  page {page} 오류: {e}")
            break

    return tickers

def build_ticker_list():
    os.makedirs('data', exist_ok=True)
    all_tickers = []

    print("KOSPI 종목 수집 중...")
    kospi = get_naver_tickers(0, 'KOSPI', '.KS')
    all_tickers.extend(kospi)

    print("KOSDAQ 종목 수집 중...")
    kosdaq = get_naver_tickers(1, 'KOSDAQ', '.KQ')
    all_tickers.extend(kosdaq)

    # 시가총액 1000억 ~ 5조 필터
    filtered = [t for t in all_tickers if 100_000_000_000 <= t['marcap'] <= 5_000_000_000_000]

    output = {
        'updated_at': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(all_tickers),
        'filtered': len(filtered),
        'tickers': filtered,
    }

    with open('data/kr_tickers.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n완료: 전체 {len(all_tickers)}개 → 필터 후 {len(filtered)}개")

if __name__ == '__main__':
    build_ticker_list()
