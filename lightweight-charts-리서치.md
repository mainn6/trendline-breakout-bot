# TradingView Lightweight Charts 딥 리서치
*작성일: 2026-05-06 · 출처: 30+ · 신뢰도: 높음*

## TL;DR
- **TradingView가 직접 만든 오픈소스 금융 차트 라이브러리**. Apache-2.0이지만 **TradingView 표기 의무** 있음.
- **번들 35KB(코어) ~ 61KB(standalone) gzip**, 동급 최저. Canvas 기반으로 **5만 캔들도 부드럽게**.
- **트레이딩 차트 한 종류만** 잘함 — 파이/레이더/지도 없음. 기술적 지표 내장 X (직접 구현).
- **v5에서 큰 breaking change**: `addCandlestickSeries()` 같은 메서드 전부 제거 → `addSeries(CandlestickSeries, options)` 통합.
- **결론**: 트레이딩/암호화폐 차트만 필요 → lightweight-charts. 풀 트레이딩(40+ 지표 내장)+예산 OK → Highcharts Stock(유료). 무료 풀스펙+큰 번들 OK → ECharts.

---

## 1. 개요

- **메이커**: TradingView. GitHub ~15.6k stars, ~2.4k forks ([repo](https://github.com/tradingview/lightweight-charts))
- **기조**: "가장 작고 빠른 금융 차트". 정적 이미지 차트를 인터랙티브로 대체.
- **번들**: 코어 ~35KB gzip(공식), standalone ~61KB gzip / 191KB raw ([bundlephobia](https://bundlephobia.com/api/size?package=lightweight-charts))
- **의존성**: 0개. TypeScript 선언 내장.

## 2. 핵심 기능

| 항목 | 내용 |
|---|---|
| 시리즈 타입 | Area, Bar, Baseline, **Candlestick**, **Histogram**(거래량), Line ([docs](https://tradingview.github.io/lightweight-charts/docs)) |
| 인터랙션 | zoom/pan, crosshair, hit-testing(v5.2), 시간축 자동 처리 |
| Pane(다중 패널) | v5부터 정식 지원 (`addPane`, `setStretchFactor`) |
| 플러그인 | Custom series API, Watermark·Series Markers는 v5에서 플러그인으로 분리 |
| 기술적 지표 | **내장 없음** — `indicator-examples` 폴더 참고하여 직접 구현 |
| 실시간 | `series.update()` (setData 반복 X) |

## 3. 라이선스 — 함정 주의

- **Apache-2.0** + **NOTICE 파일** ([NOTICE](https://github.com/tradingview/lightweight-charts/blob/master/NOTICE))
- 사이트/앱의 **공개 페이지에 TradingView 표기 + tradingview.com 링크 노출 의무**
- 가장 쉬운 해결: `attributionLogo: true` 옵션으로 차트 안에 자동 워터마크 표시 → 요건 충족
- 빠뜨리면 라이선스 위반. 상업적 사용은 가능하지만 attribution은 필수.

## 4. v5 주요 변경점 ([release notes](https://tradingview.github.io/lightweight-charts/docs/release-notes))

```js
// v4
const series = chart.addCandlestickSeries({ ... });

// v5
import { CandlestickSeries } from 'lightweight-charts';
const series = chart.addSeries(CandlestickSeries, { ... });
```

- 통합 시리즈 API (`addSeries(SeriesType, options)`)
- CommonJS 지원 중단, ES2020 타깃
- 멀티 pane 정식 지원
- Watermark/Markers → 플러그인
- v5.2: hit testing, `hoveredSeriesOnTop`, `tickMarkDensity` 추가
- 마이그레이션 가이드: [v4→v5](https://tradingview.github.io/lightweight-charts/docs/migrations/from-v4-to-v5), 이슈 [#1791](https://github.com/tradingview/lightweight-charts/issues/1791)

## 5. 경쟁 라이브러리 비교

### 번들 사이즈 (gzip)
| 라이브러리 | gzip | 비고 |
|---|---|---|
| **lightweight-charts** | **35~61KB** | 동급 최저 |
| Chart.js | 68KB | |
| D3.js (full) | 92KB | 트리쉐이킹 가능 |
| Highcharts (core) | 100KB | Stock 모듈 추가 시 더 큼 |
| ApexCharts | 138KB | |
| Recharts | 139KB | + React peer |
| ECharts | 362KB | |
| Plotly.js | **1.39MB** | 압도적 최대 |

출처: bundlephobia 각 패키지

### 라이선스/비용
- **무료(MIT/Apache-2.0)**: lightweight-charts(표기 의무), Chart.js, ApexCharts, ECharts, Recharts, Plotly.js, D3
- **유료**: Highcharts Stock ($185~366/seat, [shop.highcharts.com](https://shop.highcharts.com/)), AnyChart Stock ($49~$1,499)

### 금융 차트 특화도
- **lightweight-charts**: 캔들·거래량·시간축 zoom·streaming이 1급 시민
- **Highcharts Stock**: 40+ 내장 지표(SMA/MACD/RSI/Bollinger/Ichimoku), Navigator, Range selector ([products/stock](https://www.highcharts.com/products/stock/))
- **ApexCharts/ECharts/Plotly**: 캔들 내장, 지표·navigator는 직접 구현
- **Chart.js**: `chartjs-chart-financial` 플러그인 필요
- **Recharts/D3**: 캔들 내장 X, 직접 구현

### 성능 (50K+ candles)
- **lightweight-charts**: Canvas, 수만 bar 실시간 streaming OK
- **ECharts**: incremental + TypedArray로 수백만 포인트
- **Highcharts Stock**: WebGL boost module로 수백만 점
- **Chart.js/ApexCharts/Recharts**: 5만 점 권장 X

### Best-fit 결정표
| 상황 | 추천 |
|---|---|
| 트레이딩 차트만 + 작은 번들 | **lightweight-charts** |
| 풀 트레이딩 + 40+ 지표 + 예산 OK | **Highcharts Stock** |
| 풀 스펙 + 무료 + 큰 번들 OK | **ECharts** |
| 범용 대시보드(파이/바/라인) | **Chart.js / ApexCharts** |
| React SPA, 다양한 차트 | **Recharts** |
| 과학·통계·3D·지도 | **Plotly.js** |
| 픽셀 단위 풀커스텀 | **D3** |

## 6. 프로덕션 사용 사례

- BuiltWith 추적 기준 다수 핀테크/암호화폐 사이트 ([trends.builtwith.com](https://trends.builtwith.com/websitelist/TradingView-Lightweight-Charts))
- Binance·Coinbase·Upbit 등 **대형 거래소는 자체 차트 또는 TradingView "Advanced Charts" 위젯**(별개 유료/임베드 제품)을 더 많이 사용. lightweight-charts는 **스타트업·대시보드·플러그인** 위주
- 업비트는 TradingView 차트 위젯 임베드 ([upbit 공지](https://support.upbit.com/hc/ko/articles/30759334096153))
- Plotly Dash 통합 사례 ([Dash community](https://community.plotly.com/t/show-and-tell-dash-tradingview-light-weight-charts/72958))

## 7. 한국 개발자 후기/팁 ([Velog @hoan_c](https://velog.io/@hoan_c/lightweight-charts-%EC%82%AC%EC%9A%A9%EB%B2%95), [@mxxn](https://velog.io/@mxxn/React-TypeScript-TradingView-lightweight-charts-%EC%82%AC%EC%9A%A9), [@aerirang647](https://velog.io/@aerirang647/light-weight-%EB%9D%BC%EC%9D%B4%EB%B8%8C%EB%9F%AC%EB%A6%AC-%EC%82%AC%EC%9A%A9%ED%95%98%EA%B8%B0))

- "createChart + addSeries 두 개념만 알면 끝" — 학습 곡선은 매우 낮음
- React useRef 패턴이 표준. cleanup에 `chart.remove()` 필수
- StrictMode 이중 렌더 대비 ref guard 추가
- `autoSize: true`로 ResizeObserver 위임 (v4 후기 추가)
- 다크모드는 `applyOptions`로 토글 (재생성 X)
- 한국시간 표시: `localization.timeFormatter` 또는 timestamp에 +9h(32400초) 더하기 — 공식 timezone 옵션 없음

## 8. 자주 만나는 함정

| 증상 | 원인/해결 |
|---|---|
| 차트가 안 보임 | 부모 컨테이너 height=0 → 명시적 높이 or `autoSize:true` |
| 모바일 회전 jitter | v5.2에서 PR #2055로 수정 |
| iOS Safari 캔버스 한계 | 릴리스 노트의 메모리 관련 수정 확인 |
| 언마운트 메모리 누수 | [#1429](https://github.com/tradingview/lightweight-charts/issues/1429) — cleanup에 `chart.remove()` + ResizeObserver disconnect |
| Next.js SSR `window is not defined` | [#543](https://github.com/tradingview/lightweight-charts/issues/543) — `dynamic(() => import('./Chart'), { ssr:false })` |
| 실시간 깜빡임 | `setData` 반복 X → `series.update()` |
| 한국시간 어긋남 | UNIX초 UTC 기준이라 KST는 직접 변환 |
| Pane + crosshair 이슈 | [#1851](https://github.com/tradingview/lightweight-charts/issues/1851) |

## 9. React 래퍼 추천

- `lightweight-charts-react-components` ([repo](https://github.com/ukorvl/lightweight-charts-react-components)) — TS, 활성 유지보수, **v5 호환 추천**
- `lightweight-charts-react-wrapper` ([npm](https://www.npmjs.com/package/lightweight-charts-react-wrapper)) — 선언형이지만 마지막 릴리스 2년 전, v5 미흡
- `kaktana-react-lightweight-charts` — 간단한 래퍼
- **결론**: v5 사용 시 직접 useRef 패턴이 가장 안전. 5~10줄이면 끝남

## 10. 사용 예시 (v5)

```js
import { createChart, CandlestickSeries, HistogramSeries } from 'lightweight-charts';

const chart = createChart(containerEl, {
  width: 800, height: 400,
  layout: { background: { color: '#fff' }, textColor: '#000' },
  timeScale: { timeVisible: true, secondsVisible: false },
});

const candles = chart.addSeries(CandlestickSeries);
candles.setData([
  { time: '2026-05-01', open: 100, high: 110, low: 95, close: 105 },
  // ...
]);

const volume = chart.addSeries(HistogramSeries, { priceScaleId: '' });
volume.setData([{ time: '2026-05-01', value: 12345 }]);

// 실시간
candles.update({ time: '2026-05-01', open: 100, high: 112, low: 95, close: 108 });
```

## 핵심 인사이트

1. **"트레이딩 차트만 한 가지" 도메인 특화 라이브러리**. 욕심내면 안 됨 — 파이/지도/3D 같은 거 하나라도 필요하면 ECharts/Plotly로.
2. **번들 사이즈가 진짜 강점**. 모바일 우선/SaaS 트레이딩 대시보드에서 압도적.
3. **유료 회피 시 사실상 유일한 선택지**. 대안은 ECharts(번들 큼) 또는 Highcharts Stock(유료).
4. **TradingView attribution 의무를 절대 빠뜨리지 말 것** — `attributionLogo: true`로 끝.
5. **v5는 v4와 비호환**. 신규 프로젝트는 v5로, 기존은 마이그레이션 가이드 따라 일괄 변경.
6. **기술적 지표가 비즈니스 핵심이면 lightweight-charts는 부족함** — Highcharts Stock 또는 자체 구현 비용 감안.
