# 06.하도추적.py — 현재 이슈 및 수정 현황

> 마지막 업데이트: 2026-03-13

---

## ✅ 이번 세션에서 수정 완료된 항목

### 1. 연결선(엣지) 선택 우선순위 오류
- **원인:** SELECT 모드에서 포트 클릭 감지가 엣지 클릭 감지보다 먼저 실행 → 연결선 클릭 불가
- **수정:** 엣지 감지를 1순위로 이동, 포트 반경(HIT_R=12) 내 클릭은 포트에 양보

### 2. 연결선 삭제 TypeError
- **원인:** `_delete`에서 `self._sel_edge.id[:8]` — id는 int, 문자열 슬라이싱 불가 → TypeError → 삭제 실패
- **수정:** `edge.label or str(edge.id)` 로 변경

### 3. 일반 연결선 PropertiesPanel 버튼 미존재
- **원인:** `show_edge`에서 reach_params=None이면 `_show_empty()` → 아무 버튼 없음
- **수정:** 일반 연결선 전용 패널 추가 (연결 노드명 표시 + "연결선 삭제" 버튼)

### 4. 툴바 "적용" 버튼 추가
- **위치:** 배열최적화 버튼 오른쪽
- **동작:** JSON + .dat 저장 (무확인) → 미리보기 갱신 → "적용 완료 ✓" 상태 표시
- **경로 없을 때:** `_current_path=None` → `_save_network()` 파일 대화상자 호출 (L2700-2702)

### 5. load_operations ↔ build_operations 왕복 오염 (OUT→OUT 이중 노드)
- **원인 A:** `build_operations`에서 OUTLET N≥2 직접 연결 시 `COMBINE name='OUT'` 생성
  → `load_operations`가 이를 JUNCTION 'OUT' + 자동 OUTLET 'OUT' 으로 재구성 = OUT→OUT
- **원인 B:** `_open_editor`에서 `Sample_Redraw.json` 로드 후 즉시 `load_operations(self.operations)`로 덮어씀
- **수정 A:** OUTLET N≥2 → COMBINE 대신 에러 메시지 반환 ("합류점 노드 사용하세요")
- **수정 B:** `if self.operations and not self._editor._canvas.nodes:` 조건으로 캔버스 비었을 때만 호출

### 6. 활동 로그 미작동
- **원인:** `_create_edge`에서 `src_id[:6]`, `dst_id[:6]` — id는 int → TypeError → 로그 호출 전 예외
- **수정:** `sn.name if sn else str(src_id)` 방식으로 변경

### 7. Ctrl+Z (Undo) 2번 실행 버그
- **원인:** 캔버스 레벨 `<Control-z>` 바인딩 + 윈도우 레벨 바인딩 동시 존재
  → 이벤트 전파로 `_undo()` 가 한 번에 2번 호출 → undo 스택 2개 팝
- **수정:** `_undo()`에 `return 'break'` 추가 → 캔버스 바인딩에서 이벤트 전파 차단

---

## ✅ 검증 완료 (2026-03-13 다음 세션)

### 검증 A — 위 수정 사항들 코드 검토 완료
- 엣지 클릭 1순위(L762-785), `_delete` 수정(L983-991), 활동 로그 str() 처리(L1224-1229),
  `_undo` return 'break'(L1085) 모두 코드에 반영 확인

### 검증 B — OUT→OUT 재현 없음
- `project_config.json` `step6.operations: []` — 오염된 ops 없음 ✅

### 검증 C — "적용" 버튼 경로 없을 때 동작 확인
- `_apply_network` L2700-2702: `_current_path=None` 시 `_save_network()` 호출 확인 ✅

---

## 현재 툴바 버튼 순서 (시각 좌→우)

```
[업데이트] [배열최적화] [적용] [불러오기] [저장하기] [다른이름으로 저장] [닫기] [PNG로 저장] [초기화] [예제 로드]
```

- **업데이트**: `_apply()` — ops 빌드 → 메인앱 반영 → .dat 저장
- **적용**: `_apply_network()` — JSON + .dat 저장 (무확인) → 미리보기 갱신

---

## 주요 메서드 위치 (현재 기준)

| 항목 | 위치 |
|---|---|
| `NetworkCanvas.__init__` / 바인딩 | ~L398 |
| `NetworkCanvas._undo` | ~L1075 |
| `NetworkCanvas._delete` | ~L983 |
| `NetworkCanvas._create_edge` | ~L1210 |
| `NetworkCanvas.build_operations` | ~L1255 |
| `NetworkCanvas.load_operations` | ~L1332 |
| `NetworkCanvas._click` SELECT MODE | ~L762 |
| `PropertiesPanel.show_edge` | ~L2162 |
| `PropertiesPanel._delete_plain_edge` | ~L2245 |
| `NetworkEditorWindow.__init__` | ~L2266 |
| `NetworkEditorWindow._open_editor` (FloodRoutingApp) | ~L3029 |
| `NetworkEditorWindow._apply_network` | ~L2695 |
| `FloodRoutingApp._load_example` | ~L3073 |
| `EXAMPLE_OPERATIONS` | ~L2838 |
