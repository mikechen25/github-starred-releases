# GitHub Starred Releases RSS

订阅你（mikechen25）所有 Star 仓库的 GitHub Release 聚合 Feed。

- **数据源**：GitHub 官方 REST API，只读
  - `GET /users/mikechen25/starred` — 当前 Star 列表（每小时全量刷新：新 Star 自动加入，取消 Star 自动移除）
  - `GET /repos/{owner}/{repo}/releases` — 各仓库真正发布的 Release
- **过滤规则**
  - 纯 Git Tag **不会**进入 Feed（Tag 不是 Release）
  - Draft Release **不会**进入（且非协作者本来就读不到 draft，脚本另有 `draft=false` 兜底过滤）
  - 正式 Release 与 Pre-release（alpha/beta/rc）**都会**进入
- **无需任何 PAT / Secret**：运行时使用 GitHub Actions 自动注入的 `GITHUB_TOKEN`（作用域仅限本仓库、自动轮换、无存储）。整个仓库零 Secrets。
- **去重**：Feed 每次由当前 API 快照确定性重建，按 Release 数字 ID 保证不重复；Release Notes 被作者编辑后会自动同步。
- **频率**：每小时（cron `23 * * * *` UTC）+ 可手动触发（Actions → 该 workflow → Run workflow）。另有每月 keep-alive 空提交，防止 GitHub 因 60 天无活动停掉定时任务。
- **Feed 地址（公开）**：`https://mikechen25.github.io/github-starred-releases/index.xml`
  - GitHub Pages 免费版为公开站点：任何拿到该 URL 的人都能访问。
  - 你当前的 Star 列表本身在 GitHub 上也是公开的，本 Feed 不额外暴露你的账号私有信息。

## 文件

| 文件 | 作用 |
|---|---|
| `.github/workflows/feed.yml` | 每小时构建并部署 Feed 到 Pages |
| `.github/workflows/keepalive.yml` | 每月保活（防定时任务停摆） |
| `build_feed.py` | Feed 生成器（Python 3 标准库，只读调用 API） |

## 首次使用：启用 GitHub Pages

仓库创建并推送后，打开仓库 **Settings → Pages**，在 *Build and deployment* 下选择
**Source: GitHub Actions**（如首次自动部署失败才会需要这一步）。之后每次运行自动部署。

## 常见问题

- **Feed 为空**：请确认账号下有公开的 Star，且这些仓库确实发布过 Release。
- **想看别的账号**：把 `feed.yml` 里的 `GH_USER` 与 `FEED_URL` 改成对应值，或设置 GitHub 仓库 Variables。
