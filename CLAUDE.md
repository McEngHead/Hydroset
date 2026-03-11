# CLAUDE.md — Hydroset 코딩 가이드

Claude Code가 이 저장소에서 작업할 때 참조하는 지침 파일입니다.

---

## 실행 환경

- **Python:** `D:\Python311\python.exe` (python 명령이 PATH에 없을 경우 전체 경로 사용)
- **OS:** Windows 11 / MSYS2 bash 환경
- **GUI:** customtkinter Dark mode 전용

```bash
# 메인 실행
python Main.py

# 각 모듈 직접 실행
python "1.강우자료수집/01.강우자료분석.py"
python "2.확률강우량분석/02.확률강우량분석.py"
python "3.강우강도식/03.강우강도식.py"
python "4.유효우량/04.유효우량산정.py"
python "5.홍수량산정/05.홍수량산정.py"
python "6.하도추적/06.하도추적.py"
```

---

## 아키텍처

**6단계 순차 수문 분석 시스템.** 각 단계는 독립 Python GUI 모듈이며, `Main.py`가 서브프로세스로 실행합니다.

```
Main.py
  ├─ Step 1: 강우자료수집    → *_A_Rainfall_Data.xlsx
  ├─ Step 2: 확률강우량분석  → *_B_Probability_Rainfall.xlsx
  ├─ Step 3: 강우강도식      → *_C_Rainfall_Intensity.xlsx
  ├─ Step 4: 유효우량산정    → *_D_Effective_Rainfall.xlsx + .shp
  ├─ Step 5: 홍수량산정      → *_E_Flood_Discharge.xlsx
  └─ Step 6: 하도추적        → *_F_Flood_Routing_TIMESTAMP.xlsx
```

**프로젝트 상태 흐름:** `project_config.json` (각 단계 출력 경로 및 결과값 저장)

**스크립트 탐색 규칙 (`Main.py > find_target_script`):**
- 폴더명 앞 숫자: `N.폴더명/`
- 파일명 앞 두 자리: `0N.파일명.py`

---

## 모듈별 핵심 정보

### Step 2 — 확률강우량 분석

- FARD Ver.2006, 16개 확률분포 (NOR, GAM2, GUM, GEV, GLO, GAM3, LN2, LN3, LP3, LGU2/3, WBU2/3, GPA, WKB4/5)
- 출력 컬럼: `Return Period` (값 형식: `"2yr"`, `"5yr"`)
- GLO: 음수 강우량 클리핑, Wakeby: 이상값 필터링 적용

### Step 3 — 강우강도식

- Step 2 출력 컬럼 탐색 시 두 이름 모두 체크 + `"yr"/"year"` 접미사 제거:
  ```python
  rp_col = next((c for c in ['Return Period(Year)', 'Return Period'] if c in df.columns), None)
  ```

### Step 4 — 유효우량

- geopandas, EPSG:5186 기준
- CN 참조: `4.유효우량/CN_AMC_II.xlsx`
- 예제 셰이프파일: `4.유효우량/Shape/유역바운더리_A.*`
- AMC 조건 공식:
  - CN I  = (4.2 × CN_II) / (10 − 0.058 × CN_II)
  - CN III = (23 × CN_II) / (10 + 0.13 × CN_II)

### Step 5 — 홍수량산정

- Clark + SCS + Nakayasu 3종 합성단위도
- Huff DB: `5.홍수량산정/rainfall_db.sqlite` (`Huff_Local`, `HUFF_Area` 테이블)
- Step 3 Excel (`Intensity_Table` 시트) 자동 연동 → 재현기간×지속기간 배치계산
- `project_config.json`의 `step4_effective_rainfall.cn3` → CN 자동 로드

### Step 6 — 하도추적

**머스킹엄 공식 (KWRA CH08):**
```
C₁ = (-Kx + 0.5Δt) / (K - Kx + 0.5Δt)
C₂ = ( Kx + 0.5Δt) / (K - Kx + 0.5Δt)
C₃ = (K - Kx - 0.5Δt) / (K - Kx + 0.5Δt)
안정 조건: 2Kx ≤ Δt ≤ 2K(1-x)
NSTPS 자동계산: ceil(Δt / 2K(1-x))
```

**수문망 처리 (HEC-1 스택 방식):**
- BASIN → Clark UH 수문곡선 → push
- ROUTE → pop / Muskingum 추적 / push
- COMBINE(N) → pop N / 합산 / push

**비주얼 편집기 클래스 구조:**
```python
NetworkEditorWindow (CTkToplevel)
  ├─ PalettePanel     — 노드 팔레트 (좌측 170px)
  ├─ NetworkCanvas    — tk.Canvas 기반 편집 캔버스 (중앙, 스크롤)
  └─ PropertiesPanel  — 노드 속성 편집 (우측 280px)
```

**DFS operations 변환:** `NetworkCanvas.build_operations()` → outlet 노드에서 DFS

**내장 예제:** `100-1440-SW00.dat` 기반 (521.9 km², 27개 조작, SW00 출구 ~218 m³/s)

---

## 코드 관례

- **UI 텍스트:** 한국어 전용, 폰트 `맑은 고딕`
- **다크 타이틀바:** `DwmSetWindowAttribute(hwnd, 35/20, 1)` — 모든 창에 적용
- **진입점:** `sys.argv[1]` = project_path, `sys.argv[2]` = input_file
- **설정 저장:** `project_config.json` (UTF-8 JSON, indent=2)
- **그래프:** matplotlib TkAgg 백엔드, `plt.rcParams['font.family'] = 'Malgun Gothic'`
- **Qt 경고 억제:** `os.environ["QT_LOGGING_RULES"] = "qt.qpa.window.warning=false"`

---

## 주요 파일 경로

| 파일 | 역할 |
|---|---|
| `Main.py` | 메인 GUI, 프로젝트 관리자 |
| `4.유효우량/CN_AMC_II.xlsx` | CN 참조표 (필수) |
| `5.홍수량산정/rainfall_db.sqlite` | Huff 시간분포 DB (필수) |
| `100-1440-SW00.dat` | HEC-1 예제 입력 (Step 6 내장 예제 출처) |
| `100-1440-SW00.OUT` | HEC-1 예제 출력 (검증용 참조) |

---

## AI 행동 지침

- 지시된 내용만 정확히 수정한다. 지시 범위를 벗어난 변경 금지.
- UI 레이아웃, 변수명, 코드 구조는 명시적 지시 없이 임의로 변경하지 않는다.
- 판단이 필요한 경우 먼저 질문하고 승인을 받은 후 진행한다.
- 기존 동작하는 코드를 "개선"한다는 명목으로 건드리지 않는다.
- 수정 범위가 불명확할 때는 최소한으로 해석하여 적용한다.
