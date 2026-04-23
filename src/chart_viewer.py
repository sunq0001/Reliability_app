"""
图表查看器模块 - 封装图表弹窗的所有状态和逻辑
"""
import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import os
import numpy as np
import pandas as pd
import re

from src.chart_builder import (
    build_chart_for_item,
    build_fuse_cache,
    make_hover_callbacks,
    reset_ax_view,
)
from src.utils import sanitize_filename


class ChartViewer:
    """图表弹窗管理类（无状态，数据通过回调获取）"""

    def __init__(self, root, callbacks):
        """
        callbacks: dict，传入必要的回调函数
            - get_chart_items(): 返回测试项名称列表
            - get_current_df(): 返回当前 DataFrame
            - get_chart_cache(): 返回 ThreadSafeChartCache 实例
            - build_chart(test_item): 构建单个图表
            - log(msg): 日志回调
        """
        self.root = root
        self._cb = callbacks

        self._win = None          # 弹窗实例
        self._area = None        # 图表区域 Frame
        self._canvas = None      # 当前激活的 canvas
        self._idx = 0            # 当前索引
        self._split_var = tk.StringVar(value='1')
        self._idx_var = tk.StringVar(value="")
        self._last_items_hash = None  # 记住上一次显示的items列表，用于检测变化

        # 底部悬停信息面板引用
        self._info_panel = None  # 已废弃，保留避免引用错误
        self._info_label = None
        self._linked_label = None
        self._info_fuse_label = None   # FuseID 标签
        self._info_ts_label = None     # 时间戳标签

        # 当前 hover 的芯片信息（供"查看抓图"按钮使用）
        self._last_fuse_id = None
        self._last_readpoint = None
        self._last_timestamp = None    # hover 时间戳
        self._last_test_value = None  # hover 值
        self._last_test_item = None   # 当前图表测试项名称

        # 点击 tooltip 窗口引用
        self._tooltip_win = None
        # 数据点详情弹窗引用
        self._data_point_win = None
        # 联动信息缓存
        self._linked_info = {}
        # 右键菜单信息（悬停时记录，用于右键菜单）
        self._right_click_info = None
        # 右键菜单引用
        self._context_menu = None
        
        # 框选相关状态
        self._selected_fuse_ids = []  # 当前选中的FuseID列表
        self._selection_test_item = None  # 框选发生的图表名称
        self._chart_items = []  # 所有图表项名称（用于Tab）
        self._expanded_fuse_ids = set()  # 当前展开的FuseID集合

        # ---- 对外暴露的 API ----

    def open(self):
        """打开图表弹窗（若已存在则聚焦刷新）"""
        items = self._cb['get_chart_items']()
        if not items:
            messagebox.showwarning("提示", "先生成图表后再查看")
            return

        # 计算当前items的哈希值，用于检测是否发生变化
        import hashlib
        items_str = '|'.join(sorted(items))
        items_hash = hashlib.md5(items_str.encode()).hexdigest()[:8]

        # 如果窗口已存在且items未变化，只提升窗口
        if self._win and self._win.winfo_exists() and items_hash == self._last_items_hash:
            self._win.lift()
            self.show_at(self._idx)
            return

        # items已变化或窗口不存在，关闭旧窗口并重建
        self.close()
        self._last_items_hash = items_hash
        self._build_window()
        self.show_at(0)

    def close(self):
        """关闭弹窗"""
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None

    def show_at(self, idx):
        """在弹窗中显示从 idx 开始的 n 张图表"""
        items = self._cb['get_chart_items']()
        if not items or idx < 0 or idx >= len(items) or not self._win:
            return

        self._idx = idx
        n = int(self._split_var.get())

        # 清除旧内容
        for w in list(self._area.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass

        self._canvas = None
        shared_state = {'fuse_id': None, 'timestamp': None, 'test_value': None, 'readpoint': None, 'canvases': []}

        if n == 1:
            self._show_single(items[idx], shared_state)
        else:
            self._show_grid(items[idx: idx + n], shared_state)

        self._update_nav_buttons()
        self._win.lift()

    def prev(self):
        n = int(self._split_var.get())
        self.show_at(max(0, self._idx - n))

    def next(self):
        items = self._cb['get_chart_items']()
        n = int(self._split_var.get())
        new_idx = self._idx + n
        if new_idx < len(items):
            self.show_at(new_idx)

    def export_current(self):
        """导出当前显示的图表"""
        items = self._cb['get_chart_items']()
        if not items:
            return
        test_item = items[self._idx]
        fig, _ = self._get_chart(test_item)
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reliability_plots")
        os.makedirs(output_dir, exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime("%H%M%S")
        filename = f"{sanitize_filename(test_item)}_CDF_{ts}.png"
        fig.savefig(os.path.join(output_dir, filename), dpi=150, bbox_inches='tight')
        self._cb['log'](f"已导出: {filename}")

    def export_all(self):
        """导出所有图表"""
        items = self._cb['get_chart_items']()
        if not items:
            return
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reliability_plots")
        os.makedirs(output_dir, exist_ok=True)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(output_dir, f"CDF_all_{ts}")
        os.makedirs(base, exist_ok=True)
        for i, item in enumerate(items):
            fig, _ = self._get_chart(item)
            fig.savefig(os.path.join(base, f"{i+1:04d}_{sanitize_filename(item)}.png"),
                        dpi=150, bbox_inches='tight')
        self._cb['log'](f"已导出全部 {len(items)} 张图表到: {base}")

    # ---- 内部方法 ----

    def _build_window(self):
        win = tk.Toplevel(self.root)
        win.title("累积分布图查看器")
        win.geometry("1400x850")

        self._win = win

        # 控制栏
        ctrl = tk.Frame(win, bg='#f3f4f6', height=40)
        ctrl.pack(fill='x', side='top')
        ctrl.pack_propagate(False)

        tk.Label(ctrl, textvariable=self._idx_var,
                 bg='#f3f4f6', fg='#374151',
                 font=('Microsoft YaHei', 9)).pack(side='left', padx=8)

        # 分屏选择
        sf = tk.Frame(ctrl, bg='#f3f4f6')
        sf.pack(side='left', padx=(4, 8))
        tk.Label(sf, text='分屏:', bg='#f3f4f6', fg='#374151',
                 font=('Microsoft YaHei', 8)).pack(side='left')
        for num in ('1', '2', '4', '8'):
            tk.Radiobutton(sf, text=num, variable=self._split_var, value=num,
                           bg='#f3f4f6', fg='#374151', activebackground='#e5e7eb',
                           font=('Microsoft YaHei', 8),
                           command=self._on_split_change).pack(side='left', padx=1)

        # 提示：鼠标滚轮缩放
        tk.Label(ctrl, text='鼠标滚轮缩放', bg='#f3f4f6', fg='#9ca3af',
                 font=('Microsoft YaHei', 8)).pack(side='left', padx=(4, 0))

        # 查看数据点按钮（始终可点，点击切换详情面板）
        self._detail_btn = tk.Button(
            ctrl, text='🔍 查看数据点',
            command=self._show_data_point_dialog,
            bg='#6366f1', fg='white',
            relief='flat', cursor='hand1',
            font=('Microsoft YaHei', 8, 'bold'),
            activebackground='#4f46e5', activeforeground='white',
            padx=10, pady=2
        )
        self._detail_btn.pack(side='left', padx=6)

        nav = tk.Frame(ctrl, bg='#f3f4f6')
        nav.pack(side='right')
        btn_cfg = {'bg': '#ffffff', 'fg': '#374151', 'relief': 'flat',
                   'cursor': 'hand1', 'font': ('Microsoft YaHei', 8)}
        self._btn_prev = tk.Button(nav, text='◀ 上一页', width=7, command=self.prev, **btn_cfg)
        self._btn_prev.pack(side='left', padx=2)
        self._btn_next = tk.Button(nav, text='下一页 ▶', width=7, command=self.next, **btn_cfg)
        self._btn_next.pack(side='left', padx=2)
        tk.Button(nav, text='导出当前', width=7,
                 bg='#3b82f6', fg='white', relief='flat',
                 cursor='hand1', font=('Microsoft YaHei', 8, 'bold'),
                 command=self.export_current).pack(side='left', padx=2)
        tk.Button(nav, text='导出全部', width=7,
                 bg='#10b981', fg='white', relief='flat',
                 cursor='hand1', font=('Microsoft YaHei', 8, 'bold'),
                 command=self.export_all).pack(side='left', padx=2)

        # 图表区域
        area = tk.Frame(win, bg='#ffffff')
        area.pack(fill='both', expand=True, padx=4, pady=4)
        self._area = area

        win.protocol("WM_DELETE_WINDOW", self.close)

    def _on_split_change(self):
        self.show_at(self._idx)

    def _update_nav_buttons(self):
        items = self._cb['get_chart_items']()
        n = int(self._split_var.get())
        total = len(items)
        start = self._idx + 1
        end = min(self._idx + n, total)
        self._idx_var.set(f"{start}-{end} / {total}")
        self._btn_prev.config(state='normal' if self._idx > 0 else 'disabled')
        self._btn_next.config(state='normal' if end < total else 'disabled')

    def _get_chart(self, test_item):
        """获取图表：优先缓存，未命中则同步生成"""
        cache = self._cb['get_chart_cache']()
        if cache:
            fig = cache.get(test_item)
            if fig is not None:
                ax = fig.axes[0] if fig.axes else None
                return fig, ax
        fig, ax = self._cb['build_chart'](test_item)
        return fig, ax

    def _is_cached(self, test_item):
        cache = self._cb['get_chart_cache']()
        return cache is not None and cache.get(test_item) is not None

    def _make_loading_fig(self, test_item):
        fig = Figure(figsize=(8, 5), dpi=100)
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, f'正在加载 {test_item}\n请稍候...',
                ha='center', va='center', fontsize=12, color='#9ca3af',
                transform=ax.transAxes)
        ax.set_axis_off()
        fig.tight_layout()
        return fig, ax

    def _show_single(self, test_item, shared_state):
        """显示单图"""
        # 缓存命中则直接显示真实图，否则先显示加载占位
        if not self._is_cached(test_item):
            fig_load, ax_load = self._make_loading_fig(test_item)
            reset_ax_view(ax_load)
            fc_load = FigureCanvasTkAgg(fig_load, master=self._area)
            fc_load.get_tk_widget().pack(fill='both', expand=True)
            self._area.update_idletasks()

        fig, ax = self._get_chart(test_item)
        reset_ax_view(ax)

        for w in list(self._area.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass

        fc = FigureCanvasTkAgg(fig, master=self._area)
        tk_widget = fc.get_tk_widget()
        tk_widget.pack(fill='both', expand=True)
        # 默认箭头，hover 到数据点时自动变为手型（在 _bind_hover 中管理）
        fc.mpl_connect('key_press_event', self._on_key)
        self._canvas = fc
        self._last_test_item = test_item
        self._bind_hover(ax, fc, test_item, shared_state)
        self._bind_click(ax, fc, test_item)   # 点击 tooltip
        self._bind_context_menu(ax, fc)        # 右键菜单
        self._bind_wheel_zoom(ax, fc)          # 鼠标滚轮缩放

    def _show_grid(self, items_to_show, shared_state):
        """显示多图网格"""
        n = len(items_to_show)
        cols = 2 if n <= 4 else 4
        rows = (n + cols - 1) // cols

        grid = tk.Frame(self._area, bg='#ffffff')
        grid.pack(fill='both', expand=True)
        grid.pack_propagate(False)

        for r in range(rows):
            grid.rowconfigure(r, weight=1, minsize=0)
        for c in range(cols):
            grid.columnconfigure(c, weight=1, minsize=0)

        # 一次性渲染（命中的直接画真实图，未命中的画加载图）
        cells = []
        for k, test_item in enumerate(items_to_show):
            r, c = divmod(k, cols)
            cell = tk.Frame(grid, bg='#ffffff', bd=1, relief='groove')
            cell.grid(row=r, column=c, sticky='nsew', padx=1, pady=1)
            cell.grid_propagate(False)
            cell.rowconfigure(0, weight=1)
            cell.columnconfigure(0, weight=1)

            fig, ax = self._get_chart(test_item)
            if fig is None:
                fig, ax = self._make_loading_fig(test_item)

            fc = FigureCanvasTkAgg(fig, master=cell)
            tk_widget = fc.get_tk_widget()
            tk_widget.grid(row=0, column=0, sticky='nsew')
            cells.append((cell, ax, fc, test_item))
            self._bind_hover(ax, fc, test_item, shared_state)
            self._bind_click(ax, fc, test_item)   # 点击 tooltip
            self._bind_context_menu(ax, fc)        # 右键菜单
            self._bind_wheel_zoom(ax, fc)          # 鼠标滚轮缩放

            reset_ax_view(ax)
            fc.draw()
            self._canvas = fc  # 最后一个作为全局 canvas
            self._last_test_item = test_item

        self._area.update_idletasks()

    def _bind_hover(self, ax, canvas, test_item, shared_state):
        """绑定悬停交互（使用模块级 make_hover_callbacks）"""
        df = self._cb['get_current_df']()
        fuse_cache = build_fuse_cache(df)

        # 无 info panel，用空操作替代
        def get_info_text(text, is_active=False):
            pass  # 已移除底部信息栏

        def set_linked_text(text):
            pass  # 已移除底部信息栏

        # ---- 光标管理：默认箭头，hover到数据点变手型 ----
        def _set_cursor(is_over_point):
            try:
                tk_widget = canvas.get_tk_widget()
                # 尝试不同的光标名称以确保兼容性
                cursor_name = 'hand2' if is_over_point else 'arrow'
                tk_widget.configure(cursor=cursor_name)

            except Exception as e:

                try:
                    # 备用光标
                    tk_widget.configure(cursor='hand1' if is_over_point else 'arrow')
                except Exception:
                    pass

        canvas._set_cursor = _set_cursor
        canvas._shared_state = shared_state  # 确保每个 canvas 都有 shared_state

        result = make_hover_callbacks(
            ax, canvas, test_item, df, fuse_cache,
            get_info_text, set_linked_text, set_cursor_fn=_set_cursor
        )

        # 保存interactor引用
        interactor = result.get('interactor')
        
        # 注册进 shared_state 供联动
        if shared_state is not None and isinstance(result, dict):
            shared_state['canvases'].append(
                (ax, canvas, test_item, result.get('highlight_linked'), interactor)
            )
        
        # 设置框选回调
        if interactor:
            def _on_selection(selected_points, test_item_name):
                # 收集所有选中FuseID
                selected_fuse_ids = list(set(p.fuse_id for p in selected_points if p.fuse_id != 'N/A'))
                # 更新选中状态
                self._selected_fuse_ids = selected_fuse_ids
                self._selection_test_item = test_item_name
                # 更新详情面板
                self._update_selection_panel()
            
            interactor.on_selection_callback = _on_selection

        # 保存最后一次 hover 的芯片信息（供"查看抓图"按钮使用）
        def _track_fuse():
            ss = getattr(canvas, '_shared_state', {})
            self._last_fuse_id     = ss.get('fuse_id')
            self._last_readpoint  = ss.get('readpoint')
            self._last_timestamp  = ss.get('timestamp')
            self._last_test_value = ss.get('test_value')
            self._last_test_item  = test_item  # 保存当前测试项
            # 实时更新详情面板
            self._update_dialog_info()
            # hover 到数据点时变成手型
            _set_cursor(True)
            # 联动其他图表：高亮同一 FuseID 的数据点（排除当前canvas避免清除自己的高亮）
            if self._last_fuse_id and self._last_fuse_id != 'N/A':
                for canvas_item in ss.get('canvases', []):
                    # 解包5个元素: (ax, other_canvas, other_item, highlight_fn, interactor)
                    if len(canvas_item) >= 4:
                        _, other_canvas, _, highlight_fn = canvas_item[:4]
                        if other_canvas is not canvas and highlight_fn:  # 排除当前canvas
                            highlight_fn(self._last_fuse_id)

        canvas._on_fuse_highlight = _track_fuse

        # 鼠标离开数据点时恢复光标，但保留最后的数据（不清空详情面板）
        def _clear_fuse():
            _set_cursor(False)
            # 不再清空 _last_fuse_id，保留最后悬停的数据
            # 只清空当前的hover状态
            self._last_readpoint   = None
            self._last_timestamp   = None
            self._last_test_value  = None
            # 保留 _last_fuse_id 和 _last_test_item，以便显示最后的数据
            # 不调用 _update_dialog_info()，保持最后显示的数据不变
            # 清除其他图表的高亮（排除当前canvas）
            ss = getattr(canvas, '_shared_state', {})
            for canvas_item in ss.get('canvases', []):
                if len(canvas_item) >= 4:
                    _, other_canvas, _, highlight_fn = canvas_item[:4]
                    if other_canvas is not canvas and highlight_fn:
                        highlight_fn(None)  # 传入 None 清除高亮

        canvas._on_fuse_clear = _clear_fuse

    def _bind_click(self, ax, canvas, test_item):
        """绑定点击事件：点击数据点直接显示四张图片"""
        import numpy as np

        def on_pick(event):
            # 找到最近的数据点
            lines_data = getattr(canvas.figure, '_hover_lines', [])
            all_points = []
            for item in lines_data:
                if len(item) == 5:
                    line, xs, ys, label, rp_data = item
                elif len(item) == 4:
                    line, xs, ys, label = item
                    rp_data = None
                else:
                    continue
                for idx, (x, y) in enumerate(zip(xs, ys)):
                    all_points.append((x, y, label, idx, rp_data))

            if not all_points:
                return

            # 用鼠标事件坐标找最近点
            x_range = max(ax.get_xlim()[1] - ax.get_xlim()[0], 1e-9)
            y_range = max(ax.get_ylim()[1] - ax.get_ylim()[0], 1e-9)

            mouse_x = event.mouseevent.xdata if hasattr(event, 'mouseevent') else 0
            mouse_y = event.mouseevent.ydata if hasattr(event, 'mouseevent') else 0

            # 第一步：收集所有x坐标相近的点（竖线候选集）
            # 当多个点数值相同时，它们在x轴上对齐，形成竖线
            # 我们首先找出所有x坐标与鼠标x坐标非常接近的点（在x_range的1%内）
            x_tolerance = 0.01 * x_range  # x轴1%的容差范围
            vertical_line_candidates = []
            
            for x, y, label, idx, rp_data in all_points:
                if abs(mouse_x - x) <= x_tolerance:
                    vertical_line_candidates.append((x, y, label, idx, rp_data))
            
            # 如果有竖线候选点，根据垂直距离选择最近的点
            if vertical_line_candidates:
                # 计算每个点的垂直距离（归一化）
                vertical_distances = []
                for x, y, label, idx, rp_data in vertical_line_candidates:
                    vd = abs(mouse_y - y) / y_range
                    vertical_distances.append((vd, x, y, label, idx, rp_data))
                
                # 按垂直距离排序
                vertical_distances.sort(key=lambda item: item[0])
                
                # 选择垂直距离最小的点
                min_vd, nx, ny, label, idx, rp_data = vertical_distances[0]
                
                # 计算总距离（用于后续阈值判断）
                min_dist = min_vd  # 这里只使用垂直距离，因为水平距离已经在容差内
                
                # 获取点的唯一标识信息
                if idx < len(rp_data):
                    row = rp_data.iloc[idx]
                    fuse_id = str(row['FuseID']) if 'FuseID' in row else 'N/A'
                    # 兼容时间戳列名：可能是整数 1 或字符串 'Time'
                    time_col = 1 if 1 in row else ('Time' if 'Time' in row else None)
                    timestamp = str(row[time_col]) if time_col else None
                else:
                    fuse_id = 'N/A'
                    timestamp = None
                
                nearest = (nx, ny, label, idx, rp_data)
            
            # 如果没有竖线候选点，使用原来的欧几里得距离逻辑
            else:
                # 收集所有点的距离和唯一标识信息
                point_info_list = []
                for x, y, label, idx, rp_data in all_points:
                    d = np.sqrt(((mouse_x - x) / x_range)**2 +
                                ((mouse_y - y) / y_range)**2)
                    
                    # 获取点的唯一标识信息
                    if idx < len(rp_data):
                        row = rp_data.iloc[idx]
                        fuse_id = str(row['FuseID']) if 'FuseID' in row else 'N/A'
                        # 兼容时间戳列名：可能是整数 1 或字符串 'Time'
                        time_col = 1 if 1 in row else ('Time' if 'Time' in row else None)
                        timestamp = str(row[time_col]) if time_col else None
                    else:
                        fuse_id = 'N/A'
                        timestamp = None
                    
                    # 创建点的唯一标识键：FuseID + 读点标签 + 时间戳
                    unique_key = f"{fuse_id}_{label}_{timestamp}"
                    
                    point_info_list.append((d, x, y, label, idx, rp_data, fuse_id, timestamp, unique_key))
                
                if not point_info_list:
                    return
                
                # 找到最小距离
                min_dist = min(d for d, _, _, _, _, _, _, _, _ in point_info_list)
                
                # 收集所有距离非常接近的点（在最小距离的1%范围内，但最小距离至少为0.001）
                # 防止min_dist=0时容差为0
                effective_min_dist = max(min_dist, 0.001 * (x_range + y_range) / 2)
                candidates = []
                for d, x, y, label, idx, rp_data, fuse_id, timestamp, unique_key in point_info_list:
                    if d <= effective_min_dist * 1.01:  # 1%容差范围
                        candidates.append((d, x, y, label, idx, rp_data, fuse_id, timestamp, unique_key))
                
                # 如果有多个候选点，根据鼠标位置和点唯一标识选择不同的点
                if len(candidates) > 1:
                    # 对候选点按唯一标识排序，确保确定性
                    candidates.sort(key=lambda c: c[8])  # 按unique_key排序
                    
                    # 使用鼠标位置的小数部分创建选择索引
                    x_frac = abs(mouse_x - int(mouse_x)) if mouse_x is not None else 0
                    y_frac = abs(mouse_y - int(mouse_y)) if mouse_y is not None else 0
                    
                    # 组合小数部分创建0-1之间的值
                    frac_value = (x_frac + y_frac) % 1.0
                    
                    # 根据小数部分选择候选点
                    selected_idx = int(frac_value * len(candidates)) % len(candidates)
                    
                    d, x, y, label, idx, rp_data, fuse_id, timestamp, unique_key = candidates[selected_idx]
                    nearest = (x, y, label, idx, rp_data)
                    min_dist = d
                else:
                    d, x, y, label, idx, rp_data, fuse_id, timestamp, unique_key = candidates[0]
                    nearest = (x, y, label, idx, rp_data)
                    min_dist = d

            if min_dist < 0.06:
                nx, ny, label, idx, rp_data = nearest
                
                # 直接从保存的原始数据中获取对应行的信息
                if idx < len(rp_data):
                    row = rp_data.iloc[idx]
                    fuse_id = str(row['FuseID']) if 'FuseID' in row else 'N/A'
                    # 兼容时间戳列名：可能是整数 1 或字符串 'Time'
                    time_col = 1 if 1 in row else ('Time' if 'Time' in row else None)
                    timestamp = str(row[time_col]) if time_col else None
                else:
                    # 备用逻辑：如果索引超出范围，使用旧方法
                    df = self._cb['get_current_df']()
                    rp_row = df[df['SN'] == label]
                    vals = rp_row[test_item].astype(float)
                    closest_idx = (vals - nx).abs().idxmin()
                    
                    fuse_id = (str(rp_row.loc[closest_idx, 'FuseID'])
                               if 'FuseID' in rp_row.columns else 'N/A')
                    time_col = 1 if 1 in rp_row.columns else ('Time' if 'Time' in rp_row.columns else None)
                    timestamp = str(rp_row.loc[closest_idx, time_col]) if time_col else None

                self._show_click_tooltip(
                    event.mouseevent,
                    fuse_id=fuse_id,
                    readpoint=label,
                    test_value=nx,
                    timestamp=timestamp
                )

        cid = canvas.mpl_connect('pick_event', on_pick)

    @staticmethod
    def _format_ts(ts):
        """14位时间戳转友好格式"""
        s = str(ts)
        if len(s) >= 14:
            return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}:{s[12:14]}"
        return str(ts)

    def _on_view_images(self):
        """点击"查看抓图"按钮"""
        if not self._last_fuse_id or self._last_fuse_id == 'N/A':
            return
        cb = self._cb.get('open_image_viewer')
        if cb:
            cb(self._last_fuse_id, self._last_readpoint)

    def _open_image_viewer_from_tooltip(self, fuse_id, readpoint):
        """从 tooltip 弹出的查看图像"""
        self._close_tooltip()
        cb = self._cb.get('open_image_viewer')
        if cb:
            cb(fuse_id, readpoint)

    def _show_click_tooltip(self, event, fuse_id, readpoint, test_value, timestamp):
        """点击图表数据点时：直接打开四张图片查看器（不再显示中间tooltip窗口）"""
        if not fuse_id or fuse_id == 'N/A':
            return
        # 直接调用图片查看器显示四张图
        cb = self._cb.get('open_image_viewer')
        if cb:
            cb(fuse_id, readpoint)

    def _close_tooltip(self):
        """关闭 tooltip"""
        if hasattr(self, '_tooltip_win') and self._tooltip_win:
            try:
                self._tooltip_win.destroy()
            except Exception:
                pass
            self._tooltip_win = None

    def _on_key(self, event):
        if event.key == 'left':
            self.prev()
        elif event.key == 'right':
            self.next()

    def _zoom_action(self, direction):
        """放大/缩小当前图表视图"""
        if self._canvas is None:
            return
        ax = self._canvas.figure.axes[0] if self._canvas.figure.axes else None
        if ax is None:
            return

        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        x_center = (xlim[0] + xlim[1]) / 2
        y_center = (ylim[0] + ylim[1]) / 2
        factor = 0.75 if direction == 'in' else 1.33

        new_xw = (xlim[1] - xlim[0]) * factor
        new_yw = (ylim[1] - ylim[0]) * factor
        ax.set_xlim(x_center - new_xw / 2, x_center + new_xw / 2)
        ax.set_ylim(y_center - new_yw / 2, y_center + new_yw / 2)
        self._canvas.draw_idle()

    def _zoom_reset(self):
        """重置图表视图到原始范围"""
        if self._canvas is None:
            return
        ax = self._canvas.figure.axes[0] if self._canvas.figure.axes else None
        if ax is None:
            return
        reset_ax_view(ax)
        self._canvas.draw_idle()

    def _bind_wheel_zoom(self, ax, canvas):
        """绑定鼠标滚轮缩放（以鼠标位置为中心）"""
        def on_wheel(event):
            if event.inaxes is None:
                return
            # 以鼠标位置为中心缩放
            x, y = event.xdata, event.ydata
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()

            factor = 0.9 if event.step > 0 else 1.1  # 向上滚动放大，向下缩小
            new_xw = (xlim[1] - xlim[0]) * factor
            new_yw = (ylim[1] - ylim[0]) * factor

            # 以鼠标位置为中心
            x_ratio = (x - xlim[0]) / (xlim[1] - xlim[0]) if xlim[1] != xlim[0] else 0.5
            y_ratio = (y - ylim[0]) / (ylim[1] - ylim[0]) if ylim[1] != ylim[0] else 0.5

            ax.set_xlim(x - new_xw * x_ratio, x + new_xw * (1 - x_ratio))
            ax.set_ylim(y - new_yw * y_ratio, y + new_yw * (1 - y_ratio))
            canvas.draw_idle()

        canvas.mpl_connect('scroll_event', on_wheel)

    def _bind_context_menu(self, ax, canvas):
        """绑定右键菜单"""
        def on_button_press(event):
            # 右键（button=3）
            if event.button == 3:
                # 检查是否有悬停数据点
                if self._last_fuse_id and self._last_fuse_id != 'N/A':
                    # 显示右键菜单
                    self._show_context_menu(event)
                else:
                    # 无悬停数据点，关闭菜单
                    self._close_context_menu()
        
        def on_motion(event):
            # 鼠标移动时更新右键菜单信息
            pass  # 信息已通过悬停更新
        
        def on_leave(event):
            # 鼠标离开时关闭菜单
            self._close_context_menu()
        
        canvas.mpl_connect('button_press_event', on_button_press)
        canvas.mpl_connect('motion_notify_event', on_motion)
        canvas.mpl_connect('figure_leave_event', on_leave)
    
    def _show_context_menu(self, event):
        """显示右键菜单"""
        # 关闭已有菜单
        self._close_context_menu()
        
        if not self._win or not self._win.winfo_exists():
            return
        
        # 创建右键菜单
        menu = tk.Menu(self._win, tearoff=0, bg='#f8f9fa', fg='#374151',
                       font=('Microsoft YaHei', 9))
        
        # 查看抓图
        menu.add_command(label='📷 查看抓图', command=self._on_context_view_images)
        # 查看数据详情
        menu.add_command(label='📊 查看数据详情', command=self._on_context_view_details)
        
        # 显示菜单
        try:
            menu.tk_popup(event.guiEvent.x_root, event.guiEvent.y_root)
        except Exception:
            pass
        
        self._context_menu = menu
        
        # 菜单关闭时清理
        menu.bind('<Unmap>', lambda e: self._close_context_menu())
    
    def _close_context_menu(self):
        """关闭右键菜单"""
        if self._context_menu:
            try:
                self._context_menu.destroy()
            except Exception:
                pass
            self._context_menu = None
    
    def _on_context_view_images(self):
        """右键菜单：查看抓图"""
        self._close_context_menu()
        if self._last_fuse_id and self._last_fuse_id != 'N/A':
            cb = self._cb.get('open_image_viewer')
            if cb:
                cb(self._last_fuse_id, self._last_readpoint)
    
    def _on_context_view_details(self):
        """右键菜单：查看数据详情"""
        self._close_context_menu()
        self._show_data_point_dialog()

    def _show_data_point_dialog(self):
        """点击「查看数据点」按钮：切换显示/隐藏实时详情面板（单表格布局）"""
        if self._data_point_win is not None and self._data_point_win.winfo_exists():
            self._data_point_win.destroy()
            self._data_point_win = None
            return

        # 从当前图表获取读点颜色映射
        self._current_rp_colors = {}
        items = self._cb['get_chart_items']()
        if items and self._idx < len(items):
            test_item = items[self._idx]
            fig, _ = self._get_chart(test_item)
            if fig and hasattr(fig, '_rp_colors'):
                self._current_rp_colors = fig._rp_colors

        top = tk.Toplevel(self._win)
        self._data_point_win = top
        top.title('数据点详情')
        top.configure(bg='#f0f2f5')
        top.geometry('900x500')
        top.resizable(True, True)

        # 标题栏
        hdr = tk.Frame(top, bg='#4f46e5', height=40)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text='  数据点详情', bg='#4f46e5', fg='white',
                 font=('Microsoft YaHei', 12, 'bold')).pack(side='left', pady=10)

        def _close():
            self._data_point_win = None
            top.destroy()
        tk.Button(hdr, text='×', command=_close,
                 bg='#4f46e5', fg='white', relief='flat',
                 font=('Arial', 16, 'bold'), cursor='hand1',
                 activebackground='#4338ca', bd=0,
                 padx=16, pady=0, highlightthickness=0).pack(side='right', pady=0)

        # 搜索栏
        search_frame = tk.Frame(top, bg='#f0f2f5', height=50)
        search_frame.pack(fill='x', padx=16, pady=(12, 8))
        search_frame.pack_propagate(False)

        self._search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self._search_var,
                              bg='white', fg='#374151', relief='solid', bd=1,
                              font=('Microsoft YaHei', 10), width=40)
        search_entry.pack(side='left', padx=(0, 8))
        search_entry.bind('<Return>', lambda e: self._on_search())
        search_entry.insert(0, '输入 FuseID 或时间戳搜索...')
        search_entry.config(fg='#9ca3af')
        def on_focus_in(e):
            if search_entry.get() == '输入 FuseID 或时间戳搜索...':
                search_entry.delete(0, tk.END)
                search_entry.config(fg='#374151')
        def on_focus_out(e):
            if search_entry.get() == '':
                search_entry.insert(0, '输入 FuseID 或时间戳搜索...')
                search_entry.config(fg='#9ca3af')
        search_entry.bind('<FocusIn>', on_focus_in)
        search_entry.bind('<FocusOut>', on_focus_out)

        tk.Button(search_frame, text='🔍 搜索', command=self._on_search,
                 bg='#4f46e5', fg='white', relief='flat', cursor='hand1',
                 font=('Microsoft YaHei', 10), padx=16, pady=6).pack(side='left', padx=(0, 6))
        tk.Button(search_frame, text='清除', command=self._clear_search_highlight,
                 bg='#6b7280', fg='white', relief='flat', cursor='hand1',
                 font=('Microsoft YaHei', 9), padx=12, pady=6).pack(side='left')

        # 主体区域
        body = tk.Frame(top, bg='#f0f2f5')
        body.pack(fill='both', expand=True, padx=16, pady=(0, 12))

        # ========== 唯一表格区域 ==========
        table_container = tk.Frame(body, bg='white', relief='solid', bd=1)
        table_container.pack(fill='both', expand=True)

        tk.Label(table_container, text='📊 数据点信息', anchor='w',
                bg='#e0e7ff', fg='#3730a3',
                font=('Microsoft YaHei', 10, 'bold'),
                padx=12, pady=8).pack(fill='x')

        # 表格列：测试项 | 读点 | FuseID | 时间戳 | 值
        columns = ('test_item', 'readpoint', 'fuse_id', 'timestamp', 'test_value')
        column_widths = {'test_item': 180, 'readpoint': 80, 'fuse_id': 150, 'timestamp': 160, 'test_value': 120}

        self._info_tree = ttk.Treeview(table_container, columns=columns, show='headings',
                                       height=12, selectmode='browse')
        
        self._info_tree.heading('test_item', text='测试项')
        self._info_tree.heading('readpoint', text='读点')
        self._info_tree.heading('fuse_id', text='FuseID')
        self._info_tree.heading('timestamp', text='时间戳')
        self._info_tree.heading('test_value', text='测试值')
        
        for col, width in column_widths.items():
            self._info_tree.column(col, width=width, anchor='center')
        
        # 读点颜色配置：使用图表中的实际颜色
        style = ttk.Style()
        style.configure('Treeview', font=('Microsoft YaHei', 9), rowheight=28)
        style.configure('Treeview.Heading', font=('Microsoft YaHei', 9, 'bold'))
        
        # 配置从图表获取的读点颜色tags
        for rp, color in self._current_rp_colors.items():
            self._info_tree.tag_configure(f'rp_{rp}', background=color, foreground='white')
        
        scroll_y = ttk.Scrollbar(table_container, orient='vertical', command=self._info_tree.yview)
        scroll_y.pack(side='right', fill='y')
        self._info_tree.configure(yscrollcommand=scroll_y.set)
        
        scroll_x = ttk.Scrollbar(table_container, orient='horizontal', command=self._info_tree.xview)
        scroll_x.pack(side='bottom', fill='x')
        self._info_tree.configure(xscrollcommand=scroll_x.set)
        
        self._info_tree.pack(fill='both', expand=True, padx=8, pady=(0, 8))

        # 底部按钮
        btn_frame = tk.Frame(body, bg='#f0f2f5')
        btn_frame.pack(fill='x', pady=(12, 0))
        
        tk.Button(btn_frame, text='📷 查看抓图', command=self._on_view_images,
                 bg='#059669', fg='white', relief='flat', cursor='hand1',
                 font=('Microsoft YaHei', 10), padx=16, pady=6).pack(side='left')

        self._update_dialog_info()

    def _collect_linked_info(self, fuse_id):
        """
        收集指定 FuseID 在当前分屏展示的测试项上的数据
        返回：{test_item: {readpoint: (value, timestamp), ...}, ...}
        """
        if not fuse_id or fuse_id == 'N/A':
            return {}
        df = self._cb['get_current_df']()
        if df is None:
            return {}
        
        # 筛选该 FuseID 的所有行
        fuse_rows = df[df['FuseID'] == fuse_id]
        if fuse_rows.empty:
            return {}
        
        # 获取时间戳列
        time_col = 1 if 1 in df.columns else ('Time' if 'Time' in df.columns else None)
        
        # 获取当前分屏展示的测试项（从图表项列表获取）
        chart_items = self._cb['get_chart_items']()
        if not chart_items:
            return {}
        
        # 根据当前分屏数量确定展示的测试项范围
        n = int(self._split_var.get())
        start_idx = self._idx
        end_idx = min(self._idx + n, len(chart_items))
        current_items = chart_items[start_idx:end_idx] if chart_items else []
        
        result = {}
        for test_item in current_items:
            if test_item not in df.columns:
                continue
            readpoint_values = {}
            for _, row in fuse_rows.iterrows():
                readpoint = str(row['SN'])
                value = row[test_item]
                ts = str(row[time_col]) if time_col and time_col in row and pd.notna(row.get(time_col)) else None
                if pd.notna(value):
                    readpoint_values[readpoint] = (float(value), ts)
            if readpoint_values:
                result[test_item] = readpoint_values
        return result

    def _get_timestamp_for_readpoint(self, fuse_id, readpoint):
        """获取指定FuseID和读点对应的时间戳"""
        return None  # 已弃用，时间戳现在在 _collect_linked_info 中一并获取

    def _update_dialog_info(self):
        """更新详情表格：显示当前芯片在当前分屏测试项上的数据"""
        if self._data_point_win is None or not self._data_point_win.winfo_exists():
            return
        
        # 清空表格
        for item in self._info_tree.get_children():
            self._info_tree.delete(item)
        
        if not self._last_fuse_id or self._last_fuse_id == 'N/A':
            self._info_tree.insert('', 0, values=('悬停或框选数据点查看详情...', '', '', '', ''))
            return
        
        # 获取当前芯片在当前分屏测试项上的数据
        all_data = self._collect_linked_info(self._last_fuse_id)
        
        if not all_data:
            self._info_tree.insert('', 0, values=(f'FuseID: {self._last_fuse_id}', '无数据', '', '', ''))
            return
        
        # 收集所有行数据
        all_rows = []
        for test_item, rp_map in all_data.items():
            sorted_rps = sorted(rp_map.items(), key=lambda x: (int(re.search(r'\d+', str(x[0])).group()) if re.search(r'\d+', str(x[0])) else 0, str(x[0])))
            
            for rp, val_ts in sorted_rps:
                val, timestamp = val_ts
                is_selected = (rp == self._last_readpoint and test_item == getattr(self, '_last_test_item', None))
                
                all_rows.append({
                    'test_item': test_item,
                    'readpoint': rp,
                    'fuse_id': self._last_fuse_id,
                    'timestamp': timestamp if timestamp else '-',
                    'test_value': f'{val:.6f}' if val else '-',
                    'is_selected': is_selected
                })
        
        # 按测试项和读点排序
        all_rows.sort(key=lambda x: (x['test_item'], int(re.search(r'\d+', str(x['readpoint'])).group()) if re.search(r'\d+', str(x['readpoint'])) else 0))
        
        # 插入表格，应用读点颜色（选中用红点符号标记）
        selected_item_id = None
        for row in all_rows:
            rp_key = row['readpoint']
            color_tag = f'rp_{rp_key}' if rp_key in self._current_rp_colors else ''
            is_selected = row['is_selected']
            
            # 选中行：在FuseID前加红点符号表示
            fuse_id_display = row['fuse_id']
            if is_selected:
                fuse_id_display = '🔴 ' + fuse_id_display
            
            values = (row['test_item'], row['readpoint'], fuse_id_display, row['timestamp'], row['test_value'])
            
            # 只有当有颜色tag时才传递tags参数
            if color_tag:
                item_id = self._info_tree.insert('', 'end', values=values, tags=(color_tag,))
            else:
                item_id = self._info_tree.insert('', 'end', values=values)
            
            if is_selected:
                selected_item_id = item_id
        
        # 选中和滚动到选中行
        if selected_item_id:
            self._info_tree.selection_set(selected_item_id)
            self._info_tree.see(selected_item_id)

    def _update_selection_panel(self):
        """更新框选详情面板 - 使用同一表格显示框选的数据"""
        # 框选时不再单独更新，让悬停继续工作
        pass
    
    def _get_fuse_data_by_item(self, fuse_id, test_item):
        """
        获取指定FuseID在指定测试项下的数据
        返回: {readpoint: (value, timestamp), ...}
        """
        if not fuse_id or fuse_id == 'N/A':
            return {}
        df = self._cb['get_current_df']()
        if df is None or not test_item:
            return {}
        
        fuse_rows = df[df['FuseID'] == fuse_id]
        if fuse_rows.empty:
            return {}
        
        result = {}
        time_col = 1 if 1 in df.columns else ('Time' if 'Time' in df.columns else None)
        
        for _, row in fuse_rows.iterrows():
            readpoint = str(row['SN'])
            value = row.get(test_item)
            ts = row[time_col] if time_col and time_col in row else None
            if pd.notna(value):
                try:
                    result[readpoint] = (float(value), str(ts) if ts else None)
                except (ValueError, TypeError):
                    result[readpoint] = (None, str(ts) if ts else None)
        
        return result

    def _on_search(self, search_type=None):
        """
        处理查询输入：根据输入的 FuseID 或时间戳高亮对应数据点
        search_type: 'fuse' 或 'timestamp'，为 None 时自动判断
        """
        query = self._search_var.get().strip()
        if not query:
            messagebox.showinfo("提示", "请输入查询内容")
            return
        
        df = self._cb['get_current_df']()
        if df is None:
            return
        
        # 自动判断查询类型
        if search_type is None:
            # 尝试匹配 FuseID（可能是数字或字符串）
            if df['FuseID'].astype(str).str.contains(query, case=False, na=False).any():
                search_type = 'fuse'
            elif (1 in df.columns or 'Time' in df.columns):
                # 检查时间戳列
                time_col = 1 if 1 in df.columns else 'Time'
                # 尝试从查询中提取14位时间戳（支持 Dark_0_20260204012242 格式）
                ts_match = re.search(r'(\d{14})', query)
                ts_query = ts_match.group(1) if ts_match else query
                
                if df[time_col].astype(str).str.contains(ts_query, case=False, na=False).any():
                    search_type = 'timestamp'
                else:
                    search_type = 'fuse'  # 默认按 FuseID
            else:
                search_type = 'fuse'
        
        matched_rows = None
        fuse_id = None
        timestamp = None
        readpoint = None
        test_value = None
        
        if search_type == 'fuse':
            # 查询 FuseID
            matched_rows = df[df['FuseID'].astype(str) == query]
            if not matched_rows.empty:
                # 取第一行
                row = matched_rows.iloc[0]
                fuse_id = str(row['FuseID'])
                readpoint = str(row['SN'])
                test_value = float(row[self._last_test_item]) if self._last_test_item in row else None
                # 时间戳列
                time_col = 1 if 1 in df.columns else ('Time' if 'Time' in df.columns else None)
                timestamp = str(row[time_col]) if time_col else None
        else:
            # 查询时间戳
            time_col = 1 if 1 in df.columns else ('Time' if 'Time' in df.columns else None)
            if time_col:
                # 尝试从查询中提取14位时间戳（支持 Dark_0_20260204012242 格式）
                ts_match = re.search(r'(\d{14})', query)
                ts_query = ts_match.group(1) if ts_match else query
                
                # 搜索时间戳列
                matched_rows = df[df[time_col].astype(str) == ts_query]
                if not matched_rows.empty:
                    row = matched_rows.iloc[0]
                    fuse_id = str(row['FuseID'])
                    readpoint = str(row['SN'])
                    test_value = float(row[self._last_test_item]) if self._last_test_item in row else None
                    timestamp = str(row[time_col])
        
        if matched_rows is None or matched_rows.empty:
            messagebox.showinfo("提示", f"未找到匹配的{search_type}: {query}")
            return
        
        # 更新当前悬停信息
        self._last_fuse_id = fuse_id
        self._last_readpoint = readpoint
        self._last_timestamp = timestamp
        self._last_test_value = test_value
        
        # 触发联动高亮
        ss = getattr(self._canvas, '_shared_state', {}) if self._canvas else {}
        if fuse_id and fuse_id != 'N/A':
            for canvas_item in ss.get('canvases', []):
                if len(canvas_item) >= 4:
                    _, _, _, highlight_fn = canvas_item[:4]
                    if highlight_fn:
                        highlight_fn(fuse_id)
        
        # 更新详情面板
        self._update_dialog_info()

    def _clear_search_highlight(self):
        """清除所有图表的高亮显示"""
        ss = getattr(self._canvas, '_shared_state', {}) if self._canvas else {}
        for canvas_item in ss.get('canvases', []):
            if len(canvas_item) >= 4:
                _, _, _, highlight_fn = canvas_item[:4]
                if highlight_fn:
                    highlight_fn(None)
        # 清空当前悬停信息
        self._last_fuse_id = None
        self._last_readpoint = None
        self._last_timestamp = None
        self._last_test_value = None
        self._update_dialog_info()

    def _copy_linked_info(self):
        """复制表格信息到剪贴板"""
        if hasattr(self, '_info_tree') and self._info_tree.winfo_exists():
            lines = []
            for item in self._info_tree.get_children():
                values = self._info_tree.item(item)['values']
                if values:
                    lines.append('\t'.join(str(v) for v in values))
            if lines:
                content = '\n'.join(lines)
                self._win.clipboard_clear()
                self._win.clipboard_append(content)
                messagebox.showinfo("成功", "信息已复制到剪贴板")
