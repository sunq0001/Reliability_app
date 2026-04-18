"""
通用 UI 组件 - 可复用的 Tkinter 弹窗和工具函数
"""
import tkinter as tk
from tkinter import ttk, messagebox


def make_path_tooltip(widget, path_var):
    """
    为任意 tk widget 绑定路径悬停提示（显示完整路径）
    widget: 支持 focus 的 tk 组件
    path_var: tk.StringVar，包含完整路径
    """
    tooltip = None

    def show(event):
        nonlocal tooltip
        path = path_var.get()
        if not path:
            return
        if tooltip is None:
            tooltip = tk.Toplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+15}+{event.y_root+10}")
            label = tk.Label(
                tooltip, text=path, background="#2c3e50", foreground="white",
                font=('Microsoft YaHei', 8), padx=6, pady=3, relief='flat'
            )
            label.pack()
        else:
            tooltip.wm_geometry(f"+{event.x_root+15}+{event.y_root+10}")
            tooltip.children['!label'].config(text=path)
        tooltip.deiconify()

    def hide(event):
        nonlocal tooltip
        if tooltip:
            tooltip.withdraw()

    widget.bind('<Enter>', show)
    widget.bind('<Leave>', hide)
    widget.bind('<Motion>', show)





class TestItemSelector:
    """测试项选择弹窗"""

    def __init__(self, parent, all_items, selected_items, count_var, log_fn):
        """
        parent: 父窗口
        all_items: list，所有可选测试项
        selected_items: set，当前已选测试项（会被直接修改）
        count_var: tk.StringVar，主窗口计数标签
        log_fn: callable，日志函数
        """
        self.parent = parent
        self.all_items = all_items
        self.selected = selected_items
        self.count_var = count_var
        self.log_fn = log_fn
        self.window = None
        self.count_label = None

    def open(self):
        """打开选择弹窗"""
        if not self.all_items:
            messagebox.showinfo("提示", "请先点击「重新扫描」加载测试项")
            return

        if self.window and self.window.winfo_exists():
            self.window.lift()
            return

        win = tk.Toplevel(self.parent)
        win.title("选择测试项")
        win.geometry("750x650")
        win.transient(self.parent)

        self.window = win
        win.protocol("WM_DELETE_WINDOW", self._close)

        main_frame = ttk.Frame(win, padding="10")
        main_frame.pack(fill='both', expand=True)

        # 搜索框
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill='x', pady=(0, 10))
        ttk.Label(search_frame, text="搜索:", font=('Microsoft YaHei', 10)).pack(side='left')
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var, width=30,
                                font=('Microsoft YaHei', 10))
        search_entry.pack(side='left', padx=10)
        search_entry.focus()

        self.count_label = ttk.Label(
            main_frame,
            text=f"已选: {len(self.selected)} / {len(self.all_items)} 项",
            font=('Microsoft YaHei', 10), foreground='blue')
        self.count_label.pack(pady=(0, 5))

        # 分栏
        paned = tk.PanedWindow(main_frame, orient='horizontal', sashwidth=8,
                               sashrelief='raised', sashpad=2, bg='#cccccc')
        paned.pack(fill='both', expand=True, pady=5)

        # 左侧：可选项
        left_frame = ttk.LabelFrame(paned, text="可选项", padding="5")
        left_listbox = tk.Listbox(left_frame, selectmode='extended', font=('Consolas', 9))
        left_listbox.pack(side='left', fill='both', expand=True)
        left_scroll = ttk.Scrollbar(left_frame, orient='vertical', command=left_listbox.yview)
        left_scroll.pack(side='right', fill='y')
        left_listbox.configure(yscrollcommand=left_scroll.set)
        paned.add(left_frame, minsize=200, stretch='always')

        # 中间：操作按钮
        middle_frame = tk.Frame(paned, bg='#f0f0f0', padx=5)
        current_items_left = []

        def update_counts():
            self.count_label.config(
                text=f"已选: {len(self.selected)} / {len(self.all_items)} 项")

        def update_left_list():
            nonlocal current_items_left
            kw = search_var.get().strip().lower()
            if kw:
                current_items_left = [i for i in self.all_items
                                      if kw in i.lower() and i not in self.selected]
            else:
                current_items_left = [i for i in self.all_items
                                      if i not in self.selected]
            left_listbox.delete(0, tk.END)
            for item in current_items_left:
                left_listbox.insert(tk.END, item)

        def update_right_list():
            sel_list = list(self.selected)
            right_listbox.delete(0, tk.END)
            for item in sel_list:
                right_listbox.insert(tk.END, item)

        def add_selected():
            for i in left_listbox.curselection():
                self.selected.add(current_items_left[i])
            update_counts()
            update_right_list()
            update_left_list()

        def remove_selected():
            sel = list(right_listbox.curselection())
            items_list = list(self.selected)
            for i in reversed(sel):
                if i < len(items_list):
                    self.selected.discard(items_list[i])
            update_counts()
            update_right_list()
            update_left_list()

        def add_all():
            for item in current_items_left:
                self.selected.add(item)
            update_counts()
            update_right_list()
            update_left_list()

        def remove_all():
            self.selected.clear()
            update_counts()
            update_right_list()
            update_left_list()

        tk.Label(middle_frame, text="", bg='#f0f0f0').pack(expand=True)
        tk.Button(middle_frame, text="添加 →", command=add_selected, width=8).pack(pady=5)
        tk.Button(middle_frame, text="← 移除", command=remove_selected, width=8).pack(pady=5)
        tk.Label(middle_frame, text="", bg='#f0f0f0', height=1).pack()
        tk.Button(middle_frame, text="全加 >>", command=add_all, width=8).pack(pady=5)
        tk.Button(middle_frame, text="<< 全清", command=remove_all, width=8).pack(pady=5)
        tk.Label(middle_frame, text="", bg='#f0f0f0').pack(expand=True)

        paned.add(middle_frame, minsize=90, stretch='never')

        # 右侧：已选项
        right_frame = ttk.LabelFrame(paned, text="已选项", padding="5")
        right_listbox = tk.Listbox(right_frame, selectmode='extended', font=('Consolas', 9))
        right_listbox.pack(side='left', fill='both', expand=True)
        right_scroll = ttk.Scrollbar(right_frame, orient='vertical', command=right_listbox.yview)
        right_scroll.pack(side='right', fill='y')
        right_listbox.configure(yscrollcommand=right_scroll.set)
        paned.add(right_frame, minsize=200, stretch='always')

        # 搜索跟踪
        def on_search_change(*_):
            win.after(200, update_left_list)
        search_var.trace('w', on_search_change)

        # 底部按钮
        btn_frame = ttk.Frame(main_frame, padding="5")
        btn_frame.pack(fill='x', pady=(10, 0))

        def confirm():
            count = len(self.selected)
            if count == 0:
                self.count_var.set("点击选择测试项...")
            elif count == len(self.all_items):
                self.count_var.set(f"已选: 全部 ({count}项)")
            else:
                self.count_var.set(f"已选: {count} 项")
            self.log_fn(f"[选择] 已选择 {count} 个测试项")
            self._close()

        ttk.Button(btn_frame, text="✓ 确认", command=confirm, width=15).pack(side='right')

        update_left_list()
        update_right_list()

    def update_items(self, new_items):
        """
        扫描完成后通知选择器更新数据源。
        同时移除 selected 中已不存在于新列表的残留项。
        """
        self.all_items = new_items
        # 清理已选中但新列表里没有的项
        stale = self.selected - set(new_items)
        self.selected -= stale
        # 如果弹窗正在打开，刷新计数标签
        if self.count_label and self.window and self.window.winfo_exists():
            self.count_label.config(
                text=f"已选: {len(self.selected)} / {len(self.all_items)} 项")

    def _close(self):
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        self.window = None
