"""
通用工具函数模块 - 按照Token经济性原则拆分出的常用工具函数
"""

import re
import os
import json


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


# ---- 常用项持久化存储（支持多组） ----

def _get_favorite_path():
    """获取常用项存储路径（放在用户目录下）"""
    user_dir = os.path.expanduser("~")
    app_dir = os.path.join(user_dir, ".reliability_app")
    os.makedirs(app_dir, exist_ok=True)
    return os.path.join(app_dir, "favorite_items.json")


def save_favorite_items(items, group_name="默认"):
    """
    保存常用项到持久化存储（支持多组）

    Args:
        items: list，常用项名称列表
        group_name: str，组名称（默认为"默认"）
    """
    path = _get_favorite_path()
    # 加载现有数据
    all_groups = {}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                all_groups = json.load(f)
        except (json.JSONDecodeError, IOError):
            all_groups = {}
    
    # 更新指定组
    all_groups[group_name] = items
    
    # 保存
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(all_groups, f, ensure_ascii=False, indent=2)


def load_favorite_items(group_name=None):
    """
    从持久化存储加载常用项

    Args:
        group_name: str, 若是None则返回所有组；若是字符串则返回指定组

    Returns:
        若group_name为None，返回dict {组名: [items]}
        若group_name为字符串，返回list [items]
    """
    path = _get_favorite_path()
    if not os.path.exists(path):
        return {} if group_name is None else []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            all_groups = json.load(f)
        if group_name is None:
            return all_groups
        return all_groups.get(group_name, [])
    except (json.JSONDecodeError, IOError):
        return {} if group_name is None else []


def delete_favorite_group(group_name):
    """删除指定组的常用项"""
    path = _get_favorite_path()
    if not os.path.exists(path):
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            all_groups = json.load(f)
        if group_name in all_groups:
            del all_groups[group_name]
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(all_groups, f, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, IOError):
        pass


def clear_favorite_items():
    """清除所有保存的常用项"""
    path = _get_favorite_path()
    if os.path.exists(path):
        os.remove(path)