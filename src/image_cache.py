"""
image_cache.py - 图片本地缓存模块
将网络图片复制到本地缓存，支持 LRU 清理策略。
"""
import os
import shutil
import time
from collections import OrderedDict
from datetime import datetime


class ImageCache:
    """图片本地缓存管理器 - 使用 LRU 策略控制缓存大小"""
    
    # 默认缓存上限 500MB
    DEFAULT_MAX_SIZE_MB = 500
    
    def __init__(self, cache_dir=None, max_size_mb=None):
        """
        参数:
            cache_dir: 缓存目录路径，默认使用应用目录下的 .image_cache
            max_size_mb: 缓存大小上限（MB）
        """
        if cache_dir is None:
            # 使用应用目录下的 .image_cache
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cache_dir = os.path.join(app_dir, '.image_cache')
        
        self.cache_dir = cache_dir
        self.max_size_mb = max_size_mb or self.DEFAULT_MAX_SIZE_MB
        self.max_size_bytes = self.max_size_mb * 1024 * 1024
        
        # LRU 缓存：key -> {path, size, last_access}
        self._cache = OrderedDict()
        
        # 确保缓存目录存在
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 加载已存在的缓存文件
        self._load_existing_cache()
    
    def _load_existing_cache(self):
        """扫描缓存目录，加载已有文件信息"""
        if not os.path.isdir(self.cache_dir):
            return
        
        for fname in os.listdir(self.cache_dir):
            fpath = os.path.join(self.cache_dir, fname)
            if os.path.isfile(fpath):
                try:
                    size = os.path.getsize(fpath)
                    self._cache[fname] = {
                        'path': fpath,
                        'size': size,
                        'last_access': os.path.getmtime(fpath)
                    }
                except Exception:
                    pass
    
    def _get_cache_key(self, original_path):
        """根据原文件路径生成缓存键（使用文件名的hash避免重名）"""
        import hashlib
        # 使用文件路径的 MD5 作为缓存文件名
        key = hashlib.md5(original_path.encode()).hexdigest()
        ext = os.path.splitext(original_path)[1].lower()
        return f"{key}{ext}"
    
    def get(self, original_path):
        """
        获取图片（优先从缓存，返回本地缓存路径）
        
        参数:
            original_path: 原始图片路径（网络路径或共享盘路径）
        
        返回:
            str: 本地缓存路径，如果缓存未命中返回 None
        """
        if not original_path or not os.path.exists(original_path):
            return None
        
        cache_key = self._get_cache_key(original_path)
        
        # 检查缓存是否命中
        if cache_key in self._cache:
            # 更新访问时间
            cache_info = self._cache[cache_key]
            cache_info['last_access'] = time.time()
            # 移动到末尾（LRU）
            self._cache.move_to_end(cache_key)
            return cache_info['path']
        
        return None
    
    def add(self, original_path, progress_callback=None):
        """
        将图片添加到缓存（从原始路径复制到本地）
        
        参数:
            original_path: 原始图片路径
            progress_callback: 进度回调，可选
        
        返回:
            str: 本地缓存路径，失败返回 None
        """
        if not original_path or not os.path.exists(original_path):
            return None
        
        cache_key = self._get_cache_key(original_path)
        
        # 已存在则直接返回
        if cache_key in self._cache:
            return self.get(original_path)
        
        try:
            dest_path = os.path.join(self.cache_dir, cache_key)
            
            # 复制文件（带进度回调支持大文件）
            if progress_callback:
                file_size = os.path.getsize(original_path)
                progress_callback(0, file_size)
            
            shutil.copy2(original_path, dest_path)
            
            # 获取实际文件大小
            size = os.path.getsize(dest_path)
            
            # 添加到缓存
            self._cache[cache_key] = {
                'path': dest_path,
                'size': size,
                'last_access': time.time()
            }
            
            if progress_callback:
                progress_callback(size, size)
            
            # 检查是否需要清理
            self._evict_if_needed()
            
            return dest_path
            
        except Exception as e:
            print(f"[ImageCache] 复制文件失败: {original_path}, 错误: {e}")
            return None
    
    def add_batch(self, original_paths, progress_callback=None):
        """
        批量添加图片到缓存
        
        参数:
            original_paths: 原始图片路径列表
            progress_callback: 进度回调 (current, total)，可选
        
        返回:
            list: 成功缓存的本地路径列表
        """
        results = []
        total = len(original_paths)
        
        for i, path in enumerate(original_paths):
            cached = self.add(path)
            if cached:
                results.append(cached)
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        return results
    
    def _evict_if_needed(self):
        """如果缓存超过上限，删除最久未使用的文件"""
        while self._get_total_size() > self.max_size_bytes and self._cache:
            # 获取最旧的条目（第一个）
            oldest_key = next(iter(self._cache))
            cache_info = self._cache[oldest_key]
            
            try:
                if os.path.exists(cache_info['path']):
                    os.remove(cache_info['path'])
                    print(f"[ImageCache] 清理缓存: {cache_info['path']}")
            except Exception as e:
                print(f"[ImageCache] 删除缓存文件失败: {e}")
            
            del self._cache[oldest_key]
    
    def _get_total_size(self):
        """计算当前缓存总大小"""
        return sum(info['size'] for info in self._cache.values())
    
    def get_stats(self):
        """获取缓存统计信息"""
        total_size = self._get_total_size()
        total_count = len(self._cache)
        
        # 找出最旧的文件
        oldest = None
        if self._cache:
            oldest_key = next(iter(self._cache))
            oldest = self._cache[oldest_key]
        
        return {
            'cache_dir': self.cache_dir,
            'total_files': total_count,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'max_size_mb': self.max_size_mb,
            'usage_percent': round(total_size / self.max_size_bytes * 100, 1) if self.max_size_bytes > 0 else 0,
            'oldest_file': oldest['path'] if oldest else None,
            'oldest_access': datetime.fromtimestamp(oldest['last_access']).strftime('%Y-%m-%d %H:%M:%S') if oldest else None
        }
    
    def clear(self):
        """清空所有缓存"""
        for cache_info in self._cache.values():
            try:
                if os.path.exists(cache_info['path']):
                    os.remove(cache_info['path'])
            except Exception:
                pass
        
        self._cache.clear()
        print("[ImageCache] 缓存已清空")
    
    def remove_oldest(self, count=10):
        """删除指定数量的最旧缓存"""
        removed = 0
        for _ in range(min(count, len(self._cache))):
            if not self._cache:
                break
            
            oldest_key = next(iter(self._cache))
            cache_info = self._cache[oldest_key]
            
            try:
                if os.path.exists(cache_info['path']):
                    os.remove(cache_info['path'])
                    removed += 1
            except Exception:
                pass
            
            del self._cache[oldest_key]
        
        return removed


# 全局缓存实例（单例）
_global_cache = None

def get_cache(cache_dir=None, max_size_mb=None):
    """获取全局图片缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = ImageCache(cache_dir, max_size_mb)
    return _global_cache