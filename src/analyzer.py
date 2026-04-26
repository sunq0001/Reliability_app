"""
analyzer.py - 漂移分析引擎
负责：扫描可用测试项 + 漂移检测（均已向量化优化）
"""

import re
import numpy as np
import pandas as pd


# ========== 测试项扫描（向量化）==========

def get_available_test_items(df, log_callback=None):
    """
    获取可用于分析的测试项列表
    
    返回:
        tuple: (有效测试项列表, 全相同项字典)
            - 有效测试项: nunique > 1 的列名列表
            - 全相同项: {测试项名称: 唯一值}，如 {"Test_A": 1, "Test_B": -1}
    """
    def log(msg, level='info'):
        if log_callback:
            log_callback(msg, level)

    # 排除非数值列
    exclude_cols = {
        'SN', 'Time', 'PGM', 'LotID', 'WaferID', 'OPID', 'StationID',
        'FuseID', 'OTP_X', 'OTP_Y', 'ChromaBin', 'Bin', 'HWBin', 'SWBin',
        'HWVersion', 'TestTime', 'PowerUp_Result', 'I2CTest_Result'
    }

    candidate_cols = [c for c in df.columns if c not in exclude_cols]

    # 批量转数值
    numeric_df = df[candidate_cols].apply(pd.to_numeric, errors='coerce')

    # 批量统计
    non_null_counts = numeric_df.count()
    nunique_counts  = numeric_df.nunique(dropna=True)

    # 有效：非空 + 唯一值 > 1
    valid_mask   = (non_null_counts > 0) & (nunique_counts > 1)
    constant_mask = (non_null_counts > 0) & (nunique_counts == 1)

    valid_test_items = list(numeric_df.columns[valid_mask])
    constant_cols    = numeric_df.columns[constant_mask]

    # 获取全相同项的值（保留原始类型）
    constant_items = {}
    for c in constant_cols:
        unique_val = numeric_df[c].dropna().iloc[0]  # 取第一个非空值作为唯一值
        if pd.notna(unique_val):
            constant_items[c] = unique_val
        else:
            constant_items[c] = 0

    # 统计（按值分组）
    if len(constant_cols) > 0:
        val_counts = {}
        for v in constant_items.values():
            # 用字符串做key，保留原始精度
            key = f"{v:.4g}" if isinstance(v, float) else str(v)
            val_counts[key] = val_counts.get(key, 0) + 1
        log(f"[过滤] 跳过 {len(constant_cols)} 个全相同项", 'info')
        for val_str, count in sorted(val_counts.items()):
            log(f"  - 值={val_str}: {count} 项", 'info')

    log(f"[有效] 共 {len(valid_test_items)} 个测试项 + {len(constant_items)} 个全相同项", 'success')
    
    return valid_test_items, constant_items


# ========== 漂移分析（向量化）==========

def sort_read_points(read_points):
    """按数值排序读点名称"""
    def get_val(rp):
        m = re.search(r'(\d+)', str(rp))
        return int(m.group(1)) if m else 0
    return sorted(set(rp for rp in read_points if str(rp) != 'SN' and pd.notna(rp)),
                   key=get_val)


def build_rp_groups(df):
    """
    预建读点分组缓存，避免在 analyze_drift 里重复 df[df['SN'] == rp]
    返回: {读点名称: DataFrame子集}
    """
    if 'SN' not in df.columns:
        return {}
    return {rp: grp for rp, grp in df.groupby('SN')}


def analyze_drift(df, test_item, rule1_enabled=True, rule1_threshold=30,
                  rule2_enabled=True, rule2_threshold=50,
                  rule3_enabled=True, rule3_threshold=30,
                  rp_groups=None, log_callback=None):
    """
    漂移分析引擎（向量化版本）

    优化点:
    - 使用预建的 rp_groups 缓存，避免重复 groupby
    - 同读点偏移检测用 vectorized abs()，替代 Python 逐行循环
    - 整体漂移、趋势恶化均用向量化操作

    参数:
        df: DataFrame
        test_item: str, 测试项列名
        rule*_enabled: bool
        rule*_threshold: float (百分比)
        rp_groups: dict, build_rp_groups() 返回的缓存（可选）
        log_callback: callable(message, level)

    返回: {
        'rule1_outliers': {读点: [(index, value, pct_change), ...]},
        'rule2_drift':    {读点: {'mean_change': %, 'std_change': %}},
        'rule3_degradation': {(prev_rp, curr_rp): {'drift': %}},
        'summary': [str, ...]
    }
    """
    def log(msg, level='info'):
        if log_callback:
            log_callback(msg, level)

    result = {
        'rule1_outliers': {},
        'rule2_drift': {},
        'rule3_degradation': {},
        'summary': []
    }

    # 获取读点列表
    read_points = sort_read_points(df['SN'].unique())

    if not read_points:
        return result

    # 使用缓存的分组，或实时 groupby
    if rp_groups is not None:
        groups = rp_groups
    else:
        groups = {rp: grp for rp, grp in df.groupby('SN')}

    # 判断是否跳过：无效占位值超过 90%
    if test_item not in df.columns:
        return result

    all_values = pd.to_numeric(df[test_item], errors='coerce').dropna()
    invalid_placeholders = {0, -1, -999, 999, 255, -255}
    invalid_mask = all_values.isin(list(invalid_placeholders))
    invalid_count = int(invalid_mask.sum())
    valid_count   = len(all_values)

    invalid_ratio = invalid_count / valid_count if valid_count > 0 else 1.0

    if invalid_ratio > 0.9:
        msg = f"⚠️ 无效数据: {invalid_count}/{valid_count} 为占位值"
        log(f"  ⚠️ [{test_item}] " + msg, 'warning')
        result['summary'].append(msg)
    elif all_values.nunique() <= 1:
        msg = f"⚠️ 单一值测试项: {all_values.iloc[0] if len(all_values) > 0 else 'N/A'}"
        log(f"  ⚠️ [{test_item}] {msg}", 'warning')
        result['summary'].append(msg)

    log(f"[分析] 识别到 {len(read_points)} 个读点: {read_points}", 'info')

    # 找 T0 基准（第一个读点）
    t0_rp    = read_points[0]
    t0_grp   = groups.get(t0_rp)
    t0_values = pd.to_numeric(t0_grp[test_item], errors='coerce').dropna() if t0_grp is not None else pd.Series(dtype=float)
    t0_mean  = t0_values.mean() if len(t0_values) > 0 else np.nan
    t0_std   = t0_values.std()  if len(t0_values) > 0 else np.nan

    # ===== 标准1: 同读点内偏移检测（vectorized）=====
    if rule1_enabled:
        th1 = rule1_threshold / 100.0
        for rp in read_points:
            grp = groups.get(rp)
            if grp is None:
                continue
            vals = pd.to_numeric(grp[test_item], errors='coerce').dropna()
            mean_val = vals.mean()
            std_val  = vals.std()

            if std_val > 0 and not np.isnan(mean_val):
                # 向量化计算偏离百分比（替代 Python 逐行循环）
                pct_change = (vals - mean_val).abs() / abs(mean_val)
                outlier_mask = pct_change > th1
                if outlier_mask.any():
                    outliers = list(zip(
                        vals.index[outlier_mask],
                        vals.values[outlier_mask],
                        pct_change.values[outlier_mask]
                    ))
                    result['rule1_outliers'][rp] = outliers
                    result['summary'].append(
                        f"⚠️ {rp}: 发现 {len(outliers)} 个异常芯片 (偏离>{rule1_threshold}%)")

    # ===== 标准2: 整体漂移检测（vectorized）=====
    if rule2_enabled and not np.isnan(t0_mean):
        th2 = rule2_threshold / 100.0
        t0_mean_abs = abs(t0_mean)
        t0_std_abs  = t0_std if (not np.isnan(t0_std) and t0_std > 0) else np.nan

        for rp in read_points[1:]:  # 跳过 T0
            grp = groups.get(rp)
            if grp is None:
                continue
            vals = pd.to_numeric(grp[test_item], errors='coerce').dropna()
            rp_mean = vals.mean()
            rp_std  = vals.std()

            if np.isnan(rp_mean):
                continue

            # 防止除以零
            if t0_mean_abs == 0 or np.isnan(t0_mean_abs):
                mean_change = 0
            else:
                mean_change = abs(rp_mean - t0_mean) / t0_mean_abs
            
            if t0_std_abs == 0 or np.isnan(t0_std_abs):
                std_change = 0
            else:
                std_change  = abs(rp_std - t0_std) / t0_std_abs

            if mean_change > th2 or std_change > th2:
                result['rule2_drift'][rp] = {
                    'mean_change': mean_change * 100,
                    'std_change':  std_change  * 100,
                    't0_mean': t0_mean,
                    'rp_mean': rp_mean
                }
                result['summary'].append(
                    f"⚠️ {rp}: 整体漂移 mean={mean_change*100:.1f}%, std={std_change*100:.1f}%")

    # ===== 标准3: 趋势恶化检测（vectorized）=====
    if rule3_enabled and len(read_points) >= 3:
        th3 = rule3_threshold / 100.0

        for i in range(1, len(read_points)):
            prev_rp = read_points[i - 1]
            curr_rp = read_points[i]
            prev_grp = groups.get(prev_rp)
            curr_grp = groups.get(curr_rp)

            if prev_grp is None or curr_grp is None:
                continue

            prev_vals = pd.to_numeric(prev_grp[test_item], errors='coerce').dropna()
            curr_vals = pd.to_numeric(curr_grp[test_item], errors='coerce').dropna()

            prev_mean = prev_vals.mean()
            curr_mean = curr_vals.mean()

            if np.isnan(prev_mean) or np.isnan(curr_mean) or prev_mean == 0:
                continue

            drift = abs(curr_mean - prev_mean) / abs(prev_mean)

            if drift > th3:
                result['rule3_degradation'][(prev_rp, curr_rp)] = {
                    'drift': drift * 100,
                    'prev_mean': prev_mean,
                    'curr_mean': curr_mean
                }
                result['summary'].append(
                    f"⚠️ {prev_rp}→{curr_rp}: 偏移 {drift*100:.1f}%, 趋势恶化")

    return result


def analyze_all_items(df, test_items, rule1_enabled=True, rule1_threshold=30,
                      rule2_enabled=True, rule2_threshold=50,
                      rule3_enabled=True, rule3_threshold=30,
                      log_callback=None):
    """
    批量分析多个测试项（预建 groupby 缓存一次，分析全程复用）

    参数:
        df, test_items, 各项阈值: 同 analyze_drift
        log_callback: callable(message, level)

    返回: {test_item: analyze_drift_result, ...}
    """
    def log(msg, level='info'):
        if log_callback:
            log_callback(msg, level)

    # 一次性预建 groupby 缓存
    rp_groups = build_rp_groups(df)

    results = {}
    total = len(test_items)
    for idx, item in enumerate(test_items, 1):
        log(f"  [{idx}/{total}] 分析中: {item}...", 'info')
        results[item] = analyze_drift(
            df, item,
            rule1_enabled=rule1_enabled, rule1_threshold=rule1_threshold,
            rule2_enabled=rule2_enabled, rule2_threshold=rule2_threshold,
            rule3_enabled=rule3_enabled, rule3_threshold=rule3_threshold,
            rp_groups=rp_groups,
            log_callback=None
        )

    return results
