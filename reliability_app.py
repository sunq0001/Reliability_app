"""
可靠性测试数据分析工具 - Tkinter版本
Reliability Test Data Analysis Tool
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import re
import pandas as pd
import numpy as np

# Matplotlib 后端配置
# - 主线程用 TkAgg（Tk 事件循环），用于 FigureCanvasTkAgg 嵌入窗口
# - 后台预生成线程在内部切 Agg（由 ThreadSafeChartCache._prefill_worker 调用）
import matplotlib
matplotlib.use('TkAgg')  # 必须在 import pyplot 之前设置
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# UI 主题配置
from src.ui_theme import (
    configure_ttk_styles,
    FONT_YAHEI, FONT_CONSOLA,
    FONT_TEXT, FONT_TEXT_BOLD, FONT_TEXT_SMALL, FONT_TEXT_TITLE,
    FONT_MONO,
    COLOR_BG_DARK, COLOR_BG_LIGHT, COLOR_BG_CARD, COLOR_BG_HEADER,
    COLOR_TEXT_DARK, COLOR_TEXT_MID, COLOR_TEXT_LIGHT, COLOR_TEXT_WHITE,
    COLOR_PRIMARY, COLOR_PRIMARY_HOVER, COLOR_PRIMARY_LIGHT,
    COLOR_SUCCESS, COLOR_WARNING, COLOR_ERROR, COLOR_INFO,
    COLOR_BORDER,
    PAD_SM, PAD_MD, PAD_LG,
    tk_btn_config, tk_btn_primary_config, tk_btn_success_config,
    ttk_label_config, tk_entry_config,
    ICON_SUCCESS, ICON_WARNING, ICON_ERROR,
)

# ---- 抽取到 src/ 模块的组件 ----
from src.chart_builder import (
    configure_matplotlib_chinese,
    build_chart_for_item,
    sort_read_points as cb_sort_read_points,
    ThreadSafeChartCache,
)
from src.ui_components import make_path_tooltip
from src.chart_viewer import ChartViewer
from src.ui_components import TestItemSelector
from src.image_viewer import ImageViewer
from src.image_scanner import scan_image_root
from src.project_scanner import scan_project, ProjectScanResult, ReadPointInfo
from src.utils import format_ts_for_display, sanitize_filename
from src.event_handlers import EventHandlers



class ReliabilityAnalysisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("可靠性测试数据分析工具 v0.1")
        self.root.geometry("1200x860")
        self.root.minsize(900, 600)
        
        # 设置样式（使用 ui_theme）
        self.style = ttk.Style()
        self.style.theme_use('clam')
        configure_ttk_styles(self.root)
        
        # 配置 Matplotlib 中文字体（全局生效）
        configure_matplotlib_chinese()
        
        # 存储选择的路径
        self.read_point_folders = {}  # {时间点: 路径}
        
        # 项目扫描结果
        self._project_scan_result: ProjectScanResult = None
        
        # 事件处理器
        self._handlers = EventHandlers(self)

        # ---- 图表查看器（委托给 src/chart_viewer.py）----
        self._chart_viewer = ChartViewer(root, callbacks={
            'get_chart_items':  lambda: self._chart_items,
            'get_current_df':   lambda: self._current_df,
            'get_chart_cache':  lambda: getattr(self, '_chart_cache', None),
            'build_chart':      lambda item: build_chart_for_item(self._current_df, item),
            'log':              lambda msg: self.log(msg),
            'open_image_viewer': self._open_image_viewer,
        })

        # ---- 测试项选择器（延迟初始化，见 create_ui 末尾）----
        self._test_item_selector = None
        self._selected_test_items = set()
        self._all_test_items = []

        # ---- 抓图扫描结果（供 ImageViewer 使用）----
        self._image_scan_result = None

        # ---- 图片查看器（延迟初始化）----
        self._image_viewer = ImageViewer(
            root=root,
            get_image_scan_result_fn=lambda: self._image_scan_result,
            get_df_fn=lambda: getattr(self, '_current_df', None),
        )

        # 创建UI
        self.create_ui()
        
    def create_ui(self):
        """创建所有UI组件"""
        BG = COLOR_BG_LIGHT
        
        # ========== 标题栏 ==========
        title_bar = tk.Frame(self.root, bg=COLOR_PRIMARY, pady=12)
        title_bar.pack(fill='x')
        
        tk.Label(title_bar,
                 text="可靠性测试数据分析工具",
                 font=(FONT_YAHEI, 16, "bold"),
                 bg=COLOR_PRIMARY, fg='white').pack()
        tk.Label(title_bar,
                 text="自动扫描测试项 · 整合多时间读点数据 · 生成分析图表和PPT报告",
                 font=FONT_TEXT,
                 bg=COLOR_PRIMARY, fg='#bfdbfe').pack(pady=(2, 0))
        
        # ========== 主体：左右可拖动分栏 ==========
        paned = tk.PanedWindow(self.root, orient='horizontal',
                               sashwidth=6, sashrelief='raised', sashpad=0,
                               bg='#d1d5db', relief='flat', bd=0)
        paned.pack(fill='both', expand=True, padx=0, pady=0)
        
        # ----- 左侧：配置面板（可滚动） -----
        left_outer = tk.Frame(paned, bg=BG)
        
        # Canvas + 滚动条 实现左侧可滚动
        self.left_canvas = tk.Canvas(left_outer, bg=BG, highlightthickness=0)
        left_scrollbar = ttk.Scrollbar(left_outer, orient='vertical',
                                        command=self.left_canvas.yview)
        self.left_canvas.configure(yscrollcommand=left_scrollbar.set)
        
        left_scrollbar.pack(side='right', fill='y')
        self.left_canvas.pack(side='left', fill='both', expand=True)
        
        left_frame = ttk.Frame(self.left_canvas, padding="12")
        self.left_canvas.create_window((0, 0), window=left_frame, anchor='nw')
        left_frame.bind('<Configure>',
                        lambda e: self.left_canvas.configure(
                            scrollregion=self.left_canvas.bbox('all')))
        self.left_canvas.bind_all(
            '<MouseWheel>',
            lambda e: self.left_canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))
        
        paned.add(left_outer, minsize=380, stretch='always')
        
        # ----- 右侧：处理结果（Notebook 双标签页）-----
        right_outer = tk.Frame(paned, bg=BG)
        
        self.right_notebook = ttk.Notebook(right_outer)
        self.right_notebook.pack(fill='both', expand=True, padx=8, pady=(8, 0))
        
        # 标签1: 日志
        self.log_tab = tk.Frame(self.right_notebook, bg='#ffffff')
        self.right_notebook.add(self.log_tab, text='日志')
        
        # 标签2: 图表
        self.chart_tab = tk.Frame(self.right_notebook, bg='#ffffff')
        self.right_notebook.add(self.chart_tab, text='图表')
        
        paned.add(right_outer, minsize=320, stretch='always')
        
        # 初始化 sash 位置（左侧约450px）
        self.root.update_idletasks()
        try:
            paned.sash_place(0, 450, 0)
        except Exception:
            pass
        
        # ========== 填充内容 ==========
        self.create_folder_selection(left_frame)
        self.create_result_panel(self.log_tab)
        self.create_chart_viewer(self.chart_tab)
        
        # ========== 底部：操作按钮 ==========
        self.create_action_buttons()

        # ---- 延迟初始化：测试项选择弹窗（需等 UI 完全创建后）----
        self._test_item_selector = TestItemSelector(
            parent=self.root,
            all_items=self._all_test_items,
            selected_items=self._selected_test_items,
            count_var=self.test_item_count_var,
            log_fn=lambda msg: self.log(msg),
        )

    def create_folder_selection(self, parent):
        """创建文件夹选择区域"""

        # ========== 第一行：项目目录配置 ==========
        project_frame = ttk.LabelFrame(parent, text="项目目录", padding=PAD_MD)
        project_frame.pack(fill='x', pady=(0, PAD_MD))

        # 根目录选择行
        proj_row1 = ttk.Frame(project_frame)
        proj_row1.pack(fill='x')

        ttk.Label(proj_row1, text="目录:", width=5).pack(side='left')
        self._project_path_var = tk.StringVar(value="未选择")
        self._project_path_display_var = tk.StringVar(value="未选择")

        def _update_proj_display(*_):
            full = self._project_path_var.get()
            if not full or full == "未选择":
                self._project_path_display_var.set("未选择")
            else:
                self._project_path_display_var.set(
                    ('...' + full[-20:]) if len(full) > 23 else full
                )

        self._project_path_var.trace_add('write', _update_proj_display)

        proj_label = ttk.Label(proj_row1, textvariable=self._project_path_display_var,
                              foreground=COLOR_TEXT_MID, width=18)
        proj_label.pack(side='left', padx=(PAD_SM, PAD_MD))
        make_path_tooltip(proj_label, self._project_path_var)

        tk.Button(proj_row1, text="加载目录",
                 command=self._select_and_load_project,
                 **tk_btn_primary_config()).pack(side='left')

        self._project_status_var = tk.StringVar(value="请选择项目根目录或读点目录")
        status_label = ttk.Label(proj_row1, textvariable=self._project_status_var,
                                font=FONT_TEXT_SMALL, foreground=COLOR_TEXT_MID)
        status_label.pack(side='left', padx=(PAD_MD, 0))

        # ========== 第二行：时间读点配置 ==========
        read_point_frame = ttk.LabelFrame(parent, text="时间读点配置", padding=8)
        read_point_frame.pack(fill='x', pady=(0, PAD_SM))

        ttk.Label(read_point_frame, text="扫描后将自动识别读点，可手动调整:").pack(anchor='w', pady=(0, 4))

        # 读点容器
        self.read_point_container = ttk.Frame(read_point_frame)
        self.read_point_container.pack(fill='x')

        self.read_point_widgets = []
        self.read_point_data = {}
        self._project_scan_result = None  # 存储扫描结果

        # 默认占位行（扫描后会被替换）
        default_read_points = ["0H", "168H", "500H", "1000H"]
        for name in default_read_points:
            self._create_read_point_row(name)

        # 底部按钮行
        add_btn_frame = ttk.Frame(read_point_frame)
        add_btn_frame.pack(fill='x', pady=(PAD_SM, 0))

        self.new_read_point_entry = ttk.Entry(add_btn_frame, width=10)
        self.new_read_point_entry.insert(0, "新增读点")
        self.new_read_point_entry.pack(side='left')
        self.new_read_point_entry.bind('<FocusIn>', self._handlers._on_entry_focus_in)
        self.new_read_point_entry.bind('<FocusOut>', self._handlers._on_entry_focus_out)

        ttk.Button(add_btn_frame, text="添加", width=6,
                   command=self._add_read_point).pack(side='left', padx=(PAD_SM, 0))

        self._analysis_btn = tk.Button(
            add_btn_frame, text="开始分析", width=8,
            command=self.start_analysis,
            bg='#1e40af', fg='white', relief='flat',
            cursor='hand1', font=('Microsoft YaHei', 8, 'bold'),
            activebackground='#1d4ed8', activeforeground='white')
        self._analysis_btn.pack(side='right')

        # ========== 第三行：漂移检测标准 ==========
        drift_frame = ttk.LabelFrame(parent, text="漂移检测标准", padding=8)
        drift_frame.pack(fill='x', pady=(0, PAD_SM))

        # 三个规则并排一行
        rule_bar = ttk.Frame(drift_frame)
        rule_bar.pack(fill='x')

        self.rule1_enabled = tk.BooleanVar(value=True)
        self.rule2_enabled = tk.BooleanVar(value=True)
        self.rule3_enabled = tk.BooleanVar(value=True)
        self.rule1_threshold = tk.StringVar(value="30")
        self.rule2_threshold = tk.StringVar(value="50")
        self.rule3_threshold = tk.StringVar(value="30")

        # 规则1
        f1 = ttk.Frame(rule_bar)
        f1.pack(side='left', padx=(0, 12))
        ttk.Checkbutton(f1, text="①", variable=self.rule1_enabled, width=3).pack(side='left')
        ttk.Label(f1, text="偏离>").pack(side='left')
        ttk.Entry(f1, textvariable=self.rule1_threshold, width=4).pack(side='left', padx=2)
        ttk.Label(f1, text="%").pack(side='left')

        # 规则2
        f2 = ttk.Frame(rule_bar)
        f2.pack(side='left', padx=(0, 12))
        ttk.Checkbutton(f2, text="②", variable=self.rule2_enabled, width=3).pack(side='left')
        ttk.Label(f2, text="漂移>").pack(side='left')
        ttk.Entry(f2, textvariable=self.rule2_threshold, width=4).pack(side='left', padx=2)
        ttk.Label(f2, text="%").pack(side='left')

        # 规则3
        f3 = ttk.Frame(rule_bar)
        f3.pack(side='left', padx=(0, 12))
        ttk.Checkbutton(f3, text="③", variable=self.rule3_enabled, width=3).pack(side='left')
        ttk.Label(f3, text="增量>").pack(side='left')
        ttk.Entry(f3, textvariable=self.rule3_threshold, width=4).pack(side='left', padx=2)
        ttk.Label(f3, text="%").pack(side='left')

        # 分析上限
        limit_row = ttk.Frame(drift_frame)
        limit_row.pack(fill='x', pady=(5, 0))
        ttk.Label(limit_row, text="分析上限:").pack(side='left')
        self.analysis_limit = tk.StringVar(value="100")
        ttk.Entry(limit_row, textvariable=self.analysis_limit, width=5).pack(side='left', padx=4)
        ttk.Label(limit_row, text="项（0=全部）").pack(side='left')
        ttk.Button(limit_row, text="全选", width=4,
                   command=lambda: self._toggle_all_rules(True)).pack(side='right')
        ttk.Button(limit_row, text="全关", width=4,
                   command=lambda: self._toggle_all_rules(False)).pack(side='right', padx=(0, 4))

        # ========== 第四行：测试项选择 ==========
        test_item_frame = ttk.LabelFrame(parent, text="测试项选择", padding=8)
        test_item_frame.pack(fill='x', pady=(0, PAD_SM))

        trigger_frame = ttk.Frame(test_item_frame)
        trigger_frame.pack(fill='x')

        self.test_item_count_var = tk.StringVar(value="点击选择测试项...")
        tk.Button(trigger_frame, textvariable=self.test_item_count_var,
                 command=self._open_selector,
                 bg='#eff6ff', fg='#1e40af',
                 font=('Microsoft YaHei', 9), relief='groove',
                 cursor='hand1', pady=3).pack(side='left', fill='x', expand=True)

        tk.Button(trigger_frame, text="重新扫描", width=7,
                 command=self._scan_test_items,
                 bg='#f3f4f6', fg='#374151',
                 font=('Microsoft YaHei', 9),
                 relief='flat', cursor='hand1',
                 activebackground='#e5e7eb').pack(side='left', padx=(6, 0))

        ttk.Label(test_item_frame, text="Ctrl+多选  Shift+连选  空格过滤",
                font=('Microsoft YaHei', 7), foreground='gray').pack(anchor='w')

        self._all_test_items = []
        self._filtered_test_items = []
        self._selected_test_items = set()
    def create_result_panel(self, parent):
        """创建日志面板"""
        # 顶部：读点信息表格
        self._info_tree = ttk.Treeview(parent, columns=('读点', '文件夹', '数据文件', '抓图目录'),
                                       show='headings', height=5)
        self._info_tree.heading('读点', text='读点')
        self._info_tree.heading('文件夹', text='文件夹')
        self._info_tree.heading('数据文件', text='数据文件')
        self._info_tree.heading('抓图目录', text='抓图目录')
        self._info_tree.column('读点', width=70, anchor='center')
        self._info_tree.column('文件夹', width=100, anchor='w')
        self._info_tree.column('数据文件', width=200, anchor='w')
        self._info_tree.column('抓图目录', width=200, anchor='w')
        self._info_tree.pack(fill='x', padx=8, pady=(8, 4))

        # 底部：日志文本
        scroll_y = ttk.Scrollbar(parent, orient='vertical')
        self.result_text = tk.Text(parent,
                                    yscrollcommand=scroll_y.set,
                                    font=FONT_MONO,
                                    bg=COLOR_BG_CARD, fg=COLOR_TEXT_DARK,
                                    insertbackground=COLOR_INFO,
                                    selectbackground=COLOR_PRIMARY_LIGHT,
                                    relief='flat', bd=0,
                                    padx=8, pady=8,
                                    wrap='word')
        scroll_y.config(command=self.result_text.yview)
        scroll_y.pack(side='right', fill='y')
        self.result_text.pack(side='left', fill='both', expand=True)

        self.result_text.tag_config('title', font=FONT_MONO, foreground=COLOR_PRIMARY)
        self.result_text.tag_config('info', foreground=COLOR_INFO)
        self.result_text.tag_config('success', foreground=COLOR_SUCCESS)
        self.result_text.tag_config('warning', foreground=COLOR_WARNING)
        self.result_text.tag_config('error', foreground=COLOR_ERROR)
    
    def create_chart_viewer(self, parent):
        """创建图表查看器占位（实际内容委托给 ChartViewer）"""
        self._chart_items = []       # 测试项名称列表
        self._chart_cache = ThreadSafeChartCache(max_size=30)  # 后台预生成缓存

        # 在 tab 里放一个引导按钮，点此打开弹窗
        guide = tk.Frame(parent, bg=COLOR_BG_LIGHT)
        guide.pack(fill='both', expand=True)
        tk.Label(
            guide, text='图表查看器', font=FONT_TEXT_TITLE,
            bg=COLOR_BG_LIGHT, fg=COLOR_TEXT_MID
        ).pack(pady=(40, 8))
        tk.Label(
            guide, text='先生成分析图表后，点击下方按钮打开弹窗查看',
            bg=COLOR_BG_LIGHT, fg=COLOR_TEXT_LIGHT, font=FONT_TEXT
        ).pack()
        self._open_chart_btn = tk.Button(
            guide, text='打开图表查看器', font=FONT_TEXT_BOLD,
            bg=COLOR_INFO, fg='white', relief='flat', cursor='hand1',
            padx=20, pady=8, command=self._chart_viewer.open
        )
        self._open_chart_btn.pack(pady=16)
        self._chart_placeholder = guide
        self._open_chart_btn.config(state='disabled')
    

    def create_action_buttons(self):
        """创建底部操作按钮"""
        btn_frame = tk.Frame(self.root, bg=COLOR_PRIMARY, pady=8)
        btn_frame.pack(fill='x', side='bottom')
        
        # 按钮样式
        btn_style = {
            'bg': COLOR_BG_CARD, 'fg': COLOR_PRIMARY,
            'font': FONT_TEXT_BOLD,
            'relief': 'flat', 'cursor': 'hand1',
            'padx': 14, 'pady': 5,
            'activebackground': COLOR_PRIMARY_LIGHT, 'activeforeground': COLOR_PRIMARY,
            'bd': 0
        }
        tk.Button(btn_frame, text='生成图表',   command=self.generate_charts,  **btn_style).pack(side='left', padx=6)
        tk.Button(btn_frame, text='生成PPT报告', command=self.generate_ppt,      **btn_style).pack(side='left', padx=6)
        tk.Button(btn_frame, text='打开输出目录', command=self.open_output_dir,   **btn_style).pack(side='left', padx=6)
        
        # 右侧退出按钮
        exit_style = dict(btn_style)
        exit_style['bg'] = COLOR_TEXT_DARK
        exit_style['fg'] = COLOR_TEXT_WHITE
        exit_style['activebackground'] = COLOR_TEXT_MID
        exit_style['activeforeground'] = COLOR_TEXT_WHITE
        tk.Button(btn_frame, text='退出', command=self.root.quit, **exit_style).pack(side='right', padx=(6, 16))
        
    # ========== 事件处理方法 ==========
    
    def log(self, message, tag='info'):
        """在结果区域显示日志"""
        self.result_text.insert('end', message + '\n', tag)
        self.result_text.see('end')
        self.root.update_idletasks()

    def _clear_read_point_rows(self):
        """清空所有读点行"""
        for name in list(self.read_point_widgets):
            if name in self.read_point_data:
                frame = self.read_point_data[name].get('frame')
                if frame:
                    frame.destroy()
                del self.read_point_data[name]
        self.read_point_widgets.clear()

    def _create_read_point_row(self, name, folder_name=None, data_file=None, image_folder=None):
        """创建单个时间读点的行"""
        row_frame = ttk.Frame(self.read_point_container)
        row_frame.pack(fill='x', pady=3)

        # 时间点名称（可编辑）
        display_name = folder_name if folder_name else name
        name_var = tk.StringVar(value=display_name)
        name_entry = ttk.Entry(row_frame, textvariable=name_var, width=10, font=('Microsoft YaHei', 9))
        name_entry.pack(side='left')

        # 存储内部名称（用于数据关联）
        inner_name = name
        name_var._inner_name = inner_name

        # 数据文件路径
        if data_file:
            data_path_var = tk.StringVar(value=data_file)
        else:
            data_path_var = tk.StringVar(value="未选择")

        # 抓图目录路径
        if image_folder:
            img_path_var = tk.StringVar(value=image_folder)
        else:
            img_path_var = tk.StringVar(value="未选择")

        # 数据文件显示
        data_display_var = tk.StringVar()
        def update_data_display(*_):
            full = data_path_var.get()
            if not full or full == "未选择":
                data_display_var.set("未选择")
            else:
                data_display_var.set('…' + full[-25:] if len(full) > 28 else full)

        data_path_var.trace_add('write', update_data_display)
        update_data_display()

        data_label = ttk.Label(row_frame, textvariable=data_display_var,
                              foreground='black' if data_file else 'gray', width=22)
        data_label.pack(side='left', padx=(5, 2))
        make_path_tooltip(data_label, data_path_var)

        def select_data():
            self._select_data_file(data_path_var)
            data_label.config(foreground='black')

        ttk.Button(row_frame, text="数据", command=select_data, width=5).pack(side='left')

        # 抓图目录显示
        img_display_var = tk.StringVar()
        def update_img_display(*_):
            full = img_path_var.get()
            if not full or full == "未选择":
                img_display_var.set("未选择")
            else:
                img_display_var.set('…' + full[-25:] if len(full) > 28 else full)

        img_path_var.trace_add('write', update_img_display)
        update_img_display()

        img_label = ttk.Label(row_frame, textvariable=img_display_var,
                              foreground='black' if image_folder else 'gray', width=22)
        img_label.pack(side='left', padx=(5, 2))
        make_path_tooltip(img_label, img_path_var)

        def select_img():
            self._select_image_path(img_path_var)
            img_label.config(foreground='black')

        ttk.Button(row_frame, text="抓图", command=select_img, width=5).pack(side='left')

        # 删除按钮
        if len(self.read_point_widgets) >= 3:
            def delete_row():
                row_frame.destroy()
                if name in self.read_point_data:
                    del self.read_point_data[name]
                if name in self.read_point_widgets:
                    self.read_point_widgets.remove(name)
                self.log(f"[已删除] 读点: {name}", 'warning')
            tk.Button(row_frame, text="\u00d7", command=delete_row, width=2,
                      bg='#f87171', fg='white', relief='flat',
                      font=('Arial', 10, 'bold'), cursor='hand1',
                      activebackground='#ef4444').pack(side='left', padx=(5, 0))

        # 保存控件引用
        self.read_point_widgets.append(name)
        self.read_point_data[name] = {
            'name_var': name_var,
            'data_path_var': data_path_var,
            'img_path_var': img_path_var,
            'frame': row_frame
        }

        return row_frame

    def _select_data_file(self, path_var):
        """选择数据文件"""
        file_path = filedialog.askopenfilename(
            title="选择数据文件",
            filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv"), ("所有文件", "*.*")]
        )
        if file_path:
            path_var.set(file_path)
            self.log(f"[已选择] 数据文件: {os.path.basename(file_path)}", 'success')

    def _select_image_path(self, path_var):
        """选择抓图目录"""
        folder_path = filedialog.askdirectory(title="选择抓图目录")
        if folder_path:
            path_var.set(folder_path)
            self.log(f"[已选择] 抓图目录: {os.path.basename(folder_path)}", 'success')
    
    def _select_read_point_path(self, name_var, path_var):
        """选择文件或文件夹"""
        time_point = name_var.get().strip()
        
        # 先尝试选择文件
        file_path = filedialog.askopenfilename(
            title=f"选择 {time_point} 数据文件（Excel）",
            filetypes=[("Excel文件", "*.xlsx *.xls *.csv"), ("所有文件", "*.*")]
        )
        
        if file_path:
            path_var.set(file_path)
            path_var._is_file = True
            self.log(f"[已选择] {time_point} 文件: {os.path.basename(file_path)}", 'success')
            return
        
        # 如果没选文件，尝试选择文件夹
        folder_path = filedialog.askdirectory(title=f"选择 {time_point} 数据文件夹（将搜索其中的Excel文件）")
        if folder_path:
            path_var.set(folder_path)
            path_var._is_folder = True
            # 检查文件夹中是否有Excel文件
            excel_files = self._find_excel_files(folder_path)
            if excel_files:
                self.log(f"[已选择] {time_point} 文件夹: {folder_path}", 'success')
                self.log(f"  → 找到 {len(excel_files)} 个Excel文件", 'info')
            else:
                self.log(f"[⚠️ 注意] {time_point} 文件夹中未找到Excel文件", 'warning')
    
    def _find_excel_files(self, folder_path):
        """在文件夹中搜索Excel文件（包括子文件夹）"""
        import glob
        excel_files = []
        
        for ext in ['*.xlsx', '*.xls', '*.csv']:
            files = glob.glob(os.path.join(folder_path, '**', ext), recursive=True)
            excel_files.extend(files)
        
        return list(set(excel_files))  # 去重
    
    def _add_read_point(self):
        """添加新的时间读点"""
        # 找到时间读点配置区域的frame
        read_point_frame = None
        for widget in self.read_point_data:
            if 'frame' in self.read_point_data[widget]:
                read_point_frame = self.read_point_data[widget]['frame'].master
                break
        
        if not read_point_frame:
            self.log("[错误] 无法添加读点", 'error')
            return
        
        new_name = self.new_read_point_entry.get().strip()
        if not new_name or new_name == "新增读点":
            messagebox.showwarning("提示", "请输入新读点名称（如2000H）")
            return
        
        # 检查是否已存在
        for name in self.read_point_data:
            if name == new_name:
                messagebox.showwarning("提示", f"读点 {new_name} 已存在")
                return
        
        self._create_read_point_row(new_name)
        self.new_read_point_entry.delete(0, 'end')
        self.new_read_point_entry.insert(0, "新增读点")
        self.log(f"[已添加] 新读点: {new_name}", 'success')
    


    def _select_image_root(self):
        """选择抓图根目录"""
        folder = filedialog.askdirectory(title="选择抓图根目录（包含各读点子文件夹，如 HTOL/）")
        if folder:
            self.image_root_path_var.set(folder)
            self._img_scan_status_var.set(f"已选择: {folder}  →  点击「扫描抓图」建立索引")
            if hasattr(self, '_scan_img_btn'):
                self._scan_img_btn.config(state='normal')
            self.log(f"[已选择] 抓图根目录: {folder}", 'success')

    def _do_image_scan(self):
        """扫描抓图目录，建立时间戳→图片映射"""
        root = self.image_root_path_var.get()
        if not root or root == "未选择":
            messagebox.showwarning("提示", "请先选择抓图根目录")
            return

        self._img_scan_status_var.set("🔍 正在扫描...")
        if hasattr(self, '_scan_img_btn'):
            self._scan_img_btn.config(state='disabled', text='扫描中...')
        self.root.update_idletasks()

        import threading
        def worker():
            result = scan_image_root(root)
            self.root.after(0, lambda: self._handlers._on_image_scan_done(result))

        threading.Thread(target=worker, daemon=True).start()


    def _open_image_viewer(self, fuse_id, readpoint=None, timestamp=None):
        """由 ChartViewer 的「查看抓图」按钮触发：显示对应芯片的所有抓图"""
        # 如果没有独立的抓图扫描结果，尝试从项目扫描结果获取
        if self._image_scan_result is None:
            from src.image_scanner import scan_image_root, find_images_for_fuse
            
            # 方式1: 从项目扫描结果获取
            if self._project_scan_result is not None:
                root_paths = set()
                for rp in self._project_scan_result.readpoints:
                    if rp.image_folder:
                        # image_folder 格式: .../读点文件夹/image/
                        # 获取上级目录作为抓图根目录
                        root_paths.add(os.path.dirname(os.path.dirname(rp.image_folder)))
                
                if root_paths:
                    combined_result = {
                        'readpoints': {},
                        'global_ts': {},
                        'stats': {'total_images': 0, 'readpoints_found': []}
                    }
                    for root in root_paths:
                        result = scan_image_root(root)
                        for rp_name, ts_map in result.get('readpoints', {}).items():
                            if rp_name not in combined_result['readpoints']:
                                combined_result['readpoints'][rp_name] = {}
                            for ts, paths in ts_map.items():
                                if ts not in combined_result['readpoints'][rp_name]:
                                    combined_result['readpoints'][rp_name][ts] = []
                                combined_result['readpoints'][rp_name][ts].extend(paths)
                        combined_result['stats']['total_images'] += result.get('stats', {}).get('total_images', 0)
                        combined_result['stats']['readpoints_found'].extend(result.get('stats', {}).get('readpoints_found', []))
                        for ts, paths in result.get('global_ts', {}).items():
                            if ts not in combined_result['global_ts']:
                                combined_result['global_ts'][ts] = []
                            combined_result['global_ts'][ts].extend(paths)
                    
                    self._image_scan_result = combined_result
                    self.log(f"[抓图] 从项目目录扫描到 {combined_result['stats']['total_images']} 张图片", 'info')
            
            # 方式2: 直接从 _project_scan_result 读取图片
            if self._image_scan_result is None and self._project_scan_result is not None:
                from src.project_scanner import get_all_images_by_readpoint
                combined_result = {
                    'readpoints': {},
                    'global_ts': {},
                    'stats': {'total_images': 0, 'readpoints_found': []}
                }
                df = getattr(self, '_current_df', None)
                if df is not None:
                    time_col = 1 if 1 in df.columns else ('Time' if 'Time' in df.columns else None)
                    fuse_col = 'FuseID' if 'FuseID' in df.columns else None
                    
                    # 找匹配 FuseID 的行
                    if fuse_col:
                        matched = df[df[fuse_col].astype(str).str.strip() == str(fuse_id).strip()]
                        if not matched.empty and time_col:
                            ts = str(matched.iloc[0][time_col]).strip()
                            
                            # 从项目扫描结果直接获取该时间戳的图片
                            for rp in self._project_scan_result.readpoints:
                                if rp.image_folder:
                                    import glob
                                    pattern = os.path.join(rp.image_folder, f"*{ts}*")
                                    paths = glob.glob(pattern)
                                    if paths:
                                        if rp.folder_name not in combined_result['readpoints']:
                                            combined_result['readpoints'][rp.folder_name] = {}
                                        combined_result['readpoints'][rp.folder_name][ts] = paths
                                        combined_result['global_ts'][ts] = paths
                                        combined_result['stats']['total_images'] += len(paths)
                                        combined_result['stats']['readpoints_found'].append(rp.folder_name)
                            
                            if combined_result['stats']['total_images'] > 0:
                                self._image_scan_result = combined_result
                                self.log(f"[抓图] 直接获取 {combined_result['stats']['total_images']} 张图片", 'info')
        
        if self._image_scan_result is None:
            messagebox.showinfo("提示",
                "请先在左侧「抓图路径配置」中选择根目录并点击「扫描抓图」\n"
                "或者加载包含抓图目录的项目文件夹")
            return
        
        # 优先用传入的 timestamp，否则走 FuseID → 时间戳 → 查图 的流程
        if timestamp:
            self._image_viewer.show_for_timestamp(timestamp, readpoint, fuse_id)
        else:
            self._image_viewer.show_for_fuse(fuse_id, readpoint)




    def copy_image_path(self):
        """复制选中的图片路径"""
        selection = self.image_results_listbox.curselection()
        if selection:
            path = self.image_results_listbox.get(selection[0])
            self.root.clipboard_clear()
            self.root.clipboard_append(path)
            self.log(f"[已复制] {os.path.basename(path)}", 'success')
            messagebox.showinfo("提示", f"已复制:\n{path}")
        else:
            messagebox.showwarning("提示", "请先选择要复制的图片")

    # ========== 项目目录扫描方法 ==========

    def _select_project_root(self):
        """选择项目根目录或读点目录"""
        folder = filedialog.askdirectory(title="选择项目根目录或读点目录（如 HTOL/ 或 168H/）")
        if not folder:
            return

        self._project_path_var.set(folder)
        self._project_status_var.set(f"已选择: {os.path.basename(folder)}")

        # 自动执行扫描
        self._do_project_scan()

    def _do_project_scan(self):
        """扫描项目目录，识别读点"""
        import threading

        root = self._project_path_var.get()
        if not root or root == "未选择":
            messagebox.showwarning("提示", "请先选择项目目录")
            return

        self._project_status_var.set("正在扫描...")
        self.root.update_idletasks()

        def worker():
            result = scan_project(root, log_callback=lambda msg: self.log(msg, 'info'))
            self.root.after(0, lambda: self._on_project_scan_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _select_and_load_project(self):
        """选择目录并自动加载"""
        folder = filedialog.askdirectory(title="选择项目根目录或读点目录")
        if not folder:
            return

        self._project_path_var.set(folder)
        self._do_project_scan()

    def _on_project_scan_done(self, result: ProjectScanResult):
        """扫描完成回调：自动填充时间读点配置"""
        self._project_scan_result = result

        if not result.readpoints:
            self._project_status_var.set("未识别到任何读点目录，请检查目录结构")
            self.log("[警告] 未识别到读点目录", 'warning')
            return

        # 更新状态
        total = len(result.readpoints)
        complete = sum(1 for rp in result.readpoints if rp.is_complete)
        self._project_status_var.set(f"识别到 {total} 个读点，{complete} 个完整")

        # 清空当前读点配置
        self._clear_read_point_rows()

        # 清空右侧表格
        for item in self._info_tree.get_children():
            self._info_tree.delete(item)

        # 根据扫描结果填充
        for rp in result.readpoints:
            # 填充时间读点配置区域
            self._create_read_point_row(rp.name, rp.folder_name, rp.data_file, rp.image_folder)

            # 填充右侧信息表格
            data_basename = os.path.basename(rp.data_file) if rp.data_file else '-'
            image_name = os.path.basename(rp.image_folder) if rp.image_folder else '-'
            self._info_tree.insert('', 'end', values=(
                rp.name,
                rp.folder_name,
                data_basename,
                image_name
            ))

        # 记录到日志
        mode_desc = "根目录扫描" if result.mode == 'auto' else "直接读点"
        self.log(f"[扫描完成] {mode_desc}，识别到 {total} 个读点", 'success')
    
    def get_all_read_points(self):
        """获取所有读点及其数据文件路径"""
        result = {}
        for name, data in self.read_point_data.items():
            path = data['data_path_var'].get()
            name_value = data['name_var'].get()
            if path and path != "未选择":
                result[name_value] = path
        return result
    
    def remove_read_point(self):
        """删除选中的时间读点（旧方法，保留兼容性）"""
        # 新UI下用每行的删除按钮，这里不再使用
        pass
            
    def auto_scan_folders(self):
        """自动扫描父文件夹，识别时间读点并填充"""
        import re
        
        # 让用户选择父文件夹
        parent_folder = filedialog.askdirectory(title="选择包含各时间读点文件夹的父目录")
        if not parent_folder:
            return
            
        self.log("\n[自动扫描] 正在扫描文件夹...", 'info')
        self.log(f"[路径] {parent_folder}", 'info')
        
        # 更全面的时间读点匹配模式
        time_patterns = [
            r'(\d{3,4})H',      # 匹配 168H, 500H, 1000H
            r'(\d{3,4})h',      # 匹配 168h, 500h
            r'[_\-](\d{3,4})H', # 匹配 _168H, -500H
            r'(\d{3,4})_?Hour',  # 匹配 168Hour, 168_Hour
            r'[_\-](\d{3,4})$', # 匹配末尾 _168, -500
            r'H([\d]{3,4})',     # 匹配 H168, H500
        ]
        
        found_count = 0
        existing_count = 0
        
        try:
            # 遍历父文件夹下的所有子文件夹
            items = os.listdir(parent_folder)
            self.log(f"[扫描] 找到 {len(items)} 个项目", 'info')
            
            for item in items:
                item_path = os.path.join(parent_folder, item)
                if os.path.isdir(item_path):  # 只处理文件夹
                    matched = False
                    for pattern in time_patterns:
                        match = re.search(pattern, item, re.IGNORECASE)
                        if match:
                            time_value = match.group(1)
                            # 跳过明显不是时间的数字（如年号）
                            if int(time_value) < 24:  # 小于24H的跳过
                                continue
                            # 构造标准名称
                            time_point = time_value + "H"
                            
                            # 检查是否已存在
                            if time_point in self.read_point_data:
                                # 更新已存在的
                                self.read_point_data[time_point]['path_var'].set(item_path)
                                self.log(f"[已更新] {time_point} → {item}", 'success')
                                existing_count += 1
                            else:
                                # 添加新的
                                self.read_point_data[time_point] = {
                                    'name_var': tk.StringVar(value=time_point),
                                    'path_var': tk.StringVar(value=item_path),
                                    'frame': None
                                }
                                self.log(f"[发现] {time_point} → {item}", 'success')
                                found_count += 1
                            matched = True
                            break
                    
                    if not matched:
                        self.log(f"[跳过] {item} (未匹配时间格式)", 'info')
        except Exception as e:
            self.log(f"[错误] 扫描失败: {str(e)}", 'error')
        
        total = found_count + existing_count
        if total > 0:
            self.log(f"\n✅ 自动扫描完成！新增 {found_count} 个，更新 {existing_count} 个", 'success')
        else:
            self.log("\n⚠️ 未自动识别到时间读点，请手动选择", 'warning')
            self.log("支持的格式: 168H, 500H, 1000H, 168_hour 等", 'info')
            
    def start_analysis(self):
        """开始分析（后台线程运行，UI 实时显示进度）"""
        import threading

        # 防重入：已经在跑了就忽略
        if getattr(self, '_analysis_running', False):
            return
        self._analysis_running = True

        # 禁用按钮，防止重复点击
        if hasattr(self, '_analysis_btn'):
            self._analysis_btn.config(state='disabled', text='分析中...')

        # 启动后台分析线程
        t = threading.Thread(target=self._analysis_worker, daemon=True)
        t.start()

    def _analysis_worker(self):
        """后台分析线程（所有慢操作在这里跑，结果通过 root.after 回写 UI）"""
        def log(msg, tag='info'):
            self.root.after(0, lambda: self.log(msg, tag))

        log("="*50, 'title')
        log("开始数据分析（后台运行）...", 'title')
        log("="*50)

        # ① 加载数据
        from src.data_loader import load_data_from_read_points
        from src.analyzer import get_available_test_items as _scan_items, analyze_drift as _analyze_drift, build_rp_groups

        # ① 加载数据（每次分析都重新加载，确保数据最新）
        from src.data_loader import load_data_from_read_points
        from src.analyzer import get_available_test_items as _scan_items, analyze_drift as _analyze_drift, build_rp_groups

        log("[步骤1] 加载数据文件...", 'info')
        df = load_data_from_read_points(self.get_all_read_points(), log_callback=log)
        if df is None or len(df) == 0:
            log("[错误] 数据加载失败", 'error')
            self.root.after(0, self._handlers._on_analysis_done, None, [], 'error')
            return
        self._current_df = df
        
        # 数据已更新，清空相关缓存
        self._all_test_items = []
        self._selected_test_items = set()
        if hasattr(self, '_chart_cache'):
            self._chart_cache.clear()
        self._chart_items = []

        # ② 扫描测试项
        if not hasattr(self, '_all_test_items') or not self._all_test_items:
            log("[步骤0] 自动扫描测试项...", 'info')
            test_items = _scan_items(self._current_df, log_callback=log)
            if test_items:
                self._all_test_items = test_items
                self._filtered_test_items = test_items
                log(f"[扫描] 发现 {len(test_items)} 个可分析测试项", 'success')
                # 通知选择器同步数据（跨线程安全：走主线程）
                self.root.after(0, lambda items=test_items: (
                    self._test_item_selector.update_items(items) if self._test_item_selector else None
                ))

        # ③ 执行漂移分析
        test_items = self._get_selected_test_items()
        if not test_items:
            log("[错误] 没有找到有效的测试项", 'error')
            self.root.after(0, self._handlers._on_analysis_done, None, [])
            return

        try:
            limit = int(self.analysis_limit.get()) if self.analysis_limit.get() else 0
        except ValueError:
            limit = 0
        if limit > 0 and len(test_items) > limit:
            log(f"[分析项] 共 {len(test_items)} 个，限制分析前 {limit} 个", 'info')
            test_items = test_items[:limit]
        else:
            log(f"[分析项] 共 {len(test_items)} 个测试项", 'info')

        log(f"[启用规则] ①={self.rule1_enabled.get()} ②={self.rule2_enabled.get()} ③={self.rule3_enabled.get()}", 'info')

        # 读取阈值（含校验）
        try:
            threshold1 = float(self.rule1_threshold.get())
            threshold2 = float(self.rule2_threshold.get())
            threshold3 = float(self.rule3_threshold.get())
        except ValueError:
            log("[错误] 漂移检测阈值必须为数字（例如：30），请检查规则①②③的阈值输入", 'error')
            self.root.after(0, self._handlers._on_analysis_done, None, [])
            return

        log("\n[步骤2] 执行漂移分析（后台运行，可切换查看图表）...", 'info')

        rp_groups = build_rp_groups(self._current_df)

        all_results = {}
        total = len(test_items)
        for idx, item in enumerate(test_items, 1):
            # 每分析 10 项更新一次进度，避免刷屏
            if idx % 10 == 1:
                log(f"  进度: [{idx}/{total}] {item}...", 'info')
            result = _analyze_drift(
                self._current_df, item,
                rule1_enabled=self.rule1_enabled.get(),
                rule1_threshold=threshold1,
                rule2_enabled=self.rule2_enabled.get(),
                rule2_threshold=threshold2,
                rule3_enabled=self.rule3_enabled.get(),
                rule3_threshold=threshold3,
                rp_groups=rp_groups,
                log_callback=log
            )
            all_results[item] = result

        # ④ 合并摘要
        combined_summary = []
        for item, result in all_results.items():
            if result['summary']:
                combined_summary.append(f"[{item}] " + "; ".join(result['summary']))

        analysis_result = {
            'summary': combined_summary,
            'all_results': all_results
        }

        # ⑤ 回写结果到 UI
        self.root.after(0, self._handlers._on_analysis_done, analysis_result, test_items)


    def generate_charts(self):
        """注册测试项列表，启动后台线程预生成图表（用户边看边等，不卡 UI）"""
        if not hasattr(self, '_current_df') or self._current_df is None:
            messagebox.showwarning("提示", "请先执行「开始分析」加载数据")
            return

        test_items = self._get_selected_test_items()

        if not test_items:
            messagebox.showwarning("提示", "请先扫描数据并选择测试项")
            return

        try:
            limit = int(self.analysis_limit.get()) if self.analysis_limit.get() else 0
        except ValueError:
            messagebox.showwarning("提示", "分析上限必须为整数（如 100），0 表示全部")
            return
        if limit > 0 and len(test_items) > limit:
            test_items = test_items[:limit]

        # 配置并启动预生成缓存
        self._chart_cache.configure(
            df=self._current_df,
            items=test_items,
            build_fn=build_chart_for_item
        )
        self._chart_items = test_items

        # 后台线程开始预生成（从 index 0 往后填）
        self._chart_cache.start_prefill(current_idx=0)

        self.log(f"\n[图表] 共 {len(self._chart_items)} 个测试项，后台预生成已启动", 'success')

        if hasattr(self, '_open_chart_btn'):
            self._open_chart_btn.config(state='normal', text='打开图表查看器')
            self._chart_viewer.open()
        else:
            messagebox.showwarning("提示", "没有成功生成任何图表")
        
    def generate_ppt(self):
        """生成PPT报告"""
        self.log("\n[生成PPT] 报告生成中...", 'info')
        messagebox.showinfo("提示", "PPT生成功能开发中...")
        
    def open_output_dir(self):
        """打开输出目录"""
        output_dir = os.path.join(os.path.dirname(__file__), "reliability_plots")
        os.makedirs(output_dir, exist_ok=True)
        os.startfile(output_dir)
    
    # ========== 漂移分析引擎 ==========
    
    def _toggle_all_rules(self, enabled):
        """切换所有规则的启用状态"""
        self.rule1_enabled.set(enabled)
        self.rule2_enabled.set(enabled)
        self.rule3_enabled.set(enabled)
    
    def _scan_test_items(self):
        """扫描数据文件，获取可用的测试项"""
        from src.data_loader import load_data_from_read_points
        from src.analyzer import get_available_test_items

        read_points = self.get_all_read_points()
        df = load_data_from_read_points(read_points, log_callback=self.log)
        if df is None or len(df) == 0:
            messagebox.showwarning("提示", "未能加载数据，请检查文件路径")
            return

        test_items = get_available_test_items(df, log_callback=self.log)
        if test_items:
            self._all_test_items = test_items
            self._filtered_test_items = test_items
            self._current_df = df

            # 通知选择器同步新数据（修复：初始化时传入的是空列表引用）
            if self._test_item_selector is not None:
                self._test_item_selector.update_items(test_items)

            self.log(f"[扫描] 发现 {len(test_items)} 个可分析测试项", 'success')
            if test_items:
                self.log(f"[示例] 前5项: {test_items[:5]}", 'info')
            self.test_item_count_var.set(f"点击选择测试项（共{len(test_items)}项）")
        else:
            messagebox.showwarning("提示", "未找到可分析的测试项")

    def _open_selector(self):
        """打开测试项选择弹窗（委托给 TestItemSelector）"""
        self._test_item_selector.open()

    def _get_selected_test_items(self):
        """获取当前选中的测试项列表"""
        if not self._selected_test_items:
            return self._all_test_items.copy()
        return list(self._selected_test_items)


def main():
    """主函数"""
    root = tk.Tk()
    
    # 设置窗口图标（如果有的话）
    # root.iconbitmap('icon.ico')
    
    app = ReliabilityAnalysisApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
