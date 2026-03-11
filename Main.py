import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import os
import subprocess
import datetime
import sys
from ctypes import windll, byref, sizeof, c_int

# --- [CustomTkinter 설정] ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- [수문 분석 단계 정의 (최종 수정)] ---
# 폴더 이름과 달라도 번호(Key)를 기준으로 실행 파일을 찾습니다.
ANALYSIS_STEPS = {
    1: "A. 강우자료",
    2: "B. 확률강우량",
    3: "C. 강우강도식",
    4: "D. 유효우량",
    5: "E. 홍수량",
    6: "F. 하도추적",
}

# 폰트 설정
FONT_TITLE = ("맑은 고딕", 20, "bold")
FONT_SUBTITLE = ("맑은 고딕", 13, "bold")
FONT_BODY = ("맑은 고딕", 12)
FONT_BTN = ("맑은 고딕", 12)
FONT_LOG = ("맑은 고딕", 11)

class HydroAnalysisApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # 1. 윈도우 설정
        self.title("통합 수문 분석 시스템 (Integrated Hydrology Analysis)")
        self.geometry("1100x700")

        # 윈도우 타이틀바 색상을 다크모드로 강제 변경
        self.change_title_bar_color()

        # 2. 기본 경로 및 변수 설정
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.projects_root_folder = os.path.join(self.base_path, "0.Projects")
        self.current_project_name = None
        self.current_project_path = None
        self.current_project_log_file = None

        if not os.path.exists(self.projects_root_folder):
            try: os.makedirs(self.projects_root_folder)
            except OSError as e: messagebox.showerror("Error", f"프로젝트 루트 폴더 생성 실패: {e}")

        # 3. UI 구성
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.create_sidebar()
        self.create_main_content()
        
        self.log_message("시스템 준비 완료. 프로젝트를 선택해주세요.")

    def change_title_bar_color(self):
        """윈도우 타이틀바를 다크모드(검정색)로 강제 변경"""
        try:
            hwnd = windll.user32.GetParent(self.winfo_id())
            # DWMWA_USE_IMMERSIVE_DARK_MODE (Win10=20, Win11=35)
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(1)), sizeof(c_int))
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), sizeof(c_int))
            
            try: windll.uxtheme.SetPreferredAppMode(2)
            except: pass
        except Exception:
            pass

    def create_sidebar(self):
        """왼쪽 사이드바"""
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        
        row_idx = 0 

        # 타이틀 / 로고
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Hydro\nSystem v1.0", 
                                       font=FONT_TITLE, text_color="#3498db")
        self.logo_label.grid(row=row_idx, column=0, padx=20, pady=(20, 10))
        row_idx += 1

        # [섹션 1] 프로젝트 관리
        self.lbl_file = ctk.CTkLabel(self.sidebar_frame, text="[ 프로젝트 관리 ]", font=FONT_SUBTITLE, anchor="w")
        self.lbl_file.grid(row=row_idx, column=0, padx=20, pady=(10, 0), sticky="ew")
        row_idx += 1

        self.btn_new = ctk.CTkButton(self.sidebar_frame, text="새 프로젝트", command=self.create_new_project, 
                                     font=FONT_BTN, fg_color="transparent", border_width=1, text_color=("gray10", "#DCE4EE"))
        self.btn_new.grid(row=row_idx, column=0, padx=20, pady=5, sticky="ew")
        row_idx += 1

        self.btn_open = ctk.CTkButton(self.sidebar_frame, text="프로젝트 열기", command=self.open_existing_project,
                                      font=FONT_BTN, fg_color="transparent", border_width=1, text_color=("gray10", "#DCE4EE"))
        self.btn_open.grid(row=row_idx, column=0, padx=20, pady=5, sticky="ew")
        row_idx += 1

        self.btn_folder = ctk.CTkButton(self.sidebar_frame, text="탐색기 열기", command=self.open_current_project_folder,
                                        font=FONT_BTN, fg_color="transparent", border_width=1, text_color=("gray10", "#DCE4EE"))
        self.btn_folder.grid(row=row_idx, column=0, padx=20, pady=5, sticky="ew")
        row_idx += 1

        # [섹션 2] 수문 분석 단계 (정의된 ANALYSIS_STEPS 사용)
        self.lbl_analysis = ctk.CTkLabel(self.sidebar_frame, text="[ 수문 분석 단계 ]", font=FONT_SUBTITLE, anchor="w")
        self.lbl_analysis.grid(row=row_idx, column=0, padx=20, pady=(20, 0), sticky="ew")
        row_idx += 1

        for i, title in ANALYSIS_STEPS.items():
            btn = ctk.CTkButton(self.sidebar_frame, text=title, 
                                command=lambda n=i: self.run_sub_process(n),
                                font=FONT_BTN, height=35, anchor="w")
            btn.grid(row=row_idx, column=0, padx=20, pady=3, sticky="ew")
            row_idx += 1

        # 여백 채우기
        self.sidebar_frame.grid_rowconfigure(row_idx, weight=1)
        row_idx += 1

        # 종료 버튼
        self.btn_exit = ctk.CTkButton(self.sidebar_frame, text="종 료", command=self.quit,
                                      fg_color="#c0392b", hover_color="#e74c3c", font=FONT_BTN)
        self.btn_exit.grid(row=row_idx, column=0, padx=20, pady=20, sticky="ew")

    def create_main_content(self):
        """오른쪽 메인 컨텐츠 영역"""
        self.main_view = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_view.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)

        # 1. 프로젝트 정보 패널
        self.info_frame = ctk.CTkFrame(self.main_view)
        self.info_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(self.info_frame, text="현재 프로젝트 정보", font=FONT_TITLE).pack(anchor="w", padx=20, pady=(15, 5))
        
        self.lbl_project_name = ctk.CTkLabel(self.info_frame, text="프로젝트 명: (선택되지 않음)", font=FONT_BODY, text_color="gray")
        self.lbl_project_name.pack(anchor="w", padx=20, pady=2)

        self.lbl_project_path = ctk.CTkLabel(self.info_frame, text="저장 경로: -", font=FONT_BODY, text_color="gray")
        self.lbl_project_path.pack(anchor="w", padx=20, pady=(2, 15))

        # 2. 로그 패널
        self.log_frame = ctk.CTkFrame(self.main_view)
        self.log_frame.pack(fill="both", expand=True)

        ctk.CTkLabel(self.log_frame, text="시스템 로그 & 작업 기록", font=FONT_TITLE).pack(anchor="w", padx=20, pady=(15, 5))
        
        self.log_text = ctk.CTkTextbox(self.log_frame, font=FONT_LOG, activate_scrollbars=True)
        self.log_text.pack(fill="both", expand=True, padx=20, pady=(5, 20))
        self.log_text.configure(state="disabled")

    def log_message(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def create_new_project(self):
        name = simpledialog.askstring("새 프로젝트", "생성할 프로젝트 이름을 입력하세요:")
        if not name: return
        name = name.strip()
        project_path = os.path.join(self.projects_root_folder, name)

        if os.path.exists(project_path):
            messagebox.showwarning("경고", "이미 존재하는 프로젝트입니다.")
            return
        try:
            os.makedirs(project_path)
            self.set_current_project(name, project_path)
            self.log_message(f"새 프로젝트 '{name}' 생성됨.")
            self.append_to_project_log(f"--- 프로젝트 '{name}' 생성됨 ---", init=True)
        except OSError as e:
            messagebox.showerror("에러", f"폴더 생성 실패: {e}")

    def open_existing_project(self):
        selected_path = filedialog.askdirectory(initialdir=self.projects_root_folder, title="프로젝트 폴더 선택")
        if not selected_path: return
        project_name = os.path.basename(selected_path)
        self.set_current_project(project_name, selected_path)
        self.log_message(f"프로젝트 '{project_name}' 로드됨.")
        self.append_to_project_log(f"--- 프로젝트 '{project_name}' 로드됨 ---")

    def set_current_project(self, name, path):
        self.current_project_name = name
        self.current_project_path = path
        self.current_project_log_file = os.path.join(path, f"{name}_log.txt")
        
        self.lbl_project_name.configure(text=f"프로젝트 명: {name}", text_color="#3498db")
        self.lbl_project_path.configure(text=f"저장 경로: {path}", text_color="silver")

    def append_to_project_log(self, log_entry, step_name="-", input_file="-", output_file="-", init=False):
        if not self.current_project_log_file: return
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if init and not os.path.exists(self.current_project_log_file):
            with open(self.current_project_log_file, "w", encoding="utf-8") as f:
                f.write(f"Project: {self.current_project_name}\nCreated: {now}\n{'='*100}\n")
                f.write(f"{'Time':^20} | {'Step':^30} | {'Input File':^20} | {'Note':^20}\n{'='*100}\n")

        line = f"[{now}] {log_entry}\n" if step_name == "-" else f"{now:<20} | {step_name:<30} | {input_file:<20} | {output_file}\n"
        try:
            with open(self.current_project_log_file, "a", encoding="utf-8") as f: f.write(line)
        except Exception as e: self.log_message(f"로그 기록 실패: {e}")

    def open_current_project_folder(self):
        if self.current_project_path and os.path.exists(self.current_project_path):
            if os.name == 'nt': os.startfile(self.current_project_path)
            else: subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', self.current_project_path])
        else: messagebox.showwarning("알림", "프로젝트가 선택되지 않았습니다.")

    def find_target_script(self, step_num):
        """
        폴더 이름이 UI 라벨과 달라도, 폴더명 앞의 번호(1., 2. ...)를 기준으로 찾습니다.
        예: step_num=1 -> "1."으로 시작하는 폴더(1.강우자료수집) 안의 "01."으로 시작하는 파일 찾음.
        """
        folder_prefix = f"{step_num}."
        dirs = [d for d in os.listdir(self.base_path) if os.path.isdir(os.path.join(self.base_path, d)) and d.startswith(folder_prefix)]
        if not dirs: return None, None, f"'{folder_prefix}'로 시작하는 폴더 없음"
        
        target_folder = dirs[0]
        folder_path = os.path.join(self.base_path, target_folder)
        file_prefix = f"{step_num:02d}." 
        py_files = [f for f in os.listdir(folder_path) if f.startswith(file_prefix) and f.endswith(".py")]
        
        if not py_files: return target_folder, None, f"'{target_folder}' 안에 '{file_prefix}...' 파일 없음"
        return target_folder, py_files[0], None

    def run_sub_process(self, step_num):
        """하위 프로세스 실행"""
        if not self.current_project_path:
            messagebox.showwarning("경고", "먼저 프로젝트를 생성하거나 열어주세요.")
            return

        step_title = ANALYSIS_STEPS[step_num]
        folder_name, script_name, error_msg = self.find_target_script(step_num)
        
        if error_msg:
            messagebox.showerror("실행 불가", f"실행 파일을 찾을 수 없습니다.\n({error_msg})")
            return

        input_file_path = ""
        input_filename = "Auto/Load from Config"

        # 1, 2, 3 단계는 파일 선택 없이 Config 기반 자동 로드
        # 4단계는 GUI 내부에서 셰이프파일을 직접 선택하므로 파일 선택 불필요
        # 5단계는 GUI 내부에서 모든 매개변수 직접 입력하므로 파일 선택 불필요
        if step_num not in [1, 2, 3, 4, 5, 6]:
            input_file_path = filedialog.askopenfilename(initialdir=self.current_project_path, title=f"[{step_title}] 입력 파일 선택")
            if not input_file_path: return 
            input_filename = os.path.basename(input_file_path)

        self.log_message(f"실행: {script_name} (in {folder_name})")
        self.append_to_project_log("Script Run", step_name=step_title, input_file=input_filename, output_file="Processing...")

        try:
            cmd = [sys.executable, script_name, self.current_project_path, input_file_path]
            subprocess.Popen(cmd, cwd=os.path.join(self.base_path, folder_name))
        except Exception as e:
            self.log_message(f"실행 중 오류 발생: {e}")
            messagebox.showerror("시스템 오류", str(e))

if __name__ == "__main__":
    app = HydroAnalysisApp()
    app.mainloop()