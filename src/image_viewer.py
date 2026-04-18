"""
image_viewer.py - 抓图查看弹窗模块
使用 matplotlib 显示图像，原生支持 16位图像，无需转换。
"""
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image
import os
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt


class ImageViewer:
    """抓图查看弹窗"""

    # 图片类型显示名映射
    TYPE_NAMES = {
        'dark2': 'Dark2（暗场2）',
        'dark':  'Dark（暗场）',
        'mid':   'Mid（中灰）',
        'testpattern': 'TestPattern（测试图案）',
    }

    def __init__(self, root, get_image_scan_result_fn, get_df_fn):
        self.root = root
        self.get_scan = get_image_scan_result_fn
        self.get_df = get_df_fn
        self._win = None
        self._current_paths = []
        self._current_ts = None
        self._current_idx = 0
        self._fullscreen_win = None
        self._grid_frame = None
        self._info_label = None
        self._canvas_list = []  # 防止 GC

    # ---- 对外 API ----

    def show_for_timestamp(self, timestamp, readpoint=None, fuse_id=None):
        if not timestamp:
            messagebox.showinfo("提示", "没有找到对应的时间戳信息")
            return

        scan_result = self.get_scan()
        if scan_result is None:
            messagebox.showwarning("提示", "请先配置抓图根目录")
            return

        from src.image_scanner import find_images_for_timestamp
        paths = find_images_for_timestamp(scan_result, timestamp, readpoint)

        if not paths:
            ts_display = self._format_ts(timestamp)
            messagebox.showinfo("未找到图片",
                f"时间戳 {ts_display} 对应的抓图文件不存在\n"
                f"（已扫描 {scan_result.get('stats', {}).get('total_images', 0)} 张图片）")
            return

        self._current_paths = paths
        self._current_ts = timestamp
        self._current_idx = 0

        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._rebuild_grid()
            self._update_title(fuse_id)
        else:
            self._build_window(fuse_id)

    def show_for_fuse(self, fuse_id, readpoint=None):
        df = self.get_df()
        if df is None or df.empty:
            messagebox.showwarning("提示", "没有加载数据")
            return

        from src.image_scanner import find_images_for_fuse
        scan_result = self.get_scan() or {}
        ts, paths = find_images_for_fuse(df, scan_result, fuse_id, readpoint)

        if not paths:
            if ts:
                messagebox.showinfo("未找到图片",
                    f"FuseID={fuse_id}（时间 {self._format_ts(ts)}）\n对应的抓图文件不存在")
            else:
                messagebox.showinfo("未找到图片",
                    f"FuseID={fuse_id} 在数据中未找到时间戳")
            return

        self._current_paths = paths
        self._current_ts = ts
        self._current_idx = 0

        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._rebuild_grid()
            self._update_title(fuse_id)
        else:
            self._build_window(fuse_id)

    # ---- 窗口构建 ----

    def _build_window(self, fuse_id=None):
        win = tk.Toplevel(self.root)
        win.title("抓图查看")
        win.geometry("1200x800")
        win.configure(bg='#1a1a2e')

        self._win = win
        win.protocol("WM_DELETE_WINDOW", self._close)

        self._build_content(win, fuse_id)

    def _build_content(self, win, fuse_id=None):
        # 顶部标题栏
        header = tk.Frame(win, bg='#16213e', height=48)
        header.pack(fill='x', side='top')
        header.pack_propagate(False)

        self._title_label = tk.Label(header, font=('Microsoft YaHei', 11, 'bold'),
                                     bg='#16213e', fg='#e0e0e0', anchor='w')
        self._title_label.pack(side='left', padx=12, pady=8, fill='x', expand=True)
        self._update_title(fuse_id)

        self._count_label = tk.Label(header, font=('Microsoft YaHei', 9),
                                     bg='#16213e', fg='#888')
        self._count_label.pack(side='right', padx=12, pady=8)
        self._count_label.config(text=f"共 {len(self._current_paths)} 张")

        # 工具栏
        toolbar = tk.Frame(win, bg='#1e2a3a', height=36)
        toolbar.pack(fill='x')
        toolbar.pack_propagate(False)

        btn_cfg = {
            'bg': '#2d3a4f', 'fg': '#e0e0e0',
            'relief': 'flat', 'cursor': 'hand1',
            'font': ('Microsoft YaHei', 9),
            'activebackground': '#3d4a5f', 'activeforeground': '#ffffff', 'bd': 0
        }

        def btn(text, cmd):
            b = tk.Button(toolbar, text=text, command=cmd, **btn_cfg)
            b.pack(side='left', padx=4, pady=4)
            return b

        btn("◀ 上一张", self._prev_img)
        btn("下一张 ▶", self._next_img)
        btn("🔍 全屏", self._show_current_fullscreen)
        btn("📁 打开目录", self._open_folder)
        btn("✕ 关闭", self._close)

        # 图片显示区域
        self._grid_frame = tk.Frame(win, bg='#1a1a2e')
        self._grid_frame.pack(fill='both', expand=True, padx=8, pady=8)

        # 底部状态栏
        status = tk.Frame(win, bg='#16213e', height=28)
        status.pack(fill='x', side='bottom')
        status.pack_propagate(False)

        self._info_label = tk.Label(status, font=('Consolas', 8),
            bg='#16213e', fg='#888', anchor='w', padx=10)
        self._info_label.pack(fill='x', pady=4)
        self._info_label.config(text=self._get_current_img_info())

        self._rebuild_grid()

    def _update_title(self, fuse_id=None):
        ts_str = self._format_ts(self._current_ts) if self._current_ts else ''
        parts = []
        if ts_str:
            parts.append(f"时间: {ts_str}")
        if fuse_id:
            parts.append(f"FuseID: {fuse_id}")
        self._title_label.config(text="  |  ".join(parts) if parts else "抓图查看")

    def _rebuild_grid(self):
        if not self._grid_frame:
            return

        for w in list(self._grid_frame.winfo_children()):
            w.destroy()
        self._canvas_list.clear()

        n = len(self._current_paths)
        if n == 0:
            tk.Label(self._grid_frame, text="无图片", bg='#1a1a2e',
                    fg='#666', font=('Microsoft YaHei', 14)).pack(pady=40)
            return

        # 行列布局
        if n == 1:
            cols, rows = 1, 1
        elif n == 2:
            cols, rows = 2, 1
        elif n <= 4:
            cols, rows = 2, 2
        else:
            cols = min(4, n)
            rows = (n + cols - 1) // cols

        for r in range(rows):
            self._grid_frame.rowconfigure(r, weight=1)
        for c in range(cols):
            self._grid_frame.columnconfigure(c, weight=1)

        for k, path in enumerate(self._current_paths):
            r, c = divmod(k, cols)
            self._add_cell(path, r, c)

    def _add_cell(self, path, row, col):
        """添加单个图片格子"""
        cell = tk.Frame(self._grid_frame, bg='#252540')
        cell.grid(row=row, column=col, sticky='nsew', padx=4, pady=4)

        img_type = self._get_img_type(os.path.basename(path))
        type_name = self.TYPE_NAMES.get(img_type, '图片')

        # 类型标题栏
        title_bar = tk.Frame(cell, bg='#2a2a45', height=26)
        title_bar.pack(fill='x', side='top')
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text=type_name, font=('Microsoft YaHei', 8, 'bold'),
                bg='#2a2a45', fg='#7eb8da').pack(side='left', padx=6, pady=2)

        # 图片区域
        img_area = tk.Frame(cell, bg='#1a1a2e')
        img_area.pack(fill='both', expand=True)

        try:
            # matplotlib 原生显示，支持 16位图像
            fig = Figure(figsize=(4, 3), dpi=80)
            fig.patch.set_facecolor('#1a1a2e')
            ax = fig.add_axes([0, 0, 1, 1])  # 占满整个 figure
            ax.axis('off')

            img = Image.open(path)
            orig_mode = img.mode

            # 16位图像：使用全范围显示（不做任何处理）
            # vmin=0, vmax=65535 对应 16位的完整范围
            if orig_mode in ('I;16', 'I;16L', 'I;16B'):
                import numpy as np
                arr = np.array(img)
                vmin, vmax = 0, 65535
                ax.imshow(img, cmap='gray', vmin=vmin, vmax=vmax)
            else:
                ax.imshow(img, cmap='gray')

            ax.set_title(os.path.basename(path), fontsize=7,
                        color='#888', pad=2)

            canvas = FigureCanvasTkAgg(fig, master=img_area)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
            self._canvas_list.append(canvas)

            # 绑定双击全屏
            canvas.mpl_connect('button_press_event',
                lambda event, p=path: self._on_click(event, p))

        except Exception as ex:
            tk.Label(img_area, text=f"加载失败\n{ex}", bg='#1a1a2e',
                    fg='#e74c3c', font=('Microsoft YaHei', 8)).pack(pady=20)

    def _on_click(self, event, path):
        """matplotlib 单击事件 - 直接全屏显示"""
        self._show_fullscreen(path)

    # ---- 导航 ----

    def _prev_img(self):
        n = len(self._current_paths)
        if n <= 1:
            return
        self._current_idx = (self._current_idx - 1) % n
        self._nav_to_idx()

    def _next_img(self):
        n = len(self._current_paths)
        if n <= 1:
            return
        self._current_idx = (self._current_idx + 1) % n
        self._nav_to_idx()

    def _nav_to_idx(self):
        if not self._current_paths:
            return

        for w in list(self._grid_frame.winfo_children()):
            w.destroy()
        self._canvas_list.clear()

        path = self._current_paths[self._current_idx]
        self._add_cell(path, 0, 0)

        self._grid_frame.rowconfigure(0, weight=1)
        self._grid_frame.columnconfigure(0, weight=1)

        if self._info_label:
            self._info_label.config(text=self._get_current_img_info())

    def _show_current_fullscreen(self):
        if not self._current_paths:
            return
        self._show_fullscreen(self._current_paths[self._current_idx])

    def _show_fullscreen(self, path):
        if self._fullscreen_win and self._fullscreen_win.winfo_exists():
            self._fullscreen_win.destroy()

        top = tk.Toplevel(self.root)
        top.attributes('-fullscreen', True)
        top.configure(bg='black')
        self._fullscreen_win = top

        try:
            img = Image.open(path)

            fig = Figure(figsize=(12, 8), dpi=100)
            fig.patch.set_facecolor('black')
            ax = fig.add_axes([0, 0, 1, 1])
            ax.axis('off')

            # 16位图像：使用全范围显示（不做任何处理）
            if img.mode in ('I;16', 'I;16L', 'I;16B'):
                ax.imshow(img, cmap='gray', vmin=0, vmax=65535)
            else:
                ax.imshow(img, cmap='gray')

            ax.set_title(os.path.basename(path), fontsize=10,
                        color='#888', pad=5)

            canvas = FigureCanvasTkAgg(fig, master=top)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)

            # 底部信息条
            bar = tk.Frame(top, bg='#111', height=30)
            bar.pack(fill='x', side='bottom')
            bar.pack_propagate(False)
            tk.Label(bar, text=os.path.basename(path), font=('Consolas', 9),
                    bg='#111', fg='#888').pack(side='left', padx=12, pady=4)
            tk.Label(bar, text="双击 / ESC 关闭", font=('Microsoft YaHei', 8),
                    bg='#111', fg='#555').pack(side='right', padx=12, pady=4)

        except Exception as ex:
            tk.Label(top, text=f"加载失败: {ex}", bg='black', fg='white',
                    font=('Microsoft YaHei', 14)).pack()

        def close(event=None):
            self._fullscreen_win = None
            top.destroy()
        top.bind('<Escape>', close)
        # 右上角关闭按钮
        close_btn = tk.Button(top, text='✕ 关闭', command=close,
                             bg='#333', fg='white', relief='flat',
                             cursor='hand1', font=('Microsoft YaHei', 9),
                             padx=12, pady=4)
        close_btn.place(relx=1.0, rely=0.0, anchor='ne', x=-10, y=10)

    def _open_folder(self):
        if not self._current_paths:
            return
        folder = os.path.dirname(self._current_paths[self._current_idx])
        if os.path.isdir(folder):
            os.startfile(folder)

    def _close(self):
        self._fullscreen_win = None
        self._canvas_list.clear()
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None

    # ---- 辅助 ----

    @staticmethod
    def _format_ts(ts):
        if not ts or len(str(ts)) < 14:
            return str(ts)
        s = str(ts)
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}:{s[12:14]}"

    @staticmethod
    def _get_img_type(basename):
        n = basename.lower()
        if 'dark2' in n:   return 'dark2'
        if 'dark' in n:    return 'dark'
        if 'mid' in n:     return 'mid'
        if 'testpattern' in n: return 'testpattern'
        return None

    def _get_current_img_info(self):
        n = len(self._current_paths)
        if n == 0:
            return ""
        path = self._current_paths[self._current_idx]
        info = f"[{self._current_idx + 1}/{n}] {os.path.basename(path)}"
        t = self._get_img_type(os.path.basename(path))
        if t:
            info += f"  |  {self.TYPE_NAMES.get(t, t)}"
        return info
