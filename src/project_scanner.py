"""
project_scanner.py - 项目目录扫描器
自动识别根目录下的读点文件夹，支持：
- 匹配 "数字H" 格式（如 168H, 500H）
- 匹配 "T+数字" 格式（如 T24, T5）
- 同时识别数据文件和抓图目录
"""

import os
import re
import glob
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple


@dataclass
class ReadPointInfo:
    """单个读点的完整信息"""
    name: str              # 读点名称（如 RP168）
    folder_name: str       # 文件夹名称（如 168H）
    folder_path: str       # 文件夹完整路径
    data_file: Optional[str] = None      # 数据文件路径
    image_folder: Optional[str] = None   # 抓图目录路径
    image_timestamps: List[str] = field(default_factory=list)  # 时间戳列表
    status: str = 'pending'  # pending | ok | warning | error

    @property
    def has_data(self) -> bool:
        return self.data_file is not None

    @property
    def has_images(self) -> bool:
        return self.image_folder is not None

    @property
    def is_complete(self) -> bool:
        return self.has_data and self.has_images


@dataclass
class ProjectScanResult:
    """扫描结果"""
    root_path: str
    root_name: str
    readpoints: List[ReadPointInfo] = field(default_factory=list)
    mode: str = 'auto'  # 'auto' = 扫描根目录, 'single' = 直接选择读点目录
    # 图片索引：{读点文件夹名: {时间戳: [(场景名, 路径), ...]}}
    image_index: Dict[str, Dict[str, List[Tuple[str, str]]]] = field(default_factory=dict)

    def get_images(self, readpoint_folder: str, timestamp: str) -> List[Tuple[str, str]]:
        """
        根据读点文件夹名和时间戳获取图片列表

        参数:
            readpoint_folder: 读点文件夹名，如 "168H", "500H"
            timestamp: 时间戳字符串，如 "20260204012242"

        返回: [(场景名, 路径), ...]
        """
        if readpoint_folder in self.image_index:
            return self.image_index[readpoint_folder].get(timestamp, [])
        return []

    def get_all_images_for_readpoint(self, readpoint_folder: str) -> Dict[str, List[Tuple[str, str]]]:
        """获取读点的所有图片（按时间戳分组）"""
        return self.image_index.get(readpoint_folder, {})


def extract_readpoint_number(folder_name: str) -> Optional[int]:
    """
    从文件夹名提取读点编号

    匹配规则：
    - "数字H" 格式：168H, 500H, ReadPoint168H
    - "T+数字" 格式：T24, T5, Test_T24

    返回：数字（如 168, 500, 24）或 None
    """
    # 优先匹配 数字H 格式
    match_dh = re.search(r'(\d+)H', folder_name, re.IGNORECASE)
    if match_dh:
        return int(match_dh.group(1))

    # 匹配 T+数字 格式
    match_t = re.search(r'T(\d+)', folder_name, re.IGNORECASE)
    if match_t:
        return int(match_t.group(1))

    return None


def is_data_file(filename: str) -> bool:
    """判断是否为数据文件"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ['.csv', '.xlsx', '.xls']


def find_data_file(folder_path: str) -> Optional[str]:
    """在文件夹中查找数据文件"""
    for ext in ['csv', 'xlsx', 'xls']:
        files = glob.glob(os.path.join(folder_path, f'*.{ext}'))
        if files:
            # 返回最新的文件
            return max(files, key=os.path.getmtime)
    return None


def find_image_folder(folder_path: str) -> Optional[str]:
    """查找抓图目录（image/ 或其他名称的图片目录）"""
    # 优先查找 image/
    image_path = os.path.join(folder_path, 'image')
    if os.path.isdir(image_path):
        return image_path

    # 查找其他可能的图片目录
    for name in ['images', 'img', 'photo', 'photos', 'capture', 'captures']:
        path = os.path.join(folder_path, name)
        if os.path.isdir(path):
            return path

    # 如果文件夹直接包含图片文件
    for ext in ['.png', '.jpg', '.jpeg', '.bmp']:
        if glob.glob(os.path.join(folder_path, f'*{ext}')):
            return folder_path

    return None


def find_image_folder_deep(folder_path: str, max_depth: int = 20) -> Optional[str]:
    """
    在文件夹及其深层子目录中查找抓图目录

    参数:
        folder_path: 起始文件夹路径
        max_depth: 最大递归深度

    返回：找到的图片目录路径，或 None
    """
    def has_images(path: str) -> bool:
        """检查目录是否包含图片文件"""
        for ext in ['.png', '.jpg', '.jpeg', '.bmp']:
            if glob.glob(os.path.join(path, f'*{ext}')):
                return True
        return False

    def has_image_subfolder(path: str) -> bool:
        """检查是否有图片子目录（时间戳目录）"""
        try:
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path) and has_images(item_path):
                    return True
        except PermissionError:
            pass
        return False

    def search_recursive(current_path: str, current_depth: int) -> Optional[str]:
        if current_depth > max_depth:
            return None

        # 检查当前目录是否就是图片目录
        if has_images(current_path):
            return current_path

        # 优先查找常见的图片目录名
        for name in ['image', 'images', 'img', 'photo', 'photos', 'capture', 'captures']:
            image_path = os.path.join(current_path, name)
            if os.path.isdir(image_path):
                if has_images(image_path):
                    return image_path

        # 递归搜索所有子目录
        try:
            for item in os.listdir(current_path):
                item_path = os.path.join(current_path, item)
                if os.path.isdir(item_path):
                    result = search_recursive(item_path, current_depth + 1)
                    if result:
                        return result
        except PermissionError:
            pass

        return None

    return search_recursive(folder_path, 0)


def scan_image_timestamps(image_folder: str) -> List[str]:
    """扫描抓图目录下的所有时间戳子文件夹"""
    timestamps = []

    if not image_folder or not os.path.isdir(image_folder):
        return timestamps

    # 遍历目录
    for item in os.listdir(image_folder):
        item_path = os.path.join(image_folder, item)

        # 如果是时间戳文件夹（14位数字）
        if os.path.isdir(item_path):
            # 检查是否包含图片
            has_images = any(
                os.path.isfile(os.path.join(item_path, f))
                for f in os.listdir(item_path)
                if f.endswith(('.png', '.jpg', '.jpeg', '.bmp'))
            )
            if has_images:
                timestamps.append(item)

        # 如果直接是图片文件（没有时间戳子文件夹）
        elif os.path.isfile(item_path) and item.endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            timestamps.append('_root_')  # 标记为直接在根目录

    return sorted(timestamps)


def get_images_for_timestamp(image_folder: str, timestamp: str) -> List[Tuple[str, str]]:
    """
    获取指定时间戳下的所有图片

    返回: List[(场景名, 文件路径)]，如 [('Dark', '.../Dark.png'), ('Mid', '.../Mid.png')]
    """
    import re
    images = []

    if not image_folder or not os.path.isdir(image_folder):
        return images

    # 时间戳文件夹
    if timestamp != '_root_':
        ts_folder = os.path.join(image_folder, timestamp)
        if not os.path.isdir(ts_folder):
            return images
        folder = ts_folder
    else:
        folder = image_folder

    # 扫描图片文件
    for f in os.listdir(folder):
        if not f.endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            continue

        # 解析场景名：格式如 Dark_0_20260204012242.png
        # 场景名 = 文件名中时间戳之前的部分
        match = re.match(r'([^_]+)_(\d+)_(\d+)\.(png|jpg|jpeg|bmp)', f, re.IGNORECASE)
        if match:
            scene_name = match.group(1)  # 如 Dark, Dark2, Mid1A1D, TestPattern
        else:
            # 备用：从文件名提取第一部分
            scene_name = os.path.splitext(f)[0].split('_')[0]

        full_path = os.path.join(folder, f)
        images.append((scene_name, full_path))

    return images


def scan_all_images_for_readpoint(readpoint_info: 'ReadPointInfo') -> Dict[str, List[Tuple[str, str]]]:
    """
    扫描读点的所有图片，建立按时间戳索引的字典

    返回: {时间戳: [(场景名, 路径), ...]}

    目录结构：
    {读点文件夹}/
        image/
            {时间戳1}/
                Dark_0_{时间戳1}.png
                Dark2_0_{时间戳1}.png
            {时间戳2}/
                Dark_0_{时间戳2}.png
                ...
    """
    import re
    ts_images = {}  # {时间戳: [(场景名, 路径), ...]}

    if not readpoint_info.image_folder or not os.path.isdir(readpoint_info.image_folder):
        return ts_images

    image_folder = readpoint_info.image_folder

    # 遍历所有时间戳子文件夹
    for item in os.listdir(image_folder):
        item_path = os.path.join(image_folder, item)

        if not os.path.isdir(item_path):
            continue

        # 检查是否包含图片
        ts = item  # 时间戳就是文件夹名

        # 扫描该时间戳下的所有图片
        images = []
        for f in os.listdir(item_path):
            if not f.endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                continue

            # 解析场景名：格式如 Dark_0_20260204012242.png
            match = re.match(r'([^_]+)_(\d+)_(\d+)\.(png|jpg|jpeg|bmp)', f, re.IGNORECASE)
            if match:
                scene_name = match.group(1)
            else:
                scene_name = os.path.splitext(f)[0].split('_')[0]

            full_path = os.path.join(item_path, f)
            images.append((scene_name, full_path))

        if images:
            ts_images[ts] = images

    return ts_images


def get_all_images_by_readpoint(readpoint_info: 'ReadPointInfo', timestamp: str) -> Dict[str, List[Tuple[str, str]]]:
    """
    获取指定读点在指定时间戳下的所有图片
    
    返回: {读点名: [(场景名, 路径), ...]}
    """
    import re
    result = {}
    
    if not readpoint_info.image_folder or not os.path.isdir(readpoint_info.image_folder):
        return result
    
    # 时间戳文件夹
    if timestamp != '_root_':
        ts_folder = os.path.join(readpoint_info.image_folder, timestamp)
        if not os.path.isdir(ts_folder):
            return result
        folder = ts_folder
    else:
        folder = readpoint_info.image_folder
    
    for f in os.listdir(folder):
        if not f.endswith(('.png', '.jpg', '.jpeg', '.bmp')):
            continue
        
        # 解析场景名
        match = re.match(r'([^_]+)_(\d+)_(\d+)\.(png|jpg|jpeg|bmp)', f, re.IGNORECASE)
        if match:
            scene_name = match.group(1)
        else:
            scene_name = os.path.splitext(f)[0].split('_')[0]
        
        full_path = os.path.join(folder, f)
        
        rp_name = readpoint_info.name
        if rp_name not in result:
            result[rp_name] = []
        result[rp_name].append((scene_name, full_path))
    
    return result


def scan_readpoint_folder(folder_path: str, depth: int = 0, max_depth: int = 20) -> ReadPointInfo:
    """
    扫描单个读点文件夹，支持深层嵌套查找数据文件

    参数:
        folder_path: 读点文件夹路径
        depth: 当前递归深度
        max_depth: 最大递归深度，防止无限递归

    返回：ReadPointInfo 对象
    """
    folder_name = os.path.basename(folder_path)
    readpoint_num = extract_readpoint_number(folder_name)

    if readpoint_num is None:
        return ReadPointInfo(
            name=folder_name,
            folder_name=folder_name,
            folder_path=folder_path,
            status='error'
        )

    rp_name = f"RP{readpoint_num}"

    # 查找数据文件（包括深层嵌套）
    data_file = find_data_file_deep(folder_path, max_depth)

    # 查找抓图目录
    image_folder = find_image_folder_deep(folder_path)
    timestamps = []

    if image_folder:
        timestamps = scan_image_timestamps(image_folder)

    # 判断状态
    status = 'ok'
    if data_file and image_folder:
        status = 'ok'
    elif data_file or image_folder:
        status = 'warning'
    else:
        status = 'error'

    return ReadPointInfo(
        name=rp_name,
        folder_name=folder_name,
        folder_path=folder_path,
        data_file=data_file,
        image_folder=image_folder,
        image_timestamps=timestamps,
        status=status
    )


def find_data_file_deep(folder_path: str, max_depth: int = 20) -> Optional[str]:
    """
    在文件夹及其深层子目录中查找数据文件

    参数:
        folder_path: 起始文件夹路径
        max_depth: 最大递归深度

    返回：找到的数据文件路径，或 None
    """
    def search_recursive(current_path: str, current_depth: int) -> Optional[str]:
        if current_depth > max_depth:
            return None

        # 在当前目录查找数据文件
        data_file = find_data_file(current_path)
        if data_file:
            return data_file

        # 递归搜索所有子目录
        try:
            for item in os.listdir(current_path):
                item_path = os.path.join(current_path, item)
                if os.path.isdir(item_path):
                    result = search_recursive(item_path, current_depth + 1)
                    if result:
                        return result
        except PermissionError:
            pass

        return None

    return search_recursive(folder_path, 0)


def find_readpoint_folders_in_tree(root_path: str, log_callback=None) -> List[str]:
    """
    从根目录递归遍历，查找所有读点文件夹

    参数:
        root_path: 根目录路径
        log_callback: 日志回调函数

    返回：读点文件夹路径列表
    """
    readpoint_paths = []

    def scan_recursive(current_path: str, depth: int, max_depth: int = 20):
        if depth > max_depth:
            return

        try:
            items = os.listdir(current_path)
        except PermissionError:
            return

        for item in items:
            item_path = os.path.join(current_path, item)

            if not os.path.isdir(item_path):
                continue

            # 检查是否匹配读点格式
            readpoint_num = extract_readpoint_number(item)

            if readpoint_num is not None:
                # 找到读点文件夹，加入列表
                readpoint_paths.append(item_path)
                if log_callback:
                    log_callback(f"  发现读点: {item} (深度 {depth})")

                # 继续递归扫描此读点文件夹的子目录（可能有更多数据）
                scan_recursive(item_path, depth + 1, max_depth)
            else:
                # 不是读点格式，继续递归扫描
                scan_recursive(item_path, depth + 1, max_depth)

    scan_recursive(root_path, 0)
    return readpoint_paths


def detect_mode(path: str) -> tuple:
    """
    检测输入路径是根目录还是读点目录

    返回：(mode, actual_path)
    - mode='single': 直接是读点目录
    - mode='auto': 根目录，需要扫描子文件夹
    """
    folder_name = os.path.basename(path)
    readpoint_num = extract_readpoint_number(folder_name)

    if readpoint_num is not None:
        # 文件夹名本身就是读点格式（如 168H）
        return ('single', path)
    else:
        # 文件夹名不是读点格式，尝试作为根目录扫描
        return ('auto', path)


def scan_project(root_path: str, log_callback=None) -> ProjectScanResult:
    """
    扫描项目根目录，识别所有读点，并建立图片索引
    支持深层嵌套目录结构：
    根目录 → 子文件夹 → ... → 100H → 子文件夹 → ... → 数据文件

    目录结构示例：
    HTOL/
    ├── 168H/
    │   ├── data.csv
    │   └── image/
    ├── 500H/
    │   ├── 子文件夹/
    │   │   └── 1000H/
    │   │       └── 深层数据/
    │   │           └── data.csv
    └── ...

    返回：ProjectScanResult（包含 image_index 图片索引）
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    result = ProjectScanResult(
        root_path=root_path,
        root_name=os.path.basename(root_path)
    )

    if not os.path.isdir(root_path):
        log(f"路径不存在: {root_path}")
        return result

    # 检测是根目录还是读点目录
    mode, scan_path = detect_mode(root_path)
    result.mode = mode

    log(f"检测模式: {mode}, 扫描路径: {scan_path}")

    if mode == 'single':
        # 直接扫描单个读点目录（支持深层查找数据）
        rp_info = scan_readpoint_folder(scan_path)
        result.readpoints.append(rp_info)
        log(f"识别读点: {rp_info.name} ({rp_info.folder_name})")
    else:
        # 从根目录递归扫描所有子目录，查找读点文件夹
        log("开始递归扫描目录树...")
        readpoint_paths = find_readpoint_folders_in_tree(root_path, log)

        # 处理每个找到的读点
        for rp_path in readpoint_paths:
            rp_info = scan_readpoint_folder(rp_path)

            # 只添加成功识别的读点
            if rp_info.name.startswith('RP'):
                result.readpoints.append(rp_info)
                status_icon = '[OK]' if rp_info.status == 'ok' else '[!]' if rp_info.status == 'warning' else '[X]'
                log(f"{status_icon} 识别读点: {rp_info.name} ({rp_info.folder_name})")

                # 建立该读点的图片索引
                if rp_info.image_folder:
                    ts_images = scan_all_images_for_readpoint(rp_info)
                    if ts_images:
                        result.image_index[rp_info.folder_name] = ts_images
                        log(f"    └── 扫描到 {len(ts_images)} 个时间戳的图片")

    # 按读点编号排序
    result.readpoints.sort(key=lambda x: int(re.search(r'\d+', x.name).group())
                          if re.search(r'\d+', x.name) else 0)

    total_images = sum(len(ts_list) for ts_dict in result.image_index.values() for ts_list in ts_dict.values())
    log(f"共识别 {len(result.readpoints)} 个读点，预建图片索引 {total_images} 张")

    return result


def build_directory_tree(root_path: str, log_callback=None, max_depth: int = 20) -> str:
    """
    构建完整的目录树并返回树形字符串

    参数:
        root_path: 根目录路径
        log_callback: 日志回调函数
        max_depth: 最大显示深度

    返回: 目录树字符串
    """
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"📁 目录树分析: {root_path}")
    lines.append(f"{'='*60}\n")

    readpoint_nums = set()  # 用于记录所有读点编号

    def is_readpoint_folder(name: str) -> bool:
        """判断文件夹是否为读点"""
        return extract_readpoint_number(name) is not None

    def get_readpoint_label(name: str) -> str:
        """获取读点标签"""
        num = extract_readpoint_number(name)
        if num:
            return f" [RP{num}]"
        return ""

    def scan_tree(path: str, prefix: str = "", depth: int = 0):
        if depth > max_depth:
            return

        try:
            items = sorted(os.listdir(path))
        except PermissionError:
            lines.append(f"{prefix}└── [权限拒绝]")
            return
        except Exception as e:
            lines.append(f"{prefix}└── [错误: {e}]")
            return

        # 分离文件夹和文件
        dirs = [i for i in items if os.path.isdir(os.path.join(path, i))]
        files = [i for i in items if os.path.isfile(os.path.join(path, i))]

        all_items = [(d, True) for d in dirs] + [(f, False) for f in files]

        for i, (name, is_dir) in enumerate(all_items):
            is_last = (i == len(all_items) - 1)
            connector = "└── " if is_last else "├── "

            full_path = os.path.join(path, name)

            if is_dir:
                rp_label = get_readpoint_label(name)
                # 检查是否包含数据文件或图片
                has_data = bool(find_data_file(full_path) or find_data_file_deep(full_path, 5))
                has_imgs = bool(find_image_folder_deep(full_path, 5))

                extra_info = []
                if rp_label:
                    extra_info.append("📍读点")
                if has_data:
                    extra_info.append("📊数据")
                if has_imgs:
                    extra_info.append("🖼️图片")
                extra_str = f" ({', '.join(extra_info)})" if extra_info else ""

                lines.append(f"{prefix}{connector}📂 {name}{rp_label}{extra_str}")

                # 递归处理子目录
                new_prefix = prefix + ("    " if is_last else "│   ")
                scan_tree(full_path, new_prefix, depth + 1)
            else:
                # 检查是否为数据文件或图片
                ext = os.path.splitext(name)[1].lower()
                icon = "📊" if ext in ['.csv', '.xlsx', '.xls'] else ("🖼️" if ext in ['.png', '.jpg', '.jpeg', '.bmp'] else "📄")
                lines.append(f"{prefix}{connector}{icon} {name}")

    scan_tree(root_path)

    # 统计信息
    lines.append(f"\n{'='*60}")
    lines.append("📊 统计摘要:")
    lines.append(f"{'='*60}")

    # 统计读点
    readpoint_count = 0
    for root, dirs, files in os.walk(root_path):
        for d in dirs:
            if is_readpoint_folder(d):
                readpoint_count += 1
                break  # 每个读点只计算一次

    lines.append(f"  读点数量: {readpoint_count}")

    return "\n".join(lines)


def analyze_readpoint_detail(rp_info: 'ReadPointInfo', log_callback=None) -> str:
    """
    详细分析单个读点的内容

    返回: 分析报告字符串
    """
    lines = []
    lines.append(f"\n{'─'*50}")
    lines.append(f"📍 读点: {rp_info.name} ({rp_info.folder_name})")
    lines.append(f"{'─'*50}")

    # 文件夹路径
    lines.append(f"  📂 路径: {rp_info.folder_path}")

    # 数据文件
    if rp_info.data_file:
        lines.append(f"\n  📊 数据文件:")
        lines.append(f"     {os.path.basename(rp_info.data_file)}")
        lines.append(f"     完整路径: {rp_info.data_file}")
    else:
        lines.append(f"\n  📊 数据文件: 未找到 ✗")

    # 抓图目录
    if rp_info.image_folder:
        lines.append(f"\n  🖼️ 抓图目录:")
        lines.append(f"     {rp_info.image_folder}")

        # 扫描图片文件
        img_files = []
        for root, _, files in os.walk(rp_info.image_folder):
            for f in files:
                if f.endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                    img_files.append(os.path.join(root, f))

        if img_files:
            lines.append(f"     共 {len(img_files)} 个图片文件:")
            # 按时间戳分组显示
            ts_groups = {}
            for img_path in sorted(img_files):
                ts_match = re.search(r'(\d{14})', img_path)
                ts = ts_match.group(1) if ts_match else '_no_ts_'
                if ts not in ts_groups:
                    ts_groups[ts] = []
                ts_groups[ts].append(os.path.basename(img_path))

            for ts, files in sorted(ts_groups.items()):
                if ts == '_no_ts_':
                    lines.append(f"       [无时间戳]: {', '.join(files[:5])}")
                    if len(files) > 5:
                        lines.append(f"                    ... 共 {len(files)} 个")
                else:
                    formatted_ts = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}"
                    lines.append(f"       [{formatted_ts}]: {', '.join(files)}")
        else:
            lines.append(f"     未找到图片文件 ✗")
    else:
        lines.append(f"\n  🖼️ 抓图目录: 未找到 ✗")

    return "\n".join(lines)


def scan_project_with_tree(root_path: str, log_callback=None) -> tuple:
    """
    扫描项目并输出目录树到日志

    返回: (ProjectScanResult, directory_tree_str)
    """
    # 构建目录树并输出到日志
    tree_str = build_directory_tree(root_path, log_callback)
    
    # 输出到日志（每行单独输出）
    if log_callback:
        for line in tree_str.split('\n'):
            log_callback(line)

    # 执行标准扫描
    result = scan_project(root_path, log_callback)

    # 生成每个读点的详细分析并输出到日志
    if log_callback:
        log_callback(f"\n{'='*60}")
        log_callback("🔍 读点详细分析")
        log_callback(f"{'='*60}")

        for rp in result.readpoints:
            for line in analyze_readpoint_detail(rp, log_callback).split('\n'):
                log_callback(line)

        log_callback(f"\n{'='*60}")
        log_callback(f"扫描完成！共识别 {len(result.readpoints)} 个读点")
        log_callback(f"{'='*60}\n")

    return result, tree_str


# ========== 测试 ==========
if __name__ == '__main__':
    # 测试扫描
    test_path = r"C:\Users\mss\Desktop\168H\HTOL"
    result, tree_output = scan_project_with_tree(test_path, print)

    print(tree_output)
