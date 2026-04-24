"""
image_selector.py - 图片选择弹窗模块
以读点×场景的表格布局显示，点击文字查看原图。
不生成缩略图，避免大量图片时卡顿。
"""
import tkinter as tk
from tkinter import ttk, messagebox
import os


class ImageSelector:
    """图片选择弹窗 - 读点×场景表格布局"""
    
    def __init__(self, root):
        self.root = root
        self._win = None
        self._current_images = {}  # {场景名: {读点名: [路径列表]}}
        self._current_fuse_id = None
        self._current_ts = None
        self._all_readpoints = []
        self._all_scenes = []
    
    def show(self, fuse_id, images_by_scene_and_readpoint, timestamp=None):
        """
        显示图片选择器
        
        参数:
            fuse_id: FuseID
            images_by_scene_and_readpoint: {
                场景名: {读点心: [路径列表]},
                ...
            }
            timestamp: 时间戳（可选）
        """
        self._current_fuse_id = fuse_id
        self._current_ts = timestamp
        self._current_images = images_by_scene_and_readpoint
        
        # 收集所有读点和场景
        self._all_readpoints = set()
        self._all_scenes = set()
        
        for scene, rp_dict in images_by_scene_and_readpoint.items():
            self._all_scenes.add(scene)
            for rp in rp_dict.keys():
                self._all_readpoints.add(rp)
        
        self._all_readpoints = sorted(self._all_readpoints)
        self._all_scenes = sorted(self._all_scenes)
        
        if not self._all_scenes:
            messagebox.showinfo("提示", "没有可用的图片")
            return
        
        # 构建或更新窗口
        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._rebuild_content()
        else:
            self._build_window()
    
    def _build_window(self):
        """构建窗口"""
        win = tk.Toplevel(self.root)
        win.title("选择图片查看")
        
        # 计算窗口大小
        num_cols = len(self._all_readpoints) + 1  # +1 for scene label column
        num_rows = len(self._all_scenes) + 1  # +1 for header row
        width = min(1200, 200 + len(self._all_readpoints) * 150)
        height = min(700, 150 + len(self._all_scenes) * 80)
        
        win.geometry(f"{width}x{height}")
        win.configure(bg='#f5f5f5')
        
        self._win = win
        win.protocol("WM_DELETE_WINDOW", self._close)
        
        # 标题栏
        header = tk.Frame(win, bg='#2c3e50', height=50)
        header.pack(fill='x', side='top')
        header.pack_propagate(False)
        
        title_parts = []
        if self._current_fuse_id:
            title_parts.append(f"FuseID: {self._current_fuse_id}")
        if self._current_ts:
            title_parts.append(f"时间: {self._format_ts(self._current_ts)}")
        
        title_text = "  |  ".join(title_parts) if title_parts else "选择图片"
        
        title_label = tk.Label(header, text=title_text, font=('Microsoft YaHei', 11, 'bold'),
                              bg='#2c3e50', fg='white')
        title_label.pack(side='left', padx=15, pady=10)
        
        info_label = tk.Label(header, 
                              text=f"共 {sum(len(paths) for rp_dict in self._current_images.values() for paths in rp_dict.values())} 张 / "
                                   f"{len(self._all_scenes)} 个场景 / {len(self._all_readpoints)} 个读点",
                              font=('Microsoft YaHei', 9), bg='#2c3e50', fg='#bdc3c7')
        info_label.pack(side='right', padx=15, pady=10)
        
        # 主内容区（可滚动）
        content = tk.Frame(win, bg='#ecf0f1')
        content.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 创建表格
        self._table_frame = tk.Frame(content, bg='#ecf0f1')
        self._table_frame.pack(fill='both', expand=True)
        
        self._rebuild_content()
    
    def _rebuild_content(self):
        """重建表格内容"""
        if not hasattr(self, '_table_frame') or not self._table_frame:
            return
        
        # 清空旧内容
        for w in self._table_frame.winfo_children():
            w.destroy()
        
        # 表头行：空白 + 读点列标题
        header_frame = tk.Frame(self._table_frame, bg='#34495e', height=40)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        # 左上角空白
        corner = tk.Frame(header_frame, width=120, height=40, bg='#2c3e50')
        corner.pack(side='left')
        corner.pack_propagate(False)
        tk.Label(corner, text="场景 \\ 读点", font=('Microsoft YaHei', 9, 'bold'),
                bg='#2c3e50', fg='white', anchor='center').pack(fill='both', expand=True)
        
        # 读点列标题
        for rp in self._all_readpoints:
            rp_frame = tk.Frame(header_frame, width=150, height=40, bg='#3498db')
            rp_frame.pack(side='left', padx=1)
            rp_frame.pack_propagate(False)
            tk.Label(rp_frame, text=rp, font=('Microsoft YaHei', 9, 'bold'),
                    bg='#3498db', fg='white', anchor='center').pack(fill='both', expand=True)
        
        # 每行：一个场景 + 该场景在各读点的图片
        for scene in self._all_scenes:
            row_frame = tk.Frame(self._table_frame, bg='#ecf0f1', height=60)
            row_frame.pack(fill='x', pady=1)
            row_frame.pack_propagate(False)
            
            # 场景名列
            scene_frame = tk.Frame(row_frame, width=120, height=60, bg='#95a5a6')
            scene_frame.pack(side='left')
            scene_frame.pack_propagate(False)
            tk.Label(scene_frame, text=scene, font=('Microsoft YaHei', 9, 'bold'),
                    bg='#95a5a6', fg='white', anchor='center', wraplength=110,
                    justify='center').pack(fill='both', expand=True)
            
            # 各读点的图片链接
            rp_dict = self._current_images.get(scene, {})
            for rp in self._all_readpoints:
                cell_frame = tk.Frame(row_frame, width=150, height=60, bg='white',
                                     relief='solid', bd=0.5)
                cell_frame.pack(side='left', padx=1)
                cell_frame.pack_propagate(False)
                
                paths = rp_dict.get(rp, [])
                if paths:
                    # 显示图片数量和查看按钮
                    count_label = tk.Label(cell_frame, text=f"{len(paths)} 张图片",
                                         font=('Microsoft YaHei', 8), bg='white', fg='#27ae60')
                    count_label.pack(anchor='center', pady=(8, 2))
                    
                    view_btn = tk.Button(cell_frame, text="查看 ▶",
                                       font=('Microsoft YaHei', 8, 'bold'),
                                       bg='#27ae60', fg='white', cursor='hand1',
                                       relief='flat', padx=8, pady=2,
                                       command=lambda p=paths, s=scene, r=rp: self._show_images(p, s, r))
                    view_btn.pack(anchor='center', pady=(0, 5))
                else:
                    tk.Label(cell_frame, text="无数据", font=('Microsoft YaHei', 8),
                            bg='white', fg='#bdc3c7').pack(fill='both', expand=True)
    
    def _show_images(self, paths, scene, readpoint):
        """显示该单元格对应的所有图片"""
        if not paths:
            return
        
        if len(paths) == 1:
            # 只有一个图片，直接全屏显示
            self._show_fullscreen(paths[0])
        else:
            # 多个图片，显示选择列表
            self._show_multi_images(paths, scene, readpoint)
    
    def _show_multi_images(self, paths, scene, readpoint):
        """显示多张图片的选择列表"""
        win = tk.Toplevel(self._win)
        win.title(f"{scene} - {readpoint} - 选择图片")
        win.geometry("600x400")
        win.configure(bg='#f5f5f5')
        
        # 标题
        header = tk.Frame(win, bg='#2c3e50', height=40)
        header.pack(fill='x', side='top')
        header.pack_propagate(False)
        tk.Label(header, text=f"{scene} @ {readpoint} - 共 {len(paths)} 张",
                font=('Microsoft YaHei', 10, 'bold'), bg='#2c3e50', fg='white').pack(padx=10, pady=8)
        
        # 图片列表
        list_frame = tk.Frame(win, bg='#f5f5f5')
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        canvas = tk.Canvas(list_frame, bg='#f5f5f5', highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg='#f5f5f5')
        
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor='nw')
        scroll_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(canvas_window, width=e.width))
        
        for i, path in enumerate(paths):
            item_frame = tk.Frame(scroll_frame, bg='white', relief='solid', bd=1)
            item_frame.pack(fill='x', pady=2, padx=2)
            
            # 文件名
            fname = os.path.basename(path)
            tk.Label(item_frame, text=f"{i+1}. {fname}", font=('Microsoft YaHei', 9),
                    bg='white', fg='#2c3e50', anchor='w').pack(side='left', padx=10, pady=8)
            
            # 查看按钮
            tk.Button(item_frame, text="查看原图", font=('Microsoft YaHei', 8),
                    bg='#3498db', fg='white', cursor='hand1', relief='flat', padx=10,
                    command=lambda p=path: (win.destroy(), self._show_fullscreen(p))).pack(side='right', padx=10, pady=5)
        
        # 鼠标滚轮
        canvas.bind('<MouseWheel>', lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), 'units'))
        
        # 绑定 Configure 事件
        scroll_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    
    def _show_fullscreen(self, path):
        """使用系统默认图片查看器打开原图"""
        if not os.path.exists(path):
            messagebox.showerror("错误", f"图片文件不存在:\n{path}")
            return
        
        import subprocess
        import sys
        
        try:
            # Windows: 使用系统默认程序打开
            if sys.platform == 'win32':
                os.startfile(path)
            # macOS
            elif sys.platform == 'darwin':
                subprocess.run(['open', path])
            # Linux
            else:
                subprocess.run(['xdg-open', path])
        except Exception as e:
            # 备用：使用 PIL 显示
            self._show_with_pil(path)
    
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

    def _show_with_pil(self, path):
        """备用：用 PIL + tkinter 显示图片（带缩放）"""
        from PIL import Image, ImageTk, ImageTk_tk
        
        win = tk.Toplevel(self._win)
        win.title(os.path.basename(path))
        win.state('zoomed')
        
        # 图片变量
        img_tk = None
        img_id = None
        zoom_level = [1.0]
        offset = [0, 0]
        is_dragging = [False]
        last_pos = [0, 0]
        
        def load_and_show():
            nonlocal img_tk, img_id
            img = Image.open(path)
            w, h = img.size
            # 缩放到窗口大小
            screen_w = win.winfo_screenwidth()
            screen_h = win.winfo_screenheight()
            scale = min(screen_w / w, screen_h / h, 1.0)
            new_w, new_h = int(w * scale), int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            img_tk = ImageTk.PhotoImage(img)
            canvas.config(width=new_w, height=new_h)
            canvas.delete('all')
            img_id = canvas.create_image(0, 0, anchor='nw', image=img_tk)
        
        def on_zoom(event):
            if event.delta > 0:
                zoom_level[0] *= 1.1
            else:
                zoom_level[0] *= 0.9
            zoom_level[0] = max(0.1, min(zoom_level[0], 10.0))
            apply_zoom()
        
        def apply_zoom():
            nonlocal img_tk, img_id
            img = Image.open(path)
            w, h = img.size
            new_w, new_h = int(w * zoom_level[0]), int(h * zoom_level[0])
            if new_w > 0 and new_h > 0:
                img = img.resize((new_w, new_h), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                canvas.delete('all')
                canvas.config(scrollregion=(0, 0, new_w, new_h))
                img_id = canvas.create_image(offset[0], offset[1], anchor='nw', image=img_tk)
        
        def on_drag_start(event):
            is_dragging[0] = True
            last_pos[0] = (event.x, event.y)
        
        def on_drag(event):
            if is_dragging[0]:
                dx = event.x - last_pos[0]
                dy = event.y - last_pos[1]
                offset[0] += dx
                offset[1] += dy
                last_pos[0] = event.x
                last_pos[1] = event.y
                canvas.move('all', dx, dy)
        
        def on_drag_end(event):
            is_dragging[0] = False
        
        # Canvas + 滚动条
        frame = tk.Frame(win)
        frame.pack(fill='both', expand=True)
        
        h_scroll = tk.Scrollbar(frame, orient='horizontal')
        v_scroll = tk.Scrollbar(frame, orient='vertical')
        canvas = tk.Canvas(frame, bg='#333', xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        h_scroll.config(command=canvas.xview)
        v_scroll.config(command=canvas.yview)
        
        h_scroll.pack(side='bottom', fill='x')
        v_scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        
        # 鼠标事件
        canvas.bind('<Button-1>', on_drag_start)
        canvas.bind('<B1-Motion>', on_drag)
        canvas.bind('<ButtonRelease-1>', on_drag_end)
        canvas.bind('<MouseWheel>', on_zoom)
        canvas.bind('<Configure>', lambda e: load_and_show())
        
        # 右键重置
        def reset_view(event):
            zoom_level[0] = 1.0
            offset[0] = offset[1] = 0
            canvas.xview_moveto(0)
            canvas.yview_moveto(0)
            load_and_show()
        canvas.bind('<Button-3>', reset_view)
        
        # 关闭按钮
        tk.Button(win, text='关闭', command=win.destroy,
                 bg='#444', fg='white', relief='flat',
                 font=('Microsoft YaHei', 10), padx=20).place(relx=1.0, rely=0.0, anchor='ne', x=-10, y=10)
