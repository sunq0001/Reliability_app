"""
image_viewer.py - 抓图查看弹窗模块
按读点分行显示所有场景图片，点击缩略图放大。
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
        self._current_fuse_id = None
        self._current_ts = None
        # 新结构：{读点名: [(场景名, 路径), ...]}
        self._images_by_readpoint = {}
        self._fullscreen_win = None
        self._grid_frame = None
        self._info_label = None
        self._canvas_list = []  # 防止 GC

    # ---- 对外 API ----

    def show_for_timestamp(self, timestamp, readpoint=None, fuse_id=None):
        """按时间戳显示图片（保持兼容性）"""
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

        # 转换为新结构
        self._images_by_readpoint = {readpoint or '图片': [(self._get_img_type(os.path.basename(p)), p) for p in paths]}
        self._current_fuse_id = fuse_id
        self._current_ts = timestamp

        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._rebuild_grid()
            self._update_title()
        else:
            self._build_window()

    def show_for_fuse(self, fuse_id, readpoint=None):
        """
        按FuseID显示图片：获取该芯片所有读点的图片
        
        布局：每行一个读点，显示该读点下所有场景图片
        """
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

        self._current_fuse_id = fuse_id
        self._current_ts = ts

        # 按读点分组图片
        self._images_by_readpoint = self._group_images_by_readpoint(paths)

        if not self._images_by_readpoint:
            messagebox.showinfo("未找到图片", "无法按读点分组图片")
            return

        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._rebuild_grid()
            self._update_title()
        else:
            self._build_window()

    def show_images_by_readpoint(self, fuse_id, images_by_readpoint):
        """
        直接接收按读点分组的图片数据并显示

        参数:
            fuse_id: FuseID 字符串
            images_by_readpoint: {读点名: [(场景名, 路径), ...]}
        """
        if not images_by_readpoint:
            messagebox.showinfo("未找到图片", "没有可显示的图片")
            return

        self._current_fuse_id = fuse_id
        self._current_ts = None
        self._images_by_readpoint = images_by_readpoint

        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._rebuild_grid()
            self._update_title()
        else:
            self._build_window()

    def _group_images_by_readpoint(self, paths):
        """
        将图片路径按读点分组
        
        返回: {读点名: [(场景名, 路径), ...]}
        """
        from src.project_scanner import ReadPointInfo
        result = {}
        
        # 从扫描结果获取读点信息
        scan_result = self.get_scan()
        
        for path in paths:
            # 从路径解析读点名
            # 路径格式: .../168H/image/时间戳/xxx.png
            # 或: .../168H/image/xxx.png
            rp_name = self._extract_readpoint_from_path(path, scan_result)
            
            if rp_name not in result:
                result[rp_name] = []
            
            scene_name = self._get_img_type(os.path.basename(path))
            result[rp_name].append((scene_name, path))
        
        # 按读点名称排序
        sorted_result = {}
        for rp_name in sorted(result.keys()):
            sorted_result[rp_name] = result[rp_name]
        
        return sorted_result

    def _extract_readpoint_from_path(self, path, scan_result):
        """从路径提取读点名"""
        # 尝试从路径中找到读点文件夹名
        parts = path.replace('\\', '/').split('/')
        
        # 查找常见的读点模式：数字H, T数字
        import re
        for part in parts:
            match = re.search(r'(\d+)H', part, re.IGNORECASE)
            if match:
                return f"RP{match.group(1)}"
            match = re.search(r'T(\d+)', part, re.IGNORECASE)
            if match:
                return f"T{match.group(1)}"
        
        # 备用：返回最后一个有意义的文件夹名
        for part in reversed(parts):
            if part and part not in ['image', 'Image', 'IMG']:
                return part
        
        return '未知'

    # ---- 窗口构建 ----

    def _build_window(self):
        win = tk.Toplevel(self.root)
        win.title("抓图查看")
        win.geometry("1200x800")
        win.configure(bg='#1a1a2e')

        self._win = win
        win.protocol("WM_DELETE_WINDOW", self._close)

        self._build_content(win)

    def _build_content(self, win):
        # 顶部标题栏
        header = tk.Frame(win, bg='#16213e', height=48)
        header.pack(fill='x', side='top')
        header.pack_propagate(False)

        self._title_label = tk.Label(header, font=('Microsoft YaHei', 11, 'bold'),
                                     bg='#16213e', fg='#e0e0e0', anchor='w')
        self._title_label.pack(side='left', padx=12, pady=8, fill='x', expand=True)

        self._count_label = tk.Label(header, font=('Microsoft YaHei', 9),
                                     bg='#16213e', fg='#888')
        self._count_label.pack(side='right', padx=12, pady=8)

        # 图片显示区域（可滚动）
        self._scroll_frame = tk.Frame(win, bg='#1a1a2e')
        self._scroll_frame.pack(fill='both', expand=True, padx=8, pady=8)

        # Canvas + Scrollbar 实现滚动
        self._canvas = tk.Canvas(self._scroll_frame, bg='#1a1a2e', highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(self._scroll_frame, orient='vertical',
                                        command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side='right', fill='y')
        self._canvas.pack(side='left', fill='both', expand=True)

        # 实际内容frame放在canvas内
        self._grid_frame = tk.Frame(self._canvas, bg='#1a1a2e')
        self._canvas_window = self._canvas.create_window((0, 0), window=self._grid_frame, anchor='nw')

        # 绑定配置事件
        self._grid_frame.bind('<Configure>', self._on_frame_configure)
        self._canvas.bind('<Configure>', self._on_canvas_configure)

        # 鼠标滚轮滚动
        self._canvas.bind('<MouseWheel>', lambda e: self._canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))

        # 先更新标题，再构建网格
        self._update_title()
        self._rebuild_grid()

    def _on_frame_configure(self, event=None):
        """更新滚动区域"""
        self._canvas.configure(scrollregion=self._canvas.bbox('all'))

    def _on_canvas_configure(self, event=None):
        """Canvas大小改变时更新内部窗口宽度"""
        if self._canvas_window:
            self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _update_title(self):
        """更新标题"""
        parts = []
        if self._current_fuse_id:
            parts.append(f"FuseID: {self._current_fuse_id}")
        if self._current_ts:
            parts.append(f"时间: {self._format_ts(self._current_ts)}")
        
        total_images = sum(len(imgs) for imgs in self._images_by_readpoint.values())
        self._title_label.config(text="  |  ".join(parts) if parts else "抓图查看")
        self._count_label.config(text=f"共 {total_images} 张 / {len(self._images_by_readpoint)} 个读点")

    def _rebuild_grid(self):
        """
        按场景名行 x 读点列 显示图片矩阵

        布局:
        |           | 168H        | 500H        | 1000H       |
        |-----------|-------------|-------------|-------------|
        | Dark      | 时间戳/图片 | 时间戳/图片 | (无)        |
        | Dark2     | 时间戳/图片 | 时间戳/图片 | 时间戳/图片 |
        | Mid1A1D   | 时间戳/图片 | (无)        | 时间戳/图片 |
        """
        if not self._grid_frame:
            return

        for w in list(self._grid_frame.winfo_children()):
            w.destroy()
        self._canvas_list.clear()

        if not self._images_by_readpoint:
            tk.Label(self._grid_frame, text="无图片", bg='#1a1a2e',
                    fg='#666', font=('Microsoft YaHei', 14)).pack(pady=40)
            return

        # 收集所有读点和场景名
        readpoints = sorted(self._images_by_readpoint.keys())
        scene_matrix = {}  # {场景名: {读点心: (场景名, 路径)}}

        for rp_name, images in self._images_by_readpoint.items():
            for scene_name, path in images:
                if scene_name not in scene_matrix:
                    scene_matrix[scene_name] = {}
                scene_matrix[scene_name][rp_name] = (scene_name, path)

        scenes = sorted(scene_matrix.keys())

        if not scenes:
            tk.Label(self._grid_frame, text="无有效图片", bg='#1a1a2e',
                    fg='#666', font=('Microsoft YaHei', 14)).pack(pady=40)
            return

        # 创建表格布局
        cell_width = 200
        cell_height = 180

        # 第0行：列标题（读点名）
        header_row = tk.Frame(self._grid_frame, bg='#1a1a2e')
        header_row.pack(fill='x', pady=(0, 2))

        # 空单元格（左上角）
        tk.Frame(header_row, width=100, height=36, bg='#16213e').pack(side='left', padx=(0, 2))

        # 读点列标题
        for rp_name in readpoints:
            cell = tk.Frame(header_row, width=cell_width, height=36, bg='#2d4a6e')
            cell.pack(side='left', padx=2)
            cell.pack_propagate(False)
            tk.Label(cell, text=rp_name, font=('Microsoft YaHei', 10, 'bold'),
                    bg='#2d4a6e', fg='#ffffff', anchor='center').pack(fill='both', expand=True)

        # 每一行：一个场景名 + 该场景在各读点的图片
        for scene_name in scenes:
            # 场景名标签行
            scene_row = tk.Frame(self._grid_frame, bg='#1a1a2e')
            scene_row.pack(fill='x', pady=(0, 2))

            # 场景名（左列标题）
            scene_cell = tk.Frame(scene_row, width=100, height=cell_height, bg='#252540')
            scene_cell.pack(side='left', padx=(0, 2))
            scene_cell.pack_propagate(False)

            type_name = self.TYPE_NAMES.get(scene_name, scene_name)
            tk.Label(scene_cell, text=type_name, font=('Microsoft YaHei', 9, 'bold'),
                    bg='#252540', fg='#7eb8da', anchor='center', wraplength=90,
                    justify='center').pack(fill='both', expand=True)

            # 该场景在各读点的图片
            for rp_name in readpoints:
                cell_data = scene_matrix.get(scene_name, {}).get(rp_name)
                cell = tk.Frame(scene_row, width=cell_width, height=cell_height, bg='#1a1a2e')
                cell.pack(side='left', padx=2)
                cell.pack_propagate(False)

                if cell_data:
                    _, path = cell_data
                    self._add_thumbnail_in_cell(cell, scene_name, path)
                else:
                    # 无图片
                    tk.Label(cell, text="无数据", bg='#1a1a2e', fg='#555',
                            font=('Microsoft YaHei', 8)).pack(fill='both', expand=True)

        self._on_frame_configure()

    def _add_thumbnail_in_cell(self, parent, scene_name, path):
        """在表格单元格中添加缩略图（带时间戳）"""
        # 提取时间戳用于显示
        ts = self._extract_timestamp_from_path(path)

        cell = tk.Frame(parent, bg='#252540')
        cell.pack(fill='both', expand=True, padx=2, pady=2)

        # 时间戳标签
        if ts:
            ts_display = self._format_ts(ts) if len(ts) >= 14 else ts
            tk.Label(cell, text=ts_display, font=('Microsoft YaHei', 7),
                    bg='#2a2a45', fg='#888', anchor='w').pack(fill='x', padx=2, pady=(2, 0))

        # 图片区域
        img_area = tk.Frame(cell, bg='#1a1a2e')
        img_area.pack(fill='both', expand=True)

        try:
            fig = Figure(figsize=(1.8, 1.5), dpi=60)
            fig.patch.set_facecolor('#1a1a2e')
            ax = fig.add_axes([0, 0, 1, 1])
            ax.axis('off')

            img = Image.open(path)
            orig_mode = img.mode

            if orig_mode in ('I;16', 'I;16L', 'I;16B'):
                import numpy as np
                arr = np.array(img)
                ax.imshow(img, cmap='gray', vmin=0, vmax=65535)
            else:
                ax.imshow(img, cmap='gray')

            canvas = FigureCanvasTkAgg(fig, master=img_area)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
            self._canvas_list.append(canvas)

            canvas.mpl_connect('button_press_event',
                lambda event, p=path: self._on_click(event, p))

        except Exception as ex:
            tk.Label(img_area, text=f"加载失败", bg='#1a1a2e',
                    fg='#e74c3c', font=('Microsoft YaHei', 7)).pack(pady=10)

    def _extract_timestamp_from_path(self, path):
        """从文件路径提取时间戳"""
        import re
        # 匹配 14 位数字时间戳
        match = re.search(r'(\d{14})', path)
        return match.group(1) if match else None

    def _on_click(self, event, path):
        """点击缩略图：全屏显示原图"""
        self._show_fullscreen(path)

    def _show_fullscreen(self, path):
        """全屏显示原图"""
        if not os.path.exists(path):
            messagebox.showerror("错误", f"图片文件不存在:\n{path}")
            return

        # 关闭已有窗口
        if self._fullscreen_win and self._fullscreen_win.winfo_exists():
            self._fullscreen_win.destroy()

        win = tk.Toplevel(self.root)
        self._fullscreen_win = win
        win.title(os.path.basename(path))
        win.state('zoomed')  # 最大化窗口

        # 深色背景
        win.configure(bg='#000000')

        # 关闭按钮
        btn_frame = tk.Frame(win, bg='#1a1a1a', height=40)
        btn_frame.pack(fill='x', side='top')
        btn_frame.pack_propagate(False)
        tk.Button(btn_frame, text='关闭', command=win.destroy,
                bg='#333', fg='white', relief='flat', cursor='hand1',
                font=('Microsoft YaHei', 10), padx=20, pady=5).pack(side='right', padx=10, pady=5)

        # 图片显示区域
        img_frame = tk.Frame(win, bg='#000000')
        img_frame.pack(fill='both', expand=True)

        try:
            fig = Figure(figsize=(12, 8), dpi=100)
            fig.patch.set_facecolor('#000000')
            ax = fig.add_axes([0, 0, 1, 1])
            ax.axis('off')

            img = Image.open(path)
            orig_mode = img.mode

            # 16位图像处理
            if orig_mode in ('I;16', 'I;16L', 'I;16B'):
                import numpy as np
                ax.imshow(img, cmap='gray', vmin=0, vmax=65535)
            else:
                ax.imshow(img, cmap='gray')

            canvas = FigureCanvasTkAgg(fig, master=img_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)

        except Exception as ex:
            tk.Label(img_frame, text=f"加载失败:\n{str(ex)}", bg='#000000',
                    fg='#e74c3c', font=('Microsoft YaHei', 12)).pack(pady=50)

        # ESC 关闭
        def on_key(event):
            if event.keysym == 'Escape':
                win.destroy()
        win.bind('<Key>', on_key)
        win.protocol("WM_DELETE_WINDOW", win.destroy)

    # ---- 辅助方法 ----

    def _get_img_type(self, filename):
        """从文件名识别图片类型"""
        name_lower = filename.lower()
        if 'dark2' in name_lower:
            return 'dark2'
        elif 'dark' in name_lower:
            return 'dark'
        elif 'mid' in name_lower or '1a1d' in name_lower:
            return 'mid'
        elif 'testpattern' in name_lower:
            return 'testpattern'
        return 'other'

    @staticmethod
    def _format_ts(ts):
        """14位时间戳转友好格式"""
        s = str(ts)
        if len(s) >= 14:
            return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}:{s[12:14]}"
        return str(ts)

    def _close(self):
        """关闭窗口"""
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None
