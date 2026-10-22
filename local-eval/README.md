# DeepEval 本地评估使用文档

## 1. 方案说明

本目录提供一个基于 Docker Compose 的 DeepEval 按需评估环境：

```text
测试数据 / 被测客服系统
          ↓
    DeepEval JevEval
          ↓
第三方 Jev：emrank.tech/v1/decisions
          ↓
local-eval/reports/jev.json
```

本方案的特点：

- 使用当前仓库源码构建 DeepEval 镜像，不安装无关的 PyPI DeepEval 版本。
- 当前 DeepEval 版本：`4.3.1`。
- Jev 评估使用第三方 `emrank.tech` HTTP API，不使用 TypeSafe 官方 SDK。
- 评估模式固定为 `DEEPEVAL_EVAL_MODE=system_one`。
- 默认按需执行，容器完成任务后退出，不提供 Web 页面或常驻 Web 服务。
- 现有命令行流程仍可从 `.env` 读取 API Key；本地控制台会话改用一次性 stdin 凭证信封，不把密钥放入命令参数、容器环境或临时文件。
- 评估结果保存到宿主机的 `local-eval/reports/`。

`system_one` 和 `hybrid` 不等价。`system_one` 下，`JevEval` 直接把结构化问题发送给 Jev；Jev 调用失败时不会静默切换到其他 LLM。

## 2. 环境要求

- Windows 10/11
- Docker Desktop
- Docker Compose v2
- PowerShell
- 可用的第三方 Jev API Key

检查 Docker：

```powershell
docker version
docker compose version
```

## 3. 配置 Jev

在仓库根目录执行：

```powershell
Copy-Item local-eval\.env.example local-eval\.env
notepad local-eval\.env
```

编辑 `local-eval/.env`：

```env
DEEPEVAL_EVAL_MODE=system_one
JEV_API_KEY=你的第三方Jev密钥
JEV_BASE_URL=https://emrank.tech
JEV_MODEL=typesafe/jev-1.14.0
```

三个主要参数：

| 参数 | 说明 | 示例 |
|---|---|---|
| `JEV_API_KEY` | 第三方 Jev 密钥 | `你的真实密钥` |
| `JEV_BASE_URL` | 第三方 Jev 服务根地址，不要包含 `/v1/decisions` | `https://emrank.tech` |
| `JEV_MODEL` | 第三方 Jev 模型名 | `typesafe/jev-1.14.0` |

适配器实际请求：

```text
POST {JEV_BASE_URL}/v1/decisions
Authorization: Bearer {JEV_API_KEY}
```

也兼容第三方文档里的环境变量名：

```env
OPENAI_API_KEY=你的第三方Jev密钥
```

但是建议统一使用 `JEV_API_KEY`，避免与其他 OpenAI 服务配置混淆。

不要把真实密钥写入：

- `Dockerfile`
- `compose.yaml`
- Python 文件
- JSONL 数据集
- Git 提交记录

`local-eval/.env` 已被 Git 忽略。

## 4. 构建 Docker 镜像

当前环境如果 Docker Hub 不能直接访问，可以使用宿主机代理，并使用本机已有的 `python:3.11-slim`：

```powershell
$env:DOCKER_BUILDKIT = '0'
$env:COMPOSE_BAKE = 'false'
$env:DOCKER_BUILD_HTTP_PROXY = 'http://host.docker.internal:10808'
$env:DOCKER_BUILD_HTTPS_PROXY = 'http://host.docker.internal:10808'

docker compose -f local-eval\compose.yaml build
```

如果你的 Docker 环境可以直接访问 Docker Hub，也可以只执行：

```powershell
docker compose -f local-eval\compose.yaml build
```

## 5. 运行 Smoke Test

Smoke Test 不调用第三方 Jev，只检查容器和 DeepEval 环境：

```powershell
docker compose -f local-eval\compose.yaml run --rm eval
```

成功时会看到：

```json
{
  "status": "passed",
  "deepeval_version": "4.3.1",
  "eval_mode": "system_one",
  "jev_model": "typesafe/jev-1.14.0",
  "jev_api_key_set": true
}
```

注意：`jev_api_key_set=true` 只表示变量存在，不代表 API Key 有效。

查看报告：

```powershell
Get-Content local-eval\reports\smoke.json
```

## 6. 运行真实 Jev 评估

执行：

```powershell
docker compose -f local-eval\compose.yaml run --rm eval python -m evals.test_jev
```

因为 `compose.yaml` 会自动读取 `local-eval/.env`，通常不需要额外传递 API Key。

如果希望临时从当前 PowerShell 进程传入：

```powershell
$env:JEV_API_KEY = '你的第三方Jev密钥'
docker compose -f local-eval\compose.yaml run --rm -e JEV_API_KEY eval python -m evals.test_jev
```

查看结果：

```powershell
Get-Content local-eval\reports\jev.json
```

真实调用成功时：

```json
{
  "status": "verified",
  "metric": "gov-service-answer [JevEval]",
  "score": 0.95,
  "success": true,
  "confidence": 0.86,
  "model": "typesafe/jev-1.14.0 (emrank.tech)",
  "usage": {
    "input_tokens": 444,
    "output_tokens": 58
  }
}
```

字段说明：

- `status=verified`：确实收到了第三方 Jev 的结构化响应。
- `score`：DeepEval 根据问题答案计算出的最终分数。
- `success`：最终分数是否达到指标阈值。
- `confidence`：所有判断中最低的 confidence。
- `score_breakdown`：每个问题的概率、分数和 confidence。
- `usage`：第三方 Jev 返回的 token 用量。
- `output_source=fixture`：当前使用数据集中的固定回答，而不是实时客服系统。

不要只根据 HTTP 请求成功判断业务评估通过，应同时检查 `status`、`score` 和 `success`。

退出码：

| 退出码 | 含义 |
|---:|---|
| `0` | 已真实调用 Jev，报告为 `verified` |
| `1` | 配置错误、请求失败或返回格式错误 |
| `2` | 没有 API Key，未调用 Jev，不算通过 |

## 7. 当前测试数据

默认数据集：

```text
local-eval/datasets/property_certificate.jsonl
```

当前样例：

```json
{
  "id": "property-certificate-001",
  "input": "办理不动产权证需要提供哪些材料？",
  "actual_output": "具体材料取决于登记业务类型，例如首次登记、转移登记等，需要依据对应事项的办事指南确认。"
}
```

可以直接修改 `actual_output`，然后重新运行 `test_jev`。

注意：该回答只是技术连通性样例，不代表真实政务政策结论。具体业务内容必须以实际办事指南为准。

## 8. 接入真实客服系统

可以通过 `TARGET_BASE_URL` 让评估容器先调用真实客服系统，再把返回内容交给 Jev 评分。

在 `local-eval/.env` 中配置：

```env
TARGET_BASE_URL=http://host.docker.internal:8080
TARGET_PATH=/chat
```

Windows 宿主机上的服务必须使用 `host.docker.internal`，不能在容器中使用 `localhost`。

评估容器会向以下地址发送 POST：

```text
{TARGET_BASE_URL}{TARGET_PATH}
```

请求格式：

```json
{
  "id": "property-certificate-001",
  "input": "办理不动产权证需要哪些材料？",
  "turns": null
}
```

期望响应：

```json
{
  "actual_output": "客服系统生成的回答"
}
```

调用真实客服的完整流程：

```powershell
# 确认 local-eval/.env 中已配置 TARGET_BASE_URL

docker compose -f local-eval\compose.yaml run --rm eval python -m evals.test_jev
Get-Content local-eval\reports\jev.json
```

真实客服调用失败时，评估会直接失败，不会退回数据集中的固定回答。

## 9. 端到端评估和组件级评估

当前 `test_jev.py` 是端到端评估：

```text
用户输入 → 客服最终回答 → JevEval
```

组件级评估需要被测系统提供 trace，例如：

- 意图识别结果
- RAG 检索结果
- 问题澄清节点输出
- 工具调用输入和输出
- 最终生成节点输入和输出

DeepEval 的 `JevEval` 在不传 `evaluation_params` 时可以评估 trace，但当前示例没有真实 trace，因此报告中的：

```json
"component_eval": "not_run"
```

后续接入时需要把客服系统的 trace 转换成 DeepEval 测试用例，再针对具体组件创建 Jev 问题。

## 10. 报告和重复执行

报告目录：

```text
local-eval/reports/
├── smoke.json
└── jev.json
```

每次运行会覆盖对应报告文件，方便本地调试。需要长期保存时，请在 CI/CD 中复制报告或改为带时间戳的输出目录。

## 11. 常见问题

### 11.1 `jev_api_key_set=false`

检查：

```powershell
Test-Path local-eval\.env
Get-Content local-eval\.env
```

确认配置的是：

```env
JEV_API_KEY=...
```

不要把 Key 写成：

```env
TYPESAFE_API_KEY=...
```

当前第三方适配器主要读取 `JEV_API_KEY`，同时兼容 `OPENAI_API_KEY`。

### 11.2 `HTTP 403` 或 Cloudflare `error code: 1010`

这通常表示第三方网关拒绝了当前出口、代理或请求特征，不是 DeepEval 评分逻辑错误。

可检查：

- `JEV_BASE_URL` 是否为 `https://emrank.tech`。
- API Key 是否属于该第三方服务。
- 当前代理出口 IP 是否被第三方放行。
- 第三方账户是否有 `/v1/decisions` 权限。

适配器已经发送明确的：

```text
User-Agent: deepeval-local/1.0
```

如果仍返回 1010，需要联系第三方服务提供方放行当前网络出口。

### 11.3 `Connection refused` 或请求超时

当前 Docker 配置默认使用：

```text
http://host.docker.internal:10808
```

如果你的代理端口不同，在 `.env` 中配置：

```env
EVAL_HTTP_PROXY=http://host.docker.internal:你的端口
EVAL_HTTPS_PROXY=http://host.docker.internal:你的端口
```

如果访问的是宿主机上的客服服务，不要把客服地址写成容器内的 `localhost`。

### 11.4 `status=not_verified`

表示没有真实调用 Jev，通常是 API Key 未配置。这个状态不能当作评估通过。

### 11.5 `status=error` 且提示响应格式错误

第三方响应必须包含：

```json
{
  "answers": {
    "question_key": {
      "type": "noul | choice | score"
    }
  }
}
```

适配器当前支持：

- `noul`：读取 `noul`
- `choice`：读取 `choice`、`probabilities`、`confidence`
- `score`：读取 `score`、`probabilities`、`confidence`

## 12. 停止和清理

评估容器是一次性的，通常不需要手动停止。清理 Compose 网络：

```powershell
docker compose -f local-eval\compose.yaml down --remove-orphans
```

删除镜像：

```powershell
docker image rm deepeval-local:4.3.1
```

删除前请确认没有其他任务依赖该镜像。

## 13. 本地控制台

在仓库根目录启动标准库控制台：

```powershell
$env:PYTHONPATH = 'local-eval'
python -m ui.server
```

页面只绑定 `127.0.0.1:8787`。控制台会固定调用现有 Compose 评估命令，不接受命令、镜像或挂载路径。Compose UI 容器暂不启用：已验证评估镜像没有 Docker CLI/Compose，且 Windows 宿主路径不能安全地从容器推断；因此宿主机 Python 进程是当前明确的 fallback，限制见 `experiments/compose-ui.md`。
