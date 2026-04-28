# MCP Extension Layer

这个目录用于给主项目补充 MCP 能力，原则是：
- 优先复用 GitHub 上已维护的 MCP 仓库。
- 只有在没有现成服务可复用时，才写本地轻量 MCP（当前的 `software_server.py` 就是这个定位）。
- 尽量通过包管理器直接运行，不把外部仓库代码复制进本项目。

## 目录结构

- `weather_server.py`
  - 天气 MCP（当前是本地实现，依赖 `wttr.in` 公共接口）。
  - 如果后续找到稳定的官方/社区天气 MCP，可替换为外部服务接入。
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
  - `search_software`
  - `recommend_social_software`

主项目本身不需要改动业务 API，只要 MCP 客户端配置里注册这些 Server 即可。

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
