import json
import os
from datetime import datetime
from groq import Groq
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

def analyze_with_groq(market_data, screening_data):
    client = Groq(api_key=os.environ['GROQ_API_KEY'])

    market_lines = '\n'.join(
        f"- {name}: {d['current']} ({'+' if d['change_pct'] >= 0 else ''}{d['change_pct']}%)"
        for name, d in market_data.items()
    )

    stocks = screening_data.get('stocks', [])[:20]
    stocks_lines = '\n'.join(
        f"- {s['name']}({s['ticker']}, {s['market']}): {s['change_rate']}% 하락, "
        f"점수 {s.get('score', '?')}/12, "
        f"RSI {s.get('indicators', {}).get('rsi', '?')}, "
        f"거래량배율 {s.get('indicators', {}).get('vol_ratio', '?')}x, "
        f"시총 {int(s['market_cap_억'])}억원"
        for s in stocks
    ) if stocks else '오늘 해당 종목 없음'

    stocks_json = json.dumps(
        [{'ticker': s['ticker'], 'name': s['name'], 'market': s['market'],
          'close': s['close'], 'change_rate': s['change_rate'],
          'market_cap_억': int(s['market_cap_억']),
          'score': s.get('score', 0),
          'indicators': s.get('indicators', {})}
         for s in screening_data.get('stocks', [])[:30]],
        ensure_ascii=False
    )

    prompt = f"""당신은 한국 주식 단기 트레이딩 전문가입니다.
어제 한국 주식시장에서 5~12% 하락한 종목들이 있습니다.
미국 증시 마감 결과를 보고, 오늘 한국 장 개장 시 반등 가능성을 분석해주세요.

[미국 증시 현황]
{market_lines}

[어제 한국 하락 종목 ({screening_data.get('count', 0)}개)]
{stocks_lines}

각 종목의 점수(0~12)는 RSI, 거래량 급증, 52주 저점 거리, 이동평균 위치를 종합한 반등 가능성 지표입니다.
점수가 높을수록 반등 신호가 강하므로, 점수 높은 종목을 우선 고려하되 미국 시장 분위기와 함께 판단하세요.

아래 JSON 형식으로만 답변하세요. 다른 텍스트 없이 JSON만 출력하세요:

{{
  "market_summary": "미국 증시 전반적 분위기 2~3문장",
  "kr_market_outlook": "오늘 한국 시장 예상 2~3문장",
  "buy_candidates": [
    {{
      "ticker": "종목코드",
      "name": "종목명",
      "reason": "반등 예상 이유 (미국 시장과 연관지어 구체적으로)"
    }}
  ],
  "risk_factors": "오늘 매수 시 주의사항 2~3가지"
}}

buy_candidates는 반등 가능성 높은 순서로 최대 5개. 종목이 없으면 빈 배열 [].
반드시 위 하락 종목 목록에 있는 종목만 선택하세요."""

    response = client.chat.completions.create(
        model='llama-3.3-70b-versatile',
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=2000,
    )
    text = response.choices[0].message.content.strip()
    # JSON 파싱 시도
    try:
        start = text.find('{')
        end   = text.rfind('}') + 1
        return json.loads(text[start:end])
    except:
        return {'market_summary': text, 'kr_market_outlook': '', 'buy_candidates': [], 'risk_factors': ''}

def run_us_analysis():
    market_data = get_us_market_data()

    screening_data = {}
    if os.path.exists('data/latest_screening.json'):
        with open('data/latest_screening.json', 'r', encoding='utf-8') as f:
            screening_data = json.load(f)

    analysis = analyze_with_groq(market_data, screening_data)

    output = {
        'date': datetime.now().strftime('%Y%m%d'),
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'market_data': market_data,
        'analysis': analysis,
        'screening_date': screening_data.get('date', ''),
        'screening_count': screening_data.get('count', 0),
    }

    os.makedirs('data', exist_ok=True)
    with open('data/latest_us_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("미국 시장 분석 완료")

if __name__ == '__main__':
    run_us_analysis()
