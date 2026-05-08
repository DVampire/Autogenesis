# Autogenesis（中文）

[English](README.md) | 中文

**注意：** 代码正在整理中，可能存在 bug。目前 `examples/run_tool_calling_agent.py` 可以正常运行，其他 agent 还在调试中。

Autogenesis 是一个面向 LLM 智能体系统的**自进化协议**与工程化运行时。

现有不少 agent 协议（例如 A2A、MCP）对跨实体的 **生命周期/上下文管理**、**版本追踪**、以及**演化过程中的安全更新接口**规定不足，容易导致系统走向“大一统”的单体组合与脆弱的胶水代码。Autogenesis 的核心思路是将 **“演化什么（what evolves）”** 与 **“如何演化（how evolution occurs）”** 解耦：

- **RSPL（Resource Substrate Protocol Layer）**：把 *prompt、agent、tool、environment、memory* 建模为协议注册资源，提供显式的**状态**、**生命周期**与**版本化接口**。
- **SEPL（Self Evolution Protocol Layer）**：定义闭环的 operator 接口，用于提出（propose）、评估（assess）、提交（commit）改进，并具备可审计的 lineage 与**回滚（rollback）**能力。

基于 Autogenesis，系统也提供了 **Autogenesis-Agent** 风格的思考-行动（tool-calling）智能体，能够在执行过程中动态实例化/检索/精炼资源并持续改进。

## 架构图

![Autogenesis 架构](docs/architecture.png)

## 自进化闭环概览

从机制上看，Autogenesis 支持反复迭代的闭环：

- **行动（Act）**：智能体基于 LLM + 可用工具/环境产生行动与输出。
- **观测（Observe）**：记录结果、轨迹、关键中间信息，以及来自环境的反馈信号。
- **优化（Optimize）**：用优化器把反馈转成“可复用的改进”（提示词/解法/变量等的更新），例如 Reflection、GRPO、Reinforce++。
- **记忆（Remember）**：把会话事件、总结与洞察写入记忆系统，供后续步骤/会话复用。

## 核心模块

- **Agents（`src/agent/`）**：决定“下一步做什么”的运行逻辑（规划、工具调用、领域 agent 等）。
- **Tools（`src/tool/`）**：暴露给智能体调用的能力（工作流工具 + 默认工具）。
- **Environments（`src/environment/`）**：可交互的有状态接口（文件系统、回测环境、浏览器/移动端环境等）。
- **Memory（`src/memory/`）**：会话/事件记忆系统，用于总结、洞察与长期状态。
- **Optimizers（`src/optimizer/`）**：自进化算法，把反馈转为可落地的更新（reflection、GRPO、Reinforce++ 等）。
- **Tracing & Versioning（`src/tracer/`, `src/version/`）**：记录轨迹并管理迭代产物，便于分析与复现实验。
- **配置系统（`configs/`, `src/config/`）**：MMEngine 风格的组合式配置，用于一致地装配 agent/tool/env/memory/model。

## 设计目标

- **可组合**：能在不推翻整体架构的情况下替换/扩展 agent、工具、环境、记忆、优化器。
- **可观测**：结构化的 trace 与 memory event 让失败分析与改进步骤更透明。
- **可演化**：通过优化器 + 持久化记忆实现迭代式改进，而不是一次性推理。

## 目录结构

```
Autogenesis/
  configs/                 # 组件组合配置（agent/tool/env/memory/model）
  src/
    agent/                 # agents
    environment/           # environments
    tool/                  # tools
    memory/                # memory systems
    optimizer/             # 自进化优化器
    model/                 # model manager + provider backends
    prompt/                # prompt templates / prompt manager
    tracer/                # tracing
    version/               # versioning
  libs/                    # 内置/引入的库
  workdir/                 # 运行产物（日志/轨迹/结果等）
```

## （可选）运行 Tool-Calling Agent

前置条件：
- 先在你的环境里安装好依赖，请参考 [INSTALL.md](scripts/INSTALL.md)
- 将 `.env.template` 复制为 `.env`，并设置环境变量。

示例：

```bash
python examples/run_tool_calling_agent.py --config configs/tool_calling_agent.py
```

覆盖模型/输出目录：

```bash
python examples/run_tool_calling_agent.py \
  --config configs/tool_calling_agent.py \
  --cfg-options model_name=openrouter/gpt-4o workdir=workdir/demo tag=demo
```

## 引用
```
@misc{zhang2026autogenesisselfevolvingagentprotocol,
      title={Autogenesis: A Self-Evolving Agent Protocol}, 
      author={Wentao Zhang and Zhe Zhao and Haibin Wen and Yingcheng Wu and Cankun Guo and Ming Yin and Bo An and Mengdi Wang},
      year={2026},
      eprint={2604.15034},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2604.15034}, 
}
```