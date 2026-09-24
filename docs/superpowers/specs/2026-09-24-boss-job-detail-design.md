# BOSS 职位详情（点卡片）

## 目标

在现有列表抓取之后：对当前页每张职位卡片点击，读取详情面板，写入 `Job.detail`（职位描述 + HR 姓名/职务 + 详细工作地址），并在后端 stdout `print` 出来。

## 数据模型

`JobDetail`：

| 字段 | WS alias | 来源优先级 |
|------|----------|------------|
| `description` | `description` | `job/detail.json` / `job/card.json` → DOM |
| `hr_name` | `hrName` | 详情 API `bossInfo` → 列表 API `bossName` → DOM |
| `hr_title` | `hrTitle` | 详情 API `bossInfo` → 列表 API `bossTitle` → DOM |
| `address` | `address` | 详情 API `jobInfo.address` → DOM |

合并规则：`merge_job_detail` 按传入顺序，已有非空字段不被后写覆盖。

## 流程

1. `boss.search` 打开搜索页，拦截 `joblist.json`（薪资 + `bossName`/`bossTitle`）
2. 依次点击每张卡片
3. 拦截 `job/detail.json` / `job/card.json`，并等待详情面板 DOM
4. 合并 API + 列表 HR + DOM → `JobDetail`；`print` + WS `boss.jobs`
5. 单卡失败：该条对应字段为空，继续下一张；不翻页

## 非目标

传统分页控件不做；滚动加载见 [Reflex 迁移 spec](./2026-09-24-reflex-migration-design.md)。投递、桌面端复杂详情页（UI 展示 HR / 地址 / 描述摘要即可）
