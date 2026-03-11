"""
06.하도추적.py — 머스킹엄 하도홍수추적 (Muskingum Flood Routing)
Hydro Analysis System  Module 6

머스킹엄 방법 (KWRA 수문학 CH08 기준):
  S = K[xI + (1-x)O]
  O2 = C1*I2 + C2*I1 + C3*O1
  C1 = (-Kx + 0.5Δt) / (K - Kx + 0.5Δt)
  C2 = (Kx + 0.5Δt)  / (K - Kx + 0.5Δt)
  C3 = (K - Kx - 0.5Δt) / (K - Kx + 0.5Δt)
  안정 조건: 2Kx ≤ Δt ≤ 2K(1-x)
"""

import os, sys, json, traceback, warnings, copy
import numpy as np
from datetime import datetime
from ctypes import windll, byref, sizeof, c_int
from scipy.interpolate import PchipInterpolator

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

warnings.filterwarnings("ignore", category=RuntimeWarning)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

FONT_TITLE  = ("맑은 고딕", 18, "bold")
FONT_HEADER = ("맑은 고딕", 12, "bold")
FONT_BODY   = ("맑은 고딕", 11)
FONT_BTN    = ("맑은 고딕", 11, "bold")
FONT_SMALL  = ("맑은 고딕", 10)
FONT_LOG    = ("Consolas", 10)

HUFF_PRESETS = {
    "1분위": [0.000, 0.130, 0.262, 0.415, 0.546, 0.649, 0.726, 0.795, 0.861, 0.931, 1.000],
    "2분위": [0.000, 0.009, 0.053, 0.101, 0.184, 0.331, 0.538, 0.756, 0.916, 0.975, 1.000],
    "3분위": [0.000, 0.008, 0.041, 0.086, 0.154, 0.263, 0.437, 0.636, 0.833, 0.953, 1.000],
    "4분위": [0.000, 0.007, 0.030, 0.062, 0.110, 0.186, 0.310, 0.492, 0.700, 0.892, 1.000],
}

# 노드 타입별 스타일
NODE_STYLES = {
    'SUBBASIN': {'label': '소유역',   'fill': '#1d5c33', 'outline': '#27ae60', 'shape': 'round_rect'},
    'REACH':    {'label': '하도구간', 'fill': '#1a2d4a', 'outline': '#2980b9', 'shape': 'parallelogram'},
    'JUNCTION': {'label': '합류점',   'fill': '#1c3d5a', 'outline': '#5dade2', 'shape': 'circle'},
    'OUTLET':   {'label': '출구',     'fill': '#4a1c6e', 'outline': '#8e44ad', 'shape': 'rect'},
}

# =============================================================================
# 머스킹엄 추적 엔진
# =============================================================================

class MuskingumEngine:
    @staticmethod
    def compute_coefficients(K, X, dt_hr):
        denom = K - K * X + 0.5 * dt_hr
        if denom <= 1e-12:
            return 0.0, 1.0, 0.0, False
        C1 = (-K * X + 0.5 * dt_hr) / denom
        C2 = (K * X  + 0.5 * dt_hr) / denom
        C3 = (K - K * X - 0.5 * dt_hr) / denom
        stable = (C1 >= -1e-9) and (C3 >= -1e-9)
        return C1, C2, C3, stable

    @staticmethod
    def auto_nstps(K, X, dt_hr):
        if K <= 1e-12: return 1
        upper = 2.0 * K * (1.0 - X)
        if dt_hr <= upper + 1e-9: return 1
        return max(1, int(np.ceil(dt_hr / upper)))

    def route(self, inflow, K, X, dt_hr, NSTPS=0, Q0=None):
        n = len(inflow)
        if n == 0:
            return np.array([]), True, [], 0.0, 1.0, 0.0, 1
        if NSTPS <= 0:
            NSTPS = self.auto_nstps(K, X, dt_hr)
        dt_sub = dt_hr / NSTPS
        C1, C2, C3, stable = self.compute_coefficients(K, X, dt_sub)
        warns = []
        if not stable:
            warns.append(f"불안정: dt_sub={dt_sub:.3f}hr, 2K(1-x)={2*K*(1-X):.3f}hr")
        O_prev = inflow[0] if Q0 is None else float(Q0)
        outflow = np.zeros(n)
        for i in range(n):
            I_curr = float(inflow[i])
            I_prev = float(inflow[i-1]) if i > 0 else float(inflow[0])
            if NSTPS == 1:
                O_prev = C1 * I_curr + C2 * I_prev + C3 * O_prev
            else:
                for j in range(NSTPS):
                    t0 = j / NSTPS; t1 = (j+1) / NSTPS
                    I0s = I_prev + t0 * (I_curr - I_prev)
                    I1s = I_prev + t1 * (I_curr - I_prev)
                    O_prev = C1 * I1s + C2 * I0s + C3 * O_prev
            outflow[i] = max(0.0, O_prev)
        return outflow, stable, warns, C1, C2, C3, NSTPS


# =============================================================================
# Clark 단위도 + 유효우량 엔진
# =============================================================================

class ClarkEngine:
    def effective_rainfall(self, total_precip, tr_min, dt_min, cn, huff_pc):
        n_step = int(tr_min / dt_min) + 1
        t_huff = np.linspace(0.0, 1.0, len(huff_pc))
        t_norm = np.linspace(0.0, 1.0, n_step)
        pc_interp = np.clip(PchipInterpolator(t_huff, np.array(huff_pc, dtype=float))(t_norm), 0.0, 1.0)
        cum_rain = pc_interp * total_precip
        S = (25400.0 / cn) - 254.0
        Ia = 0.2 * S
        cum_excess = np.zeros(n_step)
        for i, P in enumerate(cum_rain):
            if P > Ia:
                cum_excess[i] = (P - Ia) ** 2 / (P - Ia + S)
        return np.maximum(0.0, np.diff(cum_excess, prepend=0.0))

    def clark_uh(self, A, Tc, R, dt_hr):
        uh_len = int((Tc + R * 10.0) / dt_hr) + 5
        t_vals = np.arange(uh_len) * dt_hr
        ai = np.zeros(uh_len)
        for i, t in enumerate(t_vals):
            T = t / Tc if Tc > 1e-12 else 1.0
            if   T >= 1.0: ai[i] = 1.0
            elif T <  0.5: ai[i] = 1.414 * T ** 1.5
            else:          ai[i] = 1.0 - 1.414 * (1.0 - T) ** 1.5
        vol_const = A * 1000.0
        I_flow = np.zeros(uh_len)
        for i in range(1, uh_len):
            dAI = max(0.0, ai[i] - ai[i-1])
            I_flow[i] = dAI * vol_const / (dt_hr * 3600.0)
        c_ca = dt_hr / (R + 0.5 * dt_hr)
        c_cb = 1.0 - c_ca
        O_inst = np.zeros(uh_len)
        for i in range(1, uh_len):
            O_inst[i] = c_ca * I_flow[i] + c_cb * O_inst[i-1]
        uh = np.zeros(uh_len)
        for i in range(1, uh_len):
            uh[i] = 0.5 * (O_inst[i] + O_inst[i-1])
        calc_vol = np.sum(uh) * dt_hr * 3600.0
        target_vol = A * 10000.0
        if calc_vol > 1e-6:
            uh *= target_vol / calc_vol
        return uh

    def compute_runoff(self, A, Tc, R, total_precip, tr_min, dt_min, cn, huff_pc, NQ):
        dt_hr  = dt_min / 60.0
        excess = self.effective_rainfall(total_precip, tr_min, dt_min, cn, huff_pc)
        uh     = self.clark_uh(A, Tc, R, dt_hr)
        full_conv = np.convolve(excess, uh) / 10.0
        result = np.zeros(NQ)
        n = min(len(full_conv), NQ)
        result[:n] = full_conv[:n]
        return np.maximum(0.0, result)


# =============================================================================
# 수문망 처리기
# =============================================================================

class HydroNetworkProcessor:
    def __init__(self):
        self.clark = ClarkEngine()
        self.musk  = MuskingumEngine()
        self.results  = {}
        self.warnings = []
        self.summary  = []

    def run(self, operations, dt_min, NQ, tr_min, huff_pc, baseflow=0.0):
        self.results  = {}
        self.warnings = []
        self.summary  = []
        stack    = []
        cum_area = 0.0
        dt_hr    = dt_min / 60.0

        for op in operations:
            t    = op['type']
            name = op['name']

            if t == 'BASIN':
                A  = float(op.get('A',  1.0))
                PB = float(op.get('PB', 100.0))
                CN = float(op.get('CN', 80.0))
                Tc = float(op.get('Tc', 1.0))
                R  = float(op.get('R',  1.5))
                flow = self.clark.compute_runoff(A, Tc, R, PB, tr_min, dt_min, CN, huff_pc, NQ)
                stack.append(flow.copy())
                cum_area += A
                pidx = int(np.argmax(flow))
                self.results[name] = {'flow': flow, 'type': 'BASIN', 'A': A,
                    'peak_q': float(flow[pidx]), 'peak_hr': pidx * dt_hr, 'cum_area': cum_area}
                self.summary.append({'op': '수문곡선', 'station': name,
                    'peak_q': float(flow[pidx]), 'peak_hr': pidx * dt_hr, 'cum_area': cum_area})

            elif t == 'ROUTE':
                if not stack:
                    self.warnings.append(f"[{name}] 추적 오류: 스택 비어있음"); continue
                K     = float(op.get('K',    1.0))
                X     = float(op.get('X',    0.20))
                NSTPS = int(  op.get('NSTPS', 0))
                inflow  = stack.pop()
                outflow, stable, rw, C1, C2, C3, ns = self.musk.route(inflow, K, X, dt_hr, NSTPS)
                stack.append(outflow.copy())
                for w in rw: self.warnings.append(f"[{name}] {w}")
                pidx = int(np.argmax(outflow))
                self.results[name] = {'flow': outflow, 'type': 'ROUTE',
                    'K': K, 'X': X, 'NSTPS': ns, 'stable': stable,
                    'C1': C1, 'C2': C2, 'C3': C3,
                    'peak_q': float(outflow[pidx]), 'peak_hr': pidx * dt_hr, 'cum_area': cum_area}
                self.summary.append({'op': f'머스킹엄(K={K:.2f},X={X:.2f})', 'station': name,
                    'peak_q': float(outflow[pidx]), 'peak_hr': pidx * dt_hr, 'cum_area': cum_area})

            elif t == 'COMBINE':
                N = int(op.get('N', 2))
                if len(stack) < N:
                    self.warnings.append(f"[{name}] 합류 오류: 스택 {len(stack)}개, 요청 {N}개")
                    N = len(stack)
                if N <= 0:
                    self.warnings.append(f"[{name}] 합류 오류: 합산 대상 없음"); continue
                combined = np.zeros(NQ)
                for _ in range(N):
                    h = stack.pop()
                    ln = min(len(h), NQ)
                    combined[:ln] += h[:ln]
                stack.append(combined.copy())
                pidx = int(np.argmax(combined))
                self.results[name] = {'flow': combined, 'type': 'COMBINE', 'N': N,
                    'peak_q': float(combined[pidx]), 'peak_hr': pidx * dt_hr, 'cum_area': cum_area}
                self.summary.append({'op': f'{N}개 합류', 'station': name,
                    'peak_q': float(combined[pidx]), 'peak_hr': pidx * dt_hr, 'cum_area': cum_area})

        if stack and baseflow > 0.0:
            stack[-1] += baseflow
            last_name = self.summary[-1]['station'] if self.summary else None
            if last_name and last_name in self.results:
                self.results[last_name]['flow'] = stack[-1].copy()
                pidx = int(np.argmax(stack[-1]))
                self.results[last_name]['peak_q'] = float(stack[-1][pidx])
                self.results[last_name]['peak_hr'] = pidx * dt_hr
                self.summary[-1]['peak_q'] = self.results[last_name]['peak_q']
                self.summary[-1]['peak_hr'] = self.results[last_name]['peak_hr']

        return self.results


# =============================================================================
# 네트워크 데이터 모델
# =============================================================================

class NetworkNode:
    _counter = 0

    def __init__(self, type_, name, x, y, params=None):
        NetworkNode._counter += 1
        self.id     = NetworkNode._counter
        self.type   = type_
        self.name   = name
        self.x      = float(x)
        self.y      = float(y)
        self.params = params if params is not None else self._default_params()

    def _default_params(self):
        if self.type == 'SUBBASIN':
            return {'A': 10.0, 'PB': 200.0, 'CN': 80.0, 'Tc': 1.0, 'R': 1.5}
        elif self.type == 'REACH':
            return {'K': 1.0, 'X': 0.20, 'NSTPS': 0}
        return {}

    # Half-sizes for hit-testing
    _HW = {'SUBBASIN': 58, 'REACH': 62, 'JUNCTION': 28, 'OUTLET': 30}
    _HH = {'SUBBASIN': 26, 'REACH': 20, 'JUNCTION': 28, 'OUTLET': 26}

    def hit_test(self, px, py):
        hw = self._HW.get(self.type, 40)
        hh = self._HH.get(self.type, 20)
        if self.type == 'JUNCTION':
            return (px - self.x)**2 + (py - self.y)**2 <= hw**2
        return abs(px - self.x) <= hw and abs(py - self.y) <= hh

    def port_out(self):
        if self.type == 'SUBBASIN': return (self.x + 58, self.y)
        if self.type == 'REACH':    return (self.x + 62, self.y)
        if self.type == 'JUNCTION': return (self.x, self.y + 28)
        return None  # OUTLET has no output

    def port_in(self):
        if self.type == 'SUBBASIN': return None  # no input
        if self.type == 'REACH':    return (self.x - 62, self.y)
        if self.type == 'JUNCTION': return (self.x, self.y - 28)
        if self.type == 'OUTLET':   return (self.x - 30, self.y)
        return None


class NetworkEdge:
    _counter = 0

    def __init__(self, src_id, dst_id):
        NetworkEdge._counter += 1
        self.id  = NetworkEdge._counter
        self.src = src_id
        self.dst = dst_id


# =============================================================================
# 네트워크 캔버스
# =============================================================================

PORT_R = 6  # port circle radius
HIT_R  = 12 # port hit radius


class NetworkCanvas(tk.Canvas):

    GRID = 40

    def __init__(self, master, on_select=None, **kwargs):
        super().__init__(master, bg='#12121e', highlightthickness=0, **kwargs)
        self.nodes   = {}   # id -> NetworkNode
        self.edges   = {}   # id -> NetworkEdge
        self._sel_node = None
        self._sel_edge = None
        self._mode     = 'select'
        self._drag_start = None       # (ex, ey, nx, ny)
        self._conn_src   = None       # node id being connected from
        self._mouse_xy   = (0, 0)
        self._on_select  = on_select  # callback(node or None)

        self.bind('<Button-1>',        self._click)
        self.bind('<B1-Motion>',       self._drag)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Motion>',          self._motion)
        self.bind('<Delete>',          self._delete)
        self.bind('<BackSpace>',       self._delete)
        self.bind('<Escape>',          self._escape)
        self.bind('<Double-Button-1>', self._dbl_click)
        self.bind('<Configure>',       lambda e: self.redraw())

    # ── coordinate helpers ───────────────────────────────────────────────────

    def _cx(self, ex): return self.canvasx(ex)
    def _cy(self, ey): return self.canvasy(ey)

    # ── mode ─────────────────────────────────────────────────────────────────

    def set_mode(self, mode):
        self._mode = mode
        self.configure(cursor='crosshair' if mode != 'select' else 'arrow')

    # ── drawing ──────────────────────────────────────────────────────────────

    def redraw(self):
        self.delete('all')
        self._draw_grid()
        self._draw_edges()
        self._draw_nodes()
        if self._mode == 'connect' and self._conn_src:
            self._draw_rubber_band()

    def _draw_grid(self):
        w = max(self.winfo_width(),  self.winfo_reqwidth(),  100)
        h = max(self.winfo_height(), self.winfo_reqheight(), 100)
        try:
            x0 = int(self.canvasx(0)); x1 = int(self.canvasx(w))
            y0 = int(self.canvasy(0)); y1 = int(self.canvasy(h))
        except Exception:
            x0, x1, y0, y1 = 0, w, 0, h
        g = self.GRID
        for x in range((x0 // g) * g, x1 + g, g):
            self.create_line(x, y0, x, y1, fill='#1e1e30', width=1)
        for y in range((y0 // g) * g, y1 + g, g):
            self.create_line(x0, y, x1, y, fill='#1e1e30', width=1)

    def _draw_edges(self):
        for edge in self.edges.values():
            src = self.nodes.get(edge.src)
            dst = self.nodes.get(edge.dst)
            if not src or not dst: continue
            p1 = src.port_out()
            p2 = dst.port_in()
            if not p1 or not p2: continue
            x1, y1 = p1; x2, y2 = p2
            sel = self._sel_edge and self._sel_edge.id == edge.id
            col = '#f39c12' if sel else '#3498db'
            lw  = 3 if sel else 2
            dx  = max(abs(x2 - x1) * 0.45, 40)
            self.create_line(x1, y1, x1+dx, y1, x2-dx, y2, x2, y2,
                             smooth=True, fill=col, width=lw,
                             arrow=tk.LAST, arrowshape=(10, 12, 4),
                             tags=f'edge_{edge.id}')

    def _draw_nodes(self):
        for node in self.nodes.values():
            self._draw_node(node)

    def _draw_node(self, node):
        style = NODE_STYLES.get(node.type, {})
        fill    = style.get('fill',    '#333333')
        outline = style.get('outline', '#ffffff')
        sel = self._sel_node and self._sel_node.id == node.id
        if sel:
            outline = '#f39c12'
            lw = 3
        else:
            lw = 2

        x, y = node.x, node.y
        tag = f'node_{node.id}'

        if node.type == 'SUBBASIN':
            self._round_rect(x-58, y-26, x+58, y+26, 10,
                             fill=fill, outline=outline, width=lw, tags=tag)
        elif node.type == 'REACH':
            off = 10
            pts = [x-62+off, y-20, x+62+off, y-20, x+62-off, y+20, x-62-off, y+20]
            self.create_polygon(*pts, fill=fill, outline=outline, width=lw, tags=tag)
        elif node.type == 'JUNCTION':
            self.create_oval(x-28, y-28, x+28, y+28,
                             fill=fill, outline=outline, width=lw, tags=tag)
        elif node.type == 'OUTLET':
            self.create_rectangle(x-30, y-26, x+30, y+26,
                                  fill=fill, outline=outline, width=lw, tags=tag)

        lbl = style.get('label', node.type)
        self.create_text(x, y-7, text=node.name, fill='white',
                         font=('맑은 고딕', 9, 'bold'), tags=tag)
        self.create_text(x, y+8, text=f'[{lbl}]', fill='#888888',
                         font=('맑은 고딕', 8), tags=tag)

        # Output port (orange)
        po = node.port_out()
        if po:
            px, py = po
            self.create_oval(px-PORT_R, py-PORT_R, px+PORT_R, py+PORT_R,
                             fill='#e67e22', outline='#f39c12', width=1,
                             tags=f'portout_{node.id}')

        # Input port (green)
        pi = node.port_in()
        if pi:
            px, py = pi
            n_in = sum(1 for e in self.edges.values() if e.dst == node.id)
            col_in = '#2ecc71' if n_in > 0 else '#27ae60'
            self.create_oval(px-PORT_R, py-PORT_R, px+PORT_R, py+PORT_R,
                             fill=col_in, outline='#2ecc71', width=1,
                             tags=f'portin_{node.id}')

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
               x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
               x1,y2, x1,y2-r, x1,y1+r, x1,y1, x1+r,y1]
        return self.create_polygon(*pts, smooth=True, **kw)

    def _draw_rubber_band(self):
        src = self.nodes.get(self._conn_src)
        if not src: return
        po = src.port_out()
        if not po: return
        x1, y1 = po
        x2, y2 = self._mouse_xy
        dx = max(abs(x2-x1)*0.4, 30)
        self.create_line(x1, y1, x1+dx, y1, x2-dx, y2, x2, y2,
                         smooth=True, fill='#5dade2', width=2, dash=(6,3))

    # ── events ───────────────────────────────────────────────────────────────

    def _motion(self, event):
        self._mouse_xy = (self._cx(event.x), self._cy(event.y))
        if self._mode == 'connect':
            self.redraw()

    def _click(self, event):
        x, y = self._cx(event.x), self._cy(event.y)

        # --- PLACE MODE ---
        if self._mode.startswith('place:'):
            ntype = self._mode.split(':')[1]
            self._place_node(ntype, x, y)
            self.set_mode('select')
            if self._on_select: self._on_select(self._sel_node)
            return

        # --- CONNECT MODE ---
        if self._mode == 'connect':
            # Check if clicked near an input port
            for node in reversed(list(self.nodes.values())):
                pi = node.port_in()
                if pi and abs(x-pi[0]) <= HIT_R and abs(y-pi[1]) <= HIT_R:
                    if node.id != self._conn_src:
                        self._create_edge(self._conn_src, node.id)
                    self._conn_src = None
                    self.set_mode('select')
                    self.redraw()
                    return
                if node.hit_test(x, y) and node.id != self._conn_src:
                    # Clicked body of destination node
                    self._create_edge(self._conn_src, node.id)
                    self._conn_src = None
                    self.set_mode('select')
                    self.redraw()
                    return
            self._conn_src = None
            self.set_mode('select')
            self.redraw()
            return

        # --- SELECT MODE ---
        # 1. Check output ports first (start connection)
        for node in reversed(list(self.nodes.values())):
            po = node.port_out()
            if po and abs(x-po[0]) <= HIT_R and abs(y-po[1]) <= HIT_R:
                self._conn_src = node.id
                self.set_mode('connect')
                self.redraw()
                return

        # 2. Check node bodies
        for node in reversed(list(self.nodes.values())):
            if node.hit_test(x, y):
                self._sel_node = node
                self._sel_edge = None
                self._drag_start = (x, y, node.x, node.y)
                if self._on_select: self._on_select(node)
                self.redraw()
                return

        # 3. Check edges (click near midpoint)
        for edge in self.edges.values():
            src = self.nodes.get(edge.src)
            dst = self.nodes.get(edge.dst)
            if src and dst:
                p1 = src.port_out(); p2 = dst.port_in()
                if p1 and p2:
                    mx = (p1[0]+p2[0])/2; my = (p1[1]+p2[1])/2
                    if abs(x-mx) <= 15 and abs(y-my) <= 15:
                        self._sel_edge = edge
                        self._sel_node = None
                        if self._on_select: self._on_select(None)
                        self.redraw()
                        return

        # 4. Nothing hit — deselect
        self._sel_node = None
        self._sel_edge = None
        if self._on_select: self._on_select(None)
        self.redraw()

    def _drag(self, event):
        if self._drag_start and self._sel_node:
            x, y = self._cx(event.x), self._cy(event.y)
            self._sel_node.x = self._drag_start[2] + (x - self._drag_start[0])
            self._sel_node.y = self._drag_start[3] + (y - self._drag_start[1])
            self.redraw()

    def _release(self, event):
        self._drag_start = None

    def _delete(self, event):
        if self._sel_edge:
            eid = self._sel_edge.id
            if eid in self.edges: del self.edges[eid]
            self._sel_edge = None
            self.redraw()
        elif self._sel_node:
            nid = self._sel_node.id
            for eid in [eid for eid, e in self.edges.items() if e.src == nid or e.dst == nid]:
                del self.edges[eid]
            del self.nodes[nid]
            self._sel_node = None
            if self._on_select: self._on_select(None)
            self.redraw()

    def _escape(self, event):
        self._conn_src = None
        self.set_mode('select')
        self.redraw()

    def _dbl_click(self, event):
        x, y = self._cx(event.x), self._cy(event.y)
        for node in reversed(list(self.nodes.values())):
            if node.hit_test(x, y):
                self._edit_node_dialog(node)
                return

    # ── helpers ──────────────────────────────────────────────────────────────

    def _place_node(self, ntype, x, y):
        count = sum(1 for n in self.nodes.values() if n.type == ntype) + 1
        prefix = {'SUBBASIN': 'SB', 'REACH': 'RC', 'JUNCTION': 'JN', 'OUTLET': 'OUT'}
        name = f"{prefix.get(ntype,'ND')}{count:02d}"
        node = NetworkNode(ntype, name, x, y)
        self.nodes[node.id] = node
        self._sel_node = node
        self._sel_edge = None
        self.redraw()

    def _create_edge(self, src_id, dst_id):
        # Prevent duplicate
        if any(e.src == src_id and e.dst == dst_id for e in self.edges.values()):
            return
        # Prevent self-loop
        if src_id == dst_id:
            return
        edge = NetworkEdge(src_id, dst_id)
        self.edges[edge.id] = edge
        self.redraw()

    def _edit_node_dialog(self, node):
        dlg = NodeEditDialog(self.winfo_toplevel(), node)
        self.winfo_toplevel().wait_window(dlg)
        self.redraw()
        if self._on_select: self._on_select(node)

    def add_node(self, node):
        self.nodes[node.id] = node

    def add_edge(self, edge):
        self.edges[edge.id] = edge

    def clear(self):
        self.nodes.clear()
        self.edges.clear()
        self._sel_node = None
        self._sel_edge = None
        self._conn_src = None
        self.redraw()

    # ── graph → operations (DFS) ─────────────────────────────────────────────

    def build_operations(self):
        outlets = [n for n in self.nodes.values() if n.type == 'OUTLET']
        if not outlets:
            return [], "출구(OUTLET) 노드가 없습니다."

        outlet = outlets[0]
        preds = {n.id: [] for n in self.nodes.values()}
        for e in self.edges.values():
            preds[e.dst].append(e.src)

        ops = []
        visited = set()
        errors  = []

        def dfs(nid):
            if nid in visited:
                errors.append(f"순환 연결 감지: {self.nodes[nid].name}")
                return
            visited.add(nid)
            node = self.nodes.get(nid)
            if not node: return
            up_ids = preds.get(nid, [])

            if node.type == 'SUBBASIN':
                ops.append({'type': 'BASIN', 'name': node.name, **node.params})

            elif node.type == 'REACH':
                for uid in up_ids:
                    dfs(uid)
                ops.append({'type': 'ROUTE', 'name': node.name, **node.params})

            elif node.type == 'JUNCTION':
                for uid in up_ids:
                    dfs(uid)
                N = len(up_ids)
                if N >= 2:
                    ops.append({'type': 'COMBINE', 'name': node.name, 'N': N})
                elif N == 1:
                    pass  # pass-through, no combine needed
                else:
                    errors.append(f"합류점 '{node.name}' 에 입력 없음")

            elif node.type == 'OUTLET':
                for uid in up_ids:
                    dfs(uid)
                N = len(up_ids)
                if N >= 2:
                    ops.append({'type': 'COMBINE', 'name': node.name, 'N': N})

        dfs(outlet.id)

        if errors:
            return ops, "\n".join(errors)
        return ops, None

    # ── flat ops → graph (for loading from config) ────────────────────────────

    def load_operations(self, operations):
        """Convert flat operations list → visual graph with auto-layout."""
        self.clear()
        stack_names = []  # stack of node names
        name_to_node = {}

        for op in operations:
            t = op['type']
            nm = op['name']
            params = {k: v for k, v in op.items() if k not in ('type', 'name')}

            if t == 'BASIN':
                node = NetworkNode('SUBBASIN', nm, 0, 0, params)
                self.nodes[node.id] = node
                name_to_node[nm] = node
                stack_names.append(nm)

            elif t == 'ROUTE':
                node = NetworkNode('REACH', nm, 0, 0, params)
                self.nodes[node.id] = node
                name_to_node[nm] = node
                if stack_names:
                    prev = stack_names.pop()
                    edge = NetworkEdge(name_to_node[prev].id, node.id)
                    self.edges[edge.id] = edge
                stack_names.append(nm)

            elif t == 'COMBINE':
                N = int(op.get('N', 2))
                node = NetworkNode('JUNCTION', nm, 0, 0, {})
                self.nodes[node.id] = node
                name_to_node[nm] = node
                pop_n = min(N, len(stack_names))
                for _ in range(pop_n):
                    prev = stack_names.pop()
                    edge = NetworkEdge(name_to_node[prev].id, node.id)
                    self.edges[edge.id] = edge
                stack_names.append(nm)

        # Add OUTLET for whatever is left on stack
        if stack_names:
            last_nm = stack_names[-1]
            out_node = NetworkNode('OUTLET', 'OUT', 0, 0, {})
            self.nodes[out_node.id] = out_node
            name_to_node['OUT'] = out_node
            edge = NetworkEdge(name_to_node[last_nm].id, out_node.id)
            self.edges[edge.id] = edge

        self._auto_layout()
        self.redraw()

    def _auto_layout(self):
        if not self.nodes: return
        names  = {n.id: n.name for n in self.nodes.values()}
        preds  = {n.id: [] for n in self.nodes.values()}
        succs  = {n.id: [] for n in self.nodes.values()}
        for e in self.edges.values():
            if e.src in preds and e.dst in preds:
                preds[e.dst].append(e.src)
                succs[e.src].append(e.dst)

        # BFS-based level assignment (longest path from source)
        levels = {n.id: 0 for n in self.nodes.values()}
        sources = [n.id for n in self.nodes.values() if not preds[n.id]]
        queue = list(sources)
        while queue:
            nid = queue.pop(0)
            for s in succs[nid]:
                lv = levels[nid] + 1
                if lv > levels[s]:
                    levels[s] = lv
                    queue.append(s)

        by_level = {}
        for nid, lv in levels.items():
            by_level.setdefault(lv, []).append(nid)

        STEP_X = 170; STEP_Y = 85; MARGIN_X = 120; MARGIN_Y = 80
        for lv, nids in sorted(by_level.items()):
            x = MARGIN_X + lv * STEP_X
            total_h = (len(nids) - 1) * STEP_Y
            start_y = MARGIN_Y + max(0, (500 - total_h) // 2)
            for i, nid in enumerate(nids):
                self.nodes[nid].x = float(x)
                self.nodes[nid].y = float(start_y + i * STEP_Y)


# =============================================================================
# 노드 편집 다이얼로그
# =============================================================================

class NodeEditDialog(ctk.CTkToplevel):
    def __init__(self, parent, node):
        super().__init__(parent)
        self.node = node
        self.title(f"노드 편집 — {node.name}")
        self.geometry("340x400")
        self.resizable(False, False)
        self.grab_set()
        self.focus()
        self._set_dark()
        self._entries = {}
        self._build()

    def _set_dark(self):
        try:
            hwnd = windll.user32.GetParent(self.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(1)), sizeof(c_int))
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), sizeof(c_int))
        except Exception: pass

    def _build(self):
        node = self.node
        style = NODE_STYLES.get(node.type, {})
        frame = ctk.CTkScrollableFrame(self)
        frame.pack(fill='both', expand=True, padx=12, pady=8)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text=f"[ {style.get('label', node.type)} ]",
                     font=FONT_HEADER,
                     text_color=style.get('outline', 'white')).grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0,8))

        def row(r, label, key, default):
            ctk.CTkLabel(frame, text=label, font=FONT_SMALL, anchor='w').grid(
                row=r, column=0, sticky='w', padx=4, pady=3)
            ent = ctk.CTkEntry(frame, font=FONT_SMALL, justify='right')
            ent.insert(0, str(default))
            ent.grid(row=r, column=1, sticky='ew', padx=4, pady=3)
            self._entries[key] = ent

        r = 1
        row(r, '노드 이름', 'name', node.name); r += 1

        if node.type == 'SUBBASIN':
            row(r, '유역면적 A (km²)',   'A',  node.params.get('A',  10.0));  r += 1
            row(r, '총강우량 PB (mm)',   'PB', node.params.get('PB', 200.0)); r += 1
            row(r, '유출곡선지수 CN',    'CN', node.params.get('CN', 80.0));  r += 1
            row(r, '도달시간 Tc (hr)',   'Tc', node.params.get('Tc', 1.0));   r += 1
            row(r, '저류상수 R (hr)',    'R',  node.params.get('R',  1.5));   r += 1
        elif node.type == 'REACH':
            row(r, '저류계수 K (hr)',        'K',    node.params.get('K',    1.0));  r += 1
            row(r, '가중계수 X (0~0.5)',     'X',    node.params.get('X',    0.20)); r += 1
            row(r, '세분할 NSTPS (0=자동)',  'NSTPS', node.params.get('NSTPS', 0));  r += 1
            ctk.CTkLabel(frame, text='※ 안정: 2Kx ≤ Δt ≤ 2K(1-x)\n   NSTPS=0 → 자동',
                         font=('맑은 고딕', 9), text_color='gray',
                         wraplength=260, justify='left').grid(
                row=r, column=0, columnspan=2, pady=(0,6)); r += 1
        elif node.type == 'JUNCTION':
            ctk.CTkLabel(frame, text='입력 수 N은 연결에서 자동 결정됩니다.',
                         font=FONT_SMALL, text_color='gray').grid(
                row=r, column=0, columnspan=2, pady=6)

        btn = ctk.CTkFrame(self, fg_color='transparent')
        btn.pack(fill='x', padx=12, pady=8)
        ctk.CTkButton(btn, text='확인', command=self._ok, font=FONT_BTN,
                      fg_color='#27ae60', hover_color='#2ecc71', width=120).pack(side='left', padx=4)
        ctk.CTkButton(btn, text='취소', command=self.destroy, font=FONT_BTN,
                      fg_color='#c0392b', hover_color='#e74c3c', width=120).pack(side='right', padx=4)

    def _ok(self):
        try:
            if 'name' in self._entries:
                nm = self._entries['name'].get().strip()
                if nm: self.node.name = nm
            for key, ent in self._entries.items():
                if key == 'name': continue
                v = ent.get().strip()
                if key == 'NSTPS':
                    self.node.params[key] = int(float(v))
                else:
                    self.node.params[key] = float(v)
            self.destroy()
        except ValueError as e:
            messagebox.showerror('입력 오류', str(e), parent=self)


# =============================================================================
# 팔레트 패널 (좌측)
# =============================================================================

class PalettePanel(ctk.CTkFrame):
    def __init__(self, master, on_type_select, **kwargs):
        super().__init__(master, width=170, **kwargs)
        self._callback = on_type_select
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text='수문 요소', font=FONT_HEADER,
                     text_color='#5dade2').pack(pady=(14, 6))

        for ntype, style in NODE_STYLES.items():
            self._item(ntype, style)

        ctk.CTkFrame(self, height=1, fg_color='#333344').pack(fill='x', padx=8, pady=10)
        ctk.CTkLabel(self, text='클릭 후 캔버스에\n배치하세요',
                     font=('맑은 고딕', 9), text_color='gray',
                     justify='center').pack()

    def _item(self, ntype, style):
        frame = ctk.CTkFrame(self, corner_radius=8, fg_color='#1a1a2e',
                             border_width=1, border_color='#333344')
        frame.pack(fill='x', padx=8, pady=4)

        mini = tk.Canvas(frame, width=148, height=48, bg='#1a1a2e', highlightthickness=0)
        mini.pack(pady=(6, 0))
        self._draw_mini(mini, ntype, style)

        lbl = ctk.CTkLabel(frame, text=style['label'],
                           font=FONT_SMALL, text_color=style['outline'])
        lbl.pack(pady=(2, 6))

        for w in (frame, mini, lbl):
            w.bind('<Button-1>', lambda e, t=ntype: self._callback(t))
            w.configure(cursor='hand2')

    def _draw_mini(self, c, ntype, style):
        cx, cy = 74, 24
        fill = style['fill']; out = style['outline']
        if ntype == 'SUBBASIN':
            self._round_rect_mini(c, cx-52, cy-17, cx+52, cy+17, 8, fill=fill, outline=out, width=2)
        elif ntype == 'REACH':
            off = 8
            pts = [cx-52+off, cy-14, cx+52+off, cy-14, cx+52-off, cy+14, cx-52-off, cy+14]
            c.create_polygon(*pts, fill=fill, outline=out, width=2)
        elif ntype == 'JUNCTION':
            c.create_oval(cx-18, cy-18, cx+18, cy+18, fill=fill, outline=out, width=2)
        elif ntype == 'OUTLET':
            c.create_rectangle(cx-24, cy-17, cx+24, cy+17, fill=fill, outline=out, width=2)
        c.create_text(cx, cy, text=style['label'], fill='white',
                      font=('맑은 고딕', 9, 'bold'))

    def _round_rect_mini(self, c, x1, y1, x2, y2, r, **kw):
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
               x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
               x1,y2, x1,y2-r, x1,y1+r, x1,y1, x1+r,y1]
        c.create_polygon(*pts, smooth=True, **kw)


# =============================================================================
# 속성 패널 (우측)
# =============================================================================

class PropertiesPanel(ctk.CTkScrollableFrame):
    def __init__(self, master, redraw_cb=None, **kwargs):
        super().__init__(master, width=260, **kwargs)
        self._node    = None
        self._entries = {}
        self._svars   = {}  # slider DoubleVars
        self._redraw  = redraw_cb
        self._show_empty()

    def _show_empty(self):
        for w in self.winfo_children(): w.destroy()
        ctk.CTkLabel(self, text='노드 속성', font=FONT_HEADER,
                     text_color='#5dade2').pack(anchor='w', padx=12, pady=(14,4))
        ctk.CTkLabel(self, text='노드를 선택하면\n속성이 여기에 표시됩니다.',
                     font=FONT_SMALL, text_color='gray',
                     justify='center').pack(pady=30)

    def show_node(self, node):
        self._node = node
        self._entries.clear()
        self._svars.clear()
        for w in self.winfo_children(): w.destroy()

        if node is None:
            self._show_empty()
            return

        style = NODE_STYLES.get(node.type, {})
        col   = style.get('outline', 'white')

        ctk.CTkLabel(self, text='노드 속성', font=FONT_HEADER,
                     text_color='#5dade2').pack(anchor='w', padx=12, pady=(14,2))

        badge = ctk.CTkFrame(self, fg_color=style.get('fill', '#333'), corner_radius=6)
        badge.pack(fill='x', padx=10, pady=4)
        ctk.CTkLabel(badge, text=f'● {style.get("label", node.type)}',
                     font=FONT_HEADER, text_color=col).pack(anchor='w', padx=8, pady=6)

        self._add_field('이름', 'name', node.name, is_str=True)

        if node.type == 'SUBBASIN':
            self._section('─── 유역 매개변수 ───')
            self._add_field('유역면적 A (km²)',   'A',  node.params.get('A',  10.0))
            self._add_field('총강우량 PB (mm)',   'PB', node.params.get('PB', 200.0))
            self._add_field('유출곡선지수 CN',    'CN', node.params.get('CN', 80.0))
            self._add_field('도달시간 Tc (hr)',   'Tc', node.params.get('Tc', 1.0))
            self._add_field('저류상수 R (hr)',    'R',  node.params.get('R',  1.5))

        elif node.type == 'REACH':
            self._section('─── 머스킹엄 매개변수 ───')
            self._add_field('저류계수 K (hr)', 'K', node.params.get('K', 1.0))
            self._add_slider('가중계수 X',     'X', node.params.get('X', 0.20), 0.0, 0.5)
            self._add_field('NSTPS (0=자동)',  'NSTPS', node.params.get('NSTPS', 0))
            ctk.CTkLabel(self, text='※ 안정: 2Kx ≤ Δt ≤ 2K(1-x)',
                         font=('맑은 고딕', 9), text_color='gray',
                         wraplength=220).pack(anchor='w', padx=12, pady=2)

        elif node.type == 'JUNCTION':
            ctk.CTkLabel(self, text='N 입력 수는 연결에서\n자동으로 결정됩니다.',
                         font=FONT_SMALL, text_color='gray',
                         justify='center').pack(pady=10)

        elif node.type == 'OUTLET':
            ctk.CTkLabel(self, text='출구 노드 — 최종 유출점',
                         font=FONT_SMALL, text_color='gray').pack(pady=10)

        ctk.CTkButton(self, text='적용', command=self._apply,
                      font=FONT_BTN, fg_color='#27ae60', hover_color='#2ecc71',
                      height=34).pack(fill='x', padx=10, pady=(14, 4))

    def _section(self, text):
        ctk.CTkLabel(self, text=text, font=FONT_SMALL,
                     text_color='gray').pack(fill='x', padx=12, pady=(8, 2))

    def _add_field(self, label, key, default, is_str=False):
        ctk.CTkLabel(self, text=label, font=FONT_SMALL,
                     anchor='w').pack(fill='x', padx=12, pady=(4, 0))
        ent = ctk.CTkEntry(self, font=FONT_SMALL,
                           justify='left' if is_str else 'right')
        ent.insert(0, str(default))
        ent.pack(fill='x', padx=10, pady=(0, 2))
        self._entries[key] = ent

    def _add_slider(self, label, key, default, from_, to):
        lbl = ctk.CTkLabel(self, text=f'{label}: {default:.2f}',
                           font=FONT_SMALL, anchor='w')
        lbl.pack(fill='x', padx=12, pady=(4, 0))
        var = ctk.DoubleVar(value=default)
        def on_change(v, _lbl=lbl, _label=label):
            _lbl.configure(text=f'{_label}: {float(v):.2f}')
        slider = ctk.CTkSlider(self, from_=from_, to=to, variable=var,
                               number_of_steps=50, command=on_change)
        slider.pack(fill='x', padx=10, pady=(0, 2))
        self._svars[key] = var

    def _apply(self):
        if not self._node: return
        try:
            nm = self._entries.get('name')
            if nm:
                v = nm.get().strip()
                if v: self._node.name = v
            for key, ent in self._entries.items():
                if key == 'name': continue
                v = ent.get().strip()
                self._node.params[key] = int(float(v)) if key == 'NSTPS' else float(v)
            for key, var in self._svars.items():
                self._node.params[key] = round(float(var.get()), 4)
            if self._redraw: self._redraw()
        except ValueError as e:
            messagebox.showerror('입력 오류', str(e))


# =============================================================================
# 수문망 편집기 창
# =============================================================================

class NetworkEditorWindow(ctk.CTkToplevel):

    def __init__(self, parent, on_apply):
        super().__init__(parent)
        self.title('수문망 편집기 — 하도추적')
        self.geometry('1380x720')
        self.minsize(900, 500)
        self._on_apply = on_apply
        self._set_dark()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left palette
        self._palette = PalettePanel(self, on_type_select=self._palette_clicked,
                                     corner_radius=0)
        self._palette.grid(row=0, column=0, sticky='nsew', rowspan=2)

        # Center canvas area
        center = tk.Frame(self, bg='#12121e')
        center.grid(row=0, column=1, sticky='nsew')
        center.grid_rowconfigure(0, weight=1)
        center.grid_columnconfigure(0, weight=1)

        # Scrollbars
        xsb = tk.Scrollbar(center, orient='horizontal')
        ysb = tk.Scrollbar(center, orient='vertical')
        xsb.grid(row=1, column=0, sticky='ew')
        ysb.grid(row=0, column=1, sticky='ns')

        self._canvas = NetworkCanvas(center,
                                     on_select=self._node_selected,
                                     xscrollcommand=xsb.set,
                                     yscrollcommand=ysb.set)
        self._canvas.grid(row=0, column=0, sticky='nsew')
        self._canvas.configure(scrollregion=(0, 0, 3000, 1200))
        xsb.configure(command=self._canvas.xview)
        ysb.configure(command=self._canvas.yview)

        # Mouse-wheel scroll
        self._canvas.bind('<MouseWheel>',
                          lambda e: self._canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units'))

        # Toolbar below canvas
        toolbar = ctk.CTkFrame(self, height=42, corner_radius=0, fg_color='#1a1a2e')
        toolbar.grid(row=1, column=1, sticky='ew')

        self._mode_lbl = ctk.CTkLabel(toolbar, text='모드: 선택',
                                      font=FONT_SMALL, text_color='#5dade2', width=160)
        self._mode_lbl.pack(side='left', padx=12)

        ctk.CTkLabel(toolbar,
                     text='주황 포트 클릭 → 연결  |  노드 드래그=이동  |  Delete=삭제  |  Esc=취소  |  더블클릭=편집',
                     font=('맑은 고딕', 9), text_color='gray').pack(side='left', padx=6)

        for txt, cmd, col in [
            ('예제 로드',   self._load_example,   '#5d6d7e'),
            ('초기화',      self._clear,           '#7f3b3b'),
            ('적용 & 닫기', self._apply_and_close, '#27ae60'),
        ]:
            ctk.CTkButton(toolbar, text=txt, command=cmd,
                          font=FONT_SMALL, height=30, width=100,
                          fg_color=col).pack(side='right', padx=4, pady=6)

        # Right properties
        self._props = PropertiesPanel(self,
                                      redraw_cb=self._canvas.redraw,
                                      corner_radius=0)
        self._props.grid(row=0, column=2, sticky='nsew', rowspan=2)
        self.grid_columnconfigure(2, minsize=280)

    def _set_dark(self):
        try:
            hwnd = windll.user32.GetParent(self.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(1)), sizeof(c_int))
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), sizeof(c_int))
        except Exception: pass

    def _palette_clicked(self, ntype):
        self._canvas.set_mode(f'place:{ntype}')
        label_map = {
            'SUBBASIN': '소유역 배치 중 (캔버스 클릭)',
            'REACH':    '하도구간 배치 중 (캔버스 클릭)',
            'JUNCTION': '합류점 배치 중 (캔버스 클릭)',
            'OUTLET':   '출구 배치 중 (캔버스 클릭)',
        }
        self._mode_lbl.configure(text=f'모드: {label_map.get(ntype, ntype)}')
        self._canvas.focus_set()

    def _node_selected(self, node):
        self._props.show_node(node)
        self._mode_lbl.configure(text='모드: 선택')
        self._canvas.set_mode('select')

    def _load_example(self):
        if self._canvas.nodes:
            if not messagebox.askyesno('확인', '기존 네트워크를 지우고 예제를 로드하시겠습니까?',
                                       parent=self):
                return
        self._canvas.load_operations(EXAMPLE_OPERATIONS)
        self._props.show_node(None)

    def _clear(self):
        if messagebox.askyesno('초기화', '네트워크를 모두 초기화하시겠습니까?', parent=self):
            self._canvas.clear()
            self._props.show_node(None)

    def _apply_and_close(self):
        ops, err = self._canvas.build_operations()
        if err:
            messagebox.showerror('오류', err, parent=self)
            return
        if not ops:
            messagebox.showwarning('알림', '네트워크가 비어 있습니다.', parent=self)
            return
        self._on_apply(ops)
        self.destroy()

    def load_operations(self, ops):
        """Load existing ops into visual editor."""
        self._canvas.load_operations(ops)

    def get_node_count(self):
        return len(self._canvas.nodes), len(self._canvas.edges)


# =============================================================================
# 예제 조작 (100-1440-SW00.dat 기반)
# =============================================================================

EXAMPLE_OPERATIONS = [
    {'type':'BASIN',   'name':'MG24',   'A':79.9,  'PB':279.3, 'CN':89.8, 'Tc':1.29, 'R':1.83},
    {'type':'ROUTE',   'name':'MG23R',  'K':0.63,  'X':0.20,   'NSTPS':0},
    {'type':'BASIN',   'name':'XMG23',  'A':27.5,  'PB':287.3, 'CN':92.9, 'Tc':0.90, 'R':1.05},
    {'type':'COMBINE', 'name':'MG23',   'N':2},
    {'type':'ROUTE',   'name':'MG18R',  'K':0.34,  'X':0.20,   'NSTPS':0},
    {'type':'BASIN',   'name':'XMG18',  'A':33.5,  'PB':305.2, 'CN':91.7, 'Tc':1.10, 'R':1.27},
    {'type':'COMBINE', 'name':'MG18',   'N':2},
    {'type':'BASIN',   'name':'GSC04',  'A':68.6,  'PB':307.7, 'CN':80.8, 'Tc':1.54, 'R':2.54},
    {'type':'ROUTE',   'name':'GSC00R', 'K':0.65,  'X':0.20,   'NSTPS':0},
    {'type':'BASIN',   'name':'XGSC00', 'A':77.1,  'PB':310.9, 'CN':86.9, 'Tc':1.76, 'R':2.89},
    {'type':'COMBINE', 'name':'GSC00',  'N':2},
    {'type':'BASIN',   'name':'XMG17',  'A':0.1,   'PB':309.5, 'CN':10.0, 'Tc':0.10, 'R':0.18},
    {'type':'COMBINE', 'name':'MG17',   'N':3},
    {'type':'ROUTE',   'name':'MG15R',  'K':1.53,  'X':0.20,   'NSTPS':0},
    {'type':'BASIN',   'name':'XMG15',  'A':68.5,  'PB':302.4, 'CN':85.9, 'Tc':1.87, 'R':3.06},
    {'type':'COMBINE', 'name':'MG15',   'N':2},
    {'type':'BASIN',   'name':'SYC00',  'A':152.7, 'PB':287.7, 'CN':87.8, 'Tc':2.15, 'R':3.55},
    {'type':'BASIN',   'name':'XMG14',  'A':0.1,   'PB':309.5, 'CN':10.0, 'Tc':0.10, 'R':0.18},
    {'type':'COMBINE', 'name':'MG14',   'N':3},
    {'type':'ROUTE',   'name':'MG13R',  'K':0.48,  'X':0.20,   'NSTPS':0},
    {'type':'BASIN',   'name':'XMG13',  'A':13.9,  'PB':255.2, 'CN':91.6, 'Tc':0.59, 'R':1.01},
    {'type':'COMBINE', 'name':'MG13',   'N':2},
    {'type':'BASIN',   'name':'JJC10',  'A':31.7,  'PB':310.4, 'CN':85.0, 'Tc':0.99, 'R':1.64},
    {'type':'BASIN',   'name':'SW01',   'A':26.0,  'PB':289.8, 'CN':88.9, 'Tc':0.71, 'R':1.02},
    {'type':'ROUTE',   'name':'SW00R',  'K':0.13,  'X':0.20,   'NSTPS':0},
    {'type':'BASIN',   'name':'XSW00',  'A':2.9,   'PB':314.2, 'CN':87.7, 'Tc':0.19, 'R':0.27},
    {'type':'COMBINE', 'name':'SW00',   'N':4},
]


# =============================================================================
# 메인 GUI
# =============================================================================

class FloodRoutingApp(ctk.CTk):

    def __init__(self, project_path='', input_file=''):
        super().__init__()
        self.project_path = project_path.strip() or os.getcwd()
        self.project_name = os.path.basename(self.project_path)
        self.config_file  = os.path.join(self.project_path, 'project_config.json')

        self.processor  = HydroNetworkProcessor()
        self.operations = []
        self._editor    = None   # NetworkEditorWindow reference
        self._mpl_canvas = None

        plt.rcParams['font.family']        = 'Malgun Gothic'
        plt.rcParams['axes.unicode_minus'] = False

        self.title(f'하도홍수추적 (6단계) — [{self.project_name}]')
        self.geometry('1280x800')
        self.minsize(900, 600)
        self._set_dark()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

        self._huff_var  = ctk.StringVar(value='3분위')
        self._pc_values = list(HUFF_PRESETS['3분위'])

        self._build_ui()
        self._load_config()

    def _set_dark(self):
        try:
            hwnd = windll.user32.GetParent(self.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(1)), sizeof(c_int))
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), sizeof(c_int))
            try: windll.uxtheme.SetPreferredAppMode(2)
            except AttributeError: pass
        except Exception: pass

    # ── UI 구성 ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_left()
        self._build_right()

    def _build_left(self):
        scroll = ctk.CTkScrollableFrame(self, width=320, corner_radius=0)
        scroll.grid(row=0, column=0, sticky='nsew')
        scroll.grid_columnconfigure(0, weight=1)
        self._left_scroll = scroll

        def section(text):
            ctk.CTkLabel(scroll, text=text, font=FONT_HEADER, anchor='w',
                         text_color='#5dade2').pack(fill='x', padx=12, pady=(12, 3))

        def sep():
            ctk.CTkFrame(scroll, height=1, fg_color='#444444').pack(fill='x', padx=8, pady=5)

        def field(label, key, default):
            row = ctk.CTkFrame(scroll, fg_color='transparent')
            row.pack(fill='x', padx=8, pady=2)
            ctk.CTkLabel(row, text=label, font=FONT_SMALL, width=185, anchor='w').pack(side='left')
            ent = ctk.CTkEntry(row, font=FONT_SMALL, width=100, justify='right')
            ent.insert(0, default)
            ent.pack(side='right')
            self._entries[key] = ent

        self._entries = {}

        section('[ 계산 설정 ]')
        field('계산 시간간격 Δt (분)', 'DT_MIN',   '60')
        field('강우 지속기간 TR (분)', 'TR_MIN',   '1440')
        field('계산 스텝 수 NQ',      'NQ',       '300')
        field('기저유량 (m³/s)',      'BASEFLOW', '0.0')
        sep()

        section('[ 강우 시간분포 (Huff) ]')
        hrow = ctk.CTkFrame(scroll, fg_color='transparent')
        hrow.pack(fill='x', padx=8, pady=4)
        ctk.CTkLabel(hrow, text='Huff 분위', font=FONT_SMALL, width=185, anchor='w').pack(side='left')
        huff_combo = ctk.CTkComboBox(hrow, values=list(HUFF_PRESETS.keys()),
                                     font=FONT_SMALL, width=100,
                                     variable=self._huff_var,
                                     command=self._on_huff_change)
        huff_combo.pack(side='right')
        sep()

        section('[ 수문망 ]')
        self._net_lbl = ctk.CTkLabel(scroll, text='네트워크가 없습니다.',
                                     font=FONT_SMALL, text_color='gray', anchor='w')
        self._net_lbl.pack(fill='x', padx=12, pady=4)

        ctk.CTkButton(scroll, text='수문망 편집기 열기  ✎',
                      command=self._open_editor,
                      font=FONT_BTN, height=38,
                      fg_color='#2c3e50', hover_color='#3d5166',
                      ).pack(fill='x', padx=8, pady=3)
        sep()

        section('[ 실행 ]')
        for label, cmd, color in [
            ('예제 네트워크 로드', self._load_example, '#5d6d7e'),
            ('분석 실행  ▶',      self._run,          '#27ae60'),
            ('결과 Excel 저장',   self._save_excel,   '#2980b9'),
        ]:
            ctk.CTkButton(scroll, text=label, command=cmd,
                          font=FONT_BTN, height=38,
                          fg_color=color).pack(fill='x', padx=8, pady=3)
        sep()

        section('[ 최종 출구 결과 ]')
        self._result_labels = {}
        for key, label, color in [
            ('outlet',   '최종 유출점',      '#f0f0f0'),
            ('peak_q',   '첨두유량 (m³/s)',  '#e74c3c'),
            ('peak_hr',  '첨두 발생 (hr)',   '#f39c12'),
            ('cum_area', '총 유역면적 (km²)','#2ecc71'),
        ]:
            row = ctk.CTkFrame(scroll, fg_color='transparent')
            row.pack(fill='x', padx=8, pady=2)
            ctk.CTkLabel(row, text=label+':', font=FONT_SMALL,
                         width=150, anchor='w').pack(side='left')
            lbl = ctk.CTkLabel(row, text='─', font=FONT_HEADER,
                               text_color=color, anchor='w')
            lbl.pack(side='left', padx=4)
            self._result_labels[key] = lbl
        sep()

        section('[ 실행 로그 ]')
        self._txt_log = tk.Text(scroll, height=8, font=FONT_LOG,
                                bg='#1a1a1a', fg='#cccccc',
                                insertbackground='white', wrap='word', relief='flat')
        self._txt_log.pack(fill='x', padx=8, pady=(0, 12))

    def _build_right(self):
        right = ctk.CTkFrame(self, corner_radius=0, fg_color='transparent')
        right.grid(row=0, column=1, sticky='nsew', padx=6, pady=6)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=1)

        self._graph_frame = ctk.CTkFrame(right, corner_radius=6)
        self._graph_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 4))
        ctk.CTkLabel(self._graph_frame,
                     text='분석 실행 후 수문곡선이 여기에 표시됩니다.',
                     font=FONT_BODY, text_color='gray').pack(expand=True)

        self._tbl_frame = ctk.CTkScrollableFrame(right, height=160, corner_radius=6)
        self._tbl_frame.grid(row=1, column=0, sticky='nsew')
        ctk.CTkLabel(self._tbl_frame,
                     text='분석 실행 후 RUNOFF SUMMARY가 표시됩니다.',
                     font=FONT_SMALL, text_color='gray').pack()

    # ── 편집기 ────────────────────────────────────────────────────────────────

    def _open_editor(self):
        if self._editor and self._editor.winfo_exists():
            self._editor.lift()
            return
        self._editor = NetworkEditorWindow(self, on_apply=self._on_network_applied)
        if self.operations:
            self._editor.load_operations(self.operations)

    def _on_network_applied(self, ops):
        self.operations = ops
        self._update_net_label()
        n = len(ops)
        bc = sum(1 for o in ops if o['type'] == 'BASIN')
        rc = sum(1 for o in ops if o['type'] == 'ROUTE')
        self._log(f'네트워크 적용: {n}개 조작 (소유역 {bc}개, 추적 {rc}구간)')

    def _update_net_label(self):
        n = len(self.operations)
        if n == 0:
            self._net_lbl.configure(text='네트워크가 없습니다.', text_color='gray')
        else:
            bc = sum(1 for o in self.operations if o['type'] == 'BASIN')
            rc = sum(1 for o in self.operations if o['type'] == 'ROUTE')
            self._net_lbl.configure(
                text=f'{n}개 조작 ({bc}개 소유역, {rc}개 추적구간)',
                text_color='#5dade2')

    # ── 예제 로드 ─────────────────────────────────────────────────────────────

    def _load_example(self):
        if self.operations:
            if not messagebox.askyesno('확인', '기존 조작을 지우고 예제를 로드하시겠습니까?'):
                return
        self._set_entry('DT_MIN',   '60')
        self._set_entry('TR_MIN',   '1440')
        self._set_entry('NQ',       '300')
        self._set_entry('BASEFLOW', '2.11')
        self._huff_var.set('3분위')
        self._pc_values = list(HUFF_PRESETS['3분위'])
        self.operations = copy.deepcopy(EXAMPLE_OPERATIONS)
        self._update_net_label()
        self._log('예제 네트워크 로드 완료 (100-1440-SW00.dat, 521.9 km²)')
        # Sync to editor if open
        if self._editor and self._editor.winfo_exists():
            self._editor.load_operations(self.operations)

    # ── 분석 실행 ─────────────────────────────────────────────────────────────

    def _run(self):
        # If editor is open, get latest ops from it
        if self._editor and self._editor.winfo_exists():
            ops, err = self._editor._canvas.build_operations()
            if err:
                messagebox.showerror('네트워크 오류', err)
                return
            self.operations = ops
            self._update_net_label()

        if not self.operations:
            messagebox.showwarning('알림', '수문망이 없습니다. 편집기 또는 예제 로드를 사용하세요.')
            return

        try:
            dt_min   = float(self._entries['DT_MIN'].get())
            tr_min   = float(self._entries['TR_MIN'].get())
            NQ       = int(  self._entries['NQ'].get())
            baseflow = float(self._entries['BASEFLOW'].get())
        except ValueError as e:
            messagebox.showerror('입력 오류', str(e))
            return

        self._log(f'분석 시작: Δt={dt_min}min TR={tr_min}min NQ={NQ}')

        try:
            results = self.processor.run(
                self.operations, dt_min, NQ, tr_min, self._pc_values, baseflow)
        except Exception:
            self._log(f'오류: {traceback.format_exc()}')
            messagebox.showerror('계산 오류', traceback.format_exc()[:300])
            return

        for w in self.processor.warnings:
            self._log(f'⚠ {w}')

        if self.processor.summary:
            last = self.processor.summary[-1]
            self._result_labels['outlet'].configure(text=last['station'])
            self._result_labels['peak_q'].configure(text=f"{last['peak_q']:.2f} m³/s")
            self._result_labels['peak_hr'].configure(text=f"{last['peak_hr']:.2f} hr")
            self._result_labels['cum_area'].configure(text=f"{last['cum_area']:.2f} km²")
            self._log(f"완료 | 출구={last['station']} | 첨두={last['peak_q']:.2f} m³/s @ {last['peak_hr']:.2f}hr")

        self._plot_results(results, dt_min, NQ)
        self._update_summary_table()

    def _plot_results(self, results, dt_min, NQ):
        for w in self._graph_frame.winfo_children(): w.destroy()
        dt_hr    = dt_min / 60.0
        time_hr  = np.arange(NQ) * dt_hr

        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
        fig.patch.set_facecolor('#1e1e1e')
        for ax in axes:
            ax.set_facecolor('#1e1e1e')
            ax.tick_params(colors='white')
            ax.xaxis.label.set_color('white')
            ax.yaxis.label.set_color('white')
            ax.title.set_color('white')
            for sp in ax.spines.values(): sp.set_edgecolor('#555555')

        colors_plot = plt.cm.tab10(np.linspace(0, 1, min(len(results), 10)))
        shown = 0
        for (name, rdata), col in zip(results.items(), colors_plot):
            if rdata['type'] in ('BASIN', 'COMBINE') and shown < 8:
                flow = rdata['flow']
                n    = min(len(flow), NQ)
                axes[0].plot(time_hr[:n], flow[:n], color=col, label=name, linewidth=1.2)
                shown += 1
        axes[0].set_title('지점별 수문곡선', fontproperties='Malgun Gothic')
        axes[0].set_xlabel('시간 (hr)', fontproperties='Malgun Gothic')
        axes[0].set_ylabel('유량 (m³/s)', fontproperties='Malgun Gothic')
        if shown > 0:
            axes[0].legend(fontsize=7, facecolor='#2a2a2a', labelcolor='white')
        axes[0].grid(True, color='#333333', alpha=0.7)

        if self.processor.summary:
            last_name = self.processor.summary[-1]['station']
            if last_name in results:
                flow = results[last_name]['flow']
                n    = min(len(flow), NQ)
                axes[1].fill_between(time_hr[:n], flow[:n], alpha=0.3, color='#3498db')
                axes[1].plot(time_hr[:n], flow[:n], color='#3498db', linewidth=2,
                             label=f'{last_name} 최종 유출')
                pidx = int(np.argmax(flow[:n]))
                axes[1].axvline(time_hr[pidx], color='#e74c3c', linestyle='--', alpha=0.7)
                axes[1].scatter([time_hr[pidx]], [flow[pidx]], color='#e74c3c', zorder=5, s=60)
                axes[1].annotate(
                    f"첨두 {flow[pidx]:.1f} m³/s\n@ {time_hr[pidx]:.1f}hr",
                    xy=(time_hr[pidx], flow[pidx]),
                    xytext=(10, -30), textcoords='offset points',
                    color='#e74c3c', fontsize=8,
                    arrowprops=dict(arrowstyle='->', color='#e74c3c'))
        axes[1].set_title('최종 출구 수문곡선', fontproperties='Malgun Gothic')
        axes[1].set_xlabel('시간 (hr)', fontproperties='Malgun Gothic')
        axes[1].set_ylabel('유량 (m³/s)', fontproperties='Malgun Gothic')
        axes[1].legend(fontsize=8, facecolor='#2a2a2a', labelcolor='white')
        axes[1].grid(True, color='#333333', alpha=0.7)
        fig.tight_layout(pad=2.0)

        if self._mpl_canvas:
            try: self._mpl_canvas.get_tk_widget().destroy()
            except Exception: pass
        self._mpl_canvas = FigureCanvasTkAgg(fig, master=self._graph_frame)
        self._mpl_canvas.draw()
        self._mpl_canvas.get_tk_widget().pack(fill='both', expand=True)

    def _update_summary_table(self):
        for w in self._tbl_frame.winfo_children(): w.destroy()
        headers = ['#', '조작', '지점명', '첨두유량(m³/s)', '첨두시간(hr)', '누가면적(km²)']
        col_w   = [30, 180, 90, 130, 110, 120]
        hrow    = ctk.CTkFrame(self._tbl_frame, fg_color='#2c3e50', corner_radius=0)
        hrow.pack(fill='x', padx=2)
        for h, w in zip(headers, col_w):
            ctk.CTkLabel(hrow, text=h, font=('맑은 고딕', 10, 'bold'),
                         width=w, anchor='center', text_color='white').pack(side='left', padx=1)
        for i, row in enumerate(self.processor.summary):
            bg = '#1e1e1e' if i % 2 == 0 else '#242424'
            fr = ctk.CTkFrame(self._tbl_frame, fg_color=bg, corner_radius=0)
            fr.pack(fill='x', padx=2)
            vals = [str(i+1), row['op'], row['station'],
                    f"{row['peak_q']:.2f}", f"{row['peak_hr']:.2f}", f"{row['cum_area']:.2f}"]
            for v, w in zip(vals, col_w):
                ctk.CTkLabel(fr, text=v, font=FONT_SMALL, width=w,
                             anchor='center', text_color='#cccccc').pack(side='left', padx=1)

    # ── Excel 저장 ────────────────────────────────────────────────────────────

    def _save_excel(self):
        if not self.processor.results:
            messagebox.showwarning('알림', '먼저 분석을 실행하세요.')
            return
        ts    = datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = f'{self.project_name}_F_Flood_Routing_{ts}.xlsx'
        out   = os.path.join(self.project_path, fname)
        try:
            self._write_excel(out)
            self._log(f'Excel 저장: {fname}')
            self._save_config(fname, out)
            messagebox.showinfo('저장 완료', f'저장되었습니다:\n{out}')
        except Exception:
            self._log(f'Excel 저장 오류: {traceback.format_exc()}')
            messagebox.showerror('저장 오류', traceback.format_exc()[:300])

    def _write_excel(self, path):
        wb    = Workbook()
        hfnt  = Font(bold=True, color='FFFFFF')
        hfill = PatternFill('solid', fgColor='2C3E50')
        rfill = PatternFill('solid', fgColor='1A252F')

        def hcell(ws, r, c, v):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = hfnt; cell.fill = hfill
            cell.alignment = Alignment(horizontal='center')

        ws1 = wb.active; ws1.title = 'Runoff Summary'
        for c, h in enumerate(['순번','조작','지점명','첨두유량(m³/s)',
                                '첨두시간(hr)','누가면적(km²)'], 1):
            hcell(ws1, 1, c, h)
            ws1.column_dimensions[get_column_letter(c)].width = 18

        for i, row in enumerate(self.processor.summary, 2):
            ws1.cell(row=i, column=1, value=i-1)
            ws1.cell(row=i, column=2, value=row['op'])
            ws1.cell(row=i, column=3, value=row['station'])
            ws1.cell(row=i, column=4, value=round(row['peak_q'],  3))
            ws1.cell(row=i, column=5, value=round(row['peak_hr'], 3))
            ws1.cell(row=i, column=6, value=round(row['cum_area'],3))
            if i % 2 == 0:
                for c in range(1, 7): ws1.cell(row=i, column=c).fill = rfill

        route_ops = [(nm, d) for nm, d in self.processor.results.items() if d['type'] == 'ROUTE']
        if route_ops:
            cs = 8
            for c, h in enumerate(['추적지점','K(hr)','X','NSTPS','C1','C2','C3','안정'], cs):
                hcell(ws1, 1, c, h)
                ws1.column_dimensions[get_column_letter(c)].width = 12
            for i, (nm, d) in enumerate(route_ops, 2):
                for j, v in enumerate([nm, d['K'], d['X'], d['NSTPS'],
                                        round(d['C1'],5), round(d['C2'],5), round(d['C3'],5),
                                        'OK' if d['stable'] else '경고']):
                    ws1.cell(row=i, column=cs+j, value=v)

        dt_min = float(self._entries['DT_MIN'].get())
        NQ     = int(  self._entries['NQ'].get())
        dt_hr  = dt_min / 60.0

        for name, rdata in self.processor.results.items():
            ws = wb.create_sheet(name[:30])
            hcell(ws, 1, 1, '시간(hr)'); hcell(ws, 1, 2, '유량(m³/s)')
            ws.column_dimensions['A'].width = 12; ws.column_dimensions['B'].width = 14
            flow = rdata['flow']
            n    = min(len(flow), NQ)
            for i in range(n):
                ws.cell(row=i+2, column=1, value=round(i * dt_hr, 4))
                ws.cell(row=i+2, column=2, value=round(float(flow[i]), 4))
            ws.cell(row=1, column=4, value='항목').font = hfnt
            ws.cell(row=1, column=4).fill = hfill
            ws.cell(row=1, column=5, value='값').font  = hfnt
            ws.cell(row=1, column=5).fill = hfill
            ws.column_dimensions['D'].width = 16
            ws.column_dimensions['E'].width = 14
            params = [('유형', rdata['type']),
                      ('첨두유량(m³/s)', round(rdata['peak_q'], 3)),
                      ('첨두시간(hr)',   round(rdata['peak_hr'],3))]
            if rdata['type'] == 'BASIN':
                params += [('A(km²)', rdata['A'])]
            elif rdata['type'] == 'ROUTE':
                params += [('K(hr)', rdata['K']), ('X', rdata['X']),
                           ('NSTPS', rdata['NSTPS']),
                           ('C1', round(rdata['C1'],5)), ('C2', round(rdata['C2'],5)),
                           ('C3', round(rdata['C3'],5)),
                           ('안정', 'OK' if rdata['stable'] else '경고')]
            for pi, (lbl, val) in enumerate(params, 2):
                ws.cell(row=pi, column=4, value=lbl)
                ws.cell(row=pi, column=5, value=val)

        wb.save(path)

    # ── Config I/O ────────────────────────────────────────────────────────────

    def _load_config(self):
        try:
            with open(self.config_file, encoding='utf-8') as f:
                cfg = json.load(f)
            s6 = cfg.get('step6', {})
            for key in ('DT_MIN', 'TR_MIN', 'NQ', 'BASEFLOW'):
                if key in s6: self._set_entry(key, str(s6[key]))
            if 'huff' in s6 and s6['huff'] in HUFF_PRESETS:
                self._huff_var.set(s6['huff'])
                self._pc_values = list(HUFF_PRESETS[s6['huff']])
            if 'operations' in s6 and isinstance(s6['operations'], list):
                self.operations = s6['operations']
                self._update_net_label()
        except Exception:
            pass

    def _save_config(self, fname='', out_path=''):
        try:
            cfg = {}
            try:
                with open(self.config_file, encoding='utf-8') as f:
                    cfg = json.load(f)
            except Exception: pass

            s6 = {}
            for key in ('DT_MIN', 'TR_MIN', 'NQ', 'BASEFLOW'):
                try: s6[key] = float(self._entries[key].get())
                except Exception: pass
            s6['huff']       = self._huff_var.get()
            s6['operations'] = copy.deepcopy(self.operations)

            if self.processor.summary:
                last = self.processor.summary[-1]
                s6['outlet']   = last['station']
                s6['peak_q']   = round(last['peak_q'],  3)
                s6['peak_hr']  = round(last['peak_hr'], 3)
                s6['cum_area'] = round(last['cum_area'],3)

            if fname:
                cfg['step6_flood_routing'] = {
                    'status':      'completed',
                    'output_file': fname,
                    'full_path':   out_path,
                    'outlet':      s6.get('outlet', ''),
                    'peak_q':      s6.get('peak_q',  0),
                    'peak_hr':     s6.get('peak_hr', 0),
                    'cum_area':    s6.get('cum_area',0),
                    'timestamp':   datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                }
            cfg['step6'] = s6
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception: pass

    # ── 헬퍼 ──────────────────────────────────────────────────────────────────

    def _set_entry(self, key, val):
        w = self._entries.get(key)
        if w is None: return
        if isinstance(w, ctk.CTkComboBox):
            w.set(val)
        else:
            w.delete(0, 'end'); w.insert(0, val)

    def _on_huff_change(self, choice):
        if choice in HUFF_PRESETS:
            self._pc_values = list(HUFF_PRESETS[choice])

    def _log(self, msg):
        self._txt_log.insert('end', f'[{datetime.now().strftime("%H:%M:%S")}] {msg}\n')
        self._txt_log.see('end')

    def _on_close(self):
        self._save_config()
        self.destroy()


# =============================================================================
# 진입점
# =============================================================================

if __name__ == '__main__':
    project_path = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    input_file   = sys.argv[2] if len(sys.argv) > 2 else ''
    app = FloodRoutingApp(project_path, input_file)
    app.mainloop()
