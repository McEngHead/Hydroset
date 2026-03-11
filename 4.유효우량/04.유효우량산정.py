import os
os.environ["QT_LOGGING_RULES"] = "qt.qpa.window.warning=false"

import sys
import json
import struct
import sqlite3
import geopandas as gpd
import pandas as pd
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib import rc
from ctypes import windll, byref, sizeof, c_int
from datetime import datetime

try:
    import contextily as cx
    _HAS_CONTEXTILY = True
except ImportError:
    _HAS_CONTEXTILY = False

# --- [CustomTkinter 설정] ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# 폰트 설정
FONT_TITLE  = ("맑은 고딕", 22, "bold")
FONT_HEADER = ("맑은 고딕", 14, "bold")
FONT_BODY   = ("맑은 고딕", 12)
FONT_SMALL  = ("맑은 고딕", 10)
FONT_BTN    = ("맑은 고딕", 12, "bold")
FONT_LOG    = ("consolas", 11)


# -----------------------------------------------------------
# CN 변환 공식
# -----------------------------------------------------------
def cn1_from_cn2(cn2: float) -> float:
    denom = 10.0 - 0.058 * cn2
    return (4.2 * cn2) / denom if denom > 0 else cn2

def cn3_from_cn2(cn2: float) -> float:
    denom = 10.0 + 0.13 * cn2
    return (23.0 * cn2) / denom if denom > 0 else cn2


# -----------------------------------------------------------
# GUI 애플리케이션
# -----------------------------------------------------------
class EffectiveRainfallApp(ctk.CTk):
    def __init__(self, project_path: str = None):
        super().__init__()

        self.title("유효우량 산정 (4단계)")
        self.geometry("1280x860")
        self.after(0, lambda: self.state("zoomed"))  # 시작 시 최대화
        self._set_dark_title_bar()

        if project_path and os.path.isdir(project_path):
            self.project_path = project_path
            self.project_name = os.path.basename(project_path)
            self.config_file  = os.path.join(project_path, "project_config.json")
            self.log_file     = os.path.join(project_path, f"{self.project_name}_log.txt")
        else:
            messagebox.showerror("오류", "유효한 프로젝트 경로가 필요합니다.")
            sys.exit(1)

        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.excel_ref  = os.path.join(self.script_dir, "CN_AMC_II.xlsx")
        self.target_crs = "EPSG:5186"

        self.gdfs      = {"Bound": None, "A": None, "B": None}
        self.path_vars = {
            "Bound": tk.StringVar(value=""),
            "A":     tk.StringVar(value=self._load_folder_from_db("A")),
            "B":     tk.StringVar(value=self._load_folder_from_db("B")),
        }
        # 폴더 레이어(A, B)의 감지된 CRS 캐시
        self._folder_crs: dict[str, str | None] = {"A": None, "B": None}

        # 레이어 투명도 (슬라이더 기본값)
        self.alpha_vals = {"A": 0.55, "B": 0.45, "Bound": 1.0}
        # 슬라이더 위젯 참조
        self._sliders: dict[str, ctk.CTkSlider] = {}
        self._alpha_lbls: dict[str, ctk.CTkLabel] = {}
        # 레이어 아티스트 참조 (alpha 즉시 갱신용)
        self._artists: dict[str, object] = {"A": None, "B": None, "Bound": None}
        # 전체 범위 (더블클릭 리셋용)
        self._full_extent: tuple | None = None
        # 패닝 상태
        self._pan_data: dict | None = None

        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._build_ui()

    # ----------------------------------------------------------
    def _set_dark_title_bar(self):
        try:
            hwnd = windll.user32.GetParent(self.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(1)), sizeof(c_int))
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), sizeof(c_int))
        except Exception:
            pass

    # ----------------------------------------------------------
    # UI 구성
    # ----------------------------------------------------------
    def _build_ui(self):
        # ── 상단 타이틀 바 ──────────────────────────────────────
        title_bar = ctk.CTkFrame(self, fg_color="transparent")
        title_bar.pack(fill="x", padx=4, pady=(4, 0))
        ctk.CTkLabel(title_bar, text="유효우량 산정 (4단계)", font=FONT_HEADER).pack(side="left")
        ctk.CTkLabel(title_bar, text=f"  |  {self.project_name}",
                     font=FONT_SMALL, text_color="gray").pack(side="left")

        bg_text  = "배경지도: ON" if _HAS_CONTEXTILY else "배경지도: OFF"
        bg_color = "#2ecc71" if _HAS_CONTEXTILY else "#e74c3c"
        ctk.CTkLabel(title_bar, text=bg_text,
                     font=FONT_SMALL, text_color=bg_color).pack(side="right", padx=4)

        # ── 메인 레이아웃 ─────────────────────────────────────────
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=2, pady=2)

        self._build_left(main)
        self._build_right(main)

    # ----------------------------------------------------------
    def _build_left(self, parent):
        left = ctk.CTkFrame(parent, width=320)
        left.pack(side="left", fill="y", padx=(0, 2))
        left.pack_propagate(False)

        # ── GIS 레이어 선택 ──────────────────────────────────────
        ctk.CTkLabel(left, text="GIS 데이터 선택", font=FONT_BODY).pack(
            anchor="w", padx=6, pady=(6, 2))

        for label_text, key in [
            ("1. 소유역 바운더리",      "Bound"),
            ("2. 토지피복도 (Layer A)", "A"),
            ("3. 토양도 (Layer B)",     "B"),
        ]:
            ctk.CTkLabel(left, text=label_text, font=FONT_SMALL).pack(
                anchor="w", padx=8, pady=(3, 0))
            row = tk.Frame(left, bg="#2b2b2b", height=32)
            row.pack(fill="x", padx=6, pady=(1, 0))
            row.pack_propagate(False)

            _BW = 75
            _ek = dict(font=FONT_SMALL, relief="flat", bd=0,
                       highlightthickness=1, highlightcolor="#1F6AA5",
                       insertbackground="white")
            if key == "Bound":
                tk.Entry(row, textvariable=self.path_vars[key],
                         bg="#343638", fg="#DCE4EE",
                         highlightbackground="#565B5E",
                         **_ek).place(x=1, y=1, relwidth=1.0, width=-(_BW + 6), height=30)
                ctk.CTkButton(row, text="파일", width=_BW, height=30,
                              font=FONT_SMALL,
                              command=lambda k=key: self._browse(k)
                              ).place(relx=1.0, x=-(_BW + 1), y=1)
            else:
                tk.Entry(row, textvariable=self.path_vars[key],
                         state="readonly",
                         readonlybackground="#2b2b2b", fg="#888888",
                         highlightbackground="#3a3a3a",
                         **_ek).place(x=1, y=1, relwidth=1.0, width=-(_BW + 6), height=30)
                ctk.CTkButton(row, text="업데이트", width=_BW, height=30,
                              font=FONT_SMALL,
                              command=lambda k=key: self._rebuild_tile_index(k)
                              ).place(relx=1.0, x=-(_BW + 1), y=1)

        ctk.CTkLabel(left, text=f"참조: {os.path.basename(self.excel_ref)}",
                     font=FONT_SMALL, text_color="gray").pack(anchor="w", padx=8, pady=(4, 0))

        # ── 실행 버튼 ────────────────────────────────────────────
        self.btn_run = ctk.CTkButton(
            left, text="CN값 산정 및 저장",
            font=FONT_BTN, height=36, command=self._run_analysis)
        self.btn_run.pack(fill="x", padx=8, pady=6)

        # ── 결과 요약 ────────────────────────────────────────────
        ctk.CTkLabel(left, text="산정 결과 (AMC 조건별 CN)", font=FONT_SMALL).pack(
            anchor="w", padx=8, pady=(0, 2))

        result_box = ctk.CTkFrame(left)
        result_box.pack(fill="x", padx=6, pady=(0, 4))

        for label_text, attr, color in [
            ("CN II  (AMC-Ⅱ, 가중평균):", "lbl_cn2", "#3498db"),
            ("CN I   (AMC-Ⅰ):",           "lbl_cn1", "#95a5a6"),
            ("CN III (AMC-Ⅲ, 채택값):",   "lbl_cn3", "#e74c3c"),
        ]:
            row = ctk.CTkFrame(result_box, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=2)
            ctk.CTkLabel(row, text=label_text, font=FONT_SMALL,
                         width=200, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(row, text="-", font=FONT_BODY, text_color=color)
            lbl.pack(side="left")
            setattr(self, attr, lbl)

        # ── 로그 ─────────────────────────────────────────────────
        ctk.CTkLabel(left, text="실행 로그", font=FONT_SMALL).pack(
            anchor="w", padx=8, pady=(2, 1))
        self.txt_log = tk.Text(
            left, font=FONT_LOG, bg="#1a1a1a", fg="#d4d4d4",
            insertbackground="white", wrap="word", relief="flat")
        self.txt_log.pack(fill="both", expand=True, padx=6, pady=(0, 4))

    # ----------------------------------------------------------
    def _build_right(self, parent):
        right = ctk.CTkFrame(parent)
        right.pack(side="left", fill="both", expand=True)

        # ── 줌 안내 (한 줄, 최소 높이) ──────────────────────────
        hdr = ctk.CTkFrame(right, fg_color="transparent")
        hdr.pack(fill="x", padx=2, pady=(2, 0))
        ctk.CTkLabel(hdr,
                     text="스크롤: 줌  |  드래그: 이동  |  더블클릭: 전체보기",
                     font=FONT_SMALL, text_color="gray").pack(side="right")

        # ── 투명도 슬라이더 바 (bottom에 먼저 pack) ──────────────
        ctrl = ctk.CTkFrame(right, fg_color="#2b2b2b", corner_radius=4)
        ctrl.pack(fill="x", padx=2, pady=(1, 2), side="bottom")

        # ── Matplotlib 캔버스 (래퍼 없이 right에 직접) ──────────
        self.fig, self.ax = plt.subplots(figsize=(7, 6), dpi=100,
                                         facecolor="#1a1a1a")
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)  # axes가 figure 전체를 채움
        self.ax.set_facecolor("#1a1a1a")
        self.ax.set_axis_off()

        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

        # 마우스 이벤트 연결
        self.canvas.mpl_connect('scroll_event',        self._on_scroll)
        self.canvas.mpl_connect('button_press_event',  self._on_press)
        self.canvas.mpl_connect('motion_notify_event', self._on_drag)
        self.canvas.mpl_connect('button_release_event',self._on_release)

        slider_defs = [
            ("A",     "토지피복",  "#27ae60"),
            ("B",     "토양도",    "#e67e22"),
            ("Bound", "경계선",    "#e74c3c"),
        ]
        for key, label, color in slider_defs:
            col = ctk.CTkFrame(ctrl, fg_color="transparent")
            col.pack(side="left", fill="x", expand=True, padx=4, pady=3)

            top_row = ctk.CTkFrame(col, fg_color="transparent")
            top_row.pack(fill="x")
            ctk.CTkLabel(top_row, text=label, font=FONT_SMALL,
                         text_color=color).pack(side="left")
            val_lbl = ctk.CTkLabel(top_row,
                                   text=f"{self.alpha_vals[key]:.2f}",
                                   font=FONT_SMALL, text_color="gray")
            val_lbl.pack(side="right")
            self._alpha_lbls[key] = val_lbl

            slider = ctk.CTkSlider(
                col, from_=0.0, to=1.0, number_of_steps=20,
                button_color=color, button_hover_color=color,
                command=lambda v, k=key: self._on_alpha_change(k, v))
            slider.set(self.alpha_vals[key])
            slider.pack(fill="x", pady=(2, 0))
            self._sliders[key] = slider

        # 새로고침 버튼 (배경지도 타일 재로드)
        ctk.CTkButton(
            ctrl, text="↺", width=44, height=44,
            font=("맑은 고딕", 16), fg_color="#3a3a3a",
            hover_color="#555555",
            command=self._refresh_map,
        ).pack(side="right", padx=8, pady=6)

    # ----------------------------------------------------------
    # 로그
    # ----------------------------------------------------------
    def _log(self, msg: str):
        self.txt_log.insert(tk.END, f"{msg}\n")
        self.txt_log.see(tk.END)
        self.update()

    # ----------------------------------------------------------
    # 레이어 선택
    # ----------------------------------------------------------
    def _browse(self, key: str):
        """바운더리 파일 선택 및 로드 (A/B는 하드코딩 경로 사용)"""
        path = filedialog.askopenfilename(filetypes=[("Shapefiles", "*.shp")])
        if not path:
            return
        self.path_vars[key].set(path)
        self._log("바운더리 로딩 중...")
        try:
            gdf = gpd.read_file(path)
            if gdf.crs is None:
                gdf = gdf.set_crs(self.target_crs)
            if str(gdf.crs) != self.target_crs:
                gdf = gdf.to_crs(self.target_crs)
            self.gdfs["Bound"] = gdf
            self._log(f"  ✔ 바운더리 로드 완료 ({len(gdf)}개 피처)")
            self._auto_match_layers()
            self._update_map()
        except Exception as e:
            messagebox.showerror("로딩 오류", str(e))
            self._log(f"  ✘ 바운더리 로딩 실패: {e}")

    # ----------------------------------------------------------
    # SHP 헤더 bbox 읽기 (32 바이트만 읽음, geopandas 불필요)
    # ----------------------------------------------------------
    def _read_shp_bbox(self, shp_path: str) -> tuple | None:
        try:
            with open(shp_path, "rb") as f:
                f.seek(36)
                return struct.unpack("<4d", f.read(32))
        except Exception:
            return None

    # ----------------------------------------------------------
    # 공유 SQLite DB 경로 (스크립트 폴더에 단일 파일로 관리)
    # ----------------------------------------------------------
    def _get_db_path(self) -> str:
        return os.path.join(self.script_dir, "_hydroset_tile_index.sqlite")

    # ----------------------------------------------------------
    # 폴더 및 1단계 하위폴더를 재귀 스캔하여 .shp 목록 반환
    # ----------------------------------------------------------
    def _scan_shp_recursive(self, folder: str) -> list[str]:
        paths = []
        for item in sorted(os.listdir(folder)):
            full = os.path.join(folder, item)
            if item.lower().endswith(".shp"):
                paths.append(full)
            elif os.path.isdir(full):
                for sub in sorted(os.listdir(full)):
                    if sub.lower().endswith(".shp"):
                        paths.append(os.path.join(full, sub))
        return paths

    # ----------------------------------------------------------
    # 첫 번째 타일 1개로 CRS 감지
    # ----------------------------------------------------------
    def _detect_crs_from_folder(self, folder: str) -> str:
        for item in sorted(os.listdir(folder)):
            if item.lower().endswith(".shp"):
                try:
                    s = gpd.read_file(os.path.join(folder, item), rows=1)
                    if s.crs:
                        return str(s.crs)
                except Exception:
                    continue
        return self.target_crs

    # ----------------------------------------------------------
    # 공유 DB 열기 / 레이어 인덱스 생성
    #   - DB 없으면 테이블 생성
    #   - 해당 layer 레코드 없거나 rebuild=True → 스캔 후 INSERT
    # ----------------------------------------------------------
    def _get_tile_index(self, key: str, rebuild: bool = False) -> sqlite3.Connection | None:
        folder = self.path_vars[key].get()
        if not folder or not os.path.isdir(folder):
            self._log(f"  [{key}] 폴더가 설정되지 않음")
            return None

        db_path = self._get_db_path()
        con = sqlite3.connect(db_path)
        cur = con.cursor()

        # 공유 테이블 (없으면 생성)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tiles (
                layer    TEXT,
                filepath TEXT,
                xmin REAL, ymin REAL, xmax REAL, ymax REAL,
                crs  TEXT,
                PRIMARY KEY (layer, filepath)
            )""")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_layer_bbox "
            "ON tiles(layer, xmin, xmax, ymin, ymax)")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS settings "
            "(key TEXT PRIMARY KEY, value TEXT)")

        count = cur.execute(
            "SELECT COUNT(*) FROM tiles WHERE layer=?", (key,)).fetchone()[0]

        if count == 0 or rebuild:
            if rebuild:
                cur.execute("DELETE FROM tiles WHERE layer=?", (key,))
                self._log(f"  [{key}] 기존 인덱스 삭제 후 재생성...")
            else:
                self._log(f"  [{key}] 인덱스 없음 → 신규 생성 중...")

            crs_detected = self._detect_crs_from_folder(folder)
            self._folder_crs[key] = crs_detected
            self._log(f"  [{key}] 감지 CRS: {crs_detected}")

            shp_paths = self._scan_shp_recursive(folder)
            self._log(f"  [{key}] {len(shp_paths)}개 .shp 헤더 스캔 중...")

            rows = []
            for path in shp_paths:
                bbox = self._read_shp_bbox(path)
                if bbox:
                    rows.append((key, path,
                                 bbox[0], bbox[1], bbox[2], bbox[3],
                                 crs_detected))
            cur.executemany(
                "INSERT OR REPLACE INTO tiles VALUES (?,?,?,?,?,?,?)", rows)
            con.commit()
            self._log(f"  [{key}] 인덱스 완료: {len(rows)}개 타일 등록")
        else:
            if not self._folder_crs[key]:
                r = cur.execute(
                    "SELECT crs FROM tiles WHERE layer=? LIMIT 1",
                    (key,)).fetchone()
                if r:
                    self._folder_crs[key] = r[0]

        return con

    # ----------------------------------------------------------
    # ----------------------------------------------------------
    # DB settings 테이블 ─ 폴더 경로 읽기/쓰기
    # ----------------------------------------------------------
    def _load_folder_from_db(self, key: str) -> str:
        db_path = self._get_db_path()
        if not os.path.exists(db_path):
            return ""
        try:
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
            row = cur.execute(
                "SELECT value FROM settings WHERE key=?", (f"folder_{key}",)).fetchone()
            con.close()
            return row[0] if row else ""
        except Exception:
            return ""

    def _save_folder_to_db(self, key: str, folder: str):
        db_path = self._get_db_path()
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        cur.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",
                    (f"folder_{key}", folder))
        con.commit()
        con.close()

    # 업데이트 버튼: 폴더 선택(변경 가능) + 재스캔 → DB 반영
    # ----------------------------------------------------------
    def _rebuild_tile_index(self, key: str):
        label = "토지피복도" if key == "A" else "토양도"
        current = self.path_vars[key].get()

        # 폴더 선택 다이얼로그 (현재 경로를 초기 디렉토리로)
        init_dir = current if os.path.isdir(current) else "/"
        new_folder = filedialog.askdirectory(
            title=f"[{label}] 데이터 폴더 선택 (취소 시 현재 폴더 재스캔)",
            initialdir=init_dir)

        if new_folder:
            # 새 폴더(또는 동일 폴더) 선택 → DB에 저장 + 표시 업데이트
            folder = new_folder
            self._save_folder_to_db(key, folder)
            self.path_vars[key].set(folder)
        elif current and os.path.isdir(current):
            # 취소했지만 기존 폴더가 유효 → 기존 경로로 재스캔
            folder = current
        else:
            messagebox.showwarning("경고",
                f"[{label}] 폴더가 설정되지 않았습니다.\n폴더를 선택해주세요.")
            return

        self._log(f"\n[{label}] 인덱스 업데이트 시작...")
        self._log(f"  폴더: {folder}")
        self._folder_crs[key] = None
        con = self._get_tile_index(key, rebuild=True)
        if con:
            con.close()
        self._log(f"  ✔ [{label}] 인덱스 업데이트 완료")

    # ----------------------------------------------------------
    # CN_AMC_II.xlsx → SQLite 1회 import (이미 있으면 스킵)
    # ----------------------------------------------------------
    def _ensure_cn_data_in_db(self) -> bool:
        db_path = self._get_db_path()
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS cn_land_cover (
            lc_code    INTEGER,
            soil_group TEXT,
            cn_value   REAL,
            PRIMARY KEY (lc_code, soil_group))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS cn_soil_class (
            soil_code  TEXT PRIMARY KEY,
            soil_group TEXT)""")

        count = cur.execute("SELECT COUNT(*) FROM cn_land_cover").fetchone()[0]
        if count > 0:
            con.close()
            return True

        if not os.path.exists(self.excel_ref):
            con.close()
            self._log(f"  ✘ 참조 파일 없음: {self.excel_ref}")
            return False

        try:
            self._log("  CN 참조 데이터 DB 로드 중 (최초 1회)...")
            df_lc   = pd.read_excel(self.excel_ref, sheet_name="LAND_COVER")
            df_soil = pd.read_excel(self.excel_ref, sheet_name="CLASS_SOIL")

            soil_col = "수문학적 토양군(SCS분류 2007)"
            rows_soil = []
            for _, r in df_soil.iterrows():
                code  = str(r["토양부호"]).strip()
                group = str(r[soil_col]).strip()
                if code and group and code != "nan":
                    rows_soil.append((code, group))
            cur.executemany("INSERT OR REPLACE INTO cn_soil_class VALUES (?,?)", rows_soil)

            sg_cols  = [c for c in df_lc.columns if c != "코드번호"]
            rows_cn  = []
            for _, r in df_lc.iterrows():
                try:
                    lc_code = int(r["코드번호"])
                except (ValueError, TypeError):
                    continue
                for sg in sg_cols:
                    try:
                        cn = float(r[sg])
                        rows_cn.append((lc_code, str(sg), cn))
                    except (ValueError, TypeError):
                        pass
            cur.executemany("INSERT OR REPLACE INTO cn_land_cover VALUES (?,?,?)", rows_cn)

            con.commit()
            self._log(f"  ✔ CN DB 로드 완료: 피복 {len(rows_cn)}건, 토양 {len(rows_soil)}건")
            return True
        except Exception as e:
            self._log(f"  ✘ CN DB 로드 실패: {e}")
            return False
        finally:
            con.close()

    # ----------------------------------------------------------
    # 폴더 CRS 반환 (캐시 우선, 없으면 DB를 통해 로드)
    # ----------------------------------------------------------
    def _detect_folder_crs(self, folder: str, key: str) -> str:
        if self._folder_crs[key]:
            return self._folder_crs[key]
        con = self._get_tile_index(key)
        if con:
            con.close()
        return self._folder_crs[key] or self.target_crs

    # ----------------------------------------------------------
    # 바운더리 bbox → 타일 CRS 좌표로 변환
    # ----------------------------------------------------------
    def _bound_bbox_in_crs(self, target_crs: str) -> tuple | None:
        gdf_b = self.gdfs["Bound"]
        if gdf_b is None:
            return None
        bx0, by0, bx1, by1 = gdf_b.total_bounds
        if str(gdf_b.crs) == target_crs:
            return bx0, by0, bx1, by1
        try:
            from pyproj import Transformer
            t = Transformer.from_crs(str(gdf_b.crs), target_crs, always_xy=True)
            bx0, by0 = t.transform(bx0, by0)
            bx1, by1 = t.transform(bx1, by1)
            return bx0, by0, bx1, by1
        except Exception as e:
            self._log(f"  ⚠ bbox CRS 변환 실패: {e}")
            return None

    # ----------------------------------------------------------
    # SQLite 쿼리로 교차 타일 검색 (filepath가 절대경로)
    # ----------------------------------------------------------
    def _find_matching_tiles(self, key: str,
                              bx0: float, by0: float,
                              bx1: float, by1: float) -> list[str]:
        con = self._get_tile_index(key)
        if con is None:
            return []
        cur = con.cursor()
        rows = cur.execute(
            "SELECT filepath FROM tiles "
            "WHERE layer=? AND xmin<=? AND xmax>=? AND ymin<=? AND ymax>=?",
            (key, bx1, bx0, by1, by0)
        ).fetchall()
        con.close()
        return [r[0] for r in rows]

    # ----------------------------------------------------------
    # 단일 레이어 자동 매칭 + 로드
    # ----------------------------------------------------------
    def _auto_match_single(self, key: str, folder: str):
        label = "토지피복도" if key == "A" else "토양도"
        self._log(f"\n[{label}] 자동 타일 매칭 시작...")

        tile_crs = self._detect_folder_crs(folder, key)
        bbox = self._bound_bbox_in_crs(tile_crs)
        if bbox is None:
            self._log(f"  ✘ 바운더리 bbox 변환 실패")
            return

        bx0, by0, bx1, by1 = bbox
        self._log(f"  바운더리 bbox (타일 CRS): X[{bx0:.0f}~{bx1:.0f}] Y[{by0:.0f}~{by1:.0f}]")

        matches = self._find_matching_tiles(key, bx0, by0, bx1, by1)
        self._log(f"  매칭 타일: {len(matches)}개")
        if not matches:
            self._log(f"  ✘ [{label}] 매칭된 타일 없음. 바운더리 CRS·범위 확인 필요.")
            return

        gdfs = []
        for path in matches:
            try:
                g = gpd.read_file(path)
                if g.crs is None:
                    g = g.set_crs(tile_crs)
                if str(g.crs) != self.target_crs:
                    g = g.to_crs(self.target_crs)
                gdfs.append(g)
                self._log(f"  ✔ {os.path.basename(path)} ({len(g)}개 피처)")
            except Exception as e:
                self._log(f"  ⚠ {os.path.basename(path)} 로드 실패: {e}")

        if gdfs:
            self.gdfs[key] = pd.concat(gdfs, ignore_index=True)
            total = len(self.gdfs[key])
            self._log(f"  ✔ [{label}] 완료: {total}개 피처 ({len(gdfs)}개 타일 병합)")

    # ----------------------------------------------------------
    # 두 폴더 레이어 모두 자동 매칭
    # ----------------------------------------------------------
    def _auto_match_layers(self):
        for key in ("A", "B"):
            folder = self.path_vars[key].get()
            if folder and os.path.isdir(folder):
                self._auto_match_single(key, folder)

    # ----------------------------------------------------------
    # 투명도 슬라이더 콜백 — 타일 재로드 없이 즉시 반영
    # ----------------------------------------------------------
    def _on_alpha_change(self, key: str, value: float):
        self.alpha_vals[key] = value
        self._alpha_lbls[key].configure(text=f"{value:.2f}")

        artist = self._artists.get(key)
        if artist is not None:
            artist.set_alpha(value)
            self.canvas.draw_idle()

    # ----------------------------------------------------------
    # 지도 전체 갱신 (배경지도 포함)
    # ----------------------------------------------------------
    def _update_map(self):
        self.ax.clear()
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self.ax.set_facecolor("#1a1a1a")
        self.fig.patch.set_facecolor("#1a1a1a")
        self._artists = {"A": None, "B": None, "Bound": None}

        has_bound = self.gdfs["Bound"] is not None
        minx = miny = maxx = maxy = 0.0

        if has_bound:
            minx, miny, maxx, maxy = self.gdfs["Bound"].total_bounds

        use_bg    = _HAS_CONTEXTILY and has_bound
        crs_disp  = "EPSG:3857" if use_bg else self.target_crs

        def _to_disp(gdf):
            return gdf.to_crs(crs_disp) if use_bg else gdf

        # ── 토지피복 (A) ─────────────────────────────────────────
        if self.gdfs["A"] is not None:
            view = self.gdfs["A"].cx[minx:maxx, miny:maxy] if has_bound else self.gdfs["A"]
            if not view.empty:
                _to_disp(view).plot(
                    ax=self.ax,
                    color="#27ae60",
                    alpha=self.alpha_vals["A"],
                    edgecolor="none",
                )
                if self.ax.collections:
                    self._artists["A"] = self.ax.collections[-1]

        # ── 토양도 (B) ───────────────────────────────────────────
        if self.gdfs["B"] is not None:
            view = self.gdfs["B"].cx[minx:maxx, miny:maxy] if has_bound else self.gdfs["B"]
            if not view.empty:
                _to_disp(view).plot(
                    ax=self.ax,
                    color="#e67e22",
                    alpha=self.alpha_vals["B"],
                    edgecolor="none",
                )
                if self.ax.collections:
                    self._artists["B"] = self.ax.collections[-1]

        # ── 바운더리 ─────────────────────────────────────────────
        if has_bound:
            _to_disp(self.gdfs["Bound"]).plot(
                ax=self.ax,
                color="none",
                edgecolor="#e74c3c",
                linewidth=2,
            )
            if self.ax.collections:
                self._artists["Bound"] = self.ax.collections[-1]

            # 표시 범위
            bnd_disp = self.gdfs["Bound"].to_crs(crs_disp) if use_bg else self.gdfs["Bound"]
            bx0, by0, bx1, by1 = bnd_disp.total_bounds
            mx = (bx1 - bx0) * 0.06
            my = (by1 - by0) * 0.06
            self.ax.set_xlim(bx0 - mx, bx1 + mx)
            self.ax.set_ylim(by0 - my, by1 + my)
            self._full_extent = (bx0 - mx, bx1 + mx, by0 - my, by1 + my)

            # 배경지도 (contextily)
            if use_bg:
                try:
                    cx.add_basemap(
                        self.ax,
                        crs=crs_disp,
                        source=cx.providers.CartoDB.DarkMatter,
                        zoom="auto",
                        attribution=False,
                    )
                except Exception as e:
                    self._log(f"  ⚠ 배경지도 로드 실패 (오프라인?): {e}")

        self.ax.set_axis_off()
        self.canvas.draw()

    def _refresh_map(self):
        """↺ 버튼: 현재 뷰 범위 유지하며 배경지도 타일 재로드"""
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        self._update_map()
        # 줌/패닝 상태가 초기화됐다면 이전 범위 복원
        if xlim != (0.0, 1.0):  # 기본값이 아닌 경우만 복원
            self.ax.set_xlim(xlim)
            self.ax.set_ylim(ylim)
            self.canvas.draw()

    # ----------------------------------------------------------
    # 창 최대화 완료 후 figure 크기 강제 동기화 (after(400) 에서 호출)
    # ----------------------------------------------------------
    def _initial_canvas_fit(self):
        self.update_idletasks()
        w = self.canvas.get_tk_widget().winfo_width()
        h = self.canvas.get_tk_widget().winfo_height()
        if w > 10 and h > 10:
            dpi = self.fig.get_dpi()
            self.fig.set_size_inches(w / dpi, h / dpi, forward=False)
            self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
            self.canvas.draw()

    # ----------------------------------------------------------
    # canvas widget 크기 변경 → figure 크기 강제 동기화
    # ----------------------------------------------------------
    def _on_canvas_configure(self, event):
        w, h = event.width, event.height
        if w > 10 and h > 10:
            dpi = self.fig.get_dpi()
            self.fig.set_size_inches(w / dpi, h / dpi, forward=False)
            self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
            self.canvas.draw_idle()

    # ----------------------------------------------------------
    # 마우스 이벤트: 스크롤 줌
    # ----------------------------------------------------------
    def _on_scroll(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            return
        factor = 0.80 if event.button == 'up' else 1.25
        cx_d, cy_d = event.xdata, event.ydata
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        self.ax.set_xlim([cx_d + (x - cx_d) * factor for x in xlim])
        self.ax.set_ylim([cy_d + (y - cy_d) * factor for y in ylim])
        self.canvas.draw_idle()

    # ----------------------------------------------------------
    # 마우스 이벤트: 좌클릭 드래그 패닝 / 더블클릭 전체보기
    # ----------------------------------------------------------
    def _on_press(self, event):
        if event.button != 1:
            return
        # 더블클릭: 전체 범위로 리셋
        if event.dblclick and self._full_extent:
            self.ax.set_xlim(self._full_extent[0], self._full_extent[1])
            self.ax.set_ylim(self._full_extent[2], self._full_extent[3])
            self.canvas.draw_idle()
            return
        # 패닝 시작
        if event.inaxes == self.ax:
            self._pan_data = {
                'x': event.x, 'y': event.y,
                'xlim': list(self.ax.get_xlim()),
                'ylim': list(self.ax.get_ylim()),
            }

    def _on_drag(self, event):
        if self._pan_data is None or event.button != 1:
            return
        dx_px = event.x - self._pan_data['x']
        dy_px = event.y - self._pan_data['y']
        # 픽셀 오프셋 → 데이터 좌표 오프셋 변환
        inv = self.ax.transData.inverted()
        p0 = inv.transform((0, 0))
        p1 = inv.transform((dx_px, dy_px))
        ddx = p1[0] - p0[0]
        ddy = p1[1] - p0[1]
        xlim = self._pan_data['xlim']
        ylim = self._pan_data['ylim']
        self.ax.set_xlim([x - ddx for x in xlim])
        self.ax.set_ylim([y - ddy for y in ylim])
        self.canvas.draw_idle()

    def _on_release(self, event):
        if event.button == 1:
            self._pan_data = None

    # ----------------------------------------------------------
    # 분석 실행
    # ----------------------------------------------------------
    def _run_analysis(self):
        if not all(v is not None for v in self.gdfs.values()):
            messagebox.showwarning("경고",
                "소유역 바운더리, 토지피복도, 토양도를 모두 선택해야 합니다.")
            return

        try:
            self._log("\n🚀 CN값 산정 시작...")

            # CN 참조 데이터: SQLite에서 dict로 로드 (필요 시 Excel에서 1회 import)
            if not self._ensure_cn_data_in_db():
                raise RuntimeError("CN 참조 데이터를 로드할 수 없습니다.")

            _con = sqlite3.connect(self._get_db_path())
            _cur = _con.cursor()
            soil_map = {r[0]: r[1] for r in _cur.execute(
                "SELECT soil_code, soil_group FROM cn_soil_class").fetchall()}
            cn_map   = {(r[0], r[1]): r[2] for r in _cur.execute(
                "SELECT lc_code, soil_group, cn_value FROM cn_land_cover").fetchall()}
            _con.close()

            gdf_a     = self.gdfs["A"].copy()
            gdf_b     = self.gdfs["B"].copy()
            gdf_bound = self.gdfs["Bound"].copy()

            gdf_a["geometry"]     = gdf_a.make_valid()
            gdf_b["geometry"]     = gdf_b.make_valid()
            gdf_bound["geometry"] = gdf_bound.make_valid()

            self._log("  레이어 클리핑 중...")
            clip_a = gpd.clip(gdf_a, gdf_bound)
            clip_b = gpd.clip(gdf_b, gdf_bound)

            self._log("  레이어 중첩(Intersection) 중...")
            res = gpd.overlay(clip_a, clip_b, how="intersection")
            res["geometry"] = res.make_valid()
            res = res[res.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()

            self._log("  CN 값 매핑 중...")
            res["_sg"] = res["SOILSY"].apply(lambda x: soil_map.get(str(x).strip()))

            def get_cn(row):
                try:
                    sg = row["_sg"]
                    if sg is None:
                        return None
                    return cn_map.get((int(row["L2_CODE"]), str(sg).strip()))
                except Exception:
                    return None

            res["CN_Value"] = res.apply(get_cn, axis=1)
            res.drop(columns=["_sg"], inplace=True, errors="ignore")

            final_df = res.dropna(subset=["CN_Value"]).copy()
            final_df["Area"] = final_df.geometry.area

            for col in ["ID", "F_ID", "ID_KEY", "AREA_M2", "CN_VAL"]:
                if col in final_df.columns:
                    final_df = final_df.drop(columns=[col])
            final_df.insert(0, "ID", range(1, len(final_df) + 1))

            total_count      = len(final_df)
            total_area       = final_df["Area"].sum()
            weighted_cn_area = (final_df["Area"] * final_df["CN_Value"]).sum()
            cn2 = weighted_cn_area / total_area if total_area > 0 else 0.0
            cn1 = cn1_from_cn2(cn2)
            cn3 = cn3_from_cn2(cn2)

            self._log(f"  ✔ CN II  (AMC-Ⅱ, 가중평균): {cn2:.4f}")
            self._log(f"  ✔ CN I   (AMC-Ⅰ):           {cn1:.4f}")
            self._log(f"  ✔ CN III (AMC-Ⅲ, 채택값):   {cn3:.4f}")

            self.lbl_cn2.configure(text=f"{cn2:.4f}")
            self.lbl_cn1.configure(text=f"{cn1:.4f}")
            self.lbl_cn3.configure(text=f"{cn3:.4f}")

            out_filename = f"{self.project_name}_D_Effective_Rainfall.xlsx"
            out_path     = os.path.join(self.project_path, out_filename)

            details_export = final_df.copy().rename(columns={
                "ID": "Feature ID", "L2_CODE": "Land Cover Code",
                "SOILSY": "Soil Symbol", "Area": "Area (m²)", "CN_Value": "CN Value",
            })
            details_export = details_export[[
                "Feature ID", "Land Cover Code", "Soil Symbol", "Area (m²)", "CN Value"
            ]]
            mapping_export = (
                details_export[["Land Cover Code", "Soil Symbol", "CN Value"]]
                .drop_duplicates().sort_values(["Land Cover Code", "Soil Symbol"])
            )
            summary_df = pd.DataFrame({
                "Total Features":    [total_count],
                "Total Area (m²)":   [round(total_area, 2)],
                "Weighted CN Area":  [round(weighted_cn_area, 4)],
                "Weighted CN Value": [round(cn2, 4)],
                "CN I":              [round(cn1, 4)],
                "CN III":            [round(cn3, 4)],
            })

            self._log(f"  엑셀 저장 중: {out_filename}")
            with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
                summary_df.to_excel(writer,     sheet_name="Summary",         index=False)
                details_export.to_excel(writer, sheet_name="Feature Details", index=False)
                mapping_export.to_excel(writer, sheet_name="CN Mapping",      index=False)
            self._log(f"  💾 저장 완료: {out_filename}")

            shp_filename = f"{self.project_name}_D_Result_Shape.shp"
            shp_path     = os.path.join(self.project_path, shp_filename)
            export_gdf   = final_df.copy().rename(columns={
                "L2_CODE": "LC_CODE", "SOILSY": "SOIL_SYM",
                "CN_Value": "CN_VAL", "Area": "AREA_M2",
            })
            save_cols  = ["ID", "LC_CODE", "SOIL_SYM", "CN_VAL", "AREA_M2", "geometry"]
            export_gdf = export_gdf[[c for c in save_cols if c in export_gdf.columns]]
            self._log(f"  셰이프파일 저장 중: {shp_filename}")
            export_gdf.to_file(shp_path, driver="ESRI Shapefile", encoding="cp949")
            self._log(f"  💾 저장 완료: {shp_filename}")

            config = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            config["step4_effective_rainfall"] = {
                "status":         "completed",
                "output_file":    out_filename,
                "full_path":      out_path,
                "cn2":            round(cn2, 4),
                "cn1":            round(cn1, 4),
                "cn3":            round(cn3, 4),
                "total_features": total_count,
                "total_area_m2":  round(total_area, 2),
                "timestamp":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            self._log("  ✔ project_config.json 업데이트 완료")

            now_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_line = (
                f"{now_str:<20} | {'4. 유효우량 산정':<30} | "
                f"{'CN_AMC_II.xlsx':<20} | "
                f"CN II={cn2:.4f}, CN I={cn1:.4f}, CN III={cn3:.4f} → {out_filename}\n"
            )
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line)
            self._log("  ✔ 프로젝트 로그 기록 완료")

            messagebox.showinfo("완료",
                f"CN 산정 완료\n\n"
                f"CN II  (AMC-Ⅱ, 가중평균): {cn2:.4f}\n"
                f"CN I   (AMC-Ⅰ):           {cn1:.4f}\n"
                f"CN III (AMC-Ⅲ, 채택값):   {cn3:.4f}\n\n"
                f"저장 위치: {out_filename}")

        except Exception as e:
            messagebox.showerror("오류 발생", str(e))
            self._log(f"  ✘ 오류: {e}")

    # ----------------------------------------------------------
    def _on_closing(self):
        plt.close("all")
        self.destroy()
        sys.exit(0)


# -----------------------------------------------------------
if __name__ == "__main__":
    if sys.platform.startswith("win"):
        rc("font", family="Malgun Gothic")
    elif sys.platform.startswith("darwin"):
        rc("font", family="AppleGothic")

    project_path_arg = sys.argv[1] if len(sys.argv) > 1 else None
    app = EffectiveRainfallApp(project_path=project_path_arg)
    app.mainloop()
