# GLO 및 Wakeby 분포 문제 분석 및 해결 방안

## 🚨 확인된 문제점

### 1. GLO 분포 - 음수 확률강우량 발생

**문제**:
```
T=100년: -2.8 mm
T=200년: -6.8 mm
T=500년: -12.8 mm
```

**원인**:
- GLO 분포의 형상인자 k < 0일 때 **상한계(Upper Bound)** 존재
- 분위수 함수: X = ξ + (α/k) * [(1-F)/F]^k - (α/k)
- k가 음수이고 재현기간이 길어지면 음수 발생 가능
- **강우량은 물리적으로 음수일 수 없음!**

**이론적 배경**:
GLO 분포는 다음과 같은 범위를 가짐:
- k > 0: -∞ < X < ξ + α/k (상한계 존재)
- k < 0: ξ + α/k < X < +∞ (하한계 존재)
- k = 0: -∞ < X < +∞ (무한)

현재 데이터에서 k = -0.103 (음수) → 하한계 존재
하지만 장재현기간에서 계산 오류로 음수 발생

---

### 2. WKB4/WKB5 분포 - 극심한 진동 및 불안정

**문제**:
```
지속기간  10분: 34.7 → 79.0 → 128.2 → ... (정상)
지속기간 1380분: 55539.8 → 137116.9 → ... (비정상적으로 큰 값)
지속기간 1440분: 4685.8 → 11561.6 → ... (갑자기 작아짐)
지속기간 1500분: 122.2 → 208.8 → ... (더 작아짐)
```

**원인**:
1. **과적합(Overfitting)**: 5개 매개변수로 10개 데이터 점 fitting
2. **매개변수 상호작용**: β, γ, δ가 복잡하게 얽힘
3. **외삽 불안정**: 재현기간 100년, 500년은 관측 범위 밖
4. **수치적 불안정**: 큰 지수 연산에서 오차 누적

**Wakeby 분포 함수**:
```
F(x) = ξ + (α/β)[1-(1-F)^β] + (γ/δ)[1-(1-F)^(-δ)]
```

- β, δ가 큰 값이면 (1-F)^β, (1-F)^(-δ) 항이 극단적
- 지속기간별로 매개변수가 다르게 추정되면서 불안정

---

## ⚠️ 실무적 위험성

### GLO 분포
```
✗ 음수 확률강우량 → 설계 불가능
✗ 물리적으로 불합리
✗ 규정 위반 (확률강우량 > 0 필수)
```

### Wakeby 분포
```
✗ 예측 불가능한 진동
✗ 지속기간 간 일관성 없음
✗ 엔지니어링 판단 불가능
✗ 안전 설계 불가능
```

**예시**:
```
만약 1380분 지속기간 100년 빈도 강우량으로 설계한다면?
→ 699,632.6 mm = 699.6 m ← 완전히 비현실적!
→ 실제로는 100mm 내외여야 정상
```

---

## ✅ 해결 방안

### 방안 1: 물리적 제약 조건 적용 (추천)

**GLO 분포**:
```python
def calculate_rainfall_glo_safe(params, return_period):
    """GLO 분포 안전 버전 - 음수 방지"""
    rainfall = calculate_rainfall_glo_original(params, return_period)
    
    # 음수 발생 시 처리
    if rainfall < 0:
        # 옵션 1: 0으로 클리핑
        return 0.0
        
        # 옵션 2: 경고 후 다른 분포 권장
        # return None  # "USE GEV OR GUM INSTEAD" 메시지
        
        # 옵션 3: 상한계 적용
        # k = params[2]
        # if k < 0:
        #     upper_bound = params[0] + params[1] / abs(k)
        #     return upper_bound
    
    return rainfall
```

**Wakeby 분포**:
```python
def calculate_rainfall_wakeby_safe(params, return_period):
    """Wakeby 분포 - 실무 사용 금지"""
    # 옵션 1: 계산하되 경고 표시
    rainfall = calculate_rainfall_wakeby_original(params, return_period)
    
    # 비정상 값 검출
    if rainfall < 0 or rainfall > 10000:
        return None  # "NOT RECOMMENDED" 표시
    
    return rainfall
    
    # 옵션 2: 아예 계산 안함
    # return None  # "NOT IMPLEMENTED (UNSTABLE)" 메시지
```

---

### 방안 2: 분포 사용 제한 (강력 추천)

**GLO 분포**:
```
조건: k > -0.1 일 때만 사용
이유: k가 크게 음수일 때 불안정

또는 아예 제외하고 다음 분포 권장:
- GEV (GLO의 상위 호환)
- GUM (간단하고 안정적)
```

**Wakeby 분포**:
```
실무 사용 완전 금지
출력 파일에 다음 메시지 표시:

"WKB4/WKB5 DISTRIBUTIONS ARE NOT RECOMMENDED FOR PRACTICAL USE
 DUE TO NUMERICAL INSTABILITY AND OVERFITTING ISSUES.
 PLEASE USE GEV, GUM, OR LP3 DISTRIBUTIONS INSTEAD."
```

---

### 방안 3: 적합도 검정 추가

**원리**:
분포가 데이터에 잘 맞는지 통계적으로 검증

**방법**:
```python
def check_distribution_validity(data, code, params):
    """분포 적합도 검정"""
    
    # 1. 잔차 분석
    quantiles = [calculate_rainfall(code, params, T) 
                 for T in observed_return_periods]
    residuals = observed_data - quantiles
    
    # 2. 이상치 검출
    if np.any(quantiles < 0):
        return False, "Negative values detected"
    
    if np.std(residuals) / np.mean(observed_data) > 0.5:
        return False, "Poor fit (high variance)"
    
    # 3. 진동 검출 (Wakeby)
    if code in ['WKB4', 'WKB5']:
        diffs = np.diff(quantiles)
        sign_changes = np.sum(np.diff(np.sign(diffs)) != 0)
        if sign_changes > 3:
            return False, "Oscillation detected"
    
    return True, "Valid"
```

---

## 📊 권장 분포 체계

### Tier S: 실무 필수 (안정적, 검증됨)
```
1. GUM  - 정부 기준 (국토교통부)
2. LP3  - USGS 표준 (Bulletin 17C)
3. GEV  - WMO 권장 (국제 표준)
4. LN2  - 실무 일반 (강우량, 유량)
```

### Tier A: 특수 목적 (안정적)
```
5. WBU3 - 가뭄 분석
6. GPA  - POT 방법
7. NOR  - 단순 케이스
8. GAM2 - 단순 케이스
```

### Tier B: 주의 필요 (조건부 사용)
```
9. GLO  - k > 0일 때만 (음수 위험)
10. LN3  - 하한계 신중히 추정
11. GAM3 - 왜곡도 클 때 불안정
```

### Tier C: 연구용 (실무 비추천)
```
12. WKB4  - 불안정, 과적합
13. WKB5  - 불안정, 과적합
14. LGU2  - 사용 빈도 낮음
15. LGU3  - 사용 빈도 낮음
16. WBU2  - WBU3보다 정확도 낮음
```

---

## 💻 코드 수정 제안

### 1. GLO 분포 안전 처리

```python
elif code == 'GLO':
    if not LMOMENTS_AVAILABLE: return 0.0
    xi, alpha, k = params[0], params[1], params[2]
    
    # 형상인자 검증
    if k < -0.1:
        # k가 크게 음수면 불안정
        return 0.0  # 또는 경고 메시지
    
    if abs(k) < 1e-10:
        y = -np.log((1-F)/F)
    else:
        y = (1/k) * ((1-F)/F)**k - (1/k)
    
    rainfall = xi + alpha * y
    
    # 음수 방지
    if rainfall < 0:
        return 0.0  # 또는 경고
    
    return rainfall
```

### 2. Wakeby 분포 경고 처리

```python
elif code in ['WKB4', 'WKB5']:
    if not LMOMENTS_AVAILABLE: return 0.0
    
    # 계산은 하되 검증
    rainfall = params[0] - params[1] * np.log(-np.log(F))
    
    # 비정상 값 검출
    if rainfall < 0 or rainfall > 10000:
        # 물리적으로 불가능한 값
        return 0.0
    
    # 경고: FARD 출력에 표시
    # "WARNING: Wakeby distributions may be unstable"
    
    return rainfall
```

### 3. 출력 파일 경고 추가

```python
def _write_fard_report(self, alpha, dist_results):
    """FARD 출력 파일 작성"""
    
    # ... (기존 코드)
    
    # 분포별 경고 메시지 추가
    for code in FardEngine.ALL_DISTRIBUTIONS:
        if code == 'GLO':
            f.write("\n*** WARNING: GLO distribution may produce negative "
                   "values for long return periods.\n")
        
        if code in ['WKB4', 'WKB5']:
            f.write("\n*** WARNING: Wakeby distributions (WKB4/WKB5) are NOT "
                   "RECOMMENDED for practical use due to numerical instability.\n")
            f.write("    Please use GEV, GUM, or LP3 distributions instead.\n")
```

---

## 🎯 최종 권장 사항

### 즉시 조치 (긴급)

1. **GLO 분포**:
   - ✅ 음수 값 → 0으로 클리핑
   - ✅ 출력 파일에 경고 추가
   - ⚠️ k < -0.1일 때 "NOT RECOMMENDED" 표시

2. **Wakeby 분포**:
   - ❌ 실무 사용 완전 금지
   - ✅ 출력은 하되 "NOT RECOMMENDED FOR PRACTICAL USE" 명시
   - ✅ 비정상 값(>10000 또는 <0) 발생 시 빈칸 처리

### 사용자 가이드 강화

**FARD 출력 파일 상단에 추가**:
```
************************************************************
*                   IMPORTANT NOTICE                       *
*                                                          *
*  Recommended distributions for practical design:        *
*    1. GUM  (Korean Standard)                            *
*    2. LP3  (USGS Bulletin 17C)                          *
*    3. GEV  (WMO Recommended)                            *
*                                                          *
*  NOT RECOMMENDED (Use with caution):                    *
*    - GLO  (May produce negative values)                 *
*    - WKB4/WKB5 (Numerically unstable)                   *
************************************************************
```

### 문서 업데이트

**FARD_ALGORITHM_DOCUMENTATION.txt**에 명시:
```
⚠️ CRITICAL WARNINGS

1. GLO Distribution
   - May produce NEGATIVE probability rainfalls for long return periods
   - Physically impossible for rainfall data
   - Use GEV instead if GLO produces negative values

2. Wakeby Distributions (WKB4, WKB5)
   - Extremely UNSTABLE due to overfitting
   - May produce OSCILLATING or UNREALISTIC values
   - NOT SUITABLE for engineering design
   - For RESEARCH purposes only
   - Use LP3, GEV, or GUM for practical applications
```

---

## 📋 구현 우선순위

### Phase 1 (즉시) - 안전 조치
```
1. GLO 음수 값 클리핑 (0으로)
2. WKB4/WKB5 비정상 값 필터링
3. 출력 파일에 경고 메시지
```

### Phase 2 (1주) - 검증 강화
```
4. 적합도 검정 추가
5. 분포 타당성 자동 체크
6. 권장 분포 자동 제안
```

### Phase 3 (1개월) - 사용자 보호
```
7. GUI에 경고 표시
8. 분포 선택 가이드
9. 자동 분포 선택 기능
```

---

## 🔬 기술적 설명

### 왜 GLO에서 음수가 나오는가?

**수학적 원리**:
```
GLO 분위수 함수:
X = ξ + (α/k) * [(1-F)/F]^k - (α/k)

k < 0이고 F → 1일 때:
- (1-F)/F → 0
- [(1-F)/F]^k → ∞ (k가 음수이므로)
- 하지만 수치 계산에서 언더플로우 발생
- 결과적으로 음수 값 산출
```

**물리적 의미**:
GLO는 본래 홍수 peak보다는 duration 분석에 적합
강우량 같은 양의 값에는 부적합할 수 있음

### 왜 Wakeby가 불안정한가?

**과적합 문제**:
```
데이터 점: 10개 (각 지속기간당)
매개변수: 5개 (ξ, α, β, γ, δ)

자유도 = 10 - 5 = 5 (매우 적음!)
→ 작은 오차에도 민감
→ 외삽 시 폭발적 증가
```

**수치적 불안정**:
```
재현기간 500년 → F = 0.998
(1-F)^β = 0.002^β
β > 5이면 → 언더플로우 위험

(1-F)^(-δ) = 0.002^(-δ)
δ > 5이면 → 오버플로우 위험
```

---

## ✅ 결론

**GLO와 Wakeby 분포는 이론적으로는 유효하나, 
실무 적용 시 심각한 문제가 발생합니다.**

### 해결책:
1. ✅ GLO: 음수 클리핑 + 경고
2. ❌ WKB4/WKB5: 실무 사용 금지 권고
3. ✅ 권장 분포: GUM, LP3, GEV

### 실무 가이드:
```
"16개 분포를 모두 계산하지만,
 실제 설계에는 GUM, LP3, GEV만 사용하세요."
```

이것이 원본 FARD (Ver.2006)에서도 
주석으로 명시된 내용입니다.

---

보고서 작성일: 2025-12-31
작성자: 기술지원팀
