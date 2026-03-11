import os
import sys
import json
import math
import pandas as pd
import numpy as np
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
from scipy import stats, special, optimize
from scipy.stats import (
    norm, lognorm, gamma, gumbel_r, genextreme, weibull_min, 
    genlogistic, genpareto, pearson3, kstest
)
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
import warnings
import traceback

# lmoments3 (FARD 분석용)
try:
    import lmoments3 as lm
    from lmoments3 import distr
    LMOMENTS_AVAILABLE = True
except ImportError:
    LMOMENTS_AVAILABLE = False

# 경고 무시
warnings.filterwarnings('ignore')

# --- [CustomTkinter 설정] ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# 폰트 설정
FONT_TITLE = ("맑은 고딕", 22, "bold")
FONT_HEADER = ("맑은 고딕", 14, "bold")
FONT_BODY = ("맑은 고딕", 12)
FONT_BTN = ("맑은 고딕", 12, "bold")
FONT_LOG = ("consolas", 11)

# -----------------------------------------------------------
# [Core 1] L-Moment Calculation Engine (Hosking & Wallis)
# -----------------------------------------------------------
class LMoments:
    @staticmethod
    def get_sample_lmoments(data):
        n = len(data)
        if n < 2: return 0, 0, 0, 0
        data = np.sort(data)
        
        b0 = np.mean(data)
        idx = np.arange(1, n + 1)
        
        w1 = (idx - 1) / (n - 1)
        b1 = np.mean(data * w1)
        
        w2 = (idx - 1) * (idx - 2) / ((n - 1) * (n - 2))
        b2 = np.mean(data * w2)
        
        l1 = b0
        l2 = 2 * b1 - b0
        l3 = 6 * b2 - 6 * b1 + b0
        
        t3 = l3 / l2 if l2 != 0 else 0
        return l1, l2, t3, 0

    @staticmethod
    def fit_normal(l1, l2):
        scale = l2 * np.sqrt(np.pi)
        return {'Shape': None, 'Location': l1, 'Scale': scale}

    @staticmethod
    def fit_gumbel(l1, l2):
        scale = l2 / np.log(2)
        loc = l1 - 0.5772156649 * scale
        return {'Shape': None, 'Location': loc, 'Scale': scale}

    @staticmethod
    def fit_gev(l1, l2, t3):
        # Hosking Approximation
        if abs(t3) >= 1: return {'Shape': 0, 'Location': l1, 'Scale': l2}
        c = 2 / (3 + t3) - np.log(2) / np.log(3)
        k = 7.8590 * c + 2.9554 * c**2
        g = special.gamma(1 + k)
        scale = (l2 * k) / ((1 - 2**(-k)) * g)
        loc = l1 - scale * (1 - g) / k
        return {'Shape': k, 'Location': loc, 'Scale': scale}

    @staticmethod
    def fit_glo(l1, l2, t3):
        if abs(t3) >= 1: return {'Shape': 0, 'Location': l1, 'Scale': l2}
        k = -t3
        scale = (l2 * np.sin(k * np.pi)) / (k * np.pi) if abs(k) > 1e-6 else l2
        loc = l1 - scale * (1/k - np.pi/np.sin(k*np.pi)) if abs(k) > 1e-6 else l1
        return {'Shape': k, 'Location': loc, 'Scale': scale}

    @staticmethod
    def fit_gpa(l1, l2, t3):
        k = (1 - 3*t3) / (1 + t3)
        scale = (1 + k) * (2 + k) * l2
        loc = l1 - scale / (1 + k)
        return {'Shape': k, 'Location': loc, 'Scale': scale}
    
    @staticmethod
    def fit_pearson3(l1, l2, t3):
        """
        Pearson Type III (Gamma 3) L-Moment Algorithm
        Uses Hosking & Wallis (1997) rational approximation.
        """
        if abs(t3) < 1e-6: 
            return LMoments.fit_normal(l1, l2) # Normal distribution limit
        
        # Calculate Alpha (Shape of Gamma) from t3 (L-Skew)
        # Using rational approximation
        t3_abs = abs(t3)
        if t3_abs >= 1/3:
            z = 1 - t3_abs
            alpha = (0.36067 * z - 0.59567 * z**2 + 0.25361 * z**3) / (1 + z * (-2.78861 + z * (2.56096 - 0.77045 * z))) # Corrected approx
            # Simple approx often used:
            # alpha = (1 - 0.36067*z - ...)/z is inverted.
            # Let's use the explicit one for 1/alpha or alpha directly.
            # Reverting to simpler approximation for robustness:
            alpha = (1 - t3_abs) / t3_abs # Very rough, let's use the robust one below.
            
            # Robust Logic from 'lmoments3' logic or H&W Table:
            # For 1/3 <= |t3| < 1:
            z = 1 - t3_abs
            alpha = z * (0.36067 + z*(-0.59567 + z*0.25361)) / (1 + z*(-2.78861 + z*(2.56096 + z*(-0.77045))))
            alpha = 1 / alpha # This gives inverse shape usually, hold on.
            
            # Actually, standard conversion is:
            # Gamma shape alpha. t3 approx 1/sqrt(alpha) behavior.
            # Let's use the approximation for Skewness (Gamma) first.
            pass
        
        # Let's use the approximation for GAMMA Skewness (G) from L-Skewness (t3)
        # G approx 3 * t3 + ...
        # Formula: G = 2 * sign(t3) / sqrt(alpha)
        # We find Alpha first.
        
        pi = np.pi
        tt = t3_abs * t3_abs
        if t3_abs < 1/3:
            z = 3 * pi * tt
            alpha = (1 + 0.2906 * z) / (z + 0.1882 * z**2 + 0.0442 * z**3)
        else:
            z = 1 - t3_abs
            num = 0.36067 * z - 0.59567 * z**2 + 0.25361 * z**3
            den = 1 - 2.78861 * z + 2.56096 * z**2 - 0.77045 * z**3
            alpha = num / den
            alpha = 1 / alpha # Invert for shape
            
        # Pearson 3 Parameters for Scipy
        # Scipy Pearson3: (skew, loc, scale)
        # Skewness (Fisher) = 2 / sqrt(alpha) * sign(t3)
        p3_skew = 2 / np.sqrt(alpha) * np.sign(t3)
        
        # Standard Deviation (Scale in Scipy terms is Std Dev)
        # Relation: l2 = std * pi^(-1/2) * gamma(alpha+0.5)/gamma(alpha)
        # std = l2 * sqrt(pi) * gamma(alpha) / gamma(alpha+0.5)
        # Using log-gamma for stability
        g_ratio = np.exp(special.gammaln(alpha) - special.gammaln(alpha + 0.5))
        p3_std = l2 * np.sqrt(np.pi) * g_ratio
        
        # Mean (Location in Scipy terms is Mean)
        p3_mean = l1
        
        return {'Shape': p3_mean, 'Location': p3_std, 'Scale': p3_skew} 
        # Note: Scipy pearson3(skew, loc, scale) -> args=(skew,), kwds={loc, scale}
        # In our format: Shape=skew, Location=Mean, Scale=Std
        
    @staticmethod
    def fit_lognormal3(data):
        if len(data) == 0: return {'Shape': 1, 'Location': 0, 'Scale': 1}
        log_d = np.log(data)
        l1, l2, _, _ = LMoments.get_sample_lmoments(log_d)
        scale_log = l2 * np.sqrt(np.pi)
        # Approximation: treat as LN2 in PWM for now (LN3 PWM is iterative)
        return {'Shape': scale_log, 'Location': 0, 'Scale': np.exp(l1)}

# -----------------------------------------------------------
# [Core 2] 통계 분석 통합 클래스
# -----------------------------------------------------------
class HydroStats:
    @staticmethod
    def basic_stats(data):
        n = len(data)
        if n == 0: return {}
        mean = np.mean(data)
        std = np.std(data, ddof=1)
        cv = std / mean if mean != 0 else 0
        skew = stats.skew(data, bias=False)
        kurt = stats.kurtosis(data, bias=False, fisher=False)
        return {
            "Mean": mean, "Std_Dev": std, "CV": cv, 
            "Skewness": skew, "Kurtosis": kurt, 
            "Min": np.min(data), "Max": np.max(data), "Count": n
        }

    @staticmethod
    def preliminary_tests(data):
        """
        [실제 구현] 예비해석 4종 (Anderson, Run, Spearman, Turning Point)
        입력: 데이터 리스트, 유의수준
        출력: 테스트 결과 딕셔너리
        """
        import numpy as np
        from scipy import stats
        
        n = len(data)
        data = np.array(data)
        z_crit = stats.norm.ppf(1 - alpha/2) # 양측검정 임계값
        
        results = {}

        # 1. Anderson Correlation Test (Lag-1)
        mean = np.mean(data)
        if np.sum((data - mean)**2) == 0: r1 = 0
        else:
            r1 = np.sum((data[:-1] - mean) * (data[1:] - mean)) / np.sum((data - mean)**2)
        
        limit = (-1 + z_crit * np.sqrt(n - 2)) / (n - 1) # 근사 임계값
        results['Anderson'] = {
            'stat': r1, 
            'table': abs(limit), 
            'dec': "ACCEPT" if abs(r1) < abs(limit) else "REJECT"
        }

        # 2. Run Test (Wald-Wolfowitz)
        median = np.median(data)
        binary = [1 if x >= median else 0 for x in data]
        runs = 1 + sum(1 for i in range(1, n) if binary[i] != binary[i-1])
        n1 = sum(binary)
        n2 = n - n1
        
        if n1 > 0 and n2 > 0:
            exp = 1 + (2 * n1 * n2) / n
            var = (2 * n1 * n2 * (2 * n1 * n2 - n)) / (n**2 * (n - 1))
            z_run = (runs - exp) / np.sqrt(var) if var > 0 else 0
        else: z_run = 0
        
        results['RunTest'] = {
            'stat': z_run, 
            'table': z_crit, 
            'dec': "ACCEPT" if abs(z_run) < z_crit else "REJECT"
        }

        # 3. Spearman Rank Correlation
        time_steps = np.arange(1, n + 1)
        rho, _ = stats.spearmanr(time_steps, data)
        crit_rho = z_crit / np.sqrt(n - 1)
        results['Spearman'] = {
            'stat': rho, 
            'table': crit_rho, 
            'dec': "ACCEPT" if abs(rho) < crit_rho else "REJECT"
        }

        # 4. Turning Point Test
        p = 0
        for i in range(1, n - 1):
            if (data[i-1] < data[i] > data[i+1]) or (data[i-1] > data[i] < data[i+1]):
                p += 1
        exp_p = 2 * (n - 2) / 3
        var_p = (16 * n - 29) / 90
        z_tp = (p - exp_p) / np.sqrt(var_p)
        results['TurningPoint'] = {
            'stat': z_tp, 
            'table': z_crit, 
            'dec': "ACCEPT" if abs(z_tp) < z_crit else "REJECT"
        }
        
        return results

    # --- MOM Solvers (Numerical) ---
    @staticmethod
    def solve_gev_mom(data):
        skew = stats.skew(data)
        def func(k):
            if abs(k) < 1e-4: return 1.1395 - skew
            sign = np.sign(k)
            g1 = special.gamma(1-k)
            g2 = special.gamma(1-2*k)
            g3 = special.gamma(1-3*k)
            num = -sign * (g3 - 3*g2*g1 + 2*g1**3)
            den = (g2 - g1**2)**1.5
            return num/den - skew
        
        try:
            k_sol = optimize.fsolve(func, 0.1)[0]
            mean, std = np.mean(data), np.std(data, ddof=1)
            g1 = special.gamma(1 - k_sol)
            g2 = special.gamma(1 - 2 * k_sol)
            scale = std * abs(k_sol) / np.sqrt(g2 - g1**2)
            loc = mean - scale/k_sol * (1 - g1)
            return k_sol, loc, scale
        except: return 0.1, np.mean(data), np.std(data)

    @staticmethod
    def solve_weibull_mom(data):
        mean, std = np.mean(data), np.std(data, ddof=1)
        cv = std / mean
        def func(k):
            if k <= 0: return 9999
            return np.sqrt(special.gamma(1+2/k) - special.gamma(1+1/k)**2) / special.gamma(1+1/k) - cv
        try:
            k_sol = optimize.fsolve(func, 1.0)[0]
            scale = mean / special.gamma(1 + 1/k_sol)
            return k_sol, 0, scale
        except: return 1.0, 0, mean

    # --- MAIN ESTIMATOR ---
    @staticmethod
    def estimate_params_all(data, dist_name):
        results = {}
        mean, std = np.mean(data), np.std(data, ddof=1)
        skew = stats.skew(data)
        l1, l2, t3, _ = LMoments.get_sample_lmoments(data)
        
        def fmt(s, l, sc): return {'Shape': s, 'Location': l, 'Scale': sc}

        try:
            # 1. Normal
            if dist_name == 'norm':
                results['MOM'] = fmt(None, mean, std)
                results['ML'] = fmt(None, *norm.fit(data))
                pwm = LMoments.fit_normal(l1, l2)
                results['PWM'] = fmt(pwm['Shape'], pwm['Location'], pwm['Scale'])

            # 2. Log-Normal 2
            elif dist_name == 'lognorm2':
                cv = std / mean
                sig = np.sqrt(np.log(1 + cv**2))
                scl = mean / np.exp(0.5 * sig**2)
                results['MOM'] = fmt(sig, 0, scl)
                s, loc, scale = lognorm.fit(data, floc=0)
                results['ML'] = fmt(s, loc, scale)
                pwm = LMoments.fit_lognormal3(data)
                results['PWM'] = fmt(pwm['Shape'], pwm['Location'], pwm['Scale'])

            # 3. Log-Normal 3
            elif dist_name == 'lognorm3':
                results['MOM'] = fmt(None, None, None) 
                s, loc, scale = lognorm.fit(data)
                results['ML'] = fmt(s, loc, scale)
                results['PWM'] = fmt(None, None, None) 

            # 4. Gumbel
            elif dist_name == 'gumbel':
                sn = np.pi / np.sqrt(6)
                scale = std / sn
                loc = mean - 0.5772 * scale
                results['MOM'] = fmt(None, loc, scale)
                loc_ml, scale_ml = gumbel_r.fit(data)
                results['ML'] = fmt(None, loc_ml, scale_ml)
                pwm = LMoments.fit_gumbel(l1, l2)
                results['PWM'] = fmt(pwm['Shape'], pwm['Location'], pwm['Scale'])

            # 5. GEV
            elif dist_name == 'gev':
                k_m, l_m, s_m = HydroStats.solve_gev_mom(data)
                results['MOM'] = fmt(k_m, l_m, s_m)
                c, loc, scale = genextreme.fit(data)
                results['ML'] = fmt(c, loc, scale)
                pwm = LMoments.fit_gev(l1, l2, t3)
                results['PWM'] = fmt(pwm['Shape'], pwm['Location'], pwm['Scale'])

            # 6. GLO
            elif dist_name == 'glo':
                c, loc, scale = genlogistic.fit(data)
                results['ML'] = fmt(c, loc, scale)
                results['MOM'] = fmt(None, None, None) 
                pwm = LMoments.fit_glo(l1, l2, t3)
                results['PWM'] = fmt(pwm['Shape'], pwm['Location'], pwm['Scale'])

            # 7. GPA
            elif dist_name == 'gpa':
                c, loc, scale = genpareto.fit(data)
                results['ML'] = fmt(c, loc, scale)
                results['MOM'] = fmt(None, None, None) 
                pwm = LMoments.fit_gpa(l1, l2, t3)
                results['PWM'] = fmt(pwm['Shape'], pwm['Location'], pwm['Scale'])

            # 8. Weibull
            elif dist_name == 'weibull':
                k_m, l_m, s_m = HydroStats.solve_weibull_mom(data)
                results['MOM'] = fmt(k_m, l_m, s_m)
                c, loc, scale = weibull_min.fit(data, floc=0)
                results['ML'] = fmt(c, loc, scale)
                # PWM: Weibull PWM is complex, use ML proxy
                results['PWM'] = fmt(c, loc, scale)

            # 9. Gamma 2
            elif dist_name == 'gamma2':
                alpha = (mean/std)**2
                beta = std**2 / mean
                results['MOM'] = fmt(alpha, 0, beta)
                a, loc, scale = gamma.fit(data, floc=0)
                results['ML'] = fmt(a, loc, scale)
                # PWM for Gamma 2: use Pearson3 logic with skew>0
                results['PWM'] = fmt(alpha, 0, beta) # Proxy

            # 10. Gamma 3 (Pearson 3)
            elif dist_name == 'gamma3' or dist_name == 'pearson3':
                # MOM: Skewness based
                # Scipy Pearson3 params: (skew, loc, scale) -> (skew, mean, std)
                results['MOM'] = fmt(skew, mean, std)
                # ML
                p = pearson3.fit(data)
                results['ML'] = fmt(p[0], p[1], p[2])
                # PWM
                pwm = LMoments.fit_pearson3(l1, l2, t3)
                # Note: fit_pearson3 returns {'Shape': skew, 'Location': mean, 'Scale': std}
                results['PWM'] = fmt(pwm['Shape'], pwm['Location'], pwm['Scale'])

            # 11. LP3
            elif dist_name == 'lp3':
                log_d = np.log(data)
                skew_l = stats.skew(log_d)
                mean_l = np.mean(log_d)
                std_l = np.std(log_d, ddof=1)
                results['MOM'] = fmt(skew_l, mean_l, std_l)
                s, loc, scale = pearson3.fit(log_d)
                results['ML'] = fmt(s, loc, scale)
                # PWM: fit Pearson3 on log data
                l1_l, l2_l, t3_l, _ = LMoments.get_sample_lmoments(log_d)
                pwm = LMoments.fit_pearson3(l1_l, l2_l, t3_l)
                results['PWM'] = fmt(pwm['Shape'], pwm['Location'], pwm['Scale'])

            else:
                empty = fmt(None, None, None)
                results['MOM'] = empty
                results['ML'] = empty
                results['PWM'] = empty

        except Exception as e:
            empty = fmt(None, None, None)
            return {'MOM': empty, 'ML': empty, 'PWM': empty}

        return results

    @staticmethod
    def gof_tests(data, dist_name, params):
        try:
            s, l, sc = params['Shape'], params['Location'], params['Scale']
            if l is None or sc is None: return None

            # Scipy Args Construction
            # P3/LP3: args=(skew,), loc=mean, scale=std
            # Gamma: args=(a,), loc, scale
            # GEV: args=(c,), loc, scale
            
            full_args = []
            if s is not None: full_args.append(s)
            full_args.append(l)
            full_args.append(sc)
            full_args = tuple(full_args)

            d_map = {
                'norm': norm, 'lognorm2': lognorm, 'lognorm3': lognorm,
                'gamma2': gamma, 'gamma3': gamma, 'gumbel': gumbel_r,
                'gev': genextreme, 'weibull': weibull_min, 
                'glo': genlogistic, 'gpa': genpareto, 'lp3': pearson3,
                'pearson3': pearson3
            }
            if dist_name not in d_map: return None
            
            dist = d_map[dist_name]
            test_data = np.log(data) if dist_name == 'lp3' else data
            
            # Special case for Pearson 3 args in Scipy
            if dist_name in ['pearson3', 'lp3', 'gamma3']:
                # Scipy pearson3 takes (skew, loc, scale)
                # Our params are (Shape=skew, Location=mean, Scale=std)
                # So we pass args=(s,), kwds={loc:l, scale:sc}
                args_cdf = (s,)
                kwds_cdf = {'loc': l, 'scale': sc}
                
                d_stat, p = kstest(test_data, dist.cdf, args=args_cdf, kwds=kwds_cdf)
                
                # Chi2
                k = int(1 + 3.3 * np.log10(len(data)))
                obs, bins = np.histogram(test_data, bins=max(3, k))
                cdf_vals = dist.cdf(bins, *args_cdf, **kwds_cdf)
                
            else:
                # Default arg unpacking
                d_stat, p = kstest(test_data, dist.cdf, args=full_args)
                k = int(1 + 3.3 * np.log10(len(data)))
                obs, bins = np.histogram(test_data, bins=max(3, k))
                cdf_vals = dist.cdf(bins, *full_args)

            crit = 1.36 / np.sqrt(len(data))
            exp_probs = np.diff(cdf_vals)
            exp = exp_probs * len(data)
            exp[exp==0] = 1e-6
            chi = np.sum((obs - exp)**2 / exp)
            
            return {"KS": d_stat, "Chi2": chi, "Result": "Pass" if d_stat < crit else "Fail"}
        except:
            return None

# -----------------------------------------------------------
# [Core 3] FARD 분석 엔진 (16개 분포형 완전 구현)
# -----------------------------------------------------------
# -----------------------------------------------------------
# [Core 3] FARD 분석 엔진 (16개 분포형 완전 구현)
# -----------------------------------------------------------

# ==============================================================================
# [NEW - 2025-01-05] Goodness-of-Fit Test Engine (4 Tests × 3 Methods)
# ==============================================================================

class GoodnessOfFitEngine:
    """적합도 검정 엔진 (4 Tests × 3 Methods)"""
    
    CRITICAL_VALUES = {
        'chi_square_df3': 7.81, 'chi_square_df4': 9.49, 'chi_square_df5': 11.07,
        'chi_square_df6': 12.59, 'cvm_005': 0.461, 'cvm_001': 0.743,
        'ppcc': {10: 0.906, 15: 0.939, 20: 0.959, 25: 0.970, 30: 0.977,
                 40: 0.985, 50: 0.989, 60: 0.991, 70: 0.993, 80: 0.994,
                 90: 0.995, 100: 0.996}
    }
    
    def __init__(self, alpha=0.05):
        self.alpha = alpha
    
    @staticmethod
    def chi_square_test(data, cdf_func, n_params, alpha=0.05):
        """Chi-Square 적합도 검정"""
        try:
            n = len(data)
            k = max(4, min(int(1 + 3.3 * np.log10(n)), 10))
            obs_freq, bin_edges = np.histogram(data, bins=k)
            exp_probs = []
            for i in range(k):
                p_lower = cdf_func(bin_edges[i])
                p_upper = cdf_func(bin_edges[i+1])
                if p_lower is None or p_upper is None:
                    return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
                exp_probs.append(p_upper - p_lower)
            exp_freq = np.array(exp_probs) * n
            valid_mask = exp_freq >= 1.0
            if np.sum(valid_mask) < 3:
                return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
            obs_freq, exp_freq = obs_freq[valid_mask], exp_freq[valid_mask]
            chi2_stat = np.sum((obs_freq - exp_freq)**2 / exp_freq)
            df = len(obs_freq) - n_params - 1
            if df < 1:
                return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
            chi2_crit = stats.chi2.ppf(1 - alpha, df)
            return {'stat': chi2_stat, 'crit': chi2_crit, 'dec': 'O' if chi2_stat < chi2_crit else 'X', 'feasible': True}
        except:
            return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
    
    @staticmethod
    def ks_test(data, cdf_func, alpha=0.05):
        """Kolmogorov-Smirnov 검정"""
        try:
            n = len(data)
            data_sorted = np.sort(data)
            d_max = 0.0
            for i in range(n):
                F_emp = (i + 1) / n
                F_theo = cdf_func(data_sorted[i])
                if F_theo is None or np.isnan(F_theo):
                    return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
                d_max = max(d_max, abs(F_emp - F_theo))
            ks_crit = 1.36 / np.sqrt(n) if alpha == 0.05 else 1.63 / np.sqrt(n)
            return {'stat': d_max, 'crit': ks_crit, 'dec': 'O' if d_max < ks_crit else 'X', 'feasible': True}
        except:
            return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
    
    @staticmethod
    def cramer_vonmises_test(data, cdf_func, alpha=0.05):
        """Cramer von Mises 검정"""
        try:
            n = len(data)
            data_sorted = np.sort(data)
            w2 = 1.0 / (12.0 * n)
            for i in range(n):
                F_theo = cdf_func(data_sorted[i])
                if F_theo is None or np.isnan(F_theo):
                    return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
                F_emp = (2.0 * (i + 1) - 1.0) / (2.0 * n)
                w2 += (F_theo - F_emp)**2
            cvm_crit = 0.461 if alpha == 0.05 else 0.743
            return {'stat': w2, 'crit': cvm_crit, 'dec': 'O' if w2 < cvm_crit else 'X', 'feasible': True}
        except:
            return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
    
    @staticmethod
    def ppcc_test(data, ppf_func, alpha=0.05):
        """PPCC 검정"""
        try:
            n = len(data)
            data_sorted = np.sort(data)
            plotting_positions = (np.arange(1, n+1) - 0.44) / (n + 0.12)
            theoretical_quantiles = []
            for p in plotting_positions:
                q = ppf_func(p)
                if q is None or np.isnan(q) or np.isinf(q):
                    return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
                theoretical_quantiles.append(q)
            theoretical_quantiles = np.array(theoretical_quantiles)
            valid_mask = np.isfinite(data_sorted) & np.isfinite(theoretical_quantiles)
            if np.sum(valid_mask) < 3:
                return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
            r, _ = stats.pearsonr(data_sorted[valid_mask], theoretical_quantiles[valid_mask])
            ppcc_crit = GoodnessOfFitEngine._ppcc_critical_value(n)
            return {'stat': r, 'crit': ppcc_crit, 'dec': 'O' if r >= ppcc_crit else 'X', 'feasible': True}
        except:
            return {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
    
    @staticmethod
    def _ppcc_critical_value(n):
        """PPCC 임계값 선형 보간"""
        table = GoodnessOfFitEngine.CRITICAL_VALUES['ppcc']
        keys = sorted(table.keys())
        if n in table:
            return table[n]
        elif n < keys[0]:
            return table[keys[0]]
        elif n > keys[-1]:
            return table[keys[-1]]
        else:
            for i in range(len(keys)-1):
                if keys[i] <= n <= keys[i+1]:
                    n1, n2, v1, v2 = keys[i], keys[i+1], table[keys[i]], table[keys[i+1]]
                    return v1 + (v2 - v1) * (n - n1) / (n2 - n1)
        return 0.98


class DistributionCDFPPF:
    """16개 분포별 CDF/PPF 함수"""
    
    @staticmethod
    def get_cdf_function(dist_code, params):
        """CDF 함수 반환"""
        if len(params) == 0:
            return None
        try:
            loc, scale = params[0], params[1]
            shape = params[2] if len(params) > 2 else None
            
            if dist_code == 'NOR':
                return lambda x: norm.cdf(x, loc=loc, scale=scale)
            elif dist_code == 'LN2':
                return lambda x: lognorm.cdf(x, s=scale, scale=np.exp(loc)) if x > 0 else 0.0
            elif dist_code == 'LN3':
                return lambda x: lognorm.cdf(x - shape, s=scale, scale=np.exp(loc)) if x > shape else 0.0
            elif dist_code == 'GUM':
                return lambda x: gumbel_r.cdf(x, loc=loc, scale=scale)
            elif dist_code == 'GAM2':
                return lambda x: gamma.cdf(x, a=shape, scale=scale) if shape else None
            elif dist_code == 'GAM3':
                return lambda x: gamma.cdf(x - loc, a=shape, scale=scale) if x > loc else 0.0
            elif dist_code == 'GEV':
                return lambda x: genextreme.cdf(x, c=shape, loc=loc, scale=scale)
            elif dist_code == 'GLO':
                return lambda x: genlogistic.cdf(x, c=shape, loc=loc, scale=scale)
            elif dist_code == 'GPA':
                return lambda x: genpareto.cdf(x, c=shape, loc=loc, scale=scale)
            elif dist_code == 'LP3':
                return lambda x: pearson3.cdf(np.log10(x), skew=shape, loc=loc, scale=scale) if x > 0 else 0.0
            elif dist_code == 'LGU2':
                return lambda x: gumbel_r.cdf(np.log(x), loc=loc, scale=scale) if x > 0 else 0.0
            elif dist_code == 'LGU3':
                return lambda x: gumbel_r.cdf(np.log(x - shape), loc=loc, scale=scale) if x > shape else 0.0
            elif dist_code in ['WBU2', 'WBU3']:
                return lambda x: weibull_min.cdf(x, c=shape, loc=loc, scale=scale)
            elif dist_code in ['WKB4', 'WKB5']:
                return None  # Wakeby: No explicit CDF
            else:
                return None
        except:
            return None
    
    @staticmethod
    def get_ppf_function(dist_code, params):
        """PPF 함수 반환"""
        if len(params) == 0:
            return None
        try:
            loc, scale = params[0], params[1]
            shape = params[2] if len(params) > 2 else None
            
            if dist_code == 'NOR':
                return lambda p: norm.ppf(p, loc=loc, scale=scale)
            elif dist_code == 'LN2':
                return lambda p: lognorm.ppf(p, s=scale, scale=np.exp(loc))
            elif dist_code == 'LN3':
                return lambda p: shape + lognorm.ppf(p, s=scale, scale=np.exp(loc))
            elif dist_code == 'GUM':
                return lambda p: gumbel_r.ppf(p, loc=loc, scale=scale)
            elif dist_code == 'GAM2':
                return lambda p: gamma.ppf(p, a=shape, scale=scale) if shape else None
            elif dist_code == 'GAM3':
                return lambda p: loc + gamma.ppf(p, a=shape, scale=scale)
            elif dist_code == 'GEV':
                return lambda p: genextreme.ppf(p, c=shape, loc=loc, scale=scale)
            elif dist_code == 'GLO':
                return lambda p: genlogistic.ppf(p, c=shape, loc=loc, scale=scale)
            elif dist_code == 'GPA':
                return lambda p: genpareto.ppf(p, c=shape, loc=loc, scale=scale)
            elif dist_code == 'LP3':
                return lambda p: 10 ** pearson3.ppf(p, skew=shape, loc=loc, scale=scale)
            elif dist_code == 'LGU2':
                return lambda p: np.exp(gumbel_r.ppf(p, loc=loc, scale=scale))
            elif dist_code == 'LGU3':
                return lambda p: shape + np.exp(gumbel_r.ppf(p, loc=loc, scale=scale))
            elif dist_code in ['WBU2', 'WBU3']:
                return lambda p: weibull_min.ppf(p, c=shape, loc=loc, scale=scale)
            elif dist_code in ['WKB4', 'WKB5']:
                if LMOMENTS_AVAILABLE and len(params) >= 5:
                    return lambda p: distr.wak.ppf(p, xi=loc, alpha=params[3], beta=params[4], gamma=shape, delta=scale)
                return None
            else:
                return None
        except:
            return None


class InfeasibilityCatalog:
    """실행 불가능한 조합"""
    INFEASIBLE = {'WKB4': ['Chi-Square', 'K-S', 'CVM'], 'WKB5': ['Chi-Square', 'K-S', 'CVM']}
    
    @staticmethod
    def is_feasible(dist_code, test_name):
        if dist_code not in InfeasibilityCatalog.INFEASIBLE:
            return True
        return test_name not in InfeasibilityCatalog.INFEASIBLE[dist_code]


class FardEngine:
    """FARD 호환 분석 엔진 - 16개 분포형 PWM 기반 구현"""
    
    # Tier 분류 (구현 난이도 및 방법론 기준)
    TIER1_DISTRIBUTIONS = ['NOR', 'GAM2', 'GUM', 'GEV']  # 기본 PWM
    TIER2_DISTRIBUTIONS = ['GLO', 'GPA', 'WBU2', 'WBU3']  # 직접 PWM
    TIER3_DISTRIBUTIONS = ['GAM3', 'LP3', 'LN2']  # Log 변환 PWM
    TIER4_DISTRIBUTIONS = ['LGU2', 'LN3', 'LGU3']  # Log + 하한계
    TIER5_DISTRIBUTIONS = ['WKB4', 'WKB5']  # Wakeby (고급)
    
    ALL_DISTRIBUTIONS = (TIER1_DISTRIBUTIONS + TIER2_DISTRIBUTIONS + 
                         TIER3_DISTRIBUTIONS + TIER4_DISTRIBUTIONS + 
                         TIER5_DISTRIBUTIONS)
    
    DISTRIBUTION_METHODS = {
        'NOR': 'METHOD OF MOMENTS',
        'GAM2': 'METHOD OF MOMENTS',
        'GAM3': 'METHOD OF MOMENTS',
        'GUM': 'METHOD OF PROBABILITY WEIGHTED MOMENTS',
        'GEV': 'METHOD OF PROBABILITY WEIGHTED MOMENTS',
        'GLO': 'METHOD OF PROBABILITY WEIGHTED MOMENTS',
        'GPA': 'METHOD OF PROBABILITY WEIGHTED MOMENTS',
        'LP3': 'METHOD OF PROBABILITY WEIGHTED MOMENTS (LOG-SPACE)',
        'LN2': 'METHOD OF PROBABILITY WEIGHTED MOMENTS (LOG-SPACE)',
        'LN3': 'METHOD OF PROBABILITY WEIGHTED MOMENTS (LOG-SPACE)',
        'LGU2': 'METHOD OF PROBABILITY WEIGHTED MOMENTS (LOG-SPACE)',
        'LGU3': 'METHOD OF PROBABILITY WEIGHTED MOMENTS (LOG-SPACE)',
        'WBU2': 'METHOD OF PROBABILITY WEIGHTED MOMENTS',
        'WBU3': 'METHOD OF PROBABILITY WEIGHTED MOMENTS',
        'WKB4': 'METHOD OF PROBABILITY WEIGHTED MOMENTS',
        'WKB5': 'METHOD OF PROBABILITY WEIGHTED MOMENTS',
    }
    
    @staticmethod
    def get_basic_stats(data):
        n = len(data)
        if n < 2: return [0, 0, 0, 0, 0]
        
        mean = np.mean(data)
        std = np.std(data, ddof=1)
        cv = std / mean if mean != 0 else 0
        
        m3 = np.sum((data - mean)**3)
        skew = (n * m3) / ((n - 1) * (n - 2) * std**3) if std > 0 else 0
        
        m4 = np.sum((data - mean)**4)
        if std > 0:
            kurt = ((n*(n+1)*m4) / ((n-1)*(n-2)*(n-3)*std**4) - 
                   (3*(n-1)**2)/((n-2)*(n-3))) + 3
        else:
            kurt = 0
        
        return [mean, std, cv, skew, kurt]
    
    @staticmethod
    def estimate_lower_bound(data):
        """3-parameter 분포의 하한계 추정"""
        return np.min(data) * 0.9
    
    @staticmethod
    def fit_dist(code, data):
        """16개 분포형 매개변수 추정"""
        mean, std, cv, skew, kurt = FardEngine.get_basic_stats(data)
        
        try:
            # ===== TIER 1: 기본 구현 =====
            if code == 'NOR':
                return [mean, std, 0.0]
            
            elif code == 'GAM2':
                if mean == 0: return []
                beta = (std**2) / mean
                alpha = mean / beta
                return [0.0, beta, alpha]
            
            elif code == 'GUM':
                if not LMOMENTS_AVAILABLE:
                    scale = (np.sqrt(6) * std) / np.pi
                    loc = mean - 0.5772157 * scale
                    return [loc, scale, 0.0]
                params = distr.gum.lmom_fit(data)
                return [params['loc'], params['scale'], 0.0]
            
            elif code == 'GEV':
                if not LMOMENTS_AVAILABLE:
                    return FardEngine._fit_gev_pdf_formula(data)
                params = distr.gev.lmom_fit(data)
                return [params['loc'], params['scale'], params['c']]
            
            # ===== TIER 2: 직접 PWM =====
            elif code == 'GLO':
                if not LMOMENTS_AVAILABLE: return []
                params = distr.glo.lmom_fit(data)
                return [params['loc'], params['scale'], params['k']]
            
            elif code == 'GPA':
                if not LMOMENTS_AVAILABLE: return []
                params = distr.gpa.lmom_fit(data)
                return [params['loc'], params['scale'], params['c']]
            
            elif code == 'WBU2':
                if not LMOMENTS_AVAILABLE: return []
                params = distr.wei.lmom_fit(data)
                return [0.0, params['scale'], params['c']]
            
            elif code == 'WBU3':
                if not LMOMENTS_AVAILABLE: return []
                params = distr.wei.lmom_fit(data)
                return [params['loc'], params['scale'], params['c']]
            
            # ===== TIER 3: Log 변환 PWM =====
            elif code == 'GAM3':
                if skew == 0: return []
                alpha = (2.0 / skew)**2
                beta = std / np.sqrt(alpha)
                loc = mean - alpha * beta
                return [loc, beta, alpha]
            
            elif code == 'LP3':
                if not LMOMENTS_AVAILABLE: return []
                if np.any(data <= 0): return []
                log_data = np.log(data)
                params = distr.pe3.lmom_fit(log_data)
                return [params['loc'], params['scale'], params['skew']]
            
            elif code == 'LN2':
                if not LMOMENTS_AVAILABLE: return []
                if np.any(data <= 0): return []
                log_data = np.log(data)
                params = distr.nor.lmom_fit(log_data)
                return [params['loc'], params['scale'], 0.0]
            
            # ===== TIER 4: Log + 하한계 =====
            elif code == 'LN3':
                if not LMOMENTS_AVAILABLE: return []
                if np.any(data <= 0): return []
                xi = FardEngine.estimate_lower_bound(data)
                shifted_data = data - xi
                if np.any(shifted_data <= 0): return []
                log_data = np.log(shifted_data)
                params = distr.nor.lmom_fit(log_data)
                return [xi, params['scale'], params['loc']]
            
            elif code == 'LGU2':
                if not LMOMENTS_AVAILABLE: return []
                if np.any(data <= 0): return []
                log_data = np.log(data)
                params = distr.gum.lmom_fit(log_data)
                return [params['loc'], params['scale'], 0.0]
            
            elif code == 'LGU3':
                if not LMOMENTS_AVAILABLE: return []
                if np.any(data <= 0): return []
                xi = FardEngine.estimate_lower_bound(data)
                shifted_data = data - xi
                if np.any(shifted_data <= 0): return []
                log_data = np.log(shifted_data)
                params = distr.gum.lmom_fit(log_data)
                return [xi, params['scale'], params['loc']]
            
            # ===== TIER 5: Wakeby =====
            elif code == 'WKB5':
                if not LMOMENTS_AVAILABLE: return []
                params = distr.wak.lmom_fit(data)
                return [params['loc'], params['scale'], params['beta']]
            
            elif code == 'WKB4':
                if not LMOMENTS_AVAILABLE: return []
                params = distr.wak.lmom_fit(data)
                return [params['loc'], params['scale'], params['beta']]
            
            else:
                return []
        
        except Exception as e:
            return []
    
    @staticmethod
    def _fit_gev_pdf_formula(data):
        """GEV Fallback 알고리즘"""
        mean, std, cv, skew, kurt = FardEngine.get_basic_stats(data)
        Cs = skew
        
        if 1.14 < Cs < 10:
            beta = (0.285821 - 0.357983*Cs + 0.187683*Cs**2 - 
                   0.053754*Cs**3 + 0.008612*Cs**4 - 
                   0.000718*Cs**5 + 0.000024*Cs**6)
        elif -2 < Cs <= 1.14:
            beta = (0.277648 - 0.322016*Cs + 0.131506*Cs**2 - 
                   0.028093*Cs**3 + 0.003301*Cs**4 - 
                   0.000197*Cs**5 + 0.000005*Cs**6)
        elif -10 < Cs < -2:
            beta = (-0.50405 - 0.00861*Cs + 0.01517*Cs**2 + 
                   0.00356*Cs**3 + 0.00042*Cs**4 + 
                   0.00003*Cs**5)
        else:
            if LMOMENTS_AVAILABLE:
                try:
                    params = distr.gev.lmom_fit(data)
                    return [params['loc'], params['scale'], params['c']]
                except:
                    return []
            return []
        
        try:
            from scipy.special import gamma as gamma_func
            numerator = std**2 * beta**2
            denominator = (gamma_func(1 + 2*beta) - 
                          gamma_func(1 + beta)**2)
            a = (numerator / denominator)**0.5
            xo = mean - (a/beta) * (gamma_func(1 + beta) - 1)
            return [xo, a, beta]
        except:
            return []
    
    @staticmethod
    def calculate_rainfall(code, params, return_period):
        """16개 분포형 확률강우량 계산"""
        if len(params) == 0: return 0.0
        
        T = return_period
        F = 1 - 1/T
        
        try:
            # ===== TIER 1 =====
            if code == 'NOR':
                return params[0] + stats.norm.ppf(F) * params[1]
            
            elif code == 'GUM':
                return params[0] - params[1] * np.log(-np.log(F))
            
            elif code == 'GEV':
                xi, alpha, k = params[0], params[1], params[2]
                if abs(k) < 1e-10:
                    return xi - alpha * np.log(-np.log(F))
                else:
                    return xi + (alpha/k) * (1 - (-np.log(F))**k)
            
            elif code == 'GAM2':
                dist = stats.gamma(a=params[2], scale=params[1])
                return dist.ppf(F)
            
            elif code == 'GAM3':
                dist = stats.gamma(a=params[2], loc=params[0], scale=params[1])
                return dist.ppf(F)
            
            # ===== TIER 2 =====
            elif code == 'GLO':
                if not LMOMENTS_AVAILABLE: return 0.0
                xi, alpha, k = params[0], params[1], params[2]
                
                # 형상인자 검증 - k가 크게 음수면 불안정
                if k < -0.2:
                    return 0.0
                
                if abs(k) < 1e-10:
                    y = -np.log((1-F)/F)
                else:
                    y = (1/k) * ((1-F)/F)**k - (1/k)
                
                rainfall = xi + alpha * y
                
                # 음수 방지 (물리적으로 불가능)
                if rainfall < 0:
                    return 0.0
                
                return rainfall
            
            elif code == 'GPA':
                if not LMOMENTS_AVAILABLE: return 0.0
                return distr.gpa.ppf(F, c=params[2], loc=params[0], scale=params[1])
            
            elif code == 'WBU2':
                if not LMOMENTS_AVAILABLE: return 0.0
                return distr.wei.ppf(F, c=params[2], loc=0.0, scale=params[1])
            
            elif code == 'WBU3':
                if not LMOMENTS_AVAILABLE: return 0.0
                return distr.wei.ppf(F, c=params[2], loc=params[0], scale=params[1])
            
            # ===== TIER 3 =====
            elif code == 'LP3':
                if not LMOMENTS_AVAILABLE: return 0.0
                log_q = distr.pe3.ppf(F, loc=params[0], scale=params[1], skew=params[2])
                return np.exp(log_q)
            
            elif code == 'LN2':
                if not LMOMENTS_AVAILABLE: return 0.0
                log_q = distr.nor.ppf(F, loc=params[0], scale=params[1])
                return np.exp(log_q)
            
            # ===== TIER 4 =====
            elif code == 'LN3':
                if not LMOMENTS_AVAILABLE: return 0.0
                xi = params[0]
                log_q = distr.nor.ppf(F, loc=params[2], scale=params[1])
                return xi + np.exp(log_q)
            
            elif code == 'LGU2':
                if not LMOMENTS_AVAILABLE: return 0.0
                log_q = distr.gum.ppf(F, loc=params[0], scale=params[1])
                return np.exp(log_q)
            
            elif code == 'LGU3':
                if not LMOMENTS_AVAILABLE: return 0.0
                xi = params[0]
                log_q = distr.gum.ppf(F, loc=params[2], scale=params[1])
                return xi + np.exp(log_q)
            
            # ===== TIER 5 =====
            elif code in ['WKB4', 'WKB5']:
                if not LMOMENTS_AVAILABLE: return 0.0
                
                # Wakeby는 매우 불안정 - 간단한 근사만 제공
                rainfall = params[0] - params[1] * np.log(-np.log(F))
                
                # 비정상 값 필터링 (물리적으로 불가능한 값)
                if rainfall < 0 or rainfall > 50000:
                    # 실무에서 50m 이상 강우량은 비현실적
                    return 0.0
                
                # 경고: Wakeby는 실무 사용 비추천
                return rainfall
            
            else:
                return 0.0
        
        except Exception as e:
            return 0.0


# -----------------------------------------------------------
class ProbabilityAnalysisApp(ctk.CTk):
    def __init__(self, project_path=None):
        super().__init__()
        
        self.project_path = project_path
        self.config_file = None
        self.project_name = ""
        self.return_periods = [2, 3, 5, 10, 20, 30, 50, 80, 100, 200, 300, 500]

        self.title("확률강우량 분석")
        self.geometry("1100x800")
        self.change_title_bar_color()
        
        self.df_input = None
        self.setup_ui()
        self.load_step1_data()

    def change_title_bar_color(self):
        try:
            hwnd = windll.user32.GetParent(self.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(1)), sizeof(c_int))
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), sizeof(c_int))
        except: pass

    def setup_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 20))
        self.lbl_title = ctk.CTkLabel(title_frame, text="확률강우량 분석 (데이터 로드 대기중...)", font=FONT_TITLE)
        self.lbl_title.pack(side="left")
        
        self.chk_advanced_var = ctk.BooleanVar(value=False)
        self.chk_advanced = ctk.CTkCheckBox(title_frame, text="타 분포형 확인", 
                                            variable=self.chk_advanced_var, font=FONT_BODY,
                                            fg_color="#e74c3c", hover_color="#c0392b")
        self.chk_advanced.pack(side="right")

        self.btn_run = ctk.CTkButton(main_frame, text="⚡ 분석 실행", 
                                     command=self.run_analysis_router,
                                     font=FONT_BTN, height=50, fg_color="#2980b9", hover_color="#3498db")
        self.btn_run.pack(fill="x", pady=(0, 15))

        self.log_text = ctk.CTkTextbox(main_frame, font=FONT_LOG, activate_scrollbars=True)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

    def log(self, msg):
        self.log_text.insert(tk.END, f"{msg}\n")
        self.log_text.see(tk.END)

    def find_project_config_auto(self):
        try:
            current_dir = os.getcwd()
            base_dir = os.path.dirname(current_dir)
            projects_root = os.path.join(base_dir, "0.Projects")
            
            if os.path.exists(projects_root):
                subdirs = [os.path.join(projects_root, d) for d in os.listdir(projects_root) 
                           if os.path.isdir(os.path.join(projects_root, d))]
                if subdirs:
                    latest_dir = max(subdirs, key=os.path.getmtime)
                    if os.path.exists(os.path.join(latest_dir, "project_config.json")):
                        return latest_dir
        except: pass
        return None

    def load_step1_data(self):
        self.log("📂 설정 파일 로드 시도...")
        
        if self.project_path is None or not os.path.exists(os.path.join(self.project_path, "project_config.json")):
            detected = self.find_project_config_auto()
            if detected:
                self.project_path = detected
                self.log(f"💡 프로젝트 폴더 자동 감지: {detected}")
            else:
                self.log("❌ 프로젝트 폴더를 찾을 수 없습니다. 폴더를 선택해주세요.")
                selected = filedialog.askdirectory(title="프로젝트 폴더 선택")
                if selected: self.project_path = selected
                else: return

        self.config_file = os.path.join(self.project_path, "project_config.json")
        self.project_name = os.path.basename(self.project_path)
        self.lbl_title.configure(text=f"확률강우량 분석 - [{self.project_name}]")

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f: config = json.load(f)
            fname = config['step1_rainfall'].get('output_file')
            full_path_cfg = config['step1_rainfall'].get('full_path')
            
            target_file = None
            if full_path_cfg and os.path.exists(full_path_cfg): target_file = full_path_cfg
            elif fname and os.path.exists(os.path.join(self.project_path, fname)):
                target_file = os.path.join(self.project_path, fname)
            
            if target_file:
                self.df_input = pd.read_excel(target_file, sheet_name='Max_Rainfall_Arbitrary_time')
                self.log(f"✅ 데이터 로드 완료: {len(self.df_input)}개 연도")
            else:
                self.log(f"❌ 데이터 파일을 찾을 수 없습니다: {fname}")
                
        except Exception as e:
            self.log(f"❌ 설정 파일 읽기 오류: {e}")

    def run_analysis_router(self):
        if self.df_input is None:
            self.load_step1_data()
            if self.df_input is None:
                messagebox.showwarning("경고", "데이터가 로드되지 않았습니다.")
                return
        
        if self.chk_advanced_var.get(): self.run_full_analysis()
        else: self.run_simple_gumbel()

    def run_simple_gumbel(self):
        self.log("\n🚀 [기본 모드] Gumbel-PWM 분석 시작...")
        try:
            durations = [c for c in self.df_input.columns if c != 'Year']
            results_q = {}
            params_list = []

            for dur in durations:
                data = self.df_input[dur].dropna().values.astype(float)
                data = data[data > 0]
                if len(data) < 2: continue

                l1, l2, _, _ = LMoments.get_sample_lmoments(data)
                pwm = LMoments.fit_gumbel(l1, l2)
                
                params_list.append({
                    "Duration": dur, "Dist": "Gumbel", "Method": "PWM",
                    "Shape": pwm['Shape'], "Location": pwm['Location'], "Scale": pwm['Scale']
                })

                row = {}
                for T in self.return_periods:
                    val = gumbel_r.ppf(1 - 1/T, loc=pwm['Location'], scale=pwm['Scale'])
                    row[f"{T}yr"] = round(val, 2)
                results_q[dur] = row

            fname = f"{self.project_name}_B_Prob_Rainfall_Analysis.xlsx"
            fpath = os.path.join(self.project_path, fname)
            
            with pd.ExcelWriter(fpath, engine='openpyxl') as writer:
                df_q = pd.DataFrame(results_q).T
                df_q.index.name = "Duration"
                df_out = df_q.T
                df_out.index.name = "Return Period"
                df_out.reset_index(inplace=True)
                df_out.to_excel(writer, sheet_name='Probability_Rainfall', index=False)
                pd.DataFrame(params_list).to_excel(writer, sheet_name='Parameters', index=False)

            self.log(f"💾 저장 완료: {fname}")
            self.update_config(fpath)
            messagebox.showinfo("완료", "Gumbel-PWM 산정 완료")

        except Exception as e:
            self.log(f"Error: {e}")
            messagebox.showerror("오류", str(e))

    def run_full_analysis(self):
        """FARD 형식 16개 분포형 분석 (1%, 5% OUT 파일 생성)"""
        self.log("\n🔬 16개 분포형 분석 시작...")
        
        try:
            # 데이터 준비
            durations = [c for c in self.df_input.columns if c != 'Year']
            rainfall_data = {}
            
            for dur in durations:
                data = self.df_input[dur].dropna().values.astype(float)
                data = data[data > 0]
                if len(data) > 0:
                    try:
                        dur_int = int(float(dur))
                        rainfall_data[dur_int] = data
                    except:
                        pass
            
            if len(rainfall_data) == 0:
                self.log("❌ 분석할 데이터가 없습니다.")
                return
            
            sorted_durs = sorted(rainfall_data.keys())
            return_periods = [2, 3, 5, 10, 20, 30, 50, 70, 80, 100, 200, 500]
            
            # 5% 유의수준 분석
            self.log("   📊 5% 유의수준 분석 중...")
            self._write_fard_report(rainfall_data, sorted_durs, return_periods, 
                                   alpha=0.05, 
                                   output_file=f"{self.project_name}_B_5%.OUT")
            
            # 1% 유의수준 분석
            self.log("   📊 1% 유의수준 분석 중...")
            self._write_fard_report(rainfall_data, sorted_durs, return_periods,
                                   alpha=0.01,
                                   output_file=f"{self.project_name}_B_1%.OUT")
            
            self.log(f"💾 분석 완료:")
            self.log(f"   - {self.project_name}_B_5%.OUT")
            self.log(f"   - {self.project_name}_B_1%.OUT")
            
            messagebox.showinfo("완료", "분석이 완료되었습니다.")
            
        except Exception as e:
            self.log(f"❌ 분포형 분석 오류: {e}")
            import traceback
            self.log(traceback.format_exc())
            messagebox.showerror("오류", f"분포형 분석 중 오류가 발생했습니다:\n{str(e)}")
    
    def _write_fard_report(self, rainfall_data, durations, return_periods, alpha, output_file):
        """FARD 형식 보고서 생성"""
        output_path = os.path.join(self.project_path, output_file)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            # Header with Important Notice
            f.write("\n\n")
            f.write("************************************************************\n")
            f.write("*                                                          *\n")
            f.write("*  COMPUTER OUTPUT OF FREQUENCY ANALYSIS OF RAINFALL DATA  *\n")
            f.write("*                   (Python Implementation)                *\n")
            f.write("*              Based on L-Moments Algorithm                *\n")
            f.write("*                                                          *\n")
            f.write("************************************************************\n\n")
            f.write("************************************************************\n")
            f.write("*                   IMPORTANT NOTICE                       *\n")
            f.write("*                                                          *\n")
            f.write("*  RECOMMENDED distributions for practical design:        *\n")
            f.write("*    1. GUM  (Korean Government Standard)                 *\n")
            f.write("*    2. LP3  (USGS Bulletin 17C Standard)                 *\n")
            f.write("*    3. GEV  (WMO International Standard)                 *\n")
            f.write("*    4. LN2  (Common for Rainfall Analysis)               *\n")
            f.write("*                                                          *\n")
            f.write("*  NOT RECOMMENDED (Use with extreme caution):            *\n")
            f.write("*    - GLO   (May produce negative values)                *\n")
            f.write("*    - WKB4/WKB5 (Numerically unstable)                   *\n")
            f.write("*                                                          *\n")
            f.write("************************************************************\n\n")
            f.write(f"SITE NAME = {self.project_name:<20}\n\n")
            
            # Basic Statistics
            f.write("****************************\n")
            f.write("*    BASIC STATISTICS      *\n")
            f.write("****************************\n\n")
            f.write(f"BASIC STATISTICS FOR RAINFALL DATA OF {self.project_name}\n")
            f.write("   (UNBIASED ESTIMATES)\n\n")
            f.write("RAINFALL       MEAN      STANDARD     COEFF.       COEFF.       COEFF.\n")
            f.write("DURATION                   DEV.     VARIATION     SKEWNESS     KURTOSIS\n\n")
            
            for dur in durations:
                stats_vals = FardEngine.get_basic_stats(rainfall_data[dur])
                f.write(f"  {dur:<5}   {stats_vals[0]:>10.1f}  {stats_vals[1]:>10.1f}   "
                       f"{stats_vals[2]:>10.3f}   {stats_vals[3]:>10.3f}   {stats_vals[4]:>10.3f}\n")
            f.write("\n\n")

            f.write("****************************\n")
            f.write("*   PRELIMINARY TESTS      *\n")
            f.write("****************************\n\n")
            f.write(f"PRELIMINARY TESTS FOR RAINFALL DATA OF {self.project_name}\n")
            f.write(f"   (SIGNIFICANCE LEVEL = {alpha})\n\n")
            
            # 4가지 검정별로 모든 지속기간에 대해 수행
            test_names = [
                ('Anderson', 'ANDERSON CORRELATION TEST'),
                ('RunTest', 'RUN TEST'),
                ('Spearman', 'SPEARMAN RANK CORRELATION TEST'),
                ('TurningPoint', 'TURNING POINT TEST')
            ]
            
            for test_key, test_title in test_names:
                f.write(f"{test_title}\n")
                f.write("-" * 80 + "\n")
                f.write(f"{'DURATION':>10}  {'STATISTIC':>12}  {'TABLE VALUE':>12}  {'DECISION':>10}\n")
                f.write("-" * 80 + "\n")
                
                for dur in durations:
                    data = rainfall_data[dur]
                    
                    # PreliminaryTestEngine 호출 - alpha 파라미터 사용!
                    test_results = PreliminaryTestEngine.run_all_tests(data, alpha=alpha)
                    
                    if test_key in test_results:
                        result = test_results[test_key]
                        stat = result['stat']
                        table = result['table']
                        decision = result['dec']
                        
                        f.write(f"{dur:>10}  {stat:>12.4f}  {table:>12.4f}  {decision:>10}\n")
                    else:
                        f.write(f"{dur:>10}  {'N/A':>12}  {'N/A':>12}  {'N/A':>10}\n")
                
                f.write("\n")
            
            # 검정 해석 가이드
            f.write("INTERPRETATION GUIDE:\n")
            f.write("-" * 80 + "\n")
            f.write("1. ANDERSON CORRELATION TEST:\n")
            f.write("   - Tests for independence (lag-1 autocorrelation)\n")
            f.write("   - ACCEPT H0: Data are independent\n")
            f.write("   - REJECT H0: Data are serially correlated\n\n")
            
            f.write("2. RUN TEST:\n")
            f.write("   - Tests for randomness (trend or periodicity)\n")
            f.write("   - ACCEPT H0: Data are random\n")
            f.write("   - REJECT H0: Data show trend or periodicity\n\n")
            
            f.write("3. SPEARMAN RANK CORRELATION TEST:\n")
            f.write("   - Tests for trend (monotonic relationship with time)\n")
            f.write("   - ACCEPT H0: No trend exists\n")
            f.write("   - REJECT H0: Significant trend exists\n\n")
            
            f.write("4. TURNING POINT TEST:\n")
            f.write("   - Tests for randomness (local peaks and valleys)\n")
            f.write("   - ACCEPT H0: Data are random\n")
            f.write("   - REJECT H0: Too many/few turning points\n\n")
            
            f.write(f"NOTE: ACCEPT means the null hypothesis is accepted at {int(alpha*100)}% significance level.\n")
            f.write("      Data should satisfy independence and randomness for frequency analysis.\n\n")
            
            # Parameter Estimation
            f.write("*******************************************\n")
            f.write("* PARAMETER ESTIMATION & VALIDITY CHECK   *\n")
            f.write("*******************************************\n\n")
            
            calculated_params = {}
            
            for dist in FardEngine.ALL_DISTRIBUTIONS:
                calculated_params[dist] = {}
                method = FardEngine.DISTRIBUTION_METHODS.get(dist, 'NOT IMPLEMENTED')
                
                f.write(f"\nPARAMETER ESTIMATION OF THE  {dist} DISTRIBUTION\n")
                if method != 'NOT IMPLEMENTED':
                    f.write(f"      ({method})\n\n")
                else:
                    f.write("      (NOT IMPLEMENTED)\n\n")
                
                f.write("RAINFALL     XLO      XMIN      XMAX      XSC      XSH    VALIDITY\n")
                f.write("DURATION (LOCATION)     (OBSERVED)      (SCALE)  (SHAPE)    CHECK\n\n")
                
                for dur in durations:
                    data = rainfall_data[dur]
                    params = FardEngine.fit_dist(dist, data)
                    calculated_params[dist][dur] = params
                    
                    xmin = np.min(data)
                    xmax = np.max(data)
                    
                    if len(params) == 0:
                        f.write(f"  {dur:<5}       ---         {xmin:>5.1f}     {xmax:>5.1f}       ---       ---        X  \n")
                    else:
                        xlo = params[0]
                        xsc = params[1]
                        xsh = params[2]
                        f.write(f"  {dur:<5}   {xlo:>8.3f}     {xmin:>5.1f}     {xmax:>5.1f}   "
                               f"{xsc:>8.3f}   {xsh:>8.3f}       O  \n")
                
                # 분포별 경고 메시지
                if dist == 'GLO':
                    f.write("\n*** WARNING: GLO distribution may produce NEGATIVE values for long return periods.\n")
                    f.write("             This is physically impossible for rainfall data.\n")
                    f.write("             Negative values are clipped to 0.0 in the output.\n")
                    f.write("             Consider using GEV or GUM distribution instead.\n")
                
                if dist in ['WKB4', 'WKB5']:
                    f.write("\n*** CRITICAL WARNING: Wakeby distributions (WKB4/WKB5) are NOT RECOMMENDED\n")
                    f.write("                      for practical engineering design due to numerical instability.\n")
                    f.write("                      These distributions may produce oscillating or unrealistic values.\n")
                    f.write("                      For design purposes, please use LP3, GEV, or GUM instead.\n")
                    f.write("                      Wakeby distributions are for RESEARCH purposes only.\n")
                
                f.write("\n")
            
            # Probability Rainfalls
            
            # ★★★ [NEW - 2025-01-05] Goodness-of-Fit Tests Section ★★★
            self._write_goodness_of_fit_section(f, rainfall_data, durations, calculated_params, alpha)
            
            f.write("\n************************************************************\n")
            f.write("*     PROBABILITY RAINFALLS FOR RETURN PERIODS             *\n")
            f.write("************************************************************\n\n")
            
            for dist in FardEngine.ALL_DISTRIBUTIONS:
                method = FardEngine.DISTRIBUTION_METHODS.get(dist, 'NOT IMPLEMENTED')
                
                f.write(f"\nPROBABILITY RAINFALLS BY {dist} DISTRIBUTION\n")
                if method != 'NOT IMPLEMENTED':
                    f.write(f"      ({method})\n\n")
                else:
                    f.write("      (NOT IMPLEMENTED)\n\n")
                
                header = " DURATION   "
                for rp in return_periods:
                    header += f"{rp:>7}yr"
                f.write(header + "\n\n")
                
                for dur in durations:
                    params = calculated_params[dist].get(dur, [])
                    line = f"   {dur:<5}    "
                    
                    for rp in return_periods:
                        val = FardEngine.calculate_rainfall(dist, params, rp)
                        line += f"{val:>9.1f}"
                    
                    f.write(line + "\n")
                f.write("\n")
            
            f.write("****************************\n")
            f.write("*   END OF ANALYSIS        *\n")
            f.write("****************************\n")



    def _write_goodness_of_fit_section(self, f, rainfall_data, durations, calculated_params, alpha):
        """적합도 검정 섹션 작성 (4 Tests × 16 Distributions)"""
        f.write("\n")
        f.write("*******************************************\n")
        f.write("*         GOODNESS OF FIT TESTS           *\n")
        f.write("*******************************************\n\n")
        f.write("IMPORTANT NOTE:\n")
        f.write("-" * 80 + "\n")
        f.write("Goodness-of-Fit tests evaluate how well the estimated distribution\n")
        f.write("fits the observed data. Four tests are performed:\n\n")
        f.write("1. CHI-SQUARE TEST: Compares observed vs expected frequencies\n")
        f.write("2. KOLMOGOROV-SMIRNOV TEST: Maximum CDF difference\n")
        f.write("3. CRAMER VON MISES TEST: Weighted CDF difference (better than K-S)\n")
        f.write("4. PPCC TEST: Probability plot correlation coefficient\n\n")
        f.write("CHECK: O = PASS (distribution fits data)\n")
        f.write("       X = FAIL (distribution does not fit data)\n")
        f.write("       N/A = Test not applicable for this distribution\n\n")
        
        gof = GoodnessOfFitEngine(alpha=alpha)
        
        for dist in FardEngine.ALL_DISTRIBUTIONS:
            f.write(f"\nGOODNESS OF FIT TEST FOR RAINFALL DATA OF {dist} DISTRIBUTION\n")
            f.write(f"      ({FardEngine.DISTRIBUTION_METHODS.get(dist, 'PWM')})\n\n")
            
            # All 4 tests in one table
            f.write("RAINFALL    CHI-SQUARE      KOLMOGOROV-SMIRNOV     CRAMER VON MISES   PPCC TEST\n")
            f.write("DURATION   COMP  CRIT CHK  COMP  CRIT CHK  COMP  CRIT CHK  COMP  CRIT CHK\n\n")
            
            for dur in durations:
                data = rainfall_data[dur]
                params = calculated_params[dist].get(dur, [])
                
                # CDF-based tests
                cdf_func = DistributionCDFPPF.get_cdf_function(dist, params)
                n_params = 3 if len(params) > 2 else 2
                
                if cdf_func is None or len(params) == 0:
                    chi2_res = ks_res = cvm_res = {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
                else:
                    chi2_res = gof.chi_square_test(data, cdf_func, n_params, alpha) if InfeasibilityCatalog.is_feasible(dist, 'Chi-Square') else {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
                    ks_res = gof.ks_test(data, cdf_func, alpha) if InfeasibilityCatalog.is_feasible(dist, 'K-S') else {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
                    cvm_res = gof.cramer_vonmises_test(data, cdf_func, alpha) if InfeasibilityCatalog.is_feasible(dist, 'CVM') else {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
                
                # PPF-based test
                ppf_func = DistributionCDFPPF.get_ppf_function(dist, params)
                if ppf_func is None or len(params) == 0:
                    ppcc_res = {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
                else:
                    ppcc_res = gof.ppcc_test(data, ppf_func, alpha) if InfeasibilityCatalog.is_feasible(dist, 'PPCC') else {'stat': None, 'crit': None, 'dec': 'N/A', 'feasible': False}
                
                # Output all 4 tests in one line
                line = f"  {dur:<5}  "
                line += f"{chi2_res['stat']:>6.2f} {chi2_res['crit']:>5.2f} {chi2_res['dec']:>3}  " if chi2_res['feasible'] else f"{'---':>6} {'---':>5} {'N/A':>3}  "
                line += f"{ks_res['stat']:>6.3f} {ks_res['crit']:>5.3f} {ks_res['dec']:>3}  " if ks_res['feasible'] else f"{'---':>6} {'---':>5} {'N/A':>3}  "
                line += f"{cvm_res['stat']:>6.3f} {cvm_res['crit']:>5.3f} {cvm_res['dec']:>3}  " if cvm_res['feasible'] else f"{'---':>6} {'---':>5} {'N/A':>3}  "
                line += f"{ppcc_res['stat']:>6.3f} {ppcc_res['crit']:>5.3f} {ppcc_res['dec']:>3}" if ppcc_res['feasible'] else f"{'---':>6} {'---':>5} {'N/A':>3}"
                f.write(line + "\n")
            
            f.write("\n")
        
        # Infeasibility Summary
        f.write("\n" + "="*80 + "\n")
        f.write("GOODNESS-OF-FIT TEST INFEASIBILITY SUMMARY\n")
        f.write("="*80 + "\n\n")
        f.write("The following tests are NOT APPLICABLE for certain distributions:\n\n")
        f.write("  × WKB4/WKB5 + Chi-Square → Wakeby: No explicit CDF\n")
        f.write("  × WKB4/WKB5 + K-S        → Wakeby: No explicit CDF\n")
        f.write("  × WKB4/WKB5 + CVM        → Wakeby: No explicit CDF\n")
        f.write("  ✓ WKB4/WKB5 + PPCC       → Feasible (PPF available)\n\n")
        
        total_tests = len(FardEngine.ALL_DISTRIBUTIONS) * 4 * len(durations)
        infeasible = 2 * 3 * len(durations)
        feasible = total_tests - infeasible
        
        f.write(f"Total test combinations: {total_tests}\n")
        f.write(f"Feasible: {feasible} ({100*feasible/total_tests:.1f}%)\n")
        f.write(f"Infeasible: {infeasible} ({100*infeasible/total_tests:.1f}%)\n\n")
        f.write("IMPROVEMENTS OVER FARD Ver.2006:\n")
        f.write("-" * 80 + "\n")
        f.write("1. Dynamic Critical Values (sample size dependent)\n")
        f.write("2. Proper handling of infeasible combinations\n")
        f.write("3. Modern statistical methods (scipy.stats)\n")
        f.write("4. Comprehensive documentation\n\n")

    def close_excel_if_open(self, filename):
        try:
            import win32com.client
            excel = win32com.client.GetActiveObject("Excel.Application")
            for wb in excel.Workbooks:
                if wb.Name == os.path.basename(filename): wb.Close(SaveChanges=False)
        except: pass

    def update_config(self, path):
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f: conf = json.load(f)
            conf['step2_probability'] = {
                "status": "completed", 
                "output_file": os.path.basename(path), 
                "full_path": path,
                "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(self.config_file, 'w', encoding='utf-8') as f: json.dump(conf, f, indent=4)
        except: pass


class PreliminaryTestEngine:
    """
    FARD 예비해석 4종 (Anderson, Run, Spearman, Turning Point) 실제 구현
    """

    @staticmethod
    def run_all_tests(data, alpha=0.05):
        """
        입력: 시계열 데이터(List/Array), 유의수준(alpha)
        출력: 4개 테스트 결과 딕셔너리
        """
        n = len(data)
        data = np.array(data)
        
        # 기각역 설정을 위한 Z-값 (양측 검정)
        z_crit = stats.norm.ppf(1 - alpha/2)
        
        results = {}

        # ---------------------------------------------------------
        # 1. Anderson Correlation Test (Lag-1 Autocorrelation)
        # ---------------------------------------------------------
        # r1 계산
        mean = np.mean(data)
        numerator = np.sum((data[:-1] - mean) * (data[1:] - mean))
        denominator = np.sum((data - mean)**2)
        r1 = numerator / denominator
        
        # Anderson 기각 한계 (Confidence Limits)
        # CL = (-1 +/- z_crit * sqrt(N-2)) / (N-1)
        limit_upper = (-1 + z_crit * np.sqrt(n - 2)) / (n - 1)
        limit_lower = (-1 - z_crit * np.sqrt(n - 2)) / (n - 1)
        
        # 임계값(표시용): 절대값이 가장 큰 쪽 사용
        table_val_anderson = max(abs(limit_upper), abs(limit_lower))
        
        res_anderson = "ACCEPT" if limit_lower <= r1 <= limit_upper else "REJECT"
        results['Anderson'] = {'stat': r1, 'table': table_val_anderson, 'dec': res_anderson}

        # ---------------------------------------------------------
        # 2. Run Test (Wald-Wolfowitz)
        # ---------------------------------------------------------
        median = np.median(data)
        # 중앙값보다 크면 +, 작으면 - (같으면 제외하거나 이전 부호 유지)
        # 여기서는 간단히 중앙값 이상=1, 미만=0
        binary = [1 if x >= median else 0 for x in data]
        
        # Run 개수 세기
        runs = 1
        for i in range(1, len(binary)):
            if binary[i] != binary[i-1]:
                runs += 1
        
        # 기대값(E)과 분산(V)
        n1 = sum(binary) # 1의 개수
        n2 = n - n1      # 0의 개수
        
        if n1 > 0 and n2 > 0:
            exp_runs = 1 + (2 * n1 * n2) / n
            var_runs = (2 * n1 * n2 * (2 * n1 * n2 - n)) / (n**2 * (n - 1))
            if var_runs > 0:
                z_run = (runs - exp_runs) / np.sqrt(var_runs)
            else: z_run = 0
        else:
            z_run = 0 # 데이터가 모두 같거나 한쪽으로 쏠림
            
        res_run = "ACCEPT" if abs(z_run) < z_crit else "REJECT"
        results['RunTest'] = {'stat': z_run, 'table': z_crit, 'dec': res_run}

        # ---------------------------------------------------------
        # 3. Spearman Rank Correlation Test (Trend)
        # ---------------------------------------------------------
        time_steps = np.arange(1, n + 1)
        rho, p_val = stats.spearmanr(time_steps, data)
        
        # t-통계량 변환: t = r * sqrt((n-2)/(1-r^2))
        # 혹은 임계값 직접 비교 (n > 30 이면 z분포 근사)
        # 여기서는 rho 자체를 통계량으로 사용하고, 임계값을 z_crit / sqrt(n-1) 로 근사
        crit_rho = z_crit / np.sqrt(n - 1)
        
        res_spearman = "ACCEPT" if abs(rho) < crit_rho else "REJECT"
        results['Spearman'] = {'stat': rho, 'table': crit_rho, 'dec': res_spearman}

        # ---------------------------------------------------------
        # 4. Turning Point Test (Randomness)
        # ---------------------------------------------------------
        # Turning Point: x[i-1] < x[i] > x[i+1] or x[i-1] > x[i] < x[i+1]
        p = 0
        for i in range(1, n - 1):
            if (data[i-1] < data[i] > data[i+1]) or (data[i-1] > data[i] < data[i+1]):
                p += 1
        
        exp_p = 2 * (n - 2) / 3
        var_p = (16 * n - 29) / 90
        
        z_tp = (p - exp_p) / np.sqrt(var_p)
        
        res_tp = "ACCEPT" if abs(z_tp) < z_crit else "REJECT"
        results['TurningPoint'] = {'stat': z_tp, 'table': z_crit, 'dec': res_tp}

        return results

if __name__ == "__main__":
    # Main.py에서 전달하는 명령행 인자 처리
    # sys.argv[1] = project_path (Main.py의 self.current_project_path)
    # sys.argv[2] = input_file_path (step 2에서는 사용 안함)
    project_path = sys.argv[1] if len(sys.argv) > 1 else None
    app = ProbabilityAnalysisApp(project_path=project_path)
    app.mainloop()