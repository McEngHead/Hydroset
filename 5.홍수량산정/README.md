# Module 5 — 홍수량 산정

Clark / SCS / Nakayasu 합성단위도 3종으로 홍수량을 동시 산정·비교하는 GUI 모듈.

---

## 실행

```bash
# Main.py 에서 E. 홍수량 버튼 클릭 (권장)
# 직접 실행:
python 05.홍수량산정.py <project_path>
```

---

## 의존 파일

| 파일 | 역할 |
|---|---|
| `rainfall_db.sqlite` | Huff 시간분포 DB (지점/지역해석) |
| `*_C_Rainfall_Intensity.xlsx` | Step 3 출력 — 재현기간×지속기간 강우강도표 |
| `project_config.json` | Step 4 CN 값 자동 로드 |

---

## 클래스 구조

```
RainfallRunoffEngine          ← 계산 엔진 (Clark / SCS / Nakayasu)
FloodDischargeApp (CTk)
  ├─ HuffDBDialog             ← Huff 시간분포 설정 (지점/지역/사용자)
  ├─ SCSNakayasuDialog        ← SCS/Nakayasu 매개변수
  └─ BatchSelectionDialog     ← 배치계산 선택
```

---

## 배치 계산

- 재현기간 또는 지속기간을 **"전체"** 선택 시 자동 배치 실행
- Step 3 `Intensity_Table` 시트에서 모든 재현기간×지속기간 조합 로드
- `ThreadPoolExecutor`로 병렬 처리
- 출력: `*_E_Flood_Batch.xlsx`

---

## Huff DB 테이블 구조

### `Huff_Local` (지점해석)
`STATN`, `NAME_STN`, `QUARTILE`, `EXCD_PROB`, `P0`~`P100`

### `HUFF_Area` (지역해석)
`GROUP_ID`, `QUARTILE`, `PROB`, `P0`~`P100`

---

## project_config.json (step5 섹션)

```json
"step5": {
  "RETURN_PERIOD": "전체",
  "TR_MIN": "전체",
  "DT_MIN": 10,
  "NQ": 300,
  "CN": 84.3,
  "TC_HR": 0.40,
  "R_HR": 0.57,
  "huff_quartile": "3분위",
  "huff_pc": [0.0, 0.008, 0.041, 0.086, 0.154, 0.263, 0.437, 0.636, 0.833, 0.953, 1.0]
}
```

---

*최종 수정: 2026-03-11*
