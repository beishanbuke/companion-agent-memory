# MCP Extension Layer

这个目录用于给主项目补充 MCP 能力，原则是：
- 优先复用 GitHub 上已维护的 MCP 仓库。
- 只有在没有现成服务可复用时，才写本地轻量 MCP（当前的 `software_server.py` 就是这个定位）。
- 尽量通过包管理器直接运行，不把外部仓库代码复制进本项目。

## 目录结构

- `weather_server.py`
  - 天气 MCP（当前是本地实现，依赖 `wttr.in` 公共接口）。
  - 如果后续找到稳定的官方/社区天气 MCP，可替换为外部服务接入。
- `horoscope_server.py`
  - 星座占卜 MCP，面向轻量娱乐与陪伴场景。
  - 根据星座、日期、情绪、主题和表达风格，生成结构化运势卡片（总体运势、建议、幸运色/数字/活动、陪伴式总结、娱乐提示）。
  - 内容由 `shared/horoscope_engine.py` 确定性生成（同星座同日同主题结果稳定），不依赖 LLM。
- `tarot_server.py`
  - 塔罗占卜 MCP，牌义数据来自 JobCannon 塔罗百科（`catalog/tarot_cards.json`，保留原文）。
  - 支持单张指引 / 三张牌阵（过去·现在·未来）抽牌，正逆位各半；`get_card_meaning` 查单牌。
- `shared/tarot_engine.py`
  - 塔罗引擎：加载牌库、洗牌抽牌、生成 prompt 文本，FastMCP 与 demo server 共用。
- `catalog/tarot_cards.json`
  - 78 张牌的结构化牌义（正逆位关键词与正文、肯定语、爱情/事业、原型、FAQ），逐张爬取自 `jobcannon.io/zh/tarot/<slug>`。
- `shared/horoscope_engine.py`
  - 运势生成引擎（纯函数），FastMCP 服务与 demo server 共用。
- `shared/weather_client.py`
  - wttr.in 抓取与 prompt 文案（纯函数），`weather_server.py` 与 demo server 共用。
- `software_server.py`
  - 社交软件推荐 MCP。
  - 面向“社交软件”检索与推荐（如 Discord、Telegram、WeChat、Signal 等）。
- `catalog/software_catalog.json`
  - 本地软件目录（当前以社交软件为主）。
- `shared/software_catalog.py`
  - 软件目录读取与结构化输出。

## 与主系统通信方式

当前通信是标准 MCP 工具调用：
- 你的 Agent/客户端 启动 MCP Server（stdio 或其他 transport）。
- 客户端通过工具名调用，例如：
  - `get_current_weather`
  - `get_weather_forecast`
  - `get_horoscope`
  - `list_zodiac_signs`
  - `list_themes`
  - `draw_tarot`
  - `get_card_meaning`
  - `list_tarot_cards`
  - `search_software`
  - `recommend_social_software`

主项目本身不需要改动业务 API，只要 MCP 客户端配置里注册这些 Server 即可。

demo server（`prototype_demo/server.py`）也直接复用 `shared/` 下的引擎：
- 对话中出现天气/星座占卜意图时，会就地调用同一套工具函数，把结果作为 system 上下文注入 prompt，
  并把结构化卡片通过 `mcp_cards` / `horoscope_card` 字段返回给前端渲染。

## 复用 GitHub MCP 仓库（推荐）

推荐顺序：
1. 先看官方聚合仓库：`modelcontextprotocol/servers`
2. 再选社区仓库（活跃维护、有 issue/版本发布）
3. 最后才落本地自研

复用方式建议：
- 优先“直接运行”而不是“复制代码”：
  - Node 生态：`npx -y <server-package>`
  - Python 生态：`uvx <server-package>` 或 `python -m <module>`
- 具体命令以目标仓库 README 为准。

你可以直接参考：`servers.example.json`
- 里面示例了官方仓库能力（fetch/time）+ 本地补位能力（software/weather）混合注册。

## 运行本地 MCP（当前目录）

在项目虚拟环境中安装依赖：

```bash
pip install mcp
```

启动天气 MCP：

```bash
python mcp/weather_server.py
```

启动社交软件 MCP：

```bash
python mcp/software_server.py
```

## 后续修改指南

新增一个 MCP 能力时按下面步骤：
1. 判断是否已有可复用仓库（优先 GitHub 已维护项目）。
2. 若需本地实现：在 `mcp/` 新建 `*_server.py`。
3. 若需要本地数据：放 `mcp/catalog/`，解析逻辑放 `mcp/shared/`。
4. 工具命名保持动词开头，返回 JSON 可序列化对象。
5. 在本 README 增加：
   - 功能说明
   - 调用工具名
   - 外部依赖和替代方案

## 社交软件场景说明

`software_server.py` 已默认偏向社交方向：
- `recommend_software()` 默认 `category="social"`
- `recommend_social_software()` 直接返回社交/消息类软件
- `search_software()` 支持按关键词与平台过滤

如果你后续想扩成“社交 + 创作 + 生产力”混合推荐，只需要扩展 `catalog/software_catalog.json` 的 `categories` 和 `tags` 即可。

## 星座占卜场景说明

`horoscope_server.py` 提供娱乐型运势能力：

- `get_horoscope(sign, date="", emotion="", theme="general", style="gentle")`
  - `sign`：星座（支持 `libra` / `天秤座` / `天秤` 等写法）
  - `date`：`YYYY-MM-DD`，留空为今天
  - `emotion`：用户当前情绪（如“焦虑”），只影响措辞
  - `theme`：`general / study / love / social / health / wealth`
  - `style`：`gentle（温柔安抚）/ cheerful（活泼轻快）/ calm（稳重简洁）`
- 输出：整体运势评分与解读、主题建议、感情社交提示、幸运色/数字/活动、陪伴式总结、娱乐提示。
- 相同星座 + 日期 + 主题的结果是确定的（哈希播种），同一天内重复查询稳定；换主题会得到不同的建议条目。

启动方式：

```bash
python mcp/horoscope_server.py
```

## 塔罗占卜场景说明

`tarot_server.py` 提供基于 JobCannon 塔罗百科原文的抽牌解读：

- `draw_tarot(spread="single", question="")`
  - `spread`：`single`（单张指引）或 `three`（三张牌阵：过去·现在·未来）
  - 每张牌随机给正位/逆位（各半），返回牌名、关键词、正/逆位含义、肯定语、爱情/事业提示、原型长文
- `get_card_meaning(slug, orientation="upright")`：查单张牌（含 FAQ）
- `list_tarot_cards()`：78 张牌索引（num/slug/中文名/大小牌/花色）
- 牌义数据：`catalog/tarot_cards.json`（由 `jobcannon.io/zh/tarot/<slug>` 逐张爬取，原文保留，更新需重新爬取）

启动方式：

```bash
python mcp/tarot_server.py
```
