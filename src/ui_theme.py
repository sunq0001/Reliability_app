"""
ui_theme.py - UI 样式常量定义
所有颜色、字体、尺寸等样式配置集中管理
"""

# ========== 字体定义 ==========
FONT_YAHEI = 'Microsoft YaHei'
FONT_CONSOLA = 'Consolas'

# 普通文本
FONT_TEXT = (FONT_YAHEI, 9)
FONT_TEXT_BOLD = (FONT_YAHEI, 9, 'bold')
FONT_TEXT_SMALL = (FONT_YAHEI, 8)
FONT_TEXT_TITLE = (FONT_YAHEI, 10, 'bold')

# 特殊文本
FONT_MONO = (FONT_CONSOLA, 9)  # 等宽文本（代码/数据）
FONT_MONO_SMALL = (FONT_CONSOLA, 8)

# ========== 颜色定义 ==========
# 主色
COLOR_PRIMARY = '#6366f1'        # 主按钮蓝紫
COLOR_PRIMARY_HOVER = '#4f46e5'
COLOR_PRIMARY_LIGHT = '#e0e7ff'

# 状态色
COLOR_SUCCESS = '#10b981'       # 绿色
COLOR_WARNING = '#f59e0b'        # 橙色/警告
COLOR_ERROR = '#ef4444'         # 红色/错误
COLOR_INFO = '#3b82f6'          # 蓝色/信息

# 背景色
COLOR_BG_DARK = '#1a1a2e'       # 深色背景
COLOR_BG_LIGHT = '#f8fafc'      # 浅色背景
COLOR_BG_CARD = '#ffffff'        # 卡片背景
COLOR_BG_HEADER = '#f3f4f6'      # 头部背景

# 文字色
COLOR_TEXT_DARK = '#1e293b'     # 深色文字
COLOR_TEXT_MID = '#64748b'      # 中等文字
COLOR_TEXT_LIGHT = '#9ca3af'    # 浅色文字
COLOR_TEXT_WHITE = '#ffffff'    # 白色文字

# 边框色
COLOR_BORDER = '#e5e7eb'
COLOR_BORDER_FOCUS = COLOR_PRIMARY

# ========== 尺寸定义 ==========
PAD_XS = 2
PAD_SM = 4
PAD_MD = 8
PAD_LG = 16
PAD_XL = 24

# 按钮
BTN_HEIGHT = 28
BTN_WIDTH_SMALL = 8
BTN_WIDTH_MEDIUM = 10
BTN_WIDTH_LARGE = 12

# 输入框
ENTRY_WIDTH_MEDIUM = 25
ENTRY_WIDTH_LARGE = 40

# 标签
LABEL_WIDTH_SHORT = 8
LABEL_WIDTH_MEDIUM = 12

# ========== Tkinter 样式配置 ==========

def configure_ttk_styles(root):
    """配置 ttk 组件样式（调用一次）"""
    from tkinter import ttk

    style = ttk.Style(root)
    style.theme_use('clam')  # 使用现代主题

    # 普通按钮
    style.configure('TButton',
                    font=FONT_TEXT,
                    padding=(PAD_MD, PAD_SM),
                    relief='flat',
                    borderwidth=1)

    # 主按钮
    style.configure('Primary.TButton',
                    background=COLOR_PRIMARY,
                    foreground=COLOR_TEXT_WHITE,
                    font=FONT_TEXT_BOLD,
                    padding=(PAD_MD, PAD_SM),
                    relief='flat',
                    borderwidth=0)

    # 成功按钮
    style.configure('Success.TButton',
                    background=COLOR_SUCCESS,
                    foreground=COLOR_TEXT_WHITE,
                    font=FONT_TEXT_BOLD,
                    padding=(PAD_MD, PAD_SM),
                    relief='flat',
                    borderwidth=0)

    # 警告按钮
    style.configure('Warning.TButton',
                    background=COLOR_WARNING,
                    foreground=COLOR_TEXT_WHITE,
                    font=FONT_TEXT_BOLD,
                    padding=(PAD_MD, PAD_SM),
                    relief='flat',
                    borderwidth=0)

    # 危险按钮
    style.configure('Danger.TButton',
                    background=COLOR_ERROR,
                    foreground=COLOR_TEXT_WHITE,
                    font=FONT_TEXT_BOLD,
                    padding=(PAD_MD, PAD_SM),
                    relief='flat',
                    borderwidth=0)

    # LabelFrame
    style.configure('TLabelframe',
                    background=COLOR_BG_CARD,
                    foreground=COLOR_TEXT_DARK,
                    font=FONT_TEXT_TITLE,
                    padding=PAD_MD)

    style.configure('TLabelframe.Label',
                    background=COLOR_BG_CARD,
                    foreground=COLOR_TEXT_DARK,
                    font=FONT_TEXT_BOLD)

    # Treeview
    style.configure('Treeview',
                    background=COLOR_BG_CARD,
                    foreground=COLOR_TEXT_DARK,
                    font=FONT_TEXT,
                    rowheight=25,
                    fieldbackground=COLOR_BG_CARD)

    style.configure('Treeview.Heading',
                    background=COLOR_BG_HEADER,
                    foreground=COLOR_TEXT_DARK,
                    font=FONT_TEXT_BOLD,
                    relief='flat')

    style.map('Treeview',
              background=[('selected', COLOR_PRIMARY_LIGHT)],
              foreground=[('selected', COLOR_PRIMARY)])

    # Notebook
    style.configure('TNotebook',
                    background=COLOR_BG_LIGHT,
                    tabmargins=[PAD_SM, PAD_SM, PAD_SM, PAD_SM])

    style.configure('TNotebook.Tab',
                    background=COLOR_BG_HEADER,
                    foreground=COLOR_TEXT_MID,
                    font=FONT_TEXT,
                    padding=[PAD_MD, PAD_SM])

    style.map('TNotebook.Tab',
              background=[('selected', COLOR_BG_CARD)],
              foreground=[('selected', COLOR_PRIMARY)])


def tk_btn_config():
    """返回 tk.Button 的通用配置字典"""
    return {
        'relief': 'flat',
        'cursor': 'hand1',
        'font': FONT_TEXT
    }


def tk_btn_primary_config():
    """返回主按钮配置"""
    return {
        **tk_btn_config(),
        'bg': COLOR_PRIMARY,
        'fg': COLOR_TEXT_WHITE,
        'activebackground': COLOR_PRIMARY_HOVER,
        'activeforeground': COLOR_TEXT_WHITE,
        'font': FONT_TEXT_BOLD
    }


def tk_btn_success_config():
    """返回成功按钮配置"""
    return {
        **tk_btn_config(),
        'bg': COLOR_SUCCESS,
        'fg': COLOR_TEXT_WHITE,
        'activebackground': '#059669',
        'activeforeground': COLOR_TEXT_WHITE,
        'font': FONT_TEXT_BOLD
    }


def tk_label_config():
    """返回 tk.Label 的通用配置"""
    return {
        'font': FONT_TEXT,
        'fg': COLOR_TEXT_DARK,
        'bg': COLOR_BG_CARD
    }


def ttk_label_config():
    """返回 ttk.Label 的通用配置（不含颜色，ttk不支持）"""
    return {
        'font': FONT_TEXT
    }


def tk_entry_config():
    """返回 tk.Entry 的通用配置"""
    return {
        'font': FONT_TEXT,
        'fg': COLOR_TEXT_DARK,
        'bg': COLOR_BG_CARD,
        'relief': 'solid',
        'bd': 1
    }


# ========== 状态图标 ==========
ICON_SUCCESS = '✓'
ICON_WARNING = '⚠'
ICON_ERROR = '✗'
ICON_INFO = 'ℹ'
ICON_LOADING = '⟳'

STATUS_SUCCESS = f"{ICON_SUCCESS} 已识别"
STATUS_WARNING = f"{ICON_WARNING} 需手动"
STATUS_ERROR = f"{ICON_ERROR} 缺失"
