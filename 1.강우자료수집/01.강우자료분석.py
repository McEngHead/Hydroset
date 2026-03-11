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
        
        # Main.py 연동 및 경로 설정
        self.project_path = project_path if project_path else os.getcwd()
        self.config_file = os.path.join(self.project_path, "project_config.json")
        self.project_name = os.path.basename(self.project_path)

        # 윈도우 설정
        self.title(f"강우자료 분석 및 임의시간 변환 - [{self.project_name}]")
        self.geometry("1000x750")
        
        # 윈도우 타이틀바 다크모드 강제 적용
        self.apply_system_dark_mode()

        self.setup_ui()
        self.load_previous_settings()

    def apply_system_dark_mode(self):
        """윈도우 타이틀바 및 시스템 다크모드 적용 시도"""
        try:
            hwnd = windll.user32.GetParent(self.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(1)), sizeof(c_int))
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), sizeof(c_int))
            try:
                windll.uxtheme.SetPreferredAppMode(2) # Force Dark
            except AttributeError:
                pass
        except Exception:
            pass

    def setup_ui(self):
        """UI 레이아웃 구성"""
        # 전체 컨테이너
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 상단 타이틀
        ctk.CTkLabel(main_frame, text="강우자료 분석 및 임의시간 변환", font=FONT_TITLE).pack(pady=(0, 20))

        # 입력 프레임
        input_frame = ctk.CTkFrame(main_frame)
        input_frame.pack(fill='x', pady=10)

        ctk.CTkLabel(input_frame, text="📂 강우자료 폴더 선택", font=FONT_HEADER).pack(anchor="w", padx=20, pady=(20, 10))

        # 1. 10분 강우자료 (및 일간자료)
        row1 = ctk.CTkFrame(input_frame, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(row1, text="1. 일간(DAY) 자료 폴더:", font=FONT_BODY, width=160, anchor="w").pack(side="left")
        self.entry_10min_dir = ctk.CTkEntry(row1, font=FONT_BODY, placeholder_text="10분 및 1시간 최다값이 포함된 폴더")
        self.entry_10min_dir.pack(side="left", fill="x", expand=True, padx=10)
        
        ctk.CTkButton(row1, text="폴더 찾기", font=FONT_BTN, width=100,
                      command=lambda: self.browse_folder(self.entry_10min_dir, "일간(DAY) 강우자료가 있는 폴더를 선택하세요")).pack(side="right")

        # 2. 1시간 강우자료
        row2 = ctk.CTkFrame(input_frame, fg_color="transparent")
        row2.pack(fill="x", padx=20, pady=(5, 20))
        
        ctk.CTkLabel(row2, text="2. 시간(HR) 자료 폴더:", font=FONT_BODY, width=160, anchor="w").pack(side="left")
        self.entry_1hr_dir = ctk.CTkEntry(row2, font=FONT_BODY, placeholder_text="장기 지속기간 산정용 폴더")
        self.entry_1hr_dir.pack(side="left", fill="x", expand=True, padx=10)
        
        ctk.CTkButton(row2, text="폴더 찾기", font=FONT_BTN, width=100,
                      command=lambda: self.browse_folder(self.entry_1hr_dir, "1시간(HR) 강우자료가 있는 폴더를 선택하세요")).pack(side="right")

        # 실행 버튼
        self.btn_run = ctk.CTkButton(main_frame, text="⚡ 분석 실행 (데이터 병합 + 극값 추출 + 임의시간 환산)", 
                                     command=self.run_analysis,
                                     font=FONT_BTN, height=50, fg_color="#c0392b", hover_color="#e74c3c")
        self.btn_run.pack(fill='x', pady=20)

        # 로그창 프레임
        log_frame = ctk.CTkFrame(main_frame)
        log_frame.pack(fill='both', expand=True)

        ctk.CTkLabel(log_frame, text="📊 진행 상황 및 로그", font=FONT_HEADER).pack(anchor="w", padx=20, pady=(15, 5))
        
        self.log_text = ctk.CTkTextbox(log_frame, font=FONT_LOG, activate_scrollbars=True)
        self.log_text.pack(fill='both', expand=True, padx=20, pady=(5, 20))

    def browse_folder(self, entry_widget, title_str):
        folder_selected = filedialog.askdirectory(initialdir=self.project_path, title=title_str)
        if folder_selected:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, folder_selected)

    def log(self, message):
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.update()

    def load_previous_settings(self):
        if not os.path.exists(self.config_file): return
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f: config_data = json.load(f)
            if 'step1_rainfall' in config_data and 'inputs' in config_data['step1_rainfall']:
                inputs = config_data['step1_rainfall']['inputs']
                if inputs.get('dir_10min'):
                    self.entry_10min_dir.delete(0, tk.END)
                    self.entry_10min_dir.insert(0, inputs['dir_10min'])
                    self.log(f"ℹ️ 이전 설정: 일간(DAY) 폴더 불러옴")
                if inputs.get('dir_1hr'):
                    self.entry_1hr_dir.delete(0, tk.END)
                    self.entry_1hr_dir.insert(0, inputs['dir_1hr'])
                    self.log(f"ℹ️ 이전 설정: 시간(HR) 폴더 불러옴")
        except Exception as e: self.log(f"⚠️ 설정 로드 실패: {e}")

    def save_input_paths(self, dir_10min, dir_1hr):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    try: config_data = json.load(f)
                    except: config_data = {"info": {"project_name": self.project_name}}
            else: config_data = {"info": {"project_name": self.project_name}}

            if 'step1_rainfall' not in config_data: config_data['step1_rainfall'] = {}
            config_data['step1_rainfall']['inputs'] = {"dir_10min": dir_10min, "dir_1hr": dir_1hr}

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            self.log(f"💾 폴더 경로 설정 저장 완료")
        except Exception as e: self.log(f"⚠️ 설정 저장 실패: {e}")

    def close_specific_excel_file(self, filename):
        try:
            import win32com.client
            excel = win32com.client.GetActiveObject("Excel.Application")
            target_name = os.path.basename(filename)
            closed = False
            for wb in excel.Workbooks:
                if wb.Name == target_name:
                    wb.Close(SaveChanges=False)
                    closed = True
                    self.log(f" -> 엑셀 파일 '{target_name}'을(를) 자동으로 닫았습니다.")
                    break
            if not closed:
                self.log(f" -> 경고: 엑셀에서 '{target_name}' 파일을 찾을 수 없습니다.")
                return False
            return True
        except ImportError:
            self.log("❌ pywin32 라이브러리가 필요합니다.")
            return False
        except Exception as e:
            self.log(f"⚠️ 엑셀 제어 실패: {e}")
            return False

    def save_excel_safe(self, df_dict, filepath):
        filename = os.path.basename(filepath)
        while True:
            try:
                with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                    for sheet_name, df in df_dict.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                break 
            except PermissionError:
                msg = f"파일이 열려있습니다:\n{filename}\n\n이 파일만 자동으로 닫고 저장을 진행하시겠습니까?"
                if messagebox.askyesno("파일 쓰기 오류", msg):
                    self.log(f"⚠️ '{filename}' 파일 닫기 시도 중...")
                    if self.close_specific_excel_file(filename):
                        time.sleep(1); continue 
                    else:
                        messagebox.showerror("실패", "파일을 자동으로 닫지 못했습니다. 수동으로 닫아주세요."); continue 
                else:
                    self.log(f"⚠️ '{filename}' 저장이 취소되었습니다."); return False
        return True

    def run_analysis(self):
        dir_10min = self.entry_10min_dir.get()
        dir_1hr = self.entry_1hr_dir.get()

        if not dir_10min or not dir_1hr:
            messagebox.showwarning("경고", "두 개의 폴더 경로를 모두 선택해주세요.")
            return

        self.save_input_paths(dir_10min, dir_1hr)
        self.log_text.delete(1.0, tk.END)
        self.log("🚀 분석 프로세스를 시작합니다...")

        try:
            # Step 1: 10분 강우자료 + [수정] 1시간 최대값 추가 로드
            self.log(f"\n[Step 1] 일간(DAY) 자료 처리 중... (폴더: {dir_10min})")
            files_10min = glob.glob(os.path.join(dir_10min, "*DAY*.csv"))
            if not files_10min: raise FileNotFoundError("일간(DAY) 자료 폴더에 'DAY'가 포함된 CSV 파일이 없습니다.")
            self.log(f" -> {len(files_10min)}개의 DAY 자료 파일을 발견했습니다.")

            df_list_10min = []
            for f in files_10min:
                try: 
                    # [수정] 1시간 최다강수량(idx 10), 1시간 최다강수량 시각(idx 11) 추가 로드
                    # 보통 순서: 지점, 일시, ..., 10분강우(8), 10분시각(9), 1시간강우(10), 1시간시각(11)
                    temp = pd.read_csv(f, encoding='cp949', header=0).iloc[:, [0, 1, 8, 9, 10, 11]]
                except UnicodeDecodeError: 
                    temp = pd.read_csv(f, encoding='utf-8', header=0).iloc[:, [0, 1, 8, 9, 10, 11]]
                except Exception as e: 
                    self.log(f"⚠️ 파일 읽기 오류 ({os.path.basename(f)}): {e}"); continue
                
                # 컬럼명 설정 (10분 및 60분)
                temp.columns = ['Station', 'Date', 'Rain_10min_Max', 'Time_10min_Max', 'Rain_60min_Max', 'Time_60min_Max']
                
                # 숫자형 변환
                temp['Rain_10min_Max'] = pd.to_numeric(temp['Rain_10min_Max'], errors='coerce').fillna(0)
                temp['Rain_60min_Max'] = pd.to_numeric(temp['Rain_60min_Max'], errors='coerce').fillna(0)
                
                df_list_10min.append(temp)
            
            merged_10min = pd.concat(df_list_10min, ignore_index=True)
            merged_10min['Date'] = pd.to_datetime(merged_10min['Date'], errors='coerce')
            merged_10min.dropna(subset=['Date'], inplace=True)
            merged_10min.sort_values(by='Date', inplace=True)
            
            save_path_10min = os.path.join(self.project_path, f"{self.project_name}_A_10min_Extreme.csv")
            merged_10min.to_csv(save_path_10min, index=False, encoding='cp949')
            self.log(f" -> 일간 병합 파일(10분 및 1시간 포함) 저장 완료.")

            # Step 2: 1시간(HR) 강우자료
            self.log(f"\n[Step 2] 시간(HR) 강우자료 처리 중... (폴더: {dir_1hr})")
            files_1hr = glob.glob(os.path.join(dir_1hr, "*HR*.csv"))
            if not files_1hr: raise FileNotFoundError("시간(HR) 자료 폴더에 'HR'가 포함된 CSV 파일이 없습니다.")
            self.log(f" -> {len(files_1hr)}개의 시간 자료 파일을 발견했습니다.")

            df_list_1hr = []
            for f in files_1hr:
                try: temp = pd.read_csv(f, encoding='cp949', header=0).iloc[:, [0, 1, 3]]
                except UnicodeDecodeError: temp = pd.read_csv(f, encoding='utf-8', header=0).iloc[:, [0, 1, 3]]
                except Exception as e: self.log(f"⚠️ 파일 읽기 오류 ({os.path.basename(f)}): {e}"); continue
                temp.columns = ['Station', 'Date', 'Rainfall']
                temp['Rainfall'] = pd.to_numeric(temp['Rainfall'], errors='coerce').fillna(0)
                df_list_1hr.append(temp)
            
            merged_1hr = pd.concat(df_list_1hr, ignore_index=True)
            merged_1hr['Date'] = pd.to_datetime(merged_1hr['Date'], errors='coerce')
            merged_1hr.dropna(subset=['Date'], inplace=True)
            merged_1hr.sort_values(by='Date', inplace=True)
            
            save_path_1hr = os.path.join(self.project_path, f"{self.project_name}_A_1hr_Extreme.csv")
            merged_1hr.to_csv(save_path_1hr, index=False, encoding='cp949')
            self.log(f" -> 시간 병합 파일 저장 완료.")

            # Step 3: 분석 수행
            self.log("\n[Step 3] 지속기간별 고정시간 최대강우량 분석 중...")
            merged_10min['Year'] = merged_10min['Date'].dt.year
            merged_1hr['Year'] = merged_1hr['Date'].dt.year
            years = sorted(merged_1hr['Year'].unique())
            self.log(f" -> 분석 기간: {min(years)}년 ~ {max(years)}년")

            # [수정] 10분 최대값 및 60분 최대값 GroupBy (DAY 자료 기반)
            grp_10min = merged_10min.groupby('Year')['Rain_10min_Max'].max()
            grp_60min = merged_10min.groupby('Year')['Rain_60min_Max'].max()

            merged_1hr_idx = merged_1hr.set_index('Date')
            merged_1hr_idx = merged_1hr_idx[~merged_1hr_idx.index.duplicated(keep='first')]
            full_idx = pd.date_range(start=merged_1hr['Date'].min(), end=merged_1hr['Date'].max(), freq='H')
            df_resampled = merged_1hr_idx.reindex(full_idx, fill_value=0)
            df_resampled['Year'] = df_resampled.index.year
            df_resampled['Rainfall'] = df_resampled['Rainfall'].fillna(0)

            # [수정] 1시간 값은 이미 구했으므로 루프는 2시간부터 시작
            durations_hr = list(range(2, 49)) 
            result_fixed, result_times_end = [], []

            for yr in years:
                row_fixed, row_end = {'Year': yr}, {'Year': yr}
                
                # 10분 및 60분 값은 DAY 파일에서 추출한 값 사용
                row_fixed[10] = grp_10min.get(yr, 0); row_end[10] = "-"
                row_fixed[60] = grp_60min.get(yr, 0); row_end[60] = "-" # 60분 값 직접 할당

                year_data = df_resampled[df_resampled['Year'] == yr]
                rain_series = year_data['Rainfall']

                if len(rain_series) == 0:
                    for h in durations_hr: row_fixed[h*60] = 0; row_end[h*60] = "-"
                    result_fixed.append(row_fixed); result_times_end.append(row_end); continue

                # [수정] 2시간 ~ 48시간에 대해서만 Rolling 계산 수행
                for h in durations_hr:
                    rolling = rain_series.rolling(window=h, min_periods=1).sum()
                    max_val = rolling.max()
                    try: end_time = rolling.idxmax()
                    except: end_time = "-"
                    row_fixed[h*60] = max_val if pd.notnull(max_val) else 0
                    row_end[h*60] = str(end_time)

                # 데이터 정합성 체크 (값이 줄어들지 않도록 보정)
                prev_val = row_fixed[60]
                for h in range(2, 49):
                    curr_min = h * 60
                    if row_fixed[curr_min] < prev_val: row_fixed[curr_min] = prev_val
                    else: prev_val = row_fixed[curr_min]

                result_fixed.append(row_fixed); result_times_end.append(row_end)

            # 컬럼 순서 정리 (10분, 60분, 120분 ... 순서)
            df_fixed = pd.DataFrame(result_fixed)
            cols = ['Year', 10, 60] + [h*60 for h in durations_hr] # 60을 명시적으로 추가
            df_fixed = df_fixed[cols]

            # Step 4: 임의시간 환산
            self.log("\n[Step 4] 임의시간 환산 적용 중...")
            df_arbitrary = df_fixed.copy()
            def get_conversion_factor(m): return 1.0 if m <= 60 else 0.1346 * ((m/60.0) ** -1.4170) + 1.0014
            
            for col in df_arbitrary.columns:
                if col == 'Year': continue
                # 1시간 이하(10, 60)는 계수 1.0 적용됨
                factor = get_conversion_factor(int(col))
                df_arbitrary[col] = (df_arbitrary[col] * factor).round(1)
                df_fixed[col] = df_fixed[col].round(1)
            
            duration_cols = [c for c in df_arbitrary.columns if c != 'Year']
            for i in range(1, len(duration_cols)):
                prev, curr = duration_cols[i-1], duration_cols[i]
                df_arbitrary[curr] = np.maximum(df_arbitrary[curr], df_arbitrary[prev])

            # Step 5: 결과 저장
            output_filename = f"{self.project_name}_A_Result_OUT.xlsx"
            output_path = os.path.join(self.project_path, output_filename)
            df_times_end = pd.DataFrame(result_times_end)[cols]
            main_sheets = {'Max_Rainfall_Fixed_time': df_fixed, 'Max_Rainfall_Arbitrary_time': df_arbitrary, 'Max_Rainfall_Event_Times': df_times_end}
            if self.save_excel_safe(main_sheets, output_path):
                self.log(f" -> 메인 엑셀 저장 완료: {output_filename}")
                self.update_project_config(output_path, min(years), max(years), dir_10min, dir_1hr)

            # Step 6: 보고서용 파일 저장
            self.log(f"\n[Step 6] 보고서용 요약 파일 생성 중...")
            target_hours = [2, 3, 4, 6, 9, 12, 18, 24]
            target_cols = ['Year', 10, 60] + [h*60 for h in target_hours]
            report_path = os.path.join(self.project_path, f"{self.project_name}_A_Result_OUT_Report.xlsx")
            report_sheets = {'Max_Rainfall_Fixed_time': df_fixed[target_cols], 'Max_Rainfall_Arbitrary_time': df_arbitrary[target_cols]}
            if self.save_excel_safe(report_sheets, report_path):
                self.log(f" -> 보고서 파일 저장 완료: {os.path.basename(report_path)}")

            self.log("\n✅ 모든 분석 및 저장이 완료되었습니다.")
            messagebox.showinfo("완료", "분석이 정상적으로 완료되었습니다.")

        except Exception as e:
            self.log(f"\n❌ 오류 발생: {str(e)}")
            messagebox.showerror("오류", f"분석 중 오류가 발생했습니다:\n{str(e)}")

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
            "description": "강우자료 분석 및 임의시간 환산 완료",
            "inputs": {"dir_10min": dir_10min, "dir_1hr": dir_1hr}
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)

    def run(self):
        self.mainloop()

if __name__ == "__main__":
    project_path_arg = sys.argv[1] if len(sys.argv) > 1 else None
    app = RainfallAnalysisTool(project_path=project_path_arg)
    app.run()