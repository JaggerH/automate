# sync_music - 音乐播放列表同步工具

这是一个用于将网易云音乐播放列表同步到本地数据库，并匹配本地音乐文件的工具。

## 功能特性

- 解析网易云音乐播放列表JSON文件
- 在用户目录和输入目录中查找匹配的音乐文件
- 自动复制和重命名文件到输出目录
- 提取音频文件元数据（码率、hash值）
- 使用SQLite数据库存储同步状态
- 支持事务操作，确保数据一致性

## 业务流程

1. **解析播放列表**: 读取JSON格式的播放列表数据
2. **创建/更新播放列表记录**: 在数据库中存储播放列表信息
3. **处理每个歌曲**:
   - **情况一**: 在用户目录中找到文件 → 提取码率和hash → 插入数据库
   - **情况二**: 在输入目录中找到文件 → 选择最高码率版本 → 复制到输出目录 → 重命名 → 插入数据库
   - **情况三**: 都未找到 → 插入数据库但码率、hash、path留空
4. **使用事务**: 确保所有操作的原子性

## 文件结构

```
sync_music/
├── __init__.py
├── models.py          # 数据库模型
├── database.py        # 数据库管理
├── file_matcher.py    # 文件匹配逻辑
├── audio_info.py      # 音频信息提取
├── main.py           # 主程序
├── cli.py            # 命令行入口
├── README.md         # 说明文档
└── tests/            # 单元测试
    ├── __init__.py
    ├── test_file_matcher.py
    ├── test_audio_info.py
    └── test_database.py
```

## 安装依赖

```bash
pip install sqlalchemy mutagen pyyaml
```

## 配置文件

sync_music 支持使用 YAML 配置文件来管理参数，避免每次都需要输入长长的命令行参数。

### 创建配置文件

```bash
# 创建默认配置文件
python -m scripts.sync_music.cli --create-config config.yaml
```

### 配置文件查找优先级

1. 命令行指定的配置文件 (`--config path/to/config.yaml`)
2. 当前目录的 `config.yaml`
3. 当前目录的 `sync_music_config.yaml`
4. 用户主目录的 `~/.sync_music/config.yaml`
5. 系统目录的 `/etc/sync_music/config.yaml` (Linux/macOS)

### 配置文件示例

```yaml
# 基本目录配置
# 用户目录支持多个路径（按优先级搜索）
user_dir:
  - ~/Music
  - ~/Documents/Music
  - ~/Music_Collection
# 或者使用单个目录：
# user_dir: ~/Music

input_dir: ./input_music
output_dir: ./output_music
json_dir: ./playlists

# 数据库配置
database_path: music_sync.db

# 文件处理选项
supported_extensions:
  - .mp3
  - .flac
max_bitrate_preference: true
copy_files: true
overwrite_existing: false

# 输出选项
verbose: true
show_progress: true
log_level: INFO

# 高级选项
enable_file_hash: true
enable_bitrate_extraction: true
batch_size: 100
max_workers: 4
```

### 多用户目录支持 ⭐

`user_dir` 支持配置多个目录，程序会按顺序搜索这些目录来查找音乐文件：

```yaml
# 方式1: 列表格式（推荐）
user_dir:
  - ~/Music                    # 优先搜索主音乐目录
  - ~/Documents/Music          # 其次搜索文档中的音乐
  - /mnt/external/music        # 最后搜索外部存储
  - D:\MusicCollection         # Windows外部盘符

# 方式2: 单目录格式
user_dir: ~/Music
```

**多目录的优势：**
- 🔍 **智能搜索**: 按配置顺序在多个位置查找音乐文件
- 📁 **灵活存储**: 支持本地、网络、外部存储等多种位置
- ⚡ **自动跳过**: 不存在的目录会自动跳过（带警告）
- 🎯 **去重处理**: 多个目录中的重复文件会自动去重

### 环境变量支持

配置文件支持环境变量，可以使用以下格式：
- `$HOME/Music` (Linux/macOS)
- `%USERPROFILE%\Music` (Windows)
- `${HOME}/Documents/music`

## 使用方法

### 使用配置文件（推荐）

```bash
# 1. 创建配置文件
python -m scripts.sync_music.cli --create-config config.yaml

# 2. 编辑配置文件，设置正确的目录路径

# 3. 同步单个播放列表
python -m scripts.sync_music.cli -f playlist.json

# 4. 同步目录中的所有播放列表
python -m scripts.sync_music.cli -d /path/to/playlists/dir

# 5. 使用指定的配置文件
python -m scripts.sync_music.cli --config my_config.yaml -f playlist.json

# 6. 查看数据库统计信息
python -m scripts.sync_music.cli --stats
```

### 使用命令行参数（传统方式）

```bash
# 同步单个播放列表
python -m scripts.sync_music.cli -f playlist.json -u /path/to/user/music -i /path/to/input/music -o /path/to/output/music

# 同步目录中的所有播放列表
python -m scripts.sync_music.cli -d /path/to/playlists/dir -u /path/to/user/music -i /path/to/input/music -o /path/to/output/music

# 查看数据库统计信息
python -m scripts.sync_music.cli --stats -u dummy -i dummy -o dummy
```

### 混合使用配置文件和命令行参数

命令行参数会覆盖配置文件中的相同设置：

```bash
# 使用配置文件中的大部分设置，但临时使用不同的输出目录
python -m scripts.sync_music.cli -d /playlists -o /tmp/music_output
```

### 参数说明

#### 配置和输入选项
- `-c, --config`: 配置文件路径
- `-f, --json-file`: 单个播放列表JSON文件路径
- `-d, --json-dir`: 包含多个JSON文件的目录路径
- `--create-config`: 创建默认配置文件到指定路径

#### 目录配置（可在配置文件中设置）
- `-u, --user-dir`: 用户音乐目录路径
- `-i, --input-dir`: 输入音乐目录路径（格式: id-bitrate-hash.mp3）
- `-o, --output-dir`: 输出音乐目录路径

#### 数据库和输出选项
- `--db, --database`: 数据库文件路径（默认: music_sync.db）
- `--stats`: 显示数据库统计信息
- `-v, --verbose`: 详细输出模式

## 文件命名规则

### 用户目录文件格式
```
艺术家 - 歌曲名.mp3
艺术家 - 歌曲名.flac
```

### 输入目录文件格式
```
{track_id}-{bitrate}-{hash}.mp3
```

### 输出目录文件格式
```
艺术家 - 歌曲名.mp3
```

## 数据库结构

### playlists 表
- id: 主键
- netease_id: 网易云播放列表ID
- name: 播放列表名称
- description: 描述
- creator_id: 创建者ID
- creator_name: 创建者名称
- track_count: 歌曲数量
- create_time: 创建时间
- update_time: 更新时间
- cover_img_url: 封面图片URL

### tracks 表
- id: 主键
- netease_id: 网易云歌曲ID
- name: 歌曲名称
- duration: 时长
- artist_names: 艺术家名称（逗号分隔）
- bitrate: 码率
- file_hash: 文件hash值
- file_path: 文件路径
- file_exists: 文件是否存在
- created_at: 创建时间
- updated_at: 更新时间

### playlist_tracks 关联表
- playlist_id: 播放列表ID
- track_id: 歌曲ID
- position: 在播放列表中的位置

## 运行测试

```bash
# 运行所有测试
python -m unittest discover scripts/sync_music/tests -v

# 运行特定测试文件
python -m unittest scripts.sync_music.tests.test_file_matcher -v
python -m unittest scripts.sync_music.tests.test_audio_info -v
python -m unittest scripts.sync_music.tests.test_database -v
python -m unittest scripts.sync_music.tests.test_config -v
```

## 配置文件完整示例

以下是一个完整的配置文件示例，包含所有可用选项：

```yaml
# sync_music 完整配置示例

# 必需的目录配置
# 用户音乐目录（支持单个或多个目录）
user_dir:                            # 多目录格式（推荐）
  - ~/Music                          # 主音乐目录
  - ~/Documents/Music                 # 备用音乐目录
  - /external/music                   # 外部存储音乐目录
# user_dir: ~/Music                  # 单目录格式

input_dir: ./music_input             # 输入目录（id-bitrate-hash格式）
output_dir: ./music_output           # 输出目录

# JSON文件配置
json_dir: ./playlists                # 播放列表JSON文件目录
json_file: null                      # 单个JSON文件（可选）

# 数据库配置
database_path: music_sync.db         # SQLite数据库文件
database_url: null                   # 完整数据库URL（可选）

# 文件处理配置
supported_extensions:                # 支持的音频格式
  - .mp3
  - .flac
max_bitrate_preference: true         # 优先选择高码率
copy_files: true                     # 复制文件而非链接
overwrite_existing: false            # 不覆盖已存在文件

# 输出和日志配置
verbose: true                        # 详细输出
show_progress: true                  # 显示进度
log_level: INFO                      # 日志级别

# 高级配置
enable_file_hash: true               # 计算文件hash
enable_bitrate_extraction: true     # 提取码率信息
batch_size: 100                      # 批处理大小
max_workers: 4                       # 最大工作线程数
```

## 注意事项

1. **依赖库要求**:
   - `sqlalchemy`: 数据库ORM支持
   - `mutagen`: 音频元数据提取（可选，影响码率获取功能）
   - `pyyaml`: YAML配置文件支持

2. **配置优先级**: 命令行参数 > 指定配置文件 > 默认配置文件 > 程序默认值

3. **文件编码**: 支持UTF-8编码的中文文件名

4. **数据库事务**: 所有数据库操作都在事务中执行，确保数据一致性

5. **路径处理**: 
   - 支持相对路径和绝对路径
   - 支持环境变量展开
   - 建议在配置文件中使用绝对路径

6. **权限要求**: 确保程序有读写相关目录的权限

7. **Windows特别注意**: 
   - 路径分隔符可以使用 `/` 或 `\`
   - 环境变量使用 `%VARIABLE%` 格式