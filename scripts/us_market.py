import json
import os
from datetime import datetime
import google.generativeai as genai
import yfinance as yf

def get_us_market_data():
    symbols = {
        '^GSPC': 'S&P 500',
        '^IXIC': 'NASDAQ',
        '^DJI': '다우존스',
        '^VIX': 'VIX 공포지수',
        'DX-Y.NYB': '달러인덱스',
    }
    data = {}
    for symbol, name in symbols.items():
        try:
            hist = yf.Ticker(symbol).history(period='2d')
            if len(hist) >= 2:
                prev = hist['Close'].iloc[-2]
                curr = hist['Close'].iloc[-1]
                data[name] = {
                    'current': round(float(curr), 2),
                    'change_pct': round((curr - prev) / prev * 100, 2),
                }
        except Exception as e:
            print(f"{name} 오류: {e}")
    return data

def analyze_with_gemini(market_data, screening_data):
    genai.configure(api_key=os.environ['GEMINI_API_KEY'])
    model = genai.GenerativeModel('gemini-1.5-flash')

    market_lines = '\n'.join(
        f"- {name}: {d['current']} ({'+' if d['change_pct'] >= 0 else ''}{d['change_pct']}%)"
        for name, d in market_data.items()
    )

    stocks = screening_data.get('stocks', [])[:20]
    stocks_lines = '\n'.join(
        f"- {s['name']}({s['ticker']}, {s['market']}): {s['change_rate']}% 하락, 시총 {int(s['market_cap_억'])}억원"
        for s in stocks
    ) if stocks else '오늘 해당 종목 없음'

    prompt = f"""오늘 한국 주식시장에서 다음 종목들이 5~12% 크게 하락했습니다.
미국 증시 상황을 분석해서 내일 반등 가능성을 평가해주세요.

[미국 증시 현황 (현재 기준)]
{market_lines}

[오늘 한국 하락 종목 ({screening_data.get('count', 0)}개)]
{stocks_lines}

아래 형식으로 한국어로 답변해주세요:

## 미국 증시 분위기
(전반적인 시장 분위기 2~3문장)

## 내일 한국 시장 영향
(미국 증시가 내일 한국 시장에 미칠 영향 2~3문장)

## 반등 주목 종목 TOP 5
(위 하락 종목 중 반등 가능성이 높은 종목과 이유. 종목이 없으면 생략)

## 리스크 요인
(주의해야 할 점 2~3가지)"""

    response = model.generate_content(prompt)
    return response.text

def run_us_analysis():
    market_data = get_us_market_data()

    screening_data = {}
    if os.path.exists('data/latest_screening.json'):
        with open('data/latest_screening.json', 'r', encoding='utf-8') as f:
            screening_data = json.load(f)

    analysis = analyze_with_gemini(market_data, screening_data)

    output = {
        'date': datetime.now().strftime('%Y%m%d'),
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'market_data': market_data,
        'analysis': analysis,
    }

    os.makedirs('data', exist_ok=True)
    with open('data/latest_us_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("미국 시장 분석 완료")

if __name__ == '__main__':
    run_us_analysis()
