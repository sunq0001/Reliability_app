"""
image_scanner.py - 抓图扫描与查找模块
扫描图片目录，建立「时间戳 → 图片路径」的映射，
支持按 FuseID 从 DataFrame 查对应图片。
"""
import os
import re
import glob
from collections import defaultdict


# 时间戳正则：14位 YYYYMMDDHHmmss
TS_PATTERN = re.compile(r'(\d{14})')


def parse_timestamp(filename):
    """
    从文件名中提取14位时间戳。
    返回字符串时间戳或 None。
    """
    m = TS_PATTERN.search(filename)
    return m.group(1) if m else None


def parse_scene_name(filename):
    """
    从文件名中提取场景名。
    格式: 场景x_时间戳.ext，如 Mid1A1D_0_20260204012242.png
    返回场景名字符串。
    """
    name = os.path.splitext(filename)[0]  # 去掉扩展名
    # 移除时间戳部分（14位数字）
    scene = TS_PATTERN.sub('', name)
    # 清理可能的下划线
    scene = scene.strip('_')
    return scene if scene else '未知场景'


def _find_images_in_dir(root_dir, recursive=False):
    """
    在一个目录（递归或不递归）下找所有图片。
    返回 {
        时间戳: {
            场景名: [图片绝对路径, ...],
            ...
        },
        ...
    }
    """
    img_map = defaultdict(lambda: defaultdict(list))
    exts = ['png', 'jpg', 'jpeg', 'bmp']

    def process_file(path):
        fname = os.path.basename(path)
        ts = parse_timestamp(fname)
        if ts:
            scene = parse_scene_name(fname)
            img_map[ts][scene].append(os.path.abspath(path))

    if recursive:
        for ext in exts:
            for path in glob.glob(os.path.join(root_dir, '**', f'*.{ext}'), recursive=True):
                process_file(path)
    else:
        for ext in exts:
            for path in glob.glob(os.path.join(root_dir, f'*.{ext}')):
                process_file(path)
        # 也检查一层子目录
        for sub in os.listdir(root_dir):
            sub_path = os.path.join(root_dir, sub)
            if os.path.isdir(sub_path):
                for ext in exts:
                    for path in glob.glob(os.path.join(sub_path, f'*.{ext}')):
                        process_file(path)

    # 转换为普通 dict
    result = {}
    for ts, scenes in img_map.items():
        result[ts] = {scene: list(paths) for scene, paths in scenes.items()}
    return result


def scan_image_root(root_dir):
    """
    扫描整个根目录（HTOL/168H/image/ 等结构）。

    扫描策略：
    1. 遍历所有直接子文件夹（读点目录，如 168H, 500H, 1000H）
    2. 在每个子文件夹中搜索 image/ 子目录（递归找图片）
    3. 也支持图片直接在 image/ 目录（不嵌套子目录）

    返回:
        dict: {
            'readpoints': {
                '168H': {
                    时间戳: {场景名: [图片路径列表]},
                    ...
                },
                ...
            },
            'global_ts': {
                时间戳: {场景名: [图片绝对路径]},
            },
            'all_scenes': [场景名1, 场景名2, ...],  # 所有发现的场景名
            'stats': {
                'total_images': int,
                'readpoints_found': [str],
            }
        }
    """
    result = {
        'readpoints': {},
        'global_ts': defaultdict(lambda: defaultdict(list)),
        'all_scenes': set(),
        'stats': {
            'total_images': 0,
            'readpoints_found': [],
        }
    }

    if not os.path.isdir(root_dir):
        return result

    # 遍历读点子目录
    for rp_name in os.listdir(root_dir):
        rp_path = os.path.join(root_dir, rp_name)
        if not os.path.isdir(rp_path):
            continue

        # 跳过 .workbuddy 等隐藏目录
        if rp_name.startswith('.'):
            continue

        # 找 image 目录（递归扫描）
        image_dir = os.path.join(rp_path, 'image')
        if os.path.isdir(image_dir):
            ts_map = _find_images_in_dir(image_dir, recursive=True)
        else:
            ts_map = {}

        if ts_map:
            result['readpoints'][rp_name] = ts_map
            result['stats']['readpoints_found'].append(rp_name)

        # 合并到全局索引，收集场景名
        for ts, scenes in ts_map.items():
            for scene_name, paths in scenes.items():
                result['all_scenes'].add(scene_name)
                result['global_ts'][ts][scene_name].extend(paths)

    # 全局去重
    for ts in result['global_ts']:
        for scene_name in result['global_ts'][ts]:
            seen = set()
            unique = []
            for p in result['global_ts'][ts][scene_name]:
                if p not in seen:
                    seen.add(p)
                    unique.append(p)
            result['global_ts'][ts][scene_name] = unique

    result['all_scenes'] = sorted(result['all_scenes'])
    result['stats']['total_images'] = sum(
        len(paths) 
        for scenes in result['global_ts'].values() 
        for paths in scenes.values()
    )

    return result


def build_df_timestamp_index(df):
    """
    从 DataFrame 建立「FuseID → {rp_name → timestamp}」映射。
    用于根据 FuseID 找到对应的时间戳。

    参数:
        df: 整合后的 DataFrame（SN 列是读点名，FuseID 和 column(1) 是原始列）

    返回:
        dict: {
            (rp_name, FuseID): 时间戳字符串,
            FuseID: 时间戳字符串,   # 同一 FuseID 在各读点相同时间戳
        }
    """
    index = {}

    if df is None or df.empty:
        return index

    # 找 Time 列（列名可能是 1 或 'Time'）
    time_col = None
    if 1 in df.columns:
        time_col = 1
    elif 'Time' in df.columns:
        time_col = 'Time'

    fuse_col = 'FuseID' if 'FuseID' in df.columns else None

    if time_col is None:
        return index

    for _, row in df.iterrows():
        rp = str(row.get('SN', ''))
        ts = str(row[time_col]).strip()
        if not ts or ts == 'nan':
            continue

        if fuse_col:
            fid = str(row.get(fuse_col, '')).strip()
            if fid and fid != 'nan':
                # 同时按 (rp, fuseid) 和单独 fuseid 索引
                index[(rp, fid)] = ts
                index[fid] = ts

        index[rp] = ts  # 最后一行（兼容旧逻辑）

    return index


def find_images_for_timestamp(scan_result, timestamp, readpoint=None):
    """
    根据时间戳查找对应图片。

    参数:
        scan_result: scan_image_root() 的返回值
        timestamp: 14位字符串时间戳
        readpoint: 可选，限定在某个读点内查找

    返回:
        {
            场景名: [图片绝对路径列表],
            ...
        }
    """
    if not timestamp:
        return {}

    if readpoint and readpoint in scan_result.get('readpoints', {}):
        return scan_result['readpoints'][readpoint].get(timestamp, {})
    else:
        # 转换 global_ts 格式
        raw = scan_result.get('global_ts', {}).get(timestamp, {})
        if isinstance(raw, dict) and any(isinstance(v, list) for v in raw.values()):
            return raw
        elif isinstance(raw, list):
            # 兼容旧格式：直接是路径列表
            return {'全部': raw}
        return {}


def find_images_for_fuse(df, scan_result, fuse_id, readpoint=None):
    """
    根据 FuseID 从 DataFrame 找到对应行的时间戳，再查找图片。

    参数:
        df: DataFrame
        scan_result: scan_image_root() 的返回值
        fuse_id: FuseID 字符串
        readpoint: 可选，限定读点

    返回:
        (timestamp_str, {场景名: [图片路径列表]})
    """
    if df is None or df.empty:
        return None, {}

    time_col = 1 if 1 in df.columns else ('Time' if 'Time' in df.columns else None)
    fuse_col = 'FuseID' if 'FuseID' in df.columns else None

    if time_col is None:
        return None, {}

    # 找匹配行
    if fuse_col:
        matched = df[df[fuse_col].astype(str).str.strip() == str(fuse_id).strip()]
    else:
        matched = df

    if matched.empty:
        return None, {}

    # 取第一个匹配行的时间戳
    ts = str(matched.iloc[0][time_col]).strip()
    if not ts or ts == 'nan':
        return None, {}

    images = find_images_for_timestamp(scan_result, ts, readpoint)
    return ts, images


def scan_single_image_folder(folder_path):
    """
    扫描单个抓图目录（用于"分别加载"模式）。
    
    返回:
        dict: 与 scan_image_root 相同格式的结构
    """
    result = {
        'readpoints': {'_single_': {}},
        'global_ts': defaultdict(lambda: defaultdict(list)),
        'all_scenes': set(),
        'stats': {
            'total_images': 0,
            'readpoints_found': [],
        }
    }
    
    if not os.path.isdir(folder_path):
        return result
    
    # 扫描目录
    ts_map = _find_images_in_dir(folder_path, recursive=True)
    
    if ts_map:
        result['readpoints']['_single_'] = ts_map
        result['stats']['readpoints_found'].append('_single_')
        
        # 合并到全局
        for ts, scenes in ts_map.items():
            for scene_name, paths in scenes.items():
                result['all_scenes'].add(scene_name)
                result['global_ts'][ts][scene_name].extend(paths)
    
    # 去重
    for ts in result['global_ts']:
        for scene_name in result['global_ts'][ts]:
            seen = set()
            unique = []
            for p in result['global_ts'][ts][scene_name]:
                if p not in seen:
                    seen.add(p)
                    unique.append(p)
            result['global_ts'][ts][scene_name] = unique
    
    result['all_scenes'] = sorted(result['all_scenes'])
    result['stats']['total_images'] = sum(
        len(paths)
        for scenes in result['global_ts'].values()
        for paths in scenes.values()
    )
    
    return result


def find_images_for_fuse(df, scan_result, fuse_id, readpoint=None):
    """
    根据 FuseID 从 DataFrame 找到对应行的时间戳，再查找图片。

    参数:
        df: DataFrame
        scan_result: scan_image_root() 的返回值
        fuse_id: FuseID 字符串
        readpoint: 可选，限定读点

    返回:
        (timestamp_str, list[图片路径])
    """
    if df is None or df.empty:
        return None, []

    time_col = 1 if 1 in df.columns else ('Time' if 'Time' in df.columns else None)
    fuse_col = 'FuseID' if 'FuseID' in df.columns else None

    if time_col is None:
        return None, []

    # 找匹配行
    if fuse_col:
        matched = df[df[fuse_col].astype(str).str.strip() == str(fuse_id).strip()]
    else:
        matched = df

    if matched.empty:
        return None, []

    # 取第一个匹配行的时间戳
    ts = str(matched.iloc[0][time_col]).strip()
    if not ts or ts == 'nan':
        return None, []

    images = find_images_for_timestamp(scan_result, ts, readpoint)
    return ts, images
