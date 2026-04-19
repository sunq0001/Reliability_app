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


def scan_readpoint_folder(folder_path: str) -> ReadPointInfo:
    """
    扫描单个读点文件夹

    返回：ReadPointInfo 对象
    """
    folder_name = os.path.basename(folder_path)
    readpoint_num = extract_readpoint_number(folder_name)

    if readpoint_num is None:
        # 无法识别的文件夹
        return ReadPointInfo(
            name=folder_name,
            folder_name=folder_name,
            folder_path=folder_path,
            status='error'
        )

    rp_name = f"RP{readpoint_num}"

    # 查找数据文件
    data_file = find_data_file(folder_path)

    # 查找抓图目录
    image_folder = find_image_folder(folder_path)
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

    目录结构：
    HTOL/
    ├── 168H/
    │   ├── data.csv
    │   └── image/
    │       ├── 20260204/
    │       └── 20260205/
    ├── 500H/
    │   └── ...
    └── 1000H/
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
        # 直接扫描单个读点目录
        rp_info = scan_readpoint_folder(scan_path)
        result.readpoints.append(rp_info)
        log(f"识别读点: {rp_info.name} ({rp_info.folder_name})")
    else:
        # 扫描根目录下的所有子文件夹
        try:
            subfolders = sorted([
                os.path.join(root_path, d)
                for d in os.listdir(root_path)
                if os.path.isdir(os.path.join(root_path, d))
            ])
        except PermissionError:
            log("权限不足，无法读取目录")
            return result

        for subfolder in subfolders:
            rp_info = scan_readpoint_folder(subfolder)

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


# ========== 测试 ==========
if __name__ == '__main__':
    # 测试扫描
    test_path = r"C:\Users\mss\Desktop\168H\HTOL"
    result = scan_project(test_path, print)

    print("\n扫描结果:")
    for rp in result.readpoints:
        print(f"\n  {rp.name} ({rp.folder_name})")
        print(f"    数据: {rp.data_file}")
        print(f"    抓图: {rp.image_folder}")
        print(f"    时间戳: {rp.image_timestamps[:3]}...")
        print(f"    状态: {rp.status}")
