# Automate - Cookie 自动提取器

智能代理服务，自动监控和提取各种网络服务的Cookie，支持与Clash等代理软件的链式代理模式。

## 功能特性

- 🔗 **智能链式代理**: 自动检测并链接到Clash等上游代理
- 🎯 **精准提取**: 只处理目标服务流量，其他请求直接透传
- ⏰ **时间窗口控制**: 避免频繁提取，支持自定义提取间隔
- 📊 **状态管理**: CSV文件记录提取状态和会话信息
- 🎵 **多服务支持**: 内置网易云音乐、夸克网盘提取器，易于扩展
- 🔧 **配置驱动**: YAML配置文件，支持热更新

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
    enabled: true    # 启用网易云音乐
  quark:
    enabled: true    # 启用夸克网盘
```

编辑 `config/proxy_config.yaml` 配置Clash端口：

```yaml
proxy:
  upstream:
    clash_detection:
      ports: [7897, 7898, 7899]  # 你的Clash端口
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

### 4. 配置系统代理

将系统代理或浏览器代理设置为 `http://127.0.0.1:8080`

## 工作原理

```
[应用程序] → [Automate:8080] → [Clash:7897] → [目标服务器]
             ↓ Cookie提取    ↓ 规则分流/翻墙
         保存到JSON文件     
```

1. **流量过滤**: 只处理配置中指定域名的流量
2. **时间控制**: 根据设定间隔（默认2小时）决定是否提取
3. **链式代理**: 自动检测并使用Clash作为上游代理
4. **状态记录**: CSV文件记录提取状态和统计信息

## 输出文件

- **网易云音乐**: `../music-sync/config/auto_cookie.json` (兼容music-sync格式)
- **夸克网盘**: `data/outputs/quark_cookie.json`
- **状态记录**: `data/extraction_status.csv`
- **会话日志**: `data/proxy_sessions.csv`

## 配置文件说明

### proxy_config.yaml
```yaml
proxy:
  listen:
    port: 8080                    # 监听端口
    backup_ports: [8081, 8082]    # 备用端口
  
  upstream:
    enabled: true                 # 启用上游代理检测
    clash_detection:
      ports: [7897, 7898, 7899]   # Clash端口列表
```

### services.yaml
```yaml
services:
  netease:
    domains: ["music.163.com"]    # 监控域名
    extract_interval: 7200        # 提取间隔(秒)
    output_file: "xxx.json"       # 输出文件路径
```

## 扩展新服务

1. 在 `src/extractors/` 下创建新的提取器类
2. 继承 `BaseExtractor` 并实现抽象方法
3. 在 `config/services.yaml` 中添加服务配置
4. 在 `smart_proxy.py` 中注册提取器

## 状态管理

### extraction_status.csv
记录每个服务的提取状态：
- 最后提取时间
- 提取次数  
- 当前状态
- 输出文件路径

### proxy_sessions.csv
记录代理会话信息：
- 会话开始/结束时间
- 上游代理地址
- 请求总数和提取次数

## 故障排除

### 1. 端口被占用
程序会自动尝试备用端口，或查看配置文件调整端口设置。

### 2. 上游代理检测失败
检查Clash是否运行，端口配置是否正确。程序会自动回退到直连模式。

### 3. Cookie提取失败
- 确认目标应用是否通过代理
- 检查域名配置是否正确
- 查看控制台输出的详细日志

### 4. 权限问题
确保对输出目录有写入权限，特别是 `../music-sync/config/` 目录。

## 注意事项

- 仅用于个人合法用途，请遵守相关服务条款
- Cookie包含敏感信息，注意保护隐私安全
- 建议定期清理旧的会话记录
- 代理服务会轻微增加网络延迟

## 版本信息

- 版本: v1.0.0  
- Python要求: 3.8+
- 主要依赖: mitmproxy, PyYAML, requests