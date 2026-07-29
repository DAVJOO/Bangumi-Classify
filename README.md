# Bangumi 自动分类工具

自动识别 Mikan RSS 中的新番，生成 qBittorrent RSS 下载规则，一键导入并开始下载。

支持 CLI 和 WebUI 两种使用方式。

## 快速开始

### 1. 环境要求

- Python 3.10+
- qBittorrent（开启 WebUI）
- Mikan RSS 订阅源（需登录后获取个人 token）

### 2. 配置

首次使用请复制配置模板：

```bash
cp config.template.py config.py
```

编辑 `config.py`，修改以下配置：

```python
# RSS 源（替换为你的 Mikan 个人 RSS token）
RSS_URL = "https://mikanime.tv/RSS/MyBangumi?token=你的token"

# qBittorrent WebUI 地址
QB_BASE_URL = "http://localhost:8080/"
QB_USERNAME = "admin"
QB_PASSWORD = ""  # 你的密码

# 下载保存路径
SAVE_PATH_WIN = r"E:\Anime"        # Windows 路径
SAVE_PATH_UNIX = "E:/Anime"         # qB torrentParams 用的路径
```

### 3. 运行

**CLI 模式：**

```bash
python main.py
```

**WebUI 模式：**

```bash
python webapp/app.py
# 浏览器访问 http://localhost:8080
```

## CLI 功能菜单

```
[0] 从 qB 同步  - 从 qBittorrent 同步规则到本地
[1] 查看状态  - 显示当前所有规则
[2] 刷新 RSS  - 连接 qBittorrent 刷新 RSS
[3] 分析规则  - 匹配现有规则 vs RSS，输出命中/未命中/未覆盖
[4] 查看差异  - 查看 RSS 中新增的、尚未有规则覆盖的番剧
[5] 生成规则  - 交互式生成新规则
[6] 导入规则  - 将规则导入 qBittorrent
[7] 启用下载  - 启用规则并开始自动下载
[8] qB 状态  - 查看 qBittorrent 规则、乱码检查
[9] 一键自动化  - 刷新→差异→生成→导入→启用
```

## WebUI 功能

- **规则管理**：查看、启用/禁用规则
- **RSS 分析**：刷新 RSS、查看匹配结果、检测未覆盖番剧
- **一键自动化**：刷新→差异→生成→导入→启用
- **状态监控**：qB 连接状态、规则/种子数量
- **路径管理**：更改下载路径、迁移文件到新路径
- **Config 设置**：在线修改 RSS 地址、qB 地址、密码等配置

## 推荐使用流程

### 首次使用

1. 先在 qBittorrent 中手动添加 RSS 源（Mikan 的 Bangumi 订阅）
2. 运行工具，选择 **[0] 从 qB 同步** → 覆盖，将 qB 已有规则拉到本地
3. 选择 **[4] 查看差异**，确认有哪些新番未覆盖
4. 选择 **[5] 生成规则**，交互式生成新规则
5. 选择 **[6] 导入规则**，将规则导入 qBittorrent
6. 选择 **[7] 启用下载**，启用规则并开始下载

### 日常使用

选择 **[9] 一键自动化** 或 WebUI 的一键按钮，自动完成全流程。

## 正则匹配规则

每条规则的 `mustContain` 格式为：

```
(?=.*番剧名)(?=.*字幕组)
```

- 使用 lookahead 确保标题同时包含番剧名和字幕组名
- 番剧名从 Mikan 官方页面获取（统一命名）
- 字幕组名从 RSS 标题中提取
- 空格用 `\s*?` 匹配，兼容不同标题格式

## 文件结构

```
bangumi_tool/
├── main.py              # CLI 主程序
├── config.py            # 配置文件
├── config.template.py   # 配置模板（供他人使用）
├── qbittorrent_api.py   # qBittorrent WebUI API 客户端
├── rss_parser.py        # RSS 抓取与标题解析
├── rule_engine.py       # 规则匹配引擎
├── rule_generator.py    # 规则生成器
├── utils.py             # 工具函数
├── rules.json           # 规则文件
├── webapp/
│   ├── app.py           # WebUI 后端 (FastAPI)
│   └── static/
│       └── index.html   # WebUI 前端
└── README.md
```

## 给他人使用

1. 将整个 `bangumi_tool/` 文件夹发送（不需要 `rules.json`）
2. 对方复制 `config.template.py` 为 `config.py`，填入自己的配置
3. 运行工具，选择 **[0] 从 qB 同步** → 覆盖，用自己的 qB 规则替换
4. 之后正常使用即可