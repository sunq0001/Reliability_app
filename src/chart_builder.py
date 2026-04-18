"""
chart_builder_new.py - 重构版图表构建模块
核心改进：直接处理数据点而非线条对象，简化悬停交互逻辑
"""

import re
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional, Any, Callable


# ========== Matplotlib 配置 ==========

_matplotlib_configured = False


def configure_matplotlib_chinese():
    """配置 Matplotlib 支持中文字体（仅首次调用生效）"""
    global _matplotlib_configured
    if _matplotlib_configured:
        return
    _matplotlib_configured = True

    import matplotlib
    import matplotlib.pyplot as plt

    chinese_fonts = ['Microsoft YaHei', 'SimHei', 'SimSun', 'KaiTi']
    for font in chinese_fonts:
        try:
            matplotlib.font_manager.fontManager.addfont(
                matplotlib.font_manager.findfont(
                    matplotlib.font_manager.FontProperties(family=font)
                )
            )
        except Exception:
            pass

    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'SimSun', 'KaiTi', 'Arial']
    plt.rcParams['axes.unicode_minus'] = False


# ========== 数据点定义 ==========

class DataPoint:
    """单个数据点的完整信息"""
    
    def __init__(self, x: float, y: float, label: str, 
                 fuse_id: str, timestamp: Any, raw_row: pd.Series):
        self.x = x  # 测试值
        self.y = y  # 累积概率
        self.label = label  # 读点名称
        self.fuse_id = fuse_id  # FuseID
        self.timestamp = timestamp  # 时间戳
        self.raw_row = raw_row  # 原始数据行
        
        # 计算哈希用于快速比较
        self._hash = hash((x, y, label, fuse_id, str(timestamp)))
    
    def __hash__(self):
        return self._hash
    
    def __eq__(self, other):
        if not isinstance(other, DataPoint):
            return False
        return (self.x == other.x and self.y == other.y and 
                self.label == other.label and self.fuse_id == other.fuse_id and 
                str(self.timestamp) == str(other.timestamp))
    
    def __repr__(self):
        return f"DataPoint({self.label}: {self.x:.4f}, {self.y:.1f}%, FuseID={self.fuse_id})"


# ========== 图表构建 ==========

def sort_read_points(read_points):
    """按数值排序读点名称"""
    def get_val(rp):
        m = re.search(r'(\d+)', str(rp))
        return int(m.group(1)) if m else 0
    return sorted(set(rp for rp in read_points if str(rp) != 'SN' and pd.notna(rp)),
                   key=get_val)


def build_chart_for_item(df, test_item):
    """
    为单个测试项构建累积分布图
    
    参数:
        df: DataFrame，包含 SN 列标识读点
        test_item: str, 测试项列名
    
    返回:
        (Figure, Axes)
    """
    configure_matplotlib_chinese()
    from matplotlib.figure import Figure
    
    read_points = sort_read_points(df['SN'].unique())
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    
    fig = Figure(figsize=(8, 5), dpi=100)
    ax = fig.add_subplot(111)
    
    all_points = []  # 存储所有数据点
    all_lines = []   # 存储线条对象（仅用于绘制）
    
    for i, rp in enumerate(read_points):
        # 获取该读点的数据，排序并保留原始索引
        rp_data = df[df['SN'] == rp][[test_item, 'FuseID', 1 if 1 in df.columns else 'Time']].copy()
        rp_data[test_item] = rp_data[test_item].astype(float)
        rp_data = rp_data.dropna(subset=[test_item])
        rp_data = rp_data.sort_values(test_item)
        
        n = len(rp_data)
        if n == 0:
            continue
        
        cumulative_prob = np.arange(1, n + 1) / n * 100
        
        # 绘制线条
        line, = ax.plot(
            rp_data[test_item].values, cumulative_prob,
            marker='o', markersize=4, alpha=0.85,
            label=str(rp), color=colors[i % len(colors)], linewidth=1.5,
            picker=True,          # 支持点击 pick 事件
            pickradius=8,         # 点击容差（像素）
        )
        all_lines.append((line, rp_data[test_item].values, cumulative_prob, str(rp)))
        
        # 构建数据点集合
        for idx, (x, y) in enumerate(zip(rp_data[test_item].values, cumulative_prob)):
            row = rp_data.iloc[idx]
            fuse_id = str(row['FuseID']) if 'FuseID' in row else 'N/A'
            time_col = 1 if 1 in row else ('Time' if 'Time' in row else None)
            timestamp = str(row[time_col]) if time_col else None
            
            point = DataPoint(x, y, str(rp), fuse_id, timestamp, row)
            all_points.append(point)
    
    ax.set_title(f'{test_item} - 累积分布图', fontsize=11, fontweight='bold')
    ax.set_xlabel(test_item, fontsize=10)
    ax.set_ylabel('Cumulative Probability (%)', fontsize=10)
    if all_lines:  # 只有有线时才添加图例
        ax.legend(loc='best', fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    
    # 保存数据点供悬停使用（不再保存线条数据）
    fig._data_points = all_points
    fig._lines_info = all_lines  # 保留线条信息用于绘制交叉线
    
    return fig, ax


def reset_ax_view(ax):
    """将 ax 视图重置回数据原始范围"""
    try:
        ax.relim()
        ax.autoscale_view()
    except Exception:
        pass


# ========== 悬停交互 ==========

class ChartInteractor:
    """单个图表的交互管理器"""
    
    def __init__(self, ax, canvas, test_item, df, fuse_cache,
                 get_info_text_fn, set_linked_fn, set_cursor_fn=None):
        # 核心引用
        self.ax = ax
        self.canvas = canvas
        self.test_item = test_item
        self.df = df
        self.fuse_cache = fuse_cache
        
        # 回调函数
        self.get_info_text = get_info_text_fn
        self.set_linked = set_linked_fn
        self.set_cursor = set_cursor_fn
        
        # 数据点集合（从图表中提取）
        self.data_points = getattr(canvas.figure, '_data_points', [])
        self.lines_info = getattr(canvas.figure, '_lines_info', [])
        
        # 状态管理
        self.drift_lines = []  # 临时图形对象列表
        self.current_highlight = None
        self.last_fuse_id = None
        
        # 配置参数
        self.hover_tolerance = 0.03  # 归一化距离阈值
        self.highlight_style = {
            'marker': 'o',
            'color': '#ff0000',  # 亮红色
            'markersize': 8,
            'zorder': 1000
        }
    
    def clear_all_highlights(self):
        """清除所有临时图形对象"""
        for line_obj in self.drift_lines:
            try:
                line_obj.remove()
            except Exception:
                pass
        self.drift_lines.clear()
        self.current_highlight = None
        
        # 重绘画布
        try:
            self.canvas.draw_idle()
        except Exception:
            pass
    
    def find_nearest_point(self, mouse_x, mouse_y):
        """
        查找距离鼠标最近的数据点
        
        返回: DataPoint 或 None
        """
        if mouse_x is None or mouse_y is None:
            return None
        
        if not self.data_points:
            return None
        
        # 计算坐标范围用于归一化
        x_range = max(self.ax.get_xlim()[1] - self.ax.get_xlim()[0], 1e-9)
        y_range = max(self.ax.get_ylim()[1] - self.ax.get_ylim()[0], 1e-9)
        
        min_norm_dist = float('inf')
        nearest_point = None
        
        for point in self.data_points:
            # 计算归一化欧几里得距离
            norm_dist = np.sqrt(
                ((mouse_x - point.x) / x_range) ** 2 +
                ((mouse_y - point.y) / y_range) ** 2
            )
            
            if norm_dist < min_norm_dist:
                min_norm_dist = norm_dist
                nearest_point = point
        
        # 检查是否在容差范围内
        if min_norm_dist < self.hover_tolerance:
            return nearest_point
        return None
    
    def draw_highlight(self, point):
        """绘制高亮点（红色圆点 markersize=8）"""
        # 清除旧高亮
        self.clear_all_highlights()
        
        # 绘制新高亮
        highlight = self.ax.plot(
            point.x, point.y,
            marker=self.highlight_style['marker'],
            color=self.highlight_style['color'],
            markersize=self.highlight_style['markersize'],
            zorder=self.highlight_style['zorder']
        )[0]
        
        self.current_highlight = highlight
        self.drift_lines.append(highlight)
        self.canvas.draw_idle()
    
    def draw_cross_lines(self, fuse_id, anchor_x, anchor_y, anchor_label):
        """
        为同一FuseID的其他读点绘制交叉连接线
        
        返回: 交叉点信息列表
        """
        if fuse_id not in self.fuse_cache:
            return []
        
        cross_info = []
        rp_map = self.fuse_cache[fuse_id]
        
        # 遍历所有读点（通过lines_info获取）
        for _, _, _, other_label in self.lines_info:
            if other_label == anchor_label or other_label not in rp_map:
                continue
            
            row = rp_map[other_label]
            try:
                v = float(row[self.test_item])
            except (KeyError, ValueError, TypeError):
                continue
            
            # 计算对应点的y坐标（累积概率）
            vy = self._calculate_cumulative_prob(other_label, v)
            if vy is None:
                continue
            
            # 绘制虚线连接线
            vline = self.ax.plot(
                [anchor_x, v], [anchor_y, vy],
                '--', color='#888', linewidth=1.0, alpha=0.7
            )[0]
            self.drift_lines.append(vline)
            
            # 绘制对应点标记
            dot = self.ax.plot(v, vy, 'o', color='#888', markersize=5, alpha=0.8)[0]
            self.drift_lines.append(dot)
            
            cross_info.append(f"  -> {other_label}: {v:.4f}  (Δ{v - anchor_x:+.4f})")
        
        self.canvas.draw_idle()
        return cross_info
    
    def _calculate_cumulative_prob(self, label, value):
        """计算给定读点和值的累积概率位置"""
        # 获取该读点的所有值
        df_sn = self.df[self.df['SN'] == label]
        try:
            sorted_vals = np.sort(df_sn[self.test_item].astype(float).dropna().values)
        except Exception:
            return None
        
        n_pts = len(sorted_vals)
        if n_pts == 0:
            return None
        
        # 计算插入位置
        pos = min(np.searchsorted(sorted_vals, value), n_pts - 1)
        return (pos + 1) / n_pts * 100
    
    def update_info_display(self, point, cross_info):
        """更新信息显示"""
        info_lines = [
            f"读点: {point.label}",
            f"值:   {point.x:.4f}",
            f"概率: {point.y:.1f}%",
            f"FuseID: {point.fuse_id}",
        ]
        
        if point.timestamp:
            info_lines.append(f"时间: {point.timestamp}")
        
        if cross_info:
            info_lines.append("同一芯片其他读点:")
            info_lines.extend(cross_info)
        
        self.get_info_text('\n'.join(info_lines), is_active=True)
    
    def update_shared_state(self, point):
        """更新shared_state触发联动"""
        if hasattr(self.canvas, '_shared_state'):
            self.canvas._shared_state['fuse_id'] = point.fuse_id
            self.canvas._shared_state['timestamp'] = point.timestamp
            self.canvas._shared_state['test_value'] = point.x
            self.canvas._shared_state['readpoint'] = point.label
            
            # 触发联动回调
            cb = getattr(self.canvas, '_on_fuse_highlight', None)
            if cb:
                cb()
    
    def clear_shared_state(self):
        """清除shared_state"""
        if hasattr(self.canvas, '_shared_state'):
            self.canvas._shared_state['fuse_id'] = None
            self.canvas._shared_state['timestamp'] = None
            self.canvas._shared_state['test_value'] = None
            self.canvas._shared_state['readpoint'] = None
            
            cb = getattr(self.canvas, '_on_fuse_clear', None)
            if cb:
                cb()
    
    def on_mouse_move(self, event):
        """鼠标移动事件处理器"""
        try:
            # 鼠标离开图表区域
            if event.inaxes != self.ax:
                self._handle_mouse_leave()
                return
            
            # 查找最近点
            point = self.find_nearest_point(event.xdata, event.ydata)
            
            if point is None:
                # 在图表内但未悬停在点上
                self._handle_no_hover()
                return
            
            # 悬停在数据点上
            self._handle_hover(event, point)
            
        except Exception as e:
            # 静默处理错误，避免中断用户交互
            self.clear_all_highlights()
            if self.set_cursor:
                self.set_cursor(False)
    
    def _handle_hover(self, event, point):
        """处理悬停在数据点上的情况"""
        # 更新光标为手型
        if self.set_cursor:
            self.set_cursor(True)
        
        # 绘制高亮点
        self.draw_highlight(point)
        
        # 绘制交叉线
        cross_info = self.draw_cross_lines(point.fuse_id, point.x, point.y, point.label)
        
        # 更新信息显示
        self.update_info_display(point, cross_info)
        
        # 更新shared_state（如果FuseID发生变化）
        if point.fuse_id != self.last_fuse_id:
            self.update_shared_state(point)
            self.last_fuse_id = point.fuse_id
    
    def _handle_no_hover(self):
        """处理在图表内但未悬停在点上的情况"""
        if self.set_cursor:
            self.set_cursor(False)
        
        self.clear_all_highlights()
        self.get_info_text('将鼠标移到图表数据点上查看详情', is_active=False)
        self.set_linked('')
        
        if self.last_fuse_id is not None:
            self.clear_shared_state()
            self.last_fuse_id = None
    
    def _handle_mouse_leave(self):
        """处理鼠标离开图表区域的情况"""
        if self.set_cursor:
            self.set_cursor(False)
        
        self.clear_all_highlights()
        self.get_info_text('将鼠标移到图表数据点上查看详情', is_active=False)
        self.set_linked('')
        
        if self.last_fuse_id is not None:
            self.clear_shared_state()
            self.last_fuse_id = None
    
    def highlight_linked(self, fuse_id):
        """
        外部调用：在其他图表上高亮相同FuseID的点（供联动使用）
        
        返回: 绘制的点坐标列表
        """
        self.clear_all_highlights()
        
        if fuse_id is None or fuse_id not in self.fuse_cache:
            return []
        
        rp_map = self.fuse_cache[fuse_id]
        points = []
        
        # 遍历所有读点
        for _, _, _, label in self.lines_info:
            if label not in rp_map:
                continue
            
            row = rp_map[label]
            try:
                v = float(row[self.test_item])
            except (KeyError, ValueError, TypeError):
                continue
            
            # 计算y坐标
            vy = self._calculate_cumulative_prob(label, v)
            if vy is None:
                continue
            
            points.append((v, vy))
            
            # 绘制橙色圆点
            dot = self.ax.plot(
                v, vy, 'o',
                color='#e67e22', markersize=6, alpha=0.9
            )[0]
            self.drift_lines.append(dot)
        
        # 连接各点形成折线
        for i in range(len(points) - 1):
            line = self.ax.plot(
                [points[i][0], points[i+1][0]],
                [points[i][1], points[i+1][1]],
                '--', color='#e67e22', linewidth=1.2, alpha=0.8
            )[0]
            self.drift_lines.append(line)
        
        self.canvas.draw_idle()
        return points


def build_fuse_cache(df):
    """
    预扫描所有数据，构建 fuse_id -> {read_point -> row} 映射
    """
    if df is None or 'FuseID' not in df.columns:
        return {}
    
    cache = {}
    for _, row in df.iterrows():
        fid = row.get('FuseID')
        sn = row.get('SN')
        if pd.isna(fid) or pd.isna(sn):
            continue
        fid = str(fid)
        if fid not in cache:
            cache[fid] = {}
        cache[fid][str(sn)] = row
    return cache


def make_hover_callbacks(ax, canvas, test_item, df, fuse_cache,
                         get_info_text_fn, set_linked_fn, set_cursor_fn=None):
    """
    为图表绑定鼠标悬停交互，返回需要清理的闭包引用
    
    参数:
        ax, canvas: matplotlib 绑定对象
        test_item: str
        df: DataFrame
        fuse_cache: dict, build_fuse_cache() 的结果
        get_info_text_fn: callable(text, is_active) -> 更新主信息区
        set_linked_fn: callable(text) -> 更新联动区
    
    返回:
        dict, 包含 highlight_linked 供联动使用
    """
    # 创建交互管理器
    interactor = ChartInteractor(
        ax, canvas, test_item, df, fuse_cache,
        get_info_text_fn, set_linked_fn, set_cursor_fn
    )
    
    # 绑定事件
    cid = canvas.mpl_connect('motion_notify_event', interactor.on_mouse_move)
    
    # 返回相同的字典结构
    return {
        'highlight_linked': interactor.highlight_linked,
        'clear_drift_lines': interactor.clear_all_highlights,
    }


# ========== 线程安全图表预生成缓存 ==========

class ThreadSafeChartCache:
    """线程安全的图表预生成缓存（与旧版本兼容）"""
    
    def __init__(self, max_size=30):
        import threading
        self._cache = {}          # {test_item: fig}
        self._max_size = max_size
        self._lock = threading.Lock()
        self._worker = None
        self._stop_event = threading.Event()
        self._df = None
        self._items = []
        self._current_idx = 0
        self._build_fn = None   # (df, item) -> fig 回调
    
    def configure(self, df, items, build_fn):
        """配置：设置数据源、测试项列表、构建函数"""
        import threading
        self._df = df
        self._items = items
        self._build_fn = build_fn
        self._current_idx = 0
    
    def start_prefill(self, current_idx=0):
        """启动后台预生成线程（从 current_idx 开始往前预渲染）"""
        import threading
        if self._worker is not None and self._worker.is_alive():
            return  # 已有一个线程在跑
        
        self._stop_event.clear()
        self._current_idx = current_idx
        self._worker = threading.Thread(target=self._prefill_worker, daemon=True)
        self._worker.start()
    
    def update_current(self, idx):
        """用户切换到 idx 时调用：更新预生成方向，确保持续往前填缓存"""
        self._current_idx = idx
    
    def stop(self):
        """停止后台线程"""
        self._stop_event.set()
    
    def get(self, test_item):
        """主线程调用：返回已生成的 Figure，未生成则返回 None"""
        with self._lock:
            return self._cache.get(test_item)
    
    def _prefill_worker(self):
        """后台预生成线程：智能双向预填充，优先用户当前看的区域"""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        while not self._stop_event.is_set():
            # 获取当前用户位置和缓存状态
            with self._lock:
                current_idx = self._current_idx
                items = self._items
                cache_keys = set(self._cache.keys())
            
            if not items:
                self._stop_event.wait(0.5)
                continue
            
            # 智能生成待填充列表
            to_fill = []
            filled_keys = set(cache_keys)
            half = self._max_size // 2
            
            # ① 当前区域（优先填）
            start_cur = max(0, current_idx - half)
            end_cur = min(len(items), current_idx + half)
            for i in range(start_cur, end_cur):
                item = items[i]
                if item not in filled_keys:
                    to_fill.append((0, i, item))
                    filled_keys.add(item)
            
            # ② 从头填
            for i in range(0, start_cur):
                item = items[i]
                if item not in filled_keys:
                    to_fill.append((1, i, item))
                    filled_keys.add(item)
            
            # ③ 当前区域之后
            for i in range(end_cur, len(items)):
                item = items[i]
                if item not in filled_keys:
                    to_fill.append((2, i, item))
                    filled_keys.add(item)
                if len(to_fill) >= self._max_size:
                    break
            
            # 按优先级排序
            to_fill.sort(key=lambda x: (x[0], x[1]))
            to_fill = [(i, item) for _, i, item in to_fill[:self._max_size]]
            
            if not to_fill:
                self._stop_event.wait(0.5)
                continue
            
            # 逐个生成图表
            for i, item in to_fill:
                if self._stop_event.is_set():
                    break
                try:
                    fig = self._build_fn(self._df, item)
                    plt.close(fig)
                    with self._lock:
                        # LRU 淘汰
                        if len(self._cache) >= self._max_size:
                            oldest_key = next(iter(self._cache))
                            old_fig = self._cache.pop(oldest_key, None)
                            if old_fig:
                                try:
                                    old_fig.clf()
                                except Exception:
                                    pass
                        self._cache[item] = fig
                except Exception:
                    with self._lock:
                        self._cache[item] = None
            
            self._stop_event.wait(0.1)
    
    def prefetch_sync(self, test_item):
        """同步获取：缓存命中直接返回，未命中则同步生成"""
        with self._lock:
            if test_item in self._cache:
                return self._cache[test_item]
        
        # 不在缓存：同步生成
        if self._df is None or self._build_fn is None:
            return None
        try:
            fig = self._build_fn(self._df, test_item)
            with self._lock:
                self._cache[test_item] = fig
            return fig
        except Exception:
            with self._lock:
                self._cache[test_item] = None
            return None
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            for fig in self._cache.values():
                if fig:
                    try:
                        fig.clf()
                    except Exception:
                        pass
            self._cache.clear()
        self.stop()