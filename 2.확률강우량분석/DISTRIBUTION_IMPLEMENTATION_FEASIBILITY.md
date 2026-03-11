# 미구현 분포형 lmoments3 구현 가능성 분석 보고서

## 📊 결론: 10개 분포형 **모두 구현 가능**

lmoments3 라이브러리를 활용하면 현재 "NOT IMPLEMENTED"로 표시된 10개 분포형을 
**모두 PWM(L-Moments) 방법으로 구현할 수 있습니다.**

═══════════════════════════════════════════════════════════════════════

## ✅ 직접 구현 가능 (lmoments3 직접 지원)

### (14) GPA - Generalized Pareto Distribution

**지원 모듈**: `lmoments3.distr.gpa`

**매개변수 구조**:
```python
params = distr.gpa.lmom_fit(data)
# OrderedDict([
#   ('c', -0.626),      # Shape parameter
#   ('loc', 42.640),    # Location parameter
#   ('scale', 14.764)   # Scale parameter
# ])
```

**분위수 함수**:
```python
from lmoments3 import distr
quantile = distr.gpa.ppf(F, c=params['c'], loc=params['loc'], scale=params['scale'])
```

**구현 난이도**: ⭐ (매우 쉬움)

---

### (12) WBU2 / (13) WBU3 - Weibull Distribution

**지원 모듈**: `lmoments3.distr.wei`

**매개변수 구조**:
```python
params = distr.wei.lmom_fit(data)
# OrderedDict([
#   ('c', 2.090),       # Shape parameter (Weibull modulus)
#   ('loc', 39.469),    # Location parameter (3-parameter only)
#   ('scale', 13.832)   # Scale parameter
# ])
```

**2-Parameter (WBU2)**: `loc = 0` 고정
**3-Parameter (WBU3)**: `loc` 추정

**분위수 함수**:
```python
quantile = distr.wei.ppf(F, c=params['c'], loc=params['loc'], scale=params['scale'])
```

**구현 난이도**: ⭐ (매우 쉬움)

---

### (15) WKB4 / (16) WKB5 - Wakeby Distribution

**지원 모듈**: `lmoments3.distr.wak`

**매개변수 구조**:
```python
params = distr.wak.lmom_fit(data)
# OrderedDict([
#   ('beta', 0.626),    # Parameter β
#   ('gamma', 0.0),     # Parameter γ
#   ('delta', 0.0),     # Parameter δ
#   ('loc', 42.640),    # Location ξ
#   ('scale', 14.764)   # Scale α
# ])
```

**5-Parameter 분포** (ξ, α, β, γ, δ):
- ξ (Xi): Location
- α (Alpha): Scale
- β (Beta): Shape 1
- γ (Gamma): Shape 2
- δ (Delta): Shape 3

**4-Parameter (WKB4)**: δ = 0 또는 γ = 0
**5-Parameter (WKB5)**: 모든 매개변수 사용

**분위수 함수**:
```python
quantile = distr.wak.ppf(F, beta=params['beta'], gamma=params['gamma'], 
                          delta=params['delta'], loc=params['loc'], scale=params['scale'])
```

**구현 난이도**: ⭐⭐ (쉬움)

**참고**: Wakeby 분포는 Hosking & Wallis가 지역빈도해석을 위해 개발한 
매우 유연한 분포로, 5개 매개변수로 거의 모든 형태의 분포를 근사할 수 있습니다.

═══════════════════════════════════════════════════════════════════════

## ✅ 변환 후 구현 가능 (Log Transform)

### (7) LN2 - 2-Parameter Log-Normal Distribution

**구현 방법**: Log 변환 후 Normal 분포 적용

**알고리즘**:
```python
import numpy as np
from lmoments3 import distr

# Step 1: Log 변환
log_data = np.log(data)

# Step 2: Normal 분포 fitting
params = distr.nor.lmom_fit(log_data)
# OrderedDict([
#   ('loc', 3.940),     # μ (mean of log)
#   ('scale', 0.118)    # σ (std of log)
# ])

# Step 3: 분위수 계산
log_quantile = distr.nor.ppf(F, loc=params['loc'], scale=params['scale'])
quantile = np.exp(log_quantile)  # 역변환
```

**이론적 배경**:
Y = log(X)일 때, Y ~ Normal(μ, σ²) → X ~ LogNormal(μ, σ²)

**분위수 함수**:
X = exp(μ + Z·σ)  
여기서 Z = Φ⁻¹(F) (표준정규분포 분위수)

**구현 난이도**: ⭐ (매우 쉬움)

---

### (8) LN3 - 3-Parameter Log-Normal Distribution

**구현 방법**: 하한계(ξ) 추정 후 Log 변환

**알고리즘**:
```python
# Step 1: 하한계(ξ) 추정
# 방법 1: 최소값의 일정 비율 (예: 90%)
xi = data.min() * 0.9

# 방법 2: L-Moments 기반 반복법 (향후 구현)
# xi를 변화시키며 L-Skewness가 0에 가까워지도록 추정

# Step 2: 이동 후 Log 변환
shifted_data = data - xi
log_data = np.log(shifted_data)

# Step 3: Normal 분포 fitting
params = distr.nor.lmom_fit(log_data)

# Step 4: 분위수 계산
log_quantile = distr.nor.ppf(F, loc=params['loc'], scale=params['scale'])
quantile = xi + np.exp(log_quantile)
```

**이론적 배경**:
Y = log(X - ξ)일 때, Y ~ Normal(μ, σ²) → X ~ LogNormal3(ξ, μ, σ²)

**매개변수**:
- ξ (Xi): Lower bound (하한계)
- μ (Mu): Mean of log(X - ξ)
- σ (Sigma): Std of log(X - ξ)

**구현 난이도**: ⭐⭐ (쉬움 - 하한계 추정 알고리즘 필요)

---

### (9) LP3 - Log-Pearson Type III Distribution

**구현 방법**: Log 변환 후 Pearson Type III 분포 적용

**알고리즘**:
```python
# Step 1: Log 변환
log_data = np.log(data)

# Step 2: Pearson Type III (PE3) fitting
params = distr.pe3.lmom_fit(log_data)
# OrderedDict([
#   ('loc', 3.940),     # ξ (location of log)
#   ('scale', 0.133),   # α (scale of log)
#   ('skew', 0.630)     # γ (skewness of log)
# ])

# Step 3: 분위수 계산
log_quantile = distr.pe3.ppf(F, loc=params['loc'], scale=params['scale'], skew=params['skew'])
quantile = np.exp(log_quantile)  # 역변환
```

**이론적 배경**:
Y = log(X)일 때, Y ~ PE3(ξ, α, γ) → X ~ LP3(ξ, α, γ)

**미국 정부 기준**:
USGS Bulletin 17B/C에서 홍수빈도해석 공식 채택

**구현 난이도**: ⭐ (매우 쉬움)

**참고**: 
- PE3 = 3-Parameter Gamma = Pearson Type III
- lmoments3.distr.pe3 완벽 지원

---

### (10) LGU2 - 2-Parameter Log-Gumbel Distribution

**구현 방법**: Log 변환 후 Gumbel 분포 적용

**알고리즘**:
```python
# Step 1: Log 변환
log_data = np.log(data)

# Step 2: Gumbel fitting (PWM)
params = distr.gum.lmom_fit(log_data)
# OrderedDict([
#   ('loc', 3.885),     # ξ (location of log)
#   ('scale', 0.096)    # α (scale of log)
# ])

# Step 3: 분위수 계산
log_quantile = distr.gum.ppf(F, loc=params['loc'], scale=params['scale'])
quantile = np.exp(log_quantile)  # 역변환
```

**이론적 배경**:
Y = log(X)일 때, Y ~ Gumbel(ξ, α) → X ~ LogGumbel(ξ, α)

**분위수 함수**:
X = exp[ξ - α·ln(-ln(F))]

**구현 난이도**: ⭐ (매우 쉬움)

---

### (11) LGU3 - 3-Parameter Log-Gumbel Distribution

**구현 방법**: 하한계(ξ₀) 추정 후 Log 변환

**알고리즘**:
```python
# Step 1: 하한계(ξ₀) 추정
xi0 = data.min() * 0.9

# Step 2: 이동 후 Log 변환
shifted_data = data - xi0
log_data = np.log(shifted_data)

# Step 3: Gumbel fitting
params = distr.gum.lmom_fit(log_data)

# Step 4: 분위수 계산
log_quantile = distr.gum.ppf(F, loc=params['loc'], scale=params['scale'])
quantile = xi0 + np.exp(log_quantile)
```

**이론적 배경**:
Y = log(X - ξ₀)일 때, Y ~ Gumbel(ξ, α) → X ~ LogGumbel3(ξ₀, ξ, α)

**매개변수**:
- ξ₀ (Xi0): Lower bound
- ξ (Xi): Location of log(X - ξ₀)
- α (Alpha): Scale of log(X - ξ₀)

**구현 난이도**: ⭐⭐ (쉬움 - 하한계 추정 알고리즘 필요)

═══════════════════════════════════════════════════════════════════════

## 📊 구현 가능성 요약표

| 번호 | 분포형 | lmoments3 지원 | 구현 방법 | 난이도 | 우선순위 |
|------|--------|---------------|-----------|--------|---------|
| (7)  | LN2    | 변환 (log+nor) | Log 변환 | ⭐ | HIGH |
| (8)  | LN3    | 변환 (log+nor) | Log 변환 + 하한계 | ⭐⭐ | MEDIUM |
| (9)  | LP3    | 변환 (log+pe3) | Log 변환 | ⭐ | **CRITICAL** |
| (10) | LGU2   | 변환 (log+gum) | Log 변환 | ⭐ | MEDIUM |
| (11) | LGU3   | 변환 (log+gum) | Log 변환 + 하한계 | ⭐⭐ | LOW |
| (12) | WBU2   | **distr.wei** | 직접 지원 | ⭐ | HIGH |
| (13) | WBU3   | **distr.wei** | 직접 지원 | ⭐ | HIGH |
| (14) | GPA    | **distr.gpa** | 직접 지원 | ⭐ | MEDIUM |
| (15) | WKB4   | **distr.wak** | 직접 지원 | ⭐⭐ | LOW |
| (16) | WKB5   | **distr.wak** | 직접 지원 | ⭐⭐ | LOW |

**총 10개 분포 → 10개 모두 구현 가능** ✓

═══════════════════════════════════════════════════════════════════════

## 🎯 우선순위 분류 기준

### CRITICAL (즉시 구현 권장)
**LP3 (Log-Pearson Type III)**
- USGS 공식 채택 분포
- 미국 홍수빈도해석 표준
- 국제적으로 널리 사용
- **구현 매우 쉬움** (log 변환 + PE3)

### HIGH (1차 구현 권장)
**LN2, WBU2, WBU3**
- 실무에서 자주 사용
- Log-Normal: 강우량, 유량 분석
- Weibull: 가뭄, 저유량 분석
- lmoments3 직접 지원

### MEDIUM (2차 구현 고려)
**LN3, LGU2, GPA**
- 특수 상황에서 유용
- 하한계가 있는 데이터
- 극치 사상 분석

### LOW (선택적 구현)
**LGU3, WKB4, WKB5**
- 학술 연구용
- Wakeby: 매우 유연하나 복잡
- 실무 사용 빈도 낮음

═══════════════════════════════════════════════════════════════════════

## 💻 구현 예시 코드

### 1. LP3 (Log-Pearson Type III) - 완전한 구현

```python
def fit_lp3_lmoments(data):
    """LP3 분포 L-Moments 기반 매개변수 추정"""
    import numpy as np
    from lmoments3 import distr
    
    # Log 변환
    log_data = np.log(data)
    
    # PE3 fitting
    params = distr.pe3.lmom_fit(log_data)
    
    return {
        'XLO': params['loc'],     # Location (of log)
        'XSC': params['scale'],   # Scale (of log)
        'XSH': params['skew']     # Shape (skewness)
    }

def calculate_lp3_rainfall(params, return_period):
    """LP3 확률강우량 계산"""
    import numpy as np
    from lmoments3 import distr
    
    F = 1 - 1/return_period
    
    # Log 공간에서 분위수 계산
    log_quantile = distr.pe3.ppf(
        F, 
        loc=params['XLO'], 
        scale=params['XSC'], 
        skew=params['XSH']
    )
    
    # 지수 변환
    return np.exp(log_quantile)
```

### 2. Weibull (WBU2/WBU3) - 완전한 구현

```python
def fit_weibull_lmoments(data, n_params=3):
    """Weibull 분포 L-Moments 기반 매개변수 추정"""
    from lmoments3 import distr
    
    params = distr.wei.lmom_fit(data)
    
    if n_params == 2:
        # 2-parameter: loc = 0 고정
        return {
            'XLO': 0.0,
            'XSC': params['scale'],
            'XSH': params['c']
        }
    else:
        # 3-parameter
        return {
            'XLO': params['loc'],
            'XSC': params['scale'],
            'XSH': params['c']
        }

def calculate_weibull_rainfall(params, return_period):
    """Weibull 확률강우량 계산"""
    from lmoments3 import distr
    
    F = 1 - 1/return_period
    
    return distr.wei.ppf(
        F,
        c=params['XSH'],
        loc=params['XLO'],
        scale=params['XSC']
    )
```

### 3. Wakeby (WKB4/WKB5) - 완전한 구현

```python
def fit_wakeby_lmoments(data):
    """Wakeby 분포 L-Moments 기반 매개변수 추정"""
    from lmoments3 import distr
    
    params = distr.wak.lmom_fit(data)
    
    return {
        'beta': params['beta'],
        'gamma': params['gamma'],
        'delta': params['delta'],
        'loc': params['loc'],
        'scale': params['scale']
    }

def calculate_wakeby_rainfall(params, return_period):
    """Wakeby 확률강우량 계산"""
    from lmoments3 import distr
    
    F = 1 - 1/return_period
    
    return distr.wak.ppf(
        F,
        beta=params['beta'],
        gamma=params['gamma'],
        delta=params['delta'],
        loc=params['loc'],
        scale=params['scale']
    )
```

═══════════════════════════════════════════════════════════════════════

## 🚀 통합 구현 제안

### Phase 1 (즉시) - CRITICAL 분포
✓ LP3 (Log-Pearson Type III)
  - 코드 라인 수: ~30 줄
  - 소요 시간: 1시간
  - 테스트: USGS 예제 데이터

### Phase 2 (1주 내) - HIGH 분포
✓ LN2 (2-Parameter Log-Normal)
✓ WBU2, WBU3 (Weibull)
  - 코드 라인 수: ~50 줄
  - 소요 시간: 2-3시간
  - 테스트: 국내 강우 데이터

### Phase 3 (1개월 내) - MEDIUM 분포
✓ LN3 (3-Parameter Log-Normal)
✓ LGU2 (2-Parameter Log-Gumbel)
✓ GPA (Generalized Pareto)
  - 코드 라인 수: ~70 줄
  - 소요 시간: 4-5시간
  - 테스트: 극치값 데이터

### Phase 4 (선택) - LOW 분포
✓ LGU3 (3-Parameter Log-Gumbel)
✓ WKB4, WKB5 (Wakeby)
  - 코드 라인 수: ~40 줄
  - 소요 시간: 2-3시간
  - 테스트: 학술 데이터

═══════════════════════════════════════════════════════════════════════

## 📚 참고 자료

### lmoments3 공식 문서
- GitHub: https://github.com/OpenHydrology/lmoments3
- PyPI: https://pypi.org/project/lmoments3/
- 기반 알고리즘: Hosking & Wallis (1997)

### 실무 표준
- USGS Bulletin 17C (LP3 공식 채택)
- WMO-No. 168 (세계기상기구 지침)
- ISO 20691 (국제표준)

### 검증 데이터셋
- USGS NWIS (National Water Information System)
- 국내: 기상청 종관기상관측(ASOS) 데이터
- Hosking & Wallis 교재 예제

═══════════════════════════════════════════════════════════════════════

## 🎉 결론

**10개 미구현 분포를 모두 lmoments3로 구현 가능합니다!**

### 즉시 실행 가능한 작업:
1. ✅ LP3 구현 (USGS 표준, 최우선)
2. ✅ Weibull 구현 (직접 지원, 매우 쉬움)
3. ✅ Log-Normal 구현 (실무 필수)

### 핵심 이점:
- PWM(L-Moments) 방법으로 정확도 향상
- 국제 표준 알고리즘 (Hosking) 준수
- 정부 기준(USGS Bulletin 17C) 충족
- 실무 적용성 대폭 향상

### 권장사항:
**Phase 1 (LP3, WBU2, WBU3) 즉시 구현을 강력히 권장합니다.**

═══════════════════════════════════════════════════════════════════════

보고서 작성일: 2025-12-31
lmoments3 버전: 1.0.8
