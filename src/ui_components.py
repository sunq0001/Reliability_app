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
        search_frame.pack(fill='x', pady=(0, 5))
        
        search_top = ttk.Frame(search_frame)
        search_top.pack(fill='x')
        
        ttk.Label(search_top, text="搜索:", font=('Microsoft YaHei', 10)).pack(side='left')
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_top, textvariable=search_var, width=30,
                                font=('Microsoft YaHei', 10))
        search_entry.pack(side='left', padx=10)
        search_entry.focus()
        
        # 搜索语法说明
        ttk.Label(search_frame, text=" 空格=AND  ;=OR  如: DIFFV;OS",
                 font=('Microsoft YaHei', 8), foreground='#666666').pack(side='left')

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
                # 搜索语法：
                # 分号(;) 表示 OR（匹配任一关键词），如 "DIFFV;OS" 匹配包含 DIFFV 或 OS
                # 空格表示 AND（同时匹配多个关键词），如 "Dark LP" 匹配同时包含 Dark 和 LP
                # 中文分号(；) 也支持
                normalized = kw.replace('；', ';')
                
                if ';' in normalized:
                    # OR 搜索：分号分隔的关键词，满足任一即可
                    keywords = [k.strip() for k in normalized.split(';') if k.strip()]
                    current_items_left = [i for i in self.all_items
                                          if any(k in i.lower() for k in keywords) and i not in self.selected]
                else:
                    # AND 搜索：空格分隔的关键词，同时满足
                    keywords = [k.strip() for k in normalized.split() if k.strip()]
                    if len(keywords) > 1:
                        current_items_left = [i for i in self.all_items
                                              if all(k in i.lower() for k in keywords) and i not in self.selected]
                    else:
                        # 单个关键词
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
