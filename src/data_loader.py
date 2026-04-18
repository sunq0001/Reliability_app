"""
data_loader.py - 数据加载模块
负责：从各读点路径加载数据文件，支持并行读取加速
"""

import os
import pandas as pd
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed


def _load_single_file(filepath, rp_name, log_callback=None):
    """
    加载单个文件，返回 (rp_name, DataFrame, error_msg)
    在线程中执行，不能操作 UI
    """
    df = None
    encodings = ['gbk', 'gb2312', 'utf-8', 'latin-1', 'iso-8859-1', 'cp1252']

    try:
        if filepath.endswith('.csv'):
            for enc in encodings:
                try:
                    df = pd.read_csv(filepath, encoding=enc, low_memory=False)
                    if 'SN' in df.columns:
                        break
                except Exception:
                    df = None
            if df is None:
                return (rp_name, None, f"编码失败: {os.path.basename(filepath)}")
        else:
            df = pd.read_excel(filepath)

        # 清理列名中的空格
        df.columns = df.columns.str.strip()

        # 动态跳过无效行：找到第一个 SN 列不是标题行（不是 "SN"）的数据行
        data_start_row = 0
        if 'SN' in df.columns:
            for idx, val in enumerate(df['SN']):
                if str(val).strip() != 'SN':
                    data_start_row = idx
                    break

        # 从第一个有效数据行开始截取
        if data_start_row > 0:
            df = df.iloc[data_start_row:].reset_index(drop=True)

        # 确保 SN 列包含读点标识
        df['SN'] = rp_name

        return (rp_name, df, None)

    except Exception as e:
        return (rp_name, None, f"加载失败: {str(e)}")


def load_data_from_read_points(read_points, log_callback=None):
    """
    从配置的读点加载数据，支持并行读取

    参数:
        read_points: dict, {读点名称: 文件路径或文件夹路径}
        log_callback: callable, 用于日志回调的函数 (message, level)

    返回:
        DataFrame or None
    """
    all_data = []
    all_errors = []

    def log(msg, level='info'):
        if log_callback:
            log_callback(msg, level)

    # 第一步：收集所有待加载的文件（文件路径 + 读点名称）
    tasks = []  # [(filepath, rp_name)]
    for rp_name, rp_path in read_points.items():
        if log_callback:
            log(f"[加载] 读点 {rp_name}: {rp_path}", 'info')

        if os.path.isfile(rp_path):
            tasks.append((rp_path, rp_name))
        else:
            # 搜索 Excel 文件
            files = glob.glob(os.path.join(rp_path, '**', '*.xlsx'), recursive=True)
            files.extend(glob.glob(os.path.join(rp_path, '**', '*.xls'), recursive=True))
            files.extend(glob.glob(os.path.join(rp_path, '**', '*.csv'), recursive=True))
            for f in files:
                tasks.append((f, rp_name))

    if not tasks:
        if log_callback:
            log("[警告] 没有找到任何数据文件", 'warning')
        return None

    # 第二步：并行加载所有文件
    log(f"[并行加载] 共 {len(tasks)} 个文件，线程数={min(8, len(tasks))}", 'info')

    with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as executor:
        futures = {executor.submit(_load_single_file, fp, rn, log_callback): (fp, rn)
                   for fp, rn in tasks}

        for future in as_completed(futures):
            rp_name, df, err = future.result()
            if err:
                all_errors.append(err)
                if log_callback:
                    log(f"  -> {err}", 'warning')
            elif df is not None:
                data_start_row = 0
                if 'SN' in df.columns:
                    for idx, val in enumerate(df['SN']):
                        if str(val).strip() != 'SN':
                            data_start_row = idx
                            break
                all_data.append(df)
                if log_callback:
                    log(f"  -> 跳过前{data_start_row}行无效数据，加载 {len(df)} 行", 'success')

    # 第三步：合并数据
    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        if log_callback:
            log(f"[总计] 合并后共 {len(combined)} 行数据", 'success')
            if all_errors:
                log(f"[警告] 有 {len(all_errors)} 个文件加载失败", 'warning')
        return combined
    else:
        if log_callback:
            log("[错误] 所有文件加载均失败", 'error')
        return None


# 以下是单线程版本，保留兼容（当并行不可用时回退）
def load_data_from_read_points_sequential(read_points, log_callback=None):
    """
    单线程顺序加载（与原实现一致，保留兼容）
    """
    def log(msg, level='info'):
        if log_callback:
            log_callback(msg, level)

    all_data = []

    for rp_name, rp_path in read_points.items():
        if log_callback:
            log(f"[加载] 读点 {rp_name}: {rp_path}", 'info')

        if os.path.isfile(rp_path):
            files = [rp_path]
        else:
            files = glob.glob(os.path.join(rp_path, '**', '*.xlsx'), recursive=True)
            files.extend(glob.glob(os.path.join(rp_path, '**', '*.xls'), recursive=True))
            files.extend(glob.glob(os.path.join(rp_path, '**', '*.csv'), recursive=True))

        for f in files:
            rp_name_out, df, err = _load_single_file(f, rp_name, log_callback)
            if err:
                if log_callback:
                    log(f"  -> {err}", 'warning')
            elif df is not None:
                all_data.append(df)
                if log_callback:
                    data_start_row = 0
                    if 'SN' in df.columns:
                        for idx, val in enumerate(df['SN']):
                            if str(val).strip() != 'SN':
                                data_start_row = idx
                                break
                    log(f"  -> 跳过前{data_start_row}行无效数据，加载 {len(df)} 行", 'success')

    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        if log_callback:
            log(f"[总计] 合并后共 {len(combined)} 行数据", 'success')
        return combined
    else:
        if log_callback:
            log("[错误] 数据加载失败", 'error')
        return None
