import os
import sys
import json
import glob
import pandas as pd
import numpy as np
import customtkinter as ctk 
import tkinter as tk
from tkinter import filedialog, messagebox
import warnings
import time
import re  # [추가] 파일명에서 연도 추출을 위한 정규표현식 모듈
from ctypes import windll, byref, sizeof, c_int

# 경고 메시지 무시
warnings.filterwarnings('ignore')

# --- [CustomTkinter 설정] ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# 폰트 설정
FONT_TITLE = ("맑은 고딕", 22, "bold")
FONT_HEADER = ("맑은 고딕", 14, "bold")
FONT_BODY = ("맑은 고딕", 12)
FONT_BTN = ("맑은 고딕", 12, "bold")
FONT_LOG = ("맑은 고딕", 11)

class RainfallAnalysisTool(ctk.CTk):
    def __init__(self, project_path=None):
        super().__init__()
        
        self.project_path = project_path if project_path else os.getcwd()
        self.config_file = os.path.join(self.project_path, "project_config.json")
        self.project_name = os.path.basename(self.project_path)

        self.title(f"강우자료 분석 및 임의시간 변환 - [{self.project_name}]")
        self.geometry("1000x800")
        
        self.change_title_bar_color()
        self.setup_ui()

    def change_title_bar_color(self):
        try:
            hwnd = windll.user32.GetParent(self.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(1)), sizeof(c_int))
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), sizeof(c_int))
        except: pass

    def setup_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(main_frame, text="강우자료 분석 (값 & 발생시각 추출 / 역전방지 보정)", font=FONT_TITLE).pack(anchor="w", pady=(0, 20))

        # 입력 영역
        input_frame = ctk.CTkFrame(main_frame)
        input_frame.pack(fill="x", pady=(0, 20))

        # 1. DAY 폴더
        row1 = ctk.CTkFrame(input_frame, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(row1, text="📂 10분/1시간(DAY) 폴더:", width=180, anchor="w", font=FONT_BODY).pack(side="left")
        self.entry_day_dir = ctk.CTkEntry(row1, placeholder_text="DAY 파일 경로")
        self.entry_day_dir.pack(side="left", fill="x", expand=True, padx=10)
        ctk.CTkButton(row1, text="선택", width=80, command=lambda: self.select_dir(self.entry_day_dir), font=FONT_BTN).pack(side="right")

        # 2. HR 폴더
        row2 = ctk.CTkFrame(input_frame, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(row2, text="📂 시(HR) 폴더:", width=180, anchor="w", font=FONT_BODY).pack(side="left")
        self.entry_hr_dir = ctk.CTkEntry(row2, placeholder_text="HR 파일 경로")
        self.entry_hr_dir.pack(side="left", fill="x", expand=True, padx=10)
        ctk.CTkButton(row2, text="선택", width=80, command=lambda: self.select_dir(self.entry_hr_dir), font=FONT_BTN).pack(side="right")

        # 설정 영역 (기간 & 회귀식 계수)
        setting_frame = ctk.CTkFrame(main_frame)
        setting_frame.pack(fill="x", pady=(0, 20))

        # 기간 설정
        period_frame = ctk.CTkFrame(setting_frame, fg_color="transparent")
        period_frame.pack(side="left", padx=20, pady=10)
        ctk.CTkLabel(period_frame, text="분석 기간:", font=FONT_HEADER).pack(side="left", padx=(0, 10))
        self.entry_start_year = ctk.CTkEntry(period_frame, width=60, placeholder_text="YYYY")
        self.entry_start_year.pack(side="left")
        ctk.CTkLabel(period_frame, text="~").pack(side="left", padx=5)
        self.entry_end_year = ctk.CTkEntry(period_frame, width=60, placeholder_text="YYYY")
        self.entry_end_year.pack(side="left")

        # 회귀식 계수 설정 (Y = A * X^B + C)
        factor_frame = ctk.CTkFrame(setting_frame, fg_color="transparent")
        factor_frame.pack(side="right", padx=20, pady=10)
        
        ctk.CTkLabel(factor_frame, text="환산계수 (Y = A·Xᴮ + C):", font=FONT_HEADER).pack(side="top", anchor="w")
        
        f_inner = ctk.CTkFrame(factor_frame, fg_color="transparent")
        f_inner.pack(side="top", pady=5)
        
        ctk.CTkLabel(f_inner, text="A:", font=FONT_BODY).pack(side="left")
        self.entry_coef_a = ctk.CTkEntry(f_inner, width=60)
        self.entry_coef_a.insert(0, "0.1346")
        self.entry_coef_a.pack(side="left", padx=5)
        
        ctk.CTkLabel(f_inner, text="B:", font=FONT_BODY).pack(side="left")
        self.entry_coef_b = ctk.CTkEntry(f_inner, width=60)
        self.entry_coef_b.insert(0, "-1.4170")
        self.entry_coef_b.pack(side="left", padx=5)

        ctk.CTkLabel(f_inner, text="C:", font=FONT_BODY).pack(side="left")
        self.entry_coef_c = ctk.CTkEntry(f_inner, width=60)
        self.entry_coef_c.insert(0, "1.0014")
        self.entry_coef_c.pack(side="left", padx=5)

        # 실행 버튼
        self.btn_run = ctk.CTkButton(main_frame, text="분석 실행 (엑셀 저장)", command=self.run_analysis,
                                     height=50, font=FONT_BTN, fg_color="#2980b9", hover_color="#3498db")
        self.btn_run.pack(fill="x", pady=(0, 15))

        # 로그창
        self.log_text = ctk.CTkTextbox(main_frame, font=FONT_LOG, activate_scrollbars=True)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

    def select_dir(self, entry_widget):
        path = filedialog.askdirectory()
        if path:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, path)
            # [수정] 폴더 선택 시 자동으로 연도 파악하여 기간 설정
            self.auto_detect_years()

    def auto_detect_years(self):
        """선택된 폴더 내 CSV 파일명을 분석하여 시작/종료 연도 자동 설정"""
        target_dirs = []
        if self.entry_day_dir.get(): target_dirs.append(self.entry_day_dir.get())
        if self.entry_hr_dir.get(): target_dirs.append(self.entry_hr_dir.get())
        
        found_years = []
        
        for d in target_dirs:
            if os.path.exists(d):
                # 폴더 내 모든 csv 검색
                csv_files = glob.glob(os.path.join(d, "*.csv"))
                for f in csv_files:
                    fname = os.path.basename(f)
                    # 19xx 또는 20xx 패턴 찾기
                    match = re.search(r'(19|20)\d{2}', fname)
                    if match:
                        found_years.append(int(match.group()))
        
        if found_years:
            min_year = min(found_years)
            max_year = max(found_years)
            
            # 입력창 업데이트
            self.entry_start_year.delete(0, tk.END)
            self.entry_start_year.insert(0, str(min_year))
            
            self.entry_end_year.delete(0, tk.END)
            self.entry_end_year.insert(0, str(max_year))
            
            self.log(f"ℹ️ 연도 감지됨: {min_year} ~ {max_year}")

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def calculate_conversion_factor(self, duration_min, a, b, c):
        duration_hr = duration_min / 60.0
        if duration_hr < 1: return 1.0
        factor = a * (duration_hr ** b) + c
        return factor

    def format_hhmi_time(self, date_val, hhmi_val):
        # YYYY-MM-DD 와 2021(HHMI) 또는 900(HHMI) 형식을 합쳐서 포맷팅
        try:
            date_str = str(date_val).split(' ')[0] # YYYY-MM-DD
            hhmi_str = str(int(hhmi_val)).zfill(4) # 900 -> 0900
            if hhmi_str == "2400": # 2400은 다음날 0000으로 처리하거나 해당일 24:00 (pd.Timestamp는 24:00 미지원)
                 # 간단히 23:59:59 혹은 문자열로 처리. 여기선 문자열로 반환
                 return f"{date_str} 24:00:00"
            
            return f"{date_str} {hhmi_str[:2]}:{hhmi_str[2:]}:00"
        except:
            return "-"

    def run_analysis(self):
        dir_day = self.entry_day_dir.get()
        dir_hr = self.entry_hr_dir.get()
        s_year = self.entry_start_year.get()
        e_year = self.entry_end_year.get()
        
        val_a = self.entry_coef_a.get()
        val_b = self.entry_coef_b.get()
        val_c = self.entry_coef_c.get()

        if not (dir_day and dir_hr and s_year and e_year):
            messagebox.showwarning("입력 오류", "모든 경로와 기간을 입력해주세요.")
            return

        try:
            start_year = int(s_year)
            end_year = int(e_year)
            coef_a = float(val_a)
            coef_b = float(val_b)
            coef_c = float(val_c)
        except:
            messagebox.showerror("입력 오류", "숫자를 입력해야 합니다.")
            return

        self.log(f"🚀 분석 시작: {start_year}년 ~ {end_year}년")
        self.process_analysis(dir_day, dir_hr, start_year, end_year, coef_a, coef_b, coef_c)

    def process_analysis(self, dir_day, dir_hr, start_year, end_year, a, b, c):
        result_values = []
        result_times = []
        
        # 지속기간: 10분, 60분, 120분 ~ 2880분(48시간)까지 60분 간격
        durations = [10] + [t * 60 for t in range(1, 49)] 
        
        # DAY 파일 필수 컬럼 정의
        REQUIRED_COLS_DAY = [
            '10분 최다 강수량(mm)', '10분 최다강수량 시각(hhmi)',
            '1시간 최다강수량(mm)', '1시간 최다 강수량 시각(hhmi)',
            '일시'
        ]

        try:
            for year in range(start_year, end_year + 1):
                self.log(f"... {year}년도 데이터 분석 중")
                
                # 데이터 담을 딕셔너리 초기화
                row_val = {'Year': year}
                row_time = {'Year': year}
                
                # ==========================================
                # [1] DAY 파일 처리 (10분, 60분)
                # ==========================================
                day_files = glob.glob(os.path.join(dir_day, f"*{year}*DAY*.csv"))
                day_processed = False
                
                if day_files:
                    try:
                        df_day = pd.read_csv(day_files[0], encoding='cp949')
                        
                        # [검증] 필수 컬럼 확인
                        missing_cols = [col for col in REQUIRED_COLS_DAY if col not in df_day.columns]
                        if missing_cols:
                            err_msg = f"❌ {year}년 DAY 파일에 필수 컬럼이 없습니다.\n누락된 컬럼: {missing_cols}"
                            messagebox.showerror("데이터 형식 오류", err_msg)
                            self.log(err_msg)
                            return # 중단

                        # 10분 데이터 추출
                        idx_10 = df_day['10분 최다 강수량(mm)'].idxmax()
                        val_10 = df_day.loc[idx_10, '10분 최다 강수량(mm)']
                        time_10_raw = df_day.loc[idx_10, '10분 최다강수량 시각(hhmi)']
                        date_10 = df_day.loc[idx_10, '일시']
                        
                        row_val[10] = val_10
                        row_time[10] = self.format_hhmi_time(date_10, time_10_raw)

                        # 60분(1시간) 데이터 추출
                        idx_60 = df_day['1시간 최다강수량(mm)'].idxmax()
                        val_60 = df_day.loc[idx_60, '1시간 최다강수량(mm)']
                        time_60_raw = df_day.loc[idx_60, '1시간 최다 강수량 시각(hhmi)']
                        date_60 = df_day.loc[idx_60, '일시']

                        row_val[60] = val_60
                        row_time[60] = self.format_hhmi_time(date_60, time_60_raw)
                        
                        day_processed = True

                    except Exception as e:
                        self.log(f"❌ {year}년 DAY 파일 처리 중 오류: {e}")
                        day_processed = False
                else:
                    self.log(f"⚠️ {year}년 DAY 파일 없음")

                if not day_processed:
                    row_val[10] = 0; row_time[10] = "-"
                    row_val[60] = 0; row_time[60] = "-"

                # ==========================================
                # [2] HR 파일 처리 (120분 ~ 2880분)
                # ==========================================
                hr_files = glob.glob(os.path.join(dir_hr, f"*{year}*HR*.csv"))
                
                if hr_files:
                    try:
                        df_hr = pd.read_csv(hr_files[0], encoding='cp949')
                        df_hr['일시'] = pd.to_datetime(df_hr['일시'])
                        df_hr = df_hr.sort_values('일시').reset_index(drop=True)
                        df_hr['강수량(mm)'] = df_hr['강수량(mm)'].fillna(0)

                        # 2시간 ~ 48시간 루프
                        for t_hour in range(2, 49):
                            duration_min = t_hour * 60
                            
                            # Rolling Sum 계산
                            rolling_series = df_hr['강수량(mm)'].rolling(window=t_hour).sum()
                            
                            if not rolling_series.empty and rolling_series.max() > 0:
                                max_val = rolling_series.max()
                                max_idx = rolling_series.idxmax() # 최대값이 발생한 시점(윈도우 끝)의 인덱스
                                
                                # 환산계수 적용
                                factor = self.calculate_conversion_factor(duration_min, a, b, c)
                                final_val = round(max_val * factor, 2)
                                
                                # 시각 추출
                                event_time = df_hr.loc[max_idx, '일시']
                                
                                row_val[duration_min] = final_val
                                row_time[duration_min] = str(event_time)
                            else:
                                row_val[duration_min] = 0
                                row_time[duration_min] = "-"
                                
                    except Exception as e:
                        self.log(f"❌ {year}년 HR 파일 처리 오류: {e}")
                        # 에러 시 0 처리
                        for t in range(2, 49):
                            row_val[t*60] = 0; row_time[t*60] = "-"
                else:
                    self.log(f"⚠️ {year}년 HR 파일 없음")
                    for t in range(2, 49):
                            row_val[t*60] = 0; row_time[t*60] = "-"

                # ==========================================
                # [3] 물리적 모순 보정 (Non-decreasing Check)
                # ==========================================
                # 지속기간 순서대로 검사: 10 -> 60 -> 120 -> ...
                # 값이 줄어들면 이전 단계의 값과 시각으로 대체
                
                sorted_durations = durations # [10, 60, 120, ..., 2880]
                
                for i in range(1, len(sorted_durations)):
                    prev_dur = sorted_durations[i-1]
                    curr_dur = sorted_durations[i]
                    
                    prev_v = row_val.get(prev_dur, 0)
                    curr_v = row_val.get(curr_dur, 0)
                    
                    if curr_v < prev_v:
                        # 역전 발생: 현재 값을 이전 값으로 대체
                        row_val[curr_dur] = prev_v
                        # 시각도 동기화 (값이 같아졌으므로 해당 값이 발생한 시각으로)
                        row_time[curr_dur] = row_time.get(prev_dur, "-")
                        # self.log(f"   ㄴ 보정: {curr_dur}분 데이터 역전 수정됨")

                result_values.append(row_val)
                result_times.append(row_time)

            # ==========================================
            # [4] 결과 저장 (Excel Sheet 분리)
            # ==========================================
            if not result_values: return

            df_val_res = pd.DataFrame(result_values)
            df_time_res = pd.DataFrame(result_times)
            
            # 컬럼 정렬 (Year, 10, 60, 120...)
            cols = ['Year'] + [c for c in durations if c in df_val_res.columns]
            df_val_res = df_val_res[cols]
            df_time_res = df_time_res[cols]

            output_filename = f"{self.project_name}_A_Result_OUT.xlsx"
            output_path = os.path.join(self.project_path, output_filename)
            
            with pd.ExcelWriter(output_path) as writer:
                # Sheet 1: 값
                df_val_res.to_excel(writer, sheet_name='Max_Rainfall_Arbitrary_time', index=False)
                # Sheet 2: 시각
                df_time_res.to_excel(writer, sheet_name='Max_Rainfall_Event_Times', index=False)
                # Sheet 3: 정보
                pd.DataFrame({'Item': ['Formula', 'Coef A', 'Coef B', 'Coef C'], 
                              'Value': ['Y=A*X^B + C', a, b, c]}).to_excel(writer, sheet_name='Info')

            self.log(f"\n💾 결과 저장 완료: {output_filename}")
            
            # Config 업데이트
            self.update_project_config(output_path, start_year, end_year, dir_day, dir_hr)
            
            messagebox.showinfo("완료", "분석이 정상적으로 완료되었습니다.\n(값 및 발생시각 시트 분리 저장됨)")

        except Exception as e:
            self.log(f"\n❌ 치명적 오류 발생: {str(e)}")
            messagebox.showerror("오류", str(e))

    def update_project_config(self, output_filepath, start_year, end_year, dir_10min, dir_1hr):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                try: config_data = json.load(f)
                except: config_data = {}
        else: config_data = {"info": {"project_name": self.project_name}}
        
        config_data['step1_rainfall'] = {
            "status": "completed",
            "output_file": os.path.basename(output_filepath),
            "full_path": output_filepath,
            "period": {"start_year": int(start_year), "end_year": int(end_year)},
            "description": "강우자료 분석 (Arbitrary Time + Event Times + Non-decreasing)",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    project_path_arg = sys.argv[1] if len(sys.argv) > 1 else None
    app = RainfallAnalysisTool(project_path=project_path_arg)
    app.mainloop()