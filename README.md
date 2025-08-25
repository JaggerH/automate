# Automate - 自动化监控

自动监控和提取各种网络服务/文件服务。

## 功能特性

- ⏰ **时间窗口控制**: 避免频繁提取，支持自定义提取间隔
- 📊 **状态管理**: CSV文件记录提取状态和会话信息
- 🎵 **多服务支持**: 内置网易云音乐、夸克网盘提取器，易于扩展
- 🔧 **配置驱动**: YAML配置文件，支持热更新
- 🔄 **守护进程模式**: 支持后台持续运行和进程监控
- 🔒 **Windows文件锁定**: 解决Windows系统文件访问冲突

## 快速开始

### 1. 环境准备

```bash
# 创建conda环境
conda env create -f environment.yaml
conda activate automate

# 或使用pip安装
pip install -r requirements.txt
```

### 2. 配置设置

编辑 `config/services.yaml` 启用需要的服务：

```yaml
services:
  netease:
    enabled: true
  quark:
    enabled: true
```

### 3. 启动服务

```bash
# 启动代理服务
python main.py

# 查看状态
python main.py --status

# 清理旧数据
python main.py --cleanup
```

## 版本信息

- 版本: v1.0.0  
- Python要求: 3.8+
- 主要依赖: mitmproxy, PyYAML, requests