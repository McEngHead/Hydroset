# Hydroset — 통합 수문 분석 시스템

한국 치수계획 기준에 따른 **6단계 홍수량·하도추적 통합 분석** Python GUI 애플리케이션.

---

## 개요

Hydroset은 강우자료 수집부터 하도홍수추적까지 수문설계의 전 단계를 하나의 프로젝트로 관리합니다.
`Main.py`가 프로젝트 관리자 역할을 하며, 각 분석 단계를 독립 서브프로세스로 실행합니다.

```
강우자료 → 확률강우량 → 강우강도식 → 유효우량(GIS) → 홍수량 → 하도추적
  (Step 1)    (Step 2)     (Step 3)      (Step 4)     (Step 5)   (Step 6)
```

---

## 기술 스택

| 분류 | 패키지 |
|---|---|
| GUI | `customtkinter` (Dark mode), `tkinter` |
| 계산 | `numpy`, `scipy`, `pandas` |
| GIS | `geopandas` (EPSG:5186) |
| 출력 | `openpyxl`, `matplotlib` |
| 수문통계 | `lmoments3` (L-Moments / PWM) |

> Python 3.10+ / Windows 10/11 환경에서 개발·검증

---

## 설치

```bash
pip install -r requirements.txt
```

> `lmoments3`가 없을 경우 Step 2 일부 분포(GLO·Wakeby 계열)가 비활성화되지만 나머지는 정상 동작합니다.

---

## 실행

```bash
python Main.py
```

각 모듈 직접 실행 (project_path 생략 시 현재 디렉토리 사용):

```bash
python "1.강우자료수집/01.강우자료분석.py"
python "2.확률강우량분석/02.확률강우량분석.py"
python "3.강우강도식/03.강우강도식.py"
python "4.유효우량/04.유효우량산정.py"
python "5.홍수량산정/05.홍수량산정.py"
python "6.하도추적/06.하도추적.py"
```

---

## 디렉토리 구조

```
Hydroset/
├── Main.py                          # 메인 GUI — 프로젝트 관리자
├── requirements.txt
├── README.md
├── CLAUDE.md                        # AI 코딩 가이드
│
├── 0.Projects/                      # 사용자 프로젝트 (gitignore됨)
│   └── 프로젝트명/
│       ├── project_config.json      # 단계별 출력 경로·상태 기록
│       ├── 프로젝트명_log.txt
│       ├── 프로젝트명_A_*.xlsx      # Step 1 출력
│       ├── 프로젝트명_B_*.xlsx      # Step 2 출력
│       ├── 프로젝트명_C_*.xlsx      # Step 3 출력
│       ├── 프로젝트명_D_*.xlsx      # Step 4 출력
│       ├── 프로젝트명_E_*.xlsx      # Step 5 출력
│       └── 프로젝트명_F_*.xlsx      # Step 6 출력
│
├── 1.강우자료수집/
│   └── 01.강우자료분석.py
├── 2.확률강우량분석/
│   └── 02.확률강우량분석.py
├── 3.강우강도식/
│   └── 03.강우강도식.py
├── 4.유효우량/
│   ├── 04.유효우량산정.py
│   └── CN_AMC_II.xlsx               # CN 참조표 (필수 데이터)
├── 5.홍수량산정/
│   ├── 05.홍수량산정.py
│   └── rainfall_db.sqlite           # Huff 시간분포 DB (필수 데이터)
└── 6.하도추적/
    └── 06.하도추적.py
```

---

## 분석 단계별 현황

### Step 1 — 강우자료 수집

| 항목 | 내용 |
|---|---|
| 기능 | 기상청 AWS/ASOS 시계열 강우 자료 수집 및 지속기간별 최대값 환산 |
| 상태 | **완성** |
| 출력 | `프로젝트명_A_Rainfall_Data.xlsx` |

---

### Step 2 — 확률강우량 분석

| 항목 | 내용 |
|---|---|
| 기능 | FARD Ver.2006 기반 16개 확률분포 적합 (L-Moments/PWM) |
| 상태 | **완성** |
| 분포 | NOR, GAM2, GUM, GEV, GLO, GAM3, LN2, LN3, LP3, LGU2/3, WBU2/3, GPA, WKB4/5 |
| 출력 | `프로젝트명_B_Probability_Rainfall.xlsx` |
| 주의 | GLO 음수 클리핑, Wakeby 이상값 필터링 적용 |

---

### Step 3 — 강우강도식

| 항목 | 내용 |
|---|---|
| 기능 | Talbot · Sherman · Japanese · General 4종 강우강도식 매개변수 최적화 |
| 상태 | **완성** |
| 출력 | `프로젝트명_C_Rainfall_Intensity.xlsx` (`Parameters` 시트, `Intensity_Table` 시트) |

---

### Step 4 — 유효우량 산정

| 항목 | 내용 |
|---|---|
| 기능 | GIS 셰이프파일(유역경계·토지피복·토양도) 중첩 → 가중 CN 산정 → SCS-CN 유효우량 |
| 상태 | **완성** |
| GIS | `geopandas`, EPSG:5186, `CN_AMC_II.xlsx` 참조 |
| AMC 조건 | CN I = 4.2·CN_II / (10 − 0.058·CN_II), CN III = 23·CN_II / (10 + 0.13·CN_II) |
| 출력 | `프로젝트명_D_Effective_Rainfall.xlsx`, `프로젝트명_D_Result_Shape.shp` |

---

### Step 5 — 홍수량 산정

| 항목 | 내용 |
|---|---|
| 기능 | Clark · SCS · Nakayasu 합성단위도 3종 동시 산정 및 비교 |
| 상태 | **완성** |
| 강우분포 | Huff 1~4분위 (지점해석 / 지역해석 / 사용자 직접 입력) |
| 배치계산 | Step 3 결과와 연동 — 전체 재현기간×지속기간 병렬 처리 |
| 출력 | `프로젝트명_E_Flood_Discharge.xlsx` |

---

### Step 6 — 하도홍수추적

| 항목 | 내용 |
|---|---|
| 기능 | 머스킹엄(Muskingum) 방법 기반 다중 유역 하도홍수추적 |
| 상태 | **완성** |
| 방법 | Clark UH + SCS-CN + Muskingum (KWRA CH08 기준) |
| 수문망 | 비주얼 노드 편집기 (드래그·클릭 배치, 포트 클릭 연결) |
| 예제 | 내장 예제망 (100-1440-SW00.dat, 521.9 km², 피크 ~218 m³/s) |
| 출력 | `프로젝트명_F_Flood_Routing_TIMESTAMP.xlsx` |

#### 머스킹엄 공식 (KWRA 수문학 CH08)

```
S = K[xI + (1-x)O]
O₂ = C₁·I₂ + C₂·I₁ + C₃·O₁

C₁ = (-Kx + 0.5Δt) / (K - Kx + 0.5Δt)
C₂ = ( Kx + 0.5Δt) / (K - Kx + 0.5Δt)
C₃ = (K - Kx - 0.5Δt) / (K - Kx + 0.5Δt)

안정 조건: 2Kx ≤ Δt ≤ 2K(1-x)
불안정 시 NSTPS = ⌈Δt / 2K(1-x)⌉ 자동 세분할
```

#### 수문망 편집기 노드 타입

| 노드 | 색상 | 대응 연산 | 매개변수 |
|---|---|---|---|
| 소유역 | 녹색 | BASIN (Clark UH) | A, PB, CN, Tc, R |
| 하도구간 | 청색 | ROUTE (Muskingum) | K, X, NSTPS |
| 합류점 | 파랑 원 | COMBINE (합산) | N 자동 결정 |
| 출구 | 보라 | 최종 유출점 | — |

---

## project_config.json 구조

```json
{
  "step4_effective_rainfall": {
    "status": "completed",
    "weighted_cn2": 91.61,
    "cn1": 74.32,
    "cn3": 96.58
  },
  "step5_flood_discharge": {
    "status": "completed",
    "peak_clark_cms": 3.42,
    "peak_scs_cms": 3.15,
    "peak_naka_cms": 4.18
  },
  "step6_flood_routing": {
    "status": "completed",
    "outlet": "SW00",
    "peak_q": 218.40,
    "peak_hr": 17.0,
    "cum_area": 521.9
  }
}
```

---

## 알려진 이슈

| 항목 | 내용 |
|---|---|
| Qt DPI 경고 | `qt.qpa.window: SetProcessDpiAwarenessContext() failed` — 무해. `QT_LOGGING_RULES` 환경변수로 억제 가능 |
| lmoments3 | 없을 경우 Step 2 GLO/Wakeby 계열 비활성. `pip install lmoments3` 설치 권장 |
| EPSG:5186 | Step 4 GIS 연산은 한국 표준 좌표계 기준. 다른 좌표계 입력 시 자동 변환 |
| Step 6 NSTPS | K, X, Δt 조합에 따라 불안정 경고 발생 가능 — NSTPS=0 설정 시 자동 안정화 |

---

## 라이선스

MIT License

---

*최종 업데이트: 2026-03-11*
