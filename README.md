# Reliability App

可靠性测试分析应用 - 用于分析传感器可靠性测试数据的可视化工具。

## 功能特性

- 📊 **数据加载**: 支持从 Excel 文件加载可靠性测试数据
- 📈 **图表生成**: 自动生成多种类型的分布图表（CDF、直方图等）
- 🖼️ **图片管理**: 自动扫描和管理测试图片
- 🔍 **图表查看**: 内置图表查看器，方便浏览分析结果
- 📁 **分类整理**: 按测试类别自动整理图表输出

## 支持的测试类型

- Blooming 测试
- Dark Current 测试
- FPN 测试
- PRNU 测试
- 温度传感器测试
- 以及更多...

## 安装

### 方式一：下载便携版

前往 [Releases](https://github.com/sunq0001/Reliability_app/releases) 下载最新版本的便携版 zip 文件，解压后直接运行 `reliability_app.exe`。

### 方式二：从源码运行

```bash
# 克隆仓库
git clone https://github.com/sunq0001/Reliability_app.git
cd Reliability_app

# 安装依赖
pip install pandas openpyxl matplotlib pillow scipy numpy

# 运行应用
python reliability_app.py
```

## 项目结构

```
reliability_app/
├── reliability_app.py     # 主程序入口
├── reliability_app.spec  # PyInstaller 打包配置
├── src/                  # 源代码目录
│   ├── analyzer.py       # 数据分析模块
│   ├── chart_builder.py  # 图表构建模块
│   ├── data_loader.py    # 数据加载模块
│   └── ...
├── category_plots/       # 按类别分类的图表输出
├── reliability_plots/    # 按测试项目分类的图表输出
└── output/               # 其他输出文件
```

## 系统要求

- Windows 10/11
- Python 3.8+ (如从源码运行)

## 技术栈

- **GUI**: Tkinter
- **数据处理**: Pandas, NumPy, SciPy
- **可视化**: Matplotlib
- **打包**: PyInstaller

## License

MIT License
