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

    def __init__(self, parent, all_items, selected_items, constant_items, count_var, log_fn):
        """
        parent: 父窗口
        all_items: list，所有可选测试项
        selected_items: set，当前已选测试项（会被直接修改）
        constant_items: dict，全相同项 {名称: 值}
        count_var: tk.StringVar，主窗口计数标签
        log_fn: callable，日志函数
        """
        self.parent = parent
        self.all_items = all_items
        self.selected = selected_items
        self.constant_items = constant_items
        self.count_var = count_var
        self.log_fn = log_fn
        self.window = None
        self.count_label = None
        self._constant_visible = False  # 全相同项是否展开
        self._constant_hidden = False   # 全相同项是否隐藏

    def update_items(self, all_items, constant_items=None):
        """更新测试项数据"""
        self.all_items = all_items
        if constant_items is not None:
            self.constant_items = constant_items
        # 如果弹窗已打开，更新内容
        if self.window and self.window.winfo_exists():
            self._update_constant_section()

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
        win.geometry("900x700")
        win.minsize(700, 500)  # 最小尺寸
        win.transient(self.parent)
        win.grab_set()

        self.window = win
        win.protocol("WM_DELETE_WINDOW", self._close)

        # 主容器
        main_frame = ttk.Frame(win, padding="10")
        main_frame.pack(fill='both', expand=True)

        # ========== 顶部：搜索框 ==========
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill='x', pady=(0, 5))
        
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var, width=40,
                                font=('Microsoft YaHei', 10))
        search_entry.pack(side='left', padx=(0, 10))
        search_entry.focus()
        
        ttk.Label(search_frame, text="空格=AND  ;=OR  如: DIFFV;OS",
                 font=('Microsoft YaHei', 8), foreground='#666666').pack(side='left')

        total_items = len(self.all_items) + len(self.constant_items)
        self.count_label = ttk.Label(
            search_frame,
            text=f"已选: {len(self.selected)} / {total_items} 项",
            font=('Microsoft YaHei', 10), foreground='#2563eb')
        self.count_label.pack(side='right')

        # ========== 中间：左右分栏 ==========
        content = tk.Frame(main_frame)
        content.pack(fill='both', expand=True, pady=5)

        # ----- 左侧：可选项（分两组）-----
        left_container = tk.Frame(content, bg='#f8fafc')
        left_container.pack(side='left', fill='both', expand=True)

        # 初始化变量
        current_items_left = []      # 当前数值变化项列表
        current_constant_left = []   # 当前全相同项列表

        # --- 数值变化项 Section ---
        var_section = tk.Frame(left_container, bg='#e8f4f8', relief='solid', bd=1)
        var_section.pack(fill='both', expand=True, pady=(0, 5))

        var_header = tk.Frame(var_section, bg='#3b82f6', height=28)
        var_header.pack(fill='x')
        var_header.pack_propagate(False)
        tk.Label(var_header, text=f"📊 数值变化项 ({len(self.all_items)}项)",
                font=('Microsoft YaHei', 9, 'bold'), bg='#3b82f6', fg='white').pack(side='left', padx=8)

        var_list_frame = tk.Frame(var_section, bg='white')
        var_list_frame.pack(fill='both', expand=True, padx=3, pady=3)

        left_listbox = tk.Listbox(var_list_frame, selectmode='extended', font=('Consolas', 9), bg='white')
        left_listbox.pack(side='left', fill='both', expand=True)
        left_scroll = ttk.Scrollbar(var_list_frame, orient='vertical', command=left_listbox.yview)
        left_scroll.pack(side='right', fill='y')
        left_listbox.configure(yscrollcommand=left_scroll.set)

        # --- 全相同项 Section ---
        const_header = tk.Frame(left_container, bg='#fbbf24', height=28)
        const_header.pack(fill='x', pady=(0, 0))
        const_header.pack_propagate(False)

        self._const_expanded = tk.BooleanVar(value=True)  # 默认展开

        def toggle_constant():
            if self._const_expanded.get():
                const_list_frame.pack_forget()
                self._btn_toggle.config(text="▶ 展开")
            else:
                const_list_frame.pack(fill='both', expand=True, padx=3, pady=3)
                self._btn_toggle.config(text="▼ 收起")
            self._const_expanded.set(not self._const_expanded.get())

        self._btn_toggle = tk.Button(const_header, text="▼ 收起",
                font=('Microsoft YaHei', 8), bg='#f59e0b', fg='white',
                relief='flat', cursor='hand1', padx=6, command=toggle_constant)
        self._btn_toggle.pack(side='right', padx=5)

        const_count = len(self.constant_items)
        tk.Label(const_header, text=f"📌 全相同项 ({const_count}项)",
                font=('Microsoft YaHei', 9, 'bold'), bg='#fbbf24', fg='#333').pack(side='left', padx=8)

        const_list_frame = tk.Frame(left_container, bg='white', height=120)
        const_list_frame.pack(fill='both', expand=True)
        const_list_frame.pack_propagate(False)

        constant_listbox = tk.Listbox(const_list_frame, selectmode='extended',
                font=('Consolas', 9), bg='white')
        constant_listbox.pack(side='left', fill='both', expand=True)
        const_scroll = ttk.Scrollbar(const_list_frame, orient='vertical', command=constant_listbox.yview)
        const_scroll.pack(side='right', fill='y')
        constant_listbox.configure(yscrollcommand=const_scroll.set)

        # ----- 中间：操作按钮 -----
        middle_frame = tk.Frame(content, bg='#f1f5f9', padx=8)
        middle_frame.pack(side='left', fill='y', padx=5)

        def update_counts():
            total = len(self.all_items) + len(self.constant_items)
            self.count_label.config(text=f"已选: {len(self.selected)} / {total} 项")

        def update_left_list():
            """更新数值变化项列表"""
            nonlocal current_items_left
            kw = search_var.get().strip().lower()
            if kw:
                normalized = kw.replace('；', ';')
                if ';' in normalized:
                    keywords = [k.strip() for k in normalized.split(';') if k.strip()]
                    current_items_left = [i for i in self.all_items
                                          if any(k in i.lower() for k in keywords) and i not in self.selected]
                else:
                    keywords = [k.strip() for k in normalized.split() if k.strip()]
                    if len(keywords) > 1:
                        current_items_left = [i for i in self.all_items
                                              if all(k in i.lower() for k in keywords) and i not in self.selected]
                    else:
                        current_items_left = [i for i in self.all_items
                                              if kw in i.lower() and i not in self.selected]
            else:
                current_items_left = [i for i in self.all_items if i not in self.selected]
            
            left_listbox.delete(0, tk.END)
            for item in current_items_left:
                left_listbox.insert(tk.END, item)

        def update_constant_list():
            """更新全相同项列表"""
            nonlocal current_constant_left
            kw = search_var.get().strip().lower()
            if kw:
                normalized = kw.replace('；', ';')
                if ';' in normalized:
                    keywords = [k.strip() for k in normalized.split(';') if k.strip()]
                    current_constant_left = [name for name, val in self.constant_items.items()
                                             if any(k in name.lower() for k in keywords) and name not in self.selected]
                else:
                    current_constant_left = [name for name, val in self.constant_items.items()
                                             if kw in name.lower() and name not in self.selected]
            else:
                current_constant_left = [name for name in self.constant_items.keys()
                                         if name not in self.selected]
            
            constant_listbox.delete(0, tk.END)
            for name in current_constant_left:
                val = self.constant_items.get(name, '?')
                constant_listbox.insert(tk.END, f"{name} [值={val}]")

        def update_right_list():
            sel_list = sorted(self.selected, key=lambda x: (x not in self.constant_items, x))
            right_listbox.delete(0, tk.END)
            for item in sel_list:
                if item in self.constant_items:
                    val = self.constant_items[item]
                    right_listbox.insert(tk.END, f"{item} [值={val}]")
                else:
                    right_listbox.insert(tk.END, item)

        def add_selected():
            # 添加数值变化项
            for i in left_listbox.curselection():
                self.selected.add(current_items_left[i])
            # 添加全相同项
            for i in constant_listbox.curselection():
                self.selected.add(current_constant_left[i])
            update_counts()
            update_right_list()
            update_left_list()
            update_constant_list()

        def remove_selected():
            sel = list(right_listbox.curselection())
            sel_list = sorted(self.selected, key=lambda x: (x not in self.constant_items, x))
            for i in reversed(sel):
                if i < len(sel_list):
                    self.selected.discard(sel_list[i])
            update_counts()
            update_right_list()
            update_left_list()
            update_constant_list()

        def add_all():
            for item in current_items_left:
                self.selected.add(item)
            for name in current_constant_left:
                self.selected.add(name)
            update_counts()
            update_right_list()
            update_left_list()
            update_constant_list()

        def remove_all():
            self.selected.clear()
            update_counts()
            update_right_list()
            update_left_list()
            update_constant_list()

        # 按钮样式
        btn_style = {'font': ('Microsoft YaHei', 9), 'relief': 'flat', 'cursor': 'hand1', 'padx': 8, 'pady': 4}
        
        tk.Label(middle_frame, text="", bg='#f1f5f9').pack(expand=True)
        
        tk.Button(middle_frame, text="→ 添加", command=add_selected,
                 bg='#22c55e', fg='white', **btn_style).pack(pady=3)
        tk.Button(middle_frame, text="← 移除", command=remove_selected,
                 bg='#ef4444', fg='white', **btn_style).pack(pady=3)
        
        tk.Label(middle_frame, text="", bg='#f1f5f9', height=1).pack()
        
        tk.Button(middle_frame, text="→→ 全加", command=add_all,
                 bg='#22c55e', fg='white', **btn_style).pack(pady=3)
        tk.Button(middle_frame, text="←← 全清", command=remove_all,
                 bg='#ef4444', fg='white', **btn_style).pack(pady=3)
        
        tk.Label(middle_frame, text="", bg='#f1f5f9').pack(expand=True)

        # ----- 右侧：已选项 -----
        right_frame = ttk.LabelFrame(content, text="已选项", padding="5")
        right_frame.pack(side='left', fill='both', expand=True)

        right_listbox = tk.Listbox(right_frame, selectmode='extended', font=('Consolas', 9))
        right_listbox.pack(side='left', fill='both', expand=True)
        right_scroll = ttk.Scrollbar(right_frame, orient='vertical', command=right_listbox.yview)
        right_scroll.pack(side='right', fill='y')
        right_listbox.configure(yscrollcommand=right_scroll.set)

        # 搜索跟踪
        def on_search_change(*_):
            win.after(150, lambda: (update_left_list(), update_constant_list()))
        search_var.trace('w', on_search_change)

        # 底部按钮
        btn_frame = ttk.Frame(main_frame, padding="5")
        btn_frame.pack(fill='x', pady=(10, 0))

        # 常用项按钮区域
        fav_frame = ttk.Frame(btn_frame)
        fav_frame.pack(side='left')

        def save_favorite():
            if not self.selected:
                messagebox.showwarning("提示", "请先选择测试项后再保存")
                return
            # 弹出对话框输入组名
            dialog = tk.Toplevel(win)
            dialog.title("保存常用项")
            dialog.geometry("350x150")
            dialog.transient(win)
            dialog.grab_set()
            
            tk.Label(dialog, text="请输入常用项组名称:", font=('Microsoft YaHei', 10)).pack(pady=(20, 10))
            
            name_var = tk.StringVar(value="我的常用项")
            name_entry = tk.Entry(dialog, textvariable=name_var, width=30, font=('Microsoft YaHei', 10))
            name_entry.pack(pady=5)
            name_entry.focus()
            name_entry.select_range(0, tk.END)
            
            btn_frame_d = tk.Frame(dialog)
            btn_frame_d.pack(pady=15)
            
            def do_save():
                group_name = name_var.get().strip() or "默认"
                from src.utils import save_favorite_items
                save_favorite_items(list(self.selected), group_name)
                self.log_fn(f"[常用] 已保存 {len(self.selected)} 项到「{group_name}」")
                dialog.destroy()
                messagebox.showinfo("成功", f"已保存 {len(self.selected)} 项到「{group_name}」")
            
            def do_save_new():
                # 追加到现有组
                group_name = name_var.get().strip() or "默认"
                from src.utils import load_favorite_items, save_favorite_items
                existing = load_favorite_items(group_name) or []
                combined = list(set(existing + list(self.selected)))
                save_favorite_items(combined, group_name)
                self.log_fn(f"[常用] 已追加 {len(self.selected)} 项到「{group_name}」")
                dialog.destroy()
                messagebox.showinfo("成功", f"已追加 {len(self.selected)} 项到「{group_name}」")
            
            tk.Button(btn_frame_d, text="保存(覆盖)", command=do_save, width=10).pack(side='left', padx=5)
            tk.Button(btn_frame_d, text="追加到组", command=do_save_new, width=10).pack(side='left', padx=5)
            tk.Button(btn_frame_d, text="取消", command=dialog.destroy, width=8).pack(side='left', padx=5)
            
            name_entry.bind('<Return>', lambda e: do_save())

        def load_favorite():
            from src.utils import load_favorite_items
            all_groups = load_favorite_items()
            if not all_groups:
                messagebox.showinfo("提示", "暂无保存的常用项")
                return
            
            # 弹出选择组对话框
            dialog = tk.Toplevel(win)
            dialog.title("加载常用项")
            dialog.geometry("400x350")
            dialog.transient(win)
            dialog.grab_set()
            
            tk.Label(dialog, text="请选择要加载的常用项组:", font=('Microsoft YaHei', 10)).pack(pady=(15, 10))
            
            # 显示所有组
            list_frame = tk.Frame(dialog)
            list_frame.pack(fill='both', expand=True, padx=20, pady=5)
            
            listbox = tk.Listbox(list_frame, selectmode='extended', font=('Consolas', 9), height=10)
            listbox.pack(side='left', fill='both', expand=True)
            scroll = ttk.Scrollbar(list_frame, orient='vertical', command=listbox.yview)
            scroll.pack(side='right', fill='y')
            listbox.configure(yscrollcommand=scroll.set)
            
            group_names = list(all_groups.keys())
            for name in group_names:
                count = len(all_groups[name])
                listbox.insert(tk.END, f"{name} ({count}项)")
            
            btn_frame_d = tk.Frame(dialog)
            btn_frame_d.pack(pady=15)
            
            def do_load():
                selection = listbox.curselection()
                if not selection:
                    messagebox.showwarning("提示", "请先选择要加载的组")
                    return
                # 加载所有选中的组
                total_valid = 0
                total_invalid = 0
                for idx in selection:
                    group_name = group_names[idx]
                    fav_items = all_groups[group_name]
                    valid_items = [i for i in fav_items if i in self.all_items]
                    invalid_items = [i for i in fav_items if i not in self.all_items]
                    for item in valid_items:
                        self.selected.add(item)
                    total_valid += len(valid_items)
                    total_invalid += len(invalid_items)
                
                self.log_fn(f"[常用] 已加载 {total_valid} 项")
                if total_invalid > 0:
                    messagebox.showinfo("加载完成", f"有效: {total_valid} 项\n已失效: {total_invalid} 项")
                else:
                    messagebox.showinfo("加载完成", f"已加载 {total_valid} 项")
                dialog.destroy()
                update_counts()
                update_right_list()
                update_left_list()
            
            def do_delete():
                selection = listbox.curselection()
                if not selection:
                    messagebox.showwarning("提示", "请先选择要删除的组")
                    return
                if messagebox.askyesno("确认", "确定要删除选中的常用项组吗？"):
                    from src.utils import delete_favorite_group
                    for idx in reversed(selection):
                        delete_favorite_group(group_names[idx])
                    messagebox.showinfo("完成", "已删除选中的常用项组")
                    dialog.destroy()
            
            tk.Button(btn_frame_d, text="加载选中", command=do_load, width=10, bg='#3b82f6', fg='white').pack(side='left', padx=5)
            tk.Button(btn_frame_d, text="删除选中", command=do_delete, width=10, bg='#ef4444', fg='white').pack(side='left', padx=5)
            tk.Button(btn_frame_d, text="取消", command=dialog.destroy, width=8).pack(side='left', padx=5)

        def clear_favorite():
            if messagebox.askyesno("确认", "确定要清除所有常用项吗？"):
                from src.utils import clear_favorite_items
                clear_favorite_items()
                self.log_fn("[常用] 已清除所有保存的常用项")
                messagebox.showinfo("提示", "常用项已全部清除")

        ttk.Button(fav_frame, text="★ 保存常用项", command=save_favorite, width=12).pack(side='left', padx=2)
        ttk.Button(fav_frame, text="☆ 加载常用项", command=load_favorite, width=12).pack(side='left', padx=2)

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
        update_constant_list()
        update_right_list()

    def update_items(self, new_items, constant_items=None):
        """
        扫描完成后通知选择器更新数据源。
        同时移除 selected 中已不存在于新列表的残留项。
        """
        self.all_items = new_items
        if constant_items is not None:
            self.constant_items = constant_items
        # 清理已选中但新列表里没有的项
        stale = self.selected - set(new_items)
        self.selected -= stale
        # 如果弹窗正在打开，刷新
        if self.window and self.window.winfo_exists():
            if self.count_label:
                total = len(self.all_items) + len(self.constant_items)
                self.count_label.config(
                    text=f"已选: {len(self.selected)} / {total} 项")
            self._update_constant_section()

    def _close(self):
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        self.window = None
