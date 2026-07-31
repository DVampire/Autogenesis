# Autogenesis

一个自进化的多智能体框架。由 **MetaAgent** 编排各子智能体来完成用户任务，同时 optimizer / evaluator / generator 等智能体持续改进工具、技能与智能体生态。

> 🌐 English version: [README.md](README.md)

## 安装

```bash
bash scripts/install.sh
```

它会创建 conda 环境（`agentos`，Python 3.12）、安装本包及其依赖、安装 Node.js，
并生成 `.env` 模板。重复执行是安全的。可加 `--extras browser` 安装浏览器自动化、
`--uv` 改用 uv、`--help` 查看全部选项。

然后在项目根目录的 `.env` 里填入 API Key：

```bash
ANTHROPIC_API_BASE='...'
ANTHROPIC_API_KEY='...'
OPENROUTER_API_BASE='...'
OPENROUTER_API_KEY='...'
```

密钥也可以交由 **Vault** 集中管理；只要 Vault 已配置且可连通，框架会优先从中读取，
否则自动回退到 `.env`。

手动安装、Vault、可选 extras 等完整说明：
**➡️ [scripts/INSTALL_zh.md](scripts/INSTALL_zh.md)**

## 使用

Autogenesis 把**整个框架都跑在容器里**（即 "Model X"）：MetaAgent、所有子智能体，以及
全部工具执行（bash / 文件编辑 / git / 实验代码）。主机只负责启动；项目仓库以 bind-mount
挂进容器，所以源码改动实时生效、产物落回主机的 `output/` 下。服务型 peer（浏览器、任务
镜像）则通过挂载的 Docker socket、共享主机网络，作为兄弟容器被拉起。

先构建一次 base 镜像：

```bash
docker build -f docker/base/Dockerfile -t autogenesis/base:latest .
```

之后**所有东西都用同一种方式跑** —— 把命令写在 `--` 之后交给启动器：

```bash
scripts/run-in-sandbox.sh -- <命令>          # 在 sandbox 里运行 <命令>
scripts/run-in-sandbox.sh --gpus -- <命令>   # ……并暴露 NVIDIA GPU
```

启动器要求 Docker 守护进程可达，且拒绝回退到主机执行；用 `--image IMG` 指定别的 base 镜像。
去掉包裹、`conda activate agentos` 后，裸命令也能在主机上直接跑（不进容器），便于本地快速调试。

下面是你会用到的三件事。

### 1. 运行任务（MetaAgent）

[`examples/run_meta_agent.py`](examples/run_meta_agent.py) 会启动 MetaAgent 及其子智能体，并把单个任务跑到完成。

```bash
# 默认任务
scripts/run-in-sandbox.sh -- python examples/run_meta_agent.py

# 直接传入任务文本
scripts/run-in-sandbox.sh -- python examples/run_meta_agent.py --task "写一个反转字符串的 Python 函数并补充单元测试。"

# 从任务文档运行（examples/tasks/ 下的 .html / .md）
scripts/run-in-sandbox.sh -- python examples/run_meta_agent.py --task-file examples/tasks/qsar_egfr_experiment.html
```

| 参数 | 说明 |
| --- | --- |
| `--task "<文本>"` | 内联任务文本，优先级高于 `--task-file`。 |
| `--task-file <路径>` | 任务文档路径（`.html` / `.md`），位于 `examples/tasks/` 下。 |
| `--config <路径>` | 配置文件（默认：`configs/meta_agent.py`）。 |
| `--cfg-options key=value ...` | 覆盖任意配置项，例如 `--cfg-options model_name=openai/o3`。 |

每次运行都是独立 session：运行产物、日志和任务视图都写到 `output/<owner>/sessions/<session-id>/` 下
（`workspace/` 存智能体的工作文件，`log/` 存日志和渲染后的任务视图）。任务结束时日志会打印
最终结果；若生成了记忆报告，还会打印其 HTML 路径。现成的任务文档在 [`examples/tasks/`](examples/tasks/) 下。

### 2. 交互式网页 UI

[`frontend/`](frontend/) 是基于 React/Vite 的浏览器界面，通过版本化 Gateway 协议连接 Python 运行时。在 Model X 下，**后端 Gateway 和前端 dev server 都跑在 sandbox 里** —— 一个容器、两个进程，由 [`scripts/serve-ui.sh`](scripts/serve-ui.sh) 一起拉起：

```bash
scripts/run-in-sandbox.sh -- scripts/serve-ui.sh
```

然后在主机浏览器打开 `http://127.0.0.1:5173`（Vite dev server），它默认连接
`ws://127.0.0.1:9876/ws`。由于 sandbox 用了 `--network host`，两个端口在主机上都直接可达，
无需额外配置。首次启动会在 sandbox 内执行 `npm install`（依赖落到 `frontend/node_modules`，
之后启动跳过）。可用 `GATEWAY_PORT` / `UI_PORT` 覆盖端口；脚本后面追加的参数会透传给
`autogenesis serve`（如 `--token`、`--allow-origin`）。

服务不在受信任的本地网络时，请先设置 `AUTOGENESIS_GATEWAY_TOKEN`（绑定非本机地址时强制
要求），浏览器来源还可用重复的 `--allow-origin` 限制。完整说明见 [`frontend/README.md`](frontend/README.md)。

### 3. 运行测试

```bash
scripts/run-in-sandbox.sh -- pytest -q                        # 快速套件
scripts/run-in-sandbox.sh -- pytest -q tests/test_gateway.py  # 单个文件
scripts/run-in-sandbox.sh -- pytest -m integration            # 需要凭证 / 服务 / peer 容器
```

测试都在 [`tests/`](tests/) 下。默认运行会带上 `-m 'not integration'`（见 `pyproject.toml`），
所以不需要 API Key 或 Docker peer，跑得很快。`scripts/install.sh` 在装完后已自动跑过一遍。

## 产物与项目目录

`autogenesis` 只有一个 CLI，提供三种模式：直接执行控制命令（如 `autogenesis /registry`）、进入终端交互循环（`autogenesis tui`），或启动 Gateway（`autogenesis serve ...`）。

可写位置只有两个。框架写入的每一条路径都声明在同一张表里（`autogenesis/paths`），统一经
`path_manager` 解析，所以下面这棵树就是完整的磁盘契约：

```
output/                        生成态，可随时删除
  .runtime/                    机器级：端口注册表、沙箱账本、deploy、staging
  <owner>/
    state/                     跨会话持久：files、flows、IDE 扩展与登录态
    sessions/<session-id>/     一个任务一个目录（workspace/、session.json）
extension/                     共享且持久的组件，随项目一起版本化
```

从 config 启动的任务和从浏览器启动的同一个任务落在**同一个目录**：两者都从这张表构建沙箱，
而不是各自拼路径。会话先在自己的输出目录内暂存扩展改动，只有显式 promote 才写入 `extension/`。

`AUTOGENESIS_HOME` 把整棵树搬到别处（共享卷、临时盘），`AUTOGENESIS_EXTENSION_ROOT` 只搬
共享组件库。不再有第三个位置 —— 这里原先描述的 `./.autogenesis/` 是容器以 root 身份创建的，
又不在 chown 循环覆盖范围内，宿主用户既改不动也删不掉；它的内容现在都在 `output/.runtime/` 下。
