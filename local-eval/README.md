# DeepEval 本地 system_one 评估与控制台

本目录提供两条兼容的本地流程：现有 Docker Compose 命令行流程，以及调用同一固定 Compose 评估命令的本地控制台。评估模式固定为 `system_one`，使用本仓库源码和第三方 Jev HTTP API；不使用 TypeSafe 官方 SDK。

```text
JSONL 数据集或目标客服系统
          ↓
DeepEval JevEval（system_one）
          ↓
第三方 Jev：{JEV_BASE_URL}/v1/decisions
          ↓
local-eval/reports/*.json
```

`system_one` 是判定引擎模式；`e2e` 和 `component` 是评估范围，不能互相替代。`system_one` 下 JevEval 直接把结构化问题发送给 Jev，Jev 请求失败时不会静默切换到其他 LLM。

## 1. 环境和配置

需要 Windows 10/11、Docker Desktop、Docker Compose v2（本机当前验证为 Compose v5.5.1）和 PowerShell。

```powershell
docker version
docker compose version
```

在仓库根目录创建本地配置：

```powershell
Copy-Item local-eval\.env.example local-eval\.env
notepad local-eval\.env
```

最小配置：

```env
DEEPEVAL_EVAL_MODE=system_one
JEV_API_KEY=你的第三方Jev密钥
JEV_BASE_URL=https://emrank.tech
JEV_MODEL=typesafe/jev-1.14.0
```

主要参数：

| 参数 | 含义 |
|---|---|
| `JEV_API_KEY` | 第三方 Jev 密钥；CLI 也兼容 `OPENAI_API_KEY` |
| `JEV_BASE_URL` | Jev 服务根地址，不包含 `/v1/decisions` |
| `JEV_MODEL` | 第三方 Jev 模型名 |
| `TARGET_BASE_URL` | 可选。设置后使用目标客服系统，不设置则使用数据集中的 `actual_output` |
| `TARGET_PATH` | 目标路径，默认 `/chat` |
| `EVAL_HTTP_PROXY` / `EVAL_HTTPS_PROXY` | 可选的容器出站代理 |

适配器请求：

```text
POST {JEV_BASE_URL}/v1/decisions
Authorization: Bearer {JEV_API_KEY}
```

`local-eval/.env` 已被 Git 忽略。不要把真实密钥写入 Dockerfile、Compose 文件、Python 文件、JSONL、报告或 Git 提交记录。

## 2. 现有 CLI 流程

以下命令保持兼容。

### 构建镜像

Docker Hub 可直接访问时：

```powershell
docker compose -f local-eval\compose.yaml build
```

当前网络需要通过宿主机代理时：

```powershell
$env:DOCKER_BUILDKIT = '0'
$env:COMPOSE_BAKE = 'false'
$env:DOCKER_BUILD_HTTP_PROXY = 'http://host.docker.internal:10808'
$env:DOCKER_BUILD_HTTPS_PROXY = 'http://host.docker.internal:10808'
docker compose -f local-eval\compose.yaml build
```

### Smoke Test

Smoke Test 不调用第三方 Jev，只检查容器和 DeepEval 环境：

```powershell
docker compose -f local-eval\compose.yaml run --rm eval
Get-Content local-eval\reports\smoke.json
```

`jev_api_key_set=true` 只代表环境变量存在，不代表密钥有效。

### 真实 Jev 评估

```powershell
docker compose -f local-eval\compose.yaml run --rm eval python -m evals.test_jev
Get-Content local-eval\reports\jev.json
```

Compose 会读取 `local-eval/.env`。也可以只对本次命令从当前 PowerShell 进程传入密钥：

```powershell
$env:JEV_API_KEY = '你的第三方Jev密钥'
docker compose -f local-eval\compose.yaml run --rm -e JEV_API_KEY eval python -m evals.test_jev
```

退出码：

| 退出码 | 含义 |
|---:|---|
| `0` | 已真实调用 Jev，报告状态为 `verified` |
| `1` | 配置错误、请求失败或响应格式错误 |
| `2` | 没有 API Key，未调用 Jev，不算通过 |

### 清理

```powershell
docker compose -f local-eval\compose.yaml down --remove-orphans
docker image rm deepeval-local:4.3.1
```

删除镜像前确认没有其他任务依赖它。

## 3. 本地控制台启动方式

当前支持的控制台入口是宿主机 Python 进程：

```powershell
$env:PYTHONPATH = 'local-eval'
python -m ui.server
```

然后打开 `http://127.0.0.1:8787`。服务只绑定 loopback，页面和 API 通过固定命令调用现有 Compose `eval` 服务；接口不接受任意命令、镜像或挂载路径。一次只允许一个活动任务。

Compose `ui` 容器不是当前支持的启动方式。已验证的限制是：现有评估镜像没有 Docker CLI/Compose，单独提供 daemon 访问也不能启动兄弟容器；此外 Compose 的相对挂载路径在 UI 容器中无法安全地推断为 Windows 宿主机路径。没有据此添加 Docker socket、宿主机路径或凭证挂载。若要改回 Compose UI，必须先验证受控的宿主机路径和 daemon 传输方案。

上述限制来自 `experiments/compose-ui.md`。本地控制台的页面、浏览器交互和 Docker 运行并未在本次交付中宣称完成验证。

## 4. 配置模型

控制台和共享执行器使用 schema version 1。配置包含：

```text
schema_version = 1
project       = {name, description}
jev           = {base_url, model, timeout, proxy, retry, credential_ref}
evaluation    = {engine, scope, threshold, strict_mode,
                 include_reason, evaluation_params, questions}
dataset       = {path, max_cases, max_bytes}
target        = {url, headers, body_template, input_path,
                 turns_path, output_path, timeout}
component     = {trace_path, node_ids, questions} | null
```

固定约束：

- `evaluation.engine` 必须是 `system_one`；`evaluation.scope` 是 `e2e` 或 `component`。
- 未知版本、未知字段、非法类型、布尔形式的数值、NaN、无穷、非法权重、越界阈值和空问题会被拒绝。
- 至少启用一个问题；问题 ID 唯一，问题类型为 `noul`、`choice` 或 `score`。
- 数据路径必须留在允许的仓库目录内，拒绝符号链接逃逸；目标 URL 和代理 URL 不得包含凭证。
- 浏览器和 API 可做预检查，但服务端 `validate_config()` 是最终边界；纯校验不触网。
- 配置导出只包含非秘密值和 `credential_ref`，不会导出 API Key 或 `credentials.configured` 之类易过期状态。

配置、数据和问题在启动时冻结；运行中修改只影响下一次运行。

## 5. E2E 与 Component 输入

### E2E

当前 `evals.test_jev` 使用 `local-eval/datasets/property_certificate.jsonl` 中的用例。每行至少包含：

```json
{
  "id": "property-certificate-001",
  "input": "办理不动产权证需要提供哪些材料？",
  "actual_output": "具体材料取决于登记业务类型，需要依据对应事项的办事指南确认。"
}
```

未配置 `TARGET_BASE_URL` 时，评分这个固定 `actual_output`，报告标记 `output_source=fixture`。配置目标系统后，评估器向 `{TARGET_BASE_URL}{TARGET_PATH}` 发送：

```json
{
  "id": "property-certificate-001",
  "input": "办理不动产权证需要哪些材料？",
  "turns": null
}
```

目标系统应返回：

```json
{"actual_output": "客服系统生成的回答"}
```

目标请求失败、响应缺少 `actual_output` 或返回空回答都会失败，不会退回 fixture。Windows 宿主机服务从容器访问必须使用 `host.docker.internal`，不能使用容器内的 `localhost`。

### Component

Component 输入是包含 `trace_id` 和 `spans` 的 trace，以及可选的 `context`、`metadata`。每个 span 需要唯一 `span_id`，可用 `parent_span_id` 建立父子关系；配置通过 `component.node_ids` 选择待评估节点。转换和校验会保留 trace、span、父子关系、上下文和 metadata，并通过 JevEval 的 trace 状态评估选中节点。

缺失节点、重复 ID、非法父引用、循环或空选择会被拒绝。Component 不是把普通输入输出伪装成 E2E；但当前示例页面和固定 `test_jev` CLI 入口仍是 E2E，Component 质量结论需要真实标注数据验证。

## 6. 报告、执行、验证和质量

CLI 兼容报告写入：

```text
local-eval/reports/smoke.json
local-eval/reports/jev.json
```

控制台运行报告写入宿主机 `local-eval/reports/run_<run_id>.json`，并原子更新 `latest.json`。报告保存冻结的非秘密配置、输入快照或摘要、版本、问题映射、逐项状态、分数、confidence、reason、breakdown、usage、尝试次数、耗时和脱敏错误。`usage` 未返回时是未知，不是零。

必须分开解释三个事实：

- `execution_status`：任务是否完成、失败或取消。
- `verification_status`：是否收到真实且结构化有效的 Jev 响应；`not_verified`、`partial`、`verified` 不是质量结论。
- `quality_passed`：完整运行且没有执行错误后，所有适用结果是否达到阈值；未完成、取消、请求失败或模拟响应不能标记整体通过。

每个用例或节点都有独立状态。部分完成时可以展示已完成项目的局部分数和数量，但整体分数与 `quality_passed` 必须为空。低分是已完成评估，不等于请求失败。`score`、`success`、`confidence` 和 `score_breakdown` 应一起查看，不能只凭 HTTP 200 判断业务通过。

## 7. 取消和凭证边界

控制台取消使用运行 ID 的 DELETE 接口。任务状态按 `queued → running → completed/failed`，取消按 `cancelling → cancelled`；只有确认实际容器退出后才报告 `cancelled`。停止 Compose 客户端本身不算取消成功；若无法确认退出，保留 `cancelling` 并显示错误。已发出的远端请求可能继续执行或计费，取消不承诺撤回远端操作。启动失败和服务重启会清理或核对带有本应用 owner label 的任务，不清理无关容器。

控制台会话凭证通过一次性 stdin JSON envelope 传给执行器，不放进命令参数、容器环境或临时文件；配置、日志、报告和浏览器导出只保留引用或脱敏值。Jev Key、目标 `Authorization`/`Cookie` 和带认证的代理都按凭证处理。

这是边界保证，不是绝对的内存安全保证：不抵御管理员读取进程内存、操作系统交换、崩溃转储或 Docker 管理层观察；Python 也不能可靠擦除不可变字符串。现有 CLI 的 `.env` 行为为兼容性保留，不应声称它具有控制台会话凭证的生命周期保证。A4 使用假凭证验证了 stdin 和脱敏边界，但没有替代真实 Docker 部署检查。

## 8. 证据和未验证事项

A1–A8 的确定性证据记录在 `experiments/a1-a8.md`。使用本地假服务、固定答案和假凭证，没有真实 Jev 请求或真实质量数据。

| 门禁 | 结果 |
|---|---|
| A1 配置边界 | **passed**：16 项测试；类型、非有限值、权重、路径、限制和秘密导出边界被拒绝 |
| A2 取消 | **passed**：8 项测试；停止并确认、cancelling、过期任务清理、启动清理和固定命令边界 |
| A3 完整性 | **passed**：3 项测试；不完整或有错误的项目不能产生整体质量结论，迟到事件不能覆盖终态报告 |
| A4 凭证/脱敏 | **passed**：4 项测试；stdin-only 假凭证、命令/环境无秘密和脱敏 |
| A5 重试边界 | **passed**：4 项测试；可恢复 Jev 错误有限重试，401/格式错误不重试，目标失败只调用一次 |
| A6 Component 上下文质量 | **unverified**：确定性 trace 测试通过，但没有真实 Jev 标注数据；不声明上下文质量、归因、token 或延迟结论 |
| A7 评分一致性 | **passed**：固定假结构化 Jev 答案下执行路径与直接 JevEval 一致；这不是真实 Jev 验证 |
| A8 本地请求保护 | **passed**：7 项测试；外部 Host/Origin 被拒绝且不修改状态，合法 loopback 请求可用 |

完整本地套件共 52 项测试通过。已知预存在的检查问题：`black --check local-eval` 仅因 `evals/test_credentials.py` 未格式化而失败，`ruff check local-eval` 仅因 `ui/tests/test_reports.py` 的未使用局部变量而失败；本交付未改动它们。Docker 集成、浏览器和真实 Jev 质量验证未运行。A6 保持 **unverified**，不得把 smoke、fixture 或假 Jev 结果标记为真实 Jev 验证。

## 9. 参考文件

- 规格：`local-eval/SPEC-system-one-console.md`
- Compose UI 可行性：`local-eval/experiments/compose-ui.md`
- A4 凭证证据：`local-eval/experiments/a4-credentials.md`
- A6 未验证说明：`local-eval/experiments/a6-component-context.md`
- A1–A8 汇总：`local-eval/experiments/a1-a8.md`
