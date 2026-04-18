"""
通用工具函数模块 - 按照Token经济性原则拆分出的常用工具函数
"""

import re
import os


def format_ts_for_display(ts):
    """14位时间戳转友好格式"""
    s = str(ts)
    if len(s) >= 14:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}:{s[12:14]}"
    return str(ts)


def sanitize_filename(name):
    """移除文件名中的非法字符"""
    return re.sub(r'[\\/:*?"<>|]', '_', str(name)).strip()


def validate_read_point_name(name):
    """验证时间读点名称格式"""
    if not name or name == "未选择":
        return False
    # 允许字母、数字、汉字、空格、括号、中划线、下划线
    pattern = r'^[A-Za-z0-9\u4e00-\u9fa5_\-\(\)\s]+$'
    return bool(re.match(pattern, name))


def get_file_size_display(size_bytes):
    """将字节数转换为可读的文件大小格式"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def safe_float_conversion(value, default=0.0):
    """安全地将值转换为浮点数"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def calculate_percentage_change(old_value, new_value):
    """计算百分比变化"""
    if old_value == 0:
        return float('inf') if new_value > 0 else 0.0
    return ((new_value - old_value) / abs(old_value)) * 100.0