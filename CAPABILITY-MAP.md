# Capability Map: Local system_one evaluation console

能力 ID 保持稳定；能力不等于独立服务或 Python 模块。

| Module id | Responsibility | Depends on |
|---|---|---|
| config | Shared versioned configuration validation, input snapshots, secret-free export | — |
| jev-adapter | Existing third-party protocol mapping, response validation, retry boundaries | config |
| execution | Docker lifecycle, E2E/Component orchestration, cancellation and recovery | config, jev-adapter |
| reporting | One canonical atomic report, completeness and separate quality verdict | config |
| console-ui | Local HTTP boundary, forms, previews, progress and report presentation | config, execution, reporting |

实现仅设 UI/HTTP、运行服务、评估执行器三个职责边界。config 和 reporting 属于运行服务；execution 管理生命周期并调用评估执行器；jev-adapter 复用现有代码。不得为本表预建五个服务。

验证顺序：部署/凭证/取消实验 → config 与 reporting 合同 → 适配器和 E2E → Trace 转换及上下文实验 → Component → UI 端到端验收。

详细合同、消融实验和未决技术事项见 local-eval/SPEC-system-one-console.md。
