"""
事件处理器模块 - 按照Token经济性原则拆分出的事件处理逻辑
包含所有以_on_开头的事件回调方法
"""

import tkinter as tk
from tkinter import messagebox
import os


class EventHandlers:
    """事件处理器类，封装所有事件回调逻辑"""
    
    def __init__(self, app):
        """
        初始化事件处理器
        
        Args:
            app: 主应用程序实例，用于访问UI组件和状态
        """
        self.app = app
    
    def _on_entry_focus_in(self, event):
        """输入框获得焦点时清空提示文字"""
        if self.app.new_read_point_entry.get() == "新增读点":
            self.app.new_read_point_entry.delete(0, 'end')
    
    def _on_entry_focus_out(self, event):
        """输入框失去焦点时恢复提示"""
        if not self.app.new_read_point_entry.get():
            self.app.new_read_point_entry.insert(0, "新增读点")
    
    def _on_search_focus_in(self, event):
        """搜索框获得焦点时清空提示"""
        if self.app.image_search_entry.get() == "输入FuseID或时间戳":
            self.app.image_search_entry.delete(0, 'end')
    
    def _on_search_focus_out(self, event):
        """搜索框失去焦点时恢复提示"""
        if not self.app.image_search_entry.get():
            self.app.image_search_entry.insert(0, "输入FuseID或时间戳")
    
    def _on_image_scan_done(self, result):
        """扫描完成后在主线程回调"""
        self.app._image_scan_result = result
        stats = result.get('stats', {})
        total = stats.get('total_images', 0)
        rps = stats.get('readpoints_found', [])
        
        if total == 0:
            self.app._img_scan_status_var.set("⚠️ 未找到任何图片，请检查目录结构")
            if hasattr(self.app, '_scan_img_btn'):
                self.app._scan_img_btn.config(state='normal', text='🔍 扫描抓图')
            self.app.log("[抓图] 扫描完成：未找到图片", 'warning')
        else:
            rp_str = ", ".join(rps)
            self.app._img_scan_status_var.set(
                f"✅ 找到 {total} 张图片  |  读点: {rp_str}"
            )
            if hasattr(self.app, '_scan_img_btn'):
                self.app._scan_img_btn.config(state='normal', text='🔍 重新扫描')
            self.app.log(f"[抓图] 扫描完成：{total} 张图片，读点: {rp_str}", 'success')
    
    def _on_search_image_output(self):
        """
        搜索栏「出图」按钮：同时支持 FuseID 和时间戳两种输入。
        - 12-14位纯数字 → 先按时间戳直接查图，找不到再试 FuseID
        - 其他纯数字 → 按 FuseID 查 DataFrame → 找时间戳 → 查图
        - 非数字 → 报错
        """
        from src.utils import format_ts_for_display
        
        search_term = self.app.image_search_entry.get().strip()
        if not search_term or search_term in ("输入FuseID或时间戳", "FuseID或时间戳"):
            messagebox.showwarning("提示", "请输入FuseID或时间戳")
            return

        if self.app._image_scan_result is None:
            messagebox.showwarning("提示",
                "请先在「抓图路径配置」中选择根目录并点击「扫描抓图」")
            return

        # 非数字报错
        if not search_term.isdigit():
            messagebox.showwarning("提示",
                f"输入「{search_term}」不是有效的FuseID或时间戳\n"
                f"时间戳示例: 20260204012242\nFuseID示例: 123456")
            return

        # 判断输入类型：12-14位数字先试时间戳，其他数字试FuseID
        is_possible_timestamp = 12 <= len(search_term) <= 14

        if is_possible_timestamp:
            # 时间戳模式：直接查图
            from src.image_scanner import find_images_for_timestamp
            paths = find_images_for_timestamp(
                self.app._image_scan_result, search_term
            )
            if paths:
                self.app.log(f"[出图] 时间戳 {search_term} → 找到 {len(paths)} 张图", 'success')
                self.app._image_viewer.show_for_timestamp(search_term)
                return

            # 时间戳没找到 → 降级试 FuseID（FuseID可能也是12-14位数字）
            if hasattr(self.app, '_current_df') and self.app._current_df is not None:
                from src.image_scanner import find_images_for_fuse
                ts, paths2 = find_images_for_fuse(
                    self.app._current_df, self.app._image_scan_result, search_term
                )
                if paths2:
                    self.app.log(f"[出图] FuseID={search_term}（{ts}）→ 找到 {len(paths2)} 张图", 'success')
                    self.app._image_viewer.show_for_fuse(search_term)
                    return

            messagebox.showinfo("未找到",
                f"时间戳 {format_ts_for_display(search_term)}\n"
                f"对应抓图不存在（也非有效FuseID）")
            self.app.log(f"[出图] 「{search_term}」既非有效时间戳也无对应FuseID图片", 'warning')
        else:
            # FuseID 模式（短数字）
            if not hasattr(self.app, '_current_df') or self.app._current_df is None:
                messagebox.showwarning("提示",
                    f"「{search_term}」不是时间戳格式（需12-14位）\n"
                    f"且尚未加载数据，无法按FuseID查图\n"
                    f"请先执行「开始分析」")
                return

            from src.image_scanner import find_images_for_fuse
            ts, paths = find_images_for_fuse(
                self.app._current_df, self.app._image_scan_result, search_term
            )
            if paths:
                self.app.log(f"[出图] FuseID={search_term}（{ts}）→ 找到 {len(paths)} 张图", 'success')
                self.app._image_viewer.show_for_fuse(search_term)
            else:
                if ts:
                    messagebox.showinfo("未找到",
                        f"FuseID={search_term}（{format_ts_for_display(ts)}）\n"
                        f"对应抓图不存在")
                else:
                    messagebox.showinfo("未找到",
                        f"FuseID={search_term} 在数据中未找到时间戳")
                self.app.log(f"[出图] FuseID={search_term} 未找到对应图片", 'warning')
    
    def _on_analysis_done(self, analysis_result, test_items, error_type=None):
        """分析完成后在主线程回调：恢复按钮、显示结果"""
        self.app._analysis_running = False
        if hasattr(self.app, '_analysis_btn'):
            self.app._analysis_btn.config(state='normal', text='开始分析')
        
        if analysis_result is None:
            if error_type:
                self.app.log(f"\n❌ 分析失败: {error_type}", 'error')
            return
        
        if analysis_result['summary']:
            self.app.log("\n=== 漂移检测结果 ===", 'warning')
            for msg in analysis_result['summary']:
                self.app.log(msg, 'warning')
        else:
            self.app.log("\n✅ 未检测到显著漂移", 'success')
        
        self.app._current_analysis = analysis_result
        self.app.log(f"\n✅ 分析完成！共分析 {len(test_items)} 个测试项", 'success')
        self.app.log("可点击「生成图表」查看可视化结果", 'info')