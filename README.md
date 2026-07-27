# Bangumi 自动分类工具

自动识别 Mikan RSS 中的新番，生成 qBittorrent RSS 下载规则，一键导入并开始下载。

## 快速开始

### 1. 环境要求

- Python 3.10+
- qBittorrent（开启 WebUI，默认端口 8080）
- Mikan RSS 订阅源（需登录后获取个人 token）

### 2. 配置

编辑 config.py，修改以下配置：

`python
# RSS 源（替换为你的 Mikan 个人 RSS token）
RSS_URL = "https://mikanime.tv/RSS/MyBangumi?token=你的token"

# qBittorrent WebUI 地址
QB_BASE_URL = "http://localhost:8080/"
QB_USERNAME = "admin"
QB_PASSWORD = ""  # 你的密码

# 下载保存路径
SAVE_PATH_WIN = r"E:\Anime"        # Windows 路径
SAVE_PATH_UNIX = "E:/Anime"         # qB torrentParams 用的路径
`

### 3. 运行

`ash
cd bangumi_tool
python main.py
`

## 功能菜单

`
[0] 从 qB 同步  - 从 qBittorrent 同步规则到本地
[1] 查看状态  - 显示当前所有规则
[2] 刷新 RSS  - 连接 qBittorrent 刷新 RSS
[3] 分析规则  - 匹配现有规则 vs RSS，输出命中/未命中/未覆盖
[4] 查看差异  - 查看 RSS 中新增的、尚未有规则覆盖的番剧
[5] 生成规则  - 交互式生成新规则（核心功能）
[6] 导入规则  - 将规则导入 qBittorrent
[7] 启用下载  - 启用规则并开始自动下载
[8] qB 状态  - 查看 qBittorrent 规则、乱码检查
[9] 一键自动化  - 识别差异→生成→导入→下载

输入 q 退出
`

## 推荐使用流程

### 首次使用

1. 先在 qBittorrent 中手动添加 RSS 源（Mikan 的 Bangumi 订阅）
2. 运行工具，选择 **[0] 从 qB 同步** → 选择 **覆盖**，将 qB 中已有规则拉到本地
3. 选择 **[4] 查看差异**，确认有哪些新番未覆盖
4. 选择 **[5] 生成规则**，交互式生成新规则
5. 选择 **[6] 导入规则**，将规则导入 qBittorrent
6. 选择 **[7] 启用下载**，启用规则并开始下载

### 日常使用（推荐一键）

选择 **[9] 一键自动化**，自动完成：刷新 RSS → 识别差异 → 生成规则 → 导入 → 启用下载

### 在 qB 中手动操作后

如果在 qBittorrent 界面中手动添加/删除了规则，选择 **[0] 从 qB 同步** 同步回本地。

## 规则文件

所有规则存储在 
ules/rules.json 中，是一个 JSON 字典：

`json
{
  "穹庐下的魔女 Baha": {
    "enabled": true,
    "addPaused": false,
    "mustContain": "(?=.*穹庐下的魔女)(?=.*Baha)",
    "mustNotContain": "720|ABEMA",
    "useRegex": true,
    "affectedFeeds": ["https://mikanime.tv/RSS/MyBangumi?token=..."],
    "savePath": "E:\\测试\\穹庐下的魔女 Baha",
    "torrentParams": { ... }
  }
}
`

- 每条规则的 key 是规则名（格式：番剧名 来源）
- mustContain 使用正则表达式，同时匹配番剧名和来源
- 番剧名优先使用中文译名

## 文件结构

`
bangumi_tool/
├── main.py              # 主程序入口，交互式菜单
├── config.py            # 配置文件（RSS 地址、qB 地址、路径等）
├── qbittorrent_api.py   # qBittorrent WebUI API 客户端
├── rss_parser.py        # RSS 抓取与标题解析（优先提取中文译名）
├── rule_engine.py       # 规则匹配引擎（命中验证、未覆盖检测）
├── rule_generator.py    # 规则生成器（为新番自动生成正则规则）
├── utils.py             # 工具函数（规则文件读写、命名规范）
└── README.md            # 本文档

rules/
└── rules.json           # 规则文件（与 qBittorrent 同步）
`

## 给他人使用

1. 将 angumi_tool/ 文件夹和 
ules/rules.json 一起发送
2. 对方修改 config.py 中的 qB 地址、RSS token、下载路径
3. 对方运行 [0] 从 qB 同步 → 覆盖，用自己的 qB 规则替换
4. 之后正常使用即可

## 注意事项

- 规则中的番剧名优先使用中文译名，确保跨版本兼容
- 每次在 qB 中手动修改规则后，记得运行 [0] 从 qB 同步 保持本地一致
- RSS 条目会随时间变化（新集上线、旧条目下架），定期运行 [4] 查看差异 检查