# NInfer 示例工作流 — 接线说明

**中文** | [English](README.md)

两份可直接运行的图。把 `.json` 拖到 ComfyUI 画布，或 **Workflow → Open** 打开。

图用 ComfyUI 的 API（可运行）格式保存，加载后连线的形状和每个节点的默认值都能
直接看到、可编辑。

## 一条规则避免所有接线 bug

Server Control 节点的 **Status** 输出和 Chat 节点的 **Model** 输入**都是纯文本**。
如果你从 Status 拉一根线到 Model，ComfyUI 会欣然接受，然后你的请求报错：

```
openai.NotFoundError: model '运行中\n健康: 是\n进程号: ...' not found
```

服务器把一段状态*报告*当成了*模型 id*。

**永远不要接线 Status → Model。** 让 **Model 留空**；对话节点会自动探测服务器
第一个模型 id。或者接一个来自客户端模型文件的真实模型 id。

## `minimal_ninfer_chat.json` — 最少正确的图

三个节点，三条连接：

```text
NInfer - 客户端 ──Client──▶ NInfer - 对话 ──answer──▶ 预览 Any
```

| 步骤 | 连接 | 为什么 |
|---|---|---|
| 1 | **客户端.Client** → **对话.Client** | 给对话节点服务端端点（base URL + 自动启动 + 模型文件） |
| 2 | **对话.answer** → **预览 Any.source** | ComfyUI 不允许没有输出节点的图运行，这里显示回复 |
| 3 | **对话.Model 留空** | 自动探测服务器第一个模型 id |

其它全是默认值。这是用来排错的最小基线：感觉哪坏了，先缩到这张图来测。

## `full_ninfer_chat.json` — 全部节点接上

加上 Server Control 节点和完整的参数链：

```text
NInfer - 服务控制                     （独立节点：确保运行）

NInfer - 客户端 ──Client──▶ NInfer - 对话 ──answer──▶ 预览 Any
                                    ▲ options
  系统提示词 ─▶ 温度 ─▶ 最大tokens ─▶ 思考强度 ─▶ Top P ─▶ Top K ─▶ 种子 ─▶ 附加Body
```

| 步骤 | 连接 | 为什么 |
|---|---|---|
| 1 | **服务控制**设为 `ensure running` | 保证对话节点触发前 NInfer 已就绪。它的 **Status / healthy** 是只读输出，**不要接到任何地方** |
| 2 | **客户端.Client** → **对话.Client** | 同最小图 |
| 3 | 参数节点**从左到右串联**，最后一个的 **Options** 输出 → **对话.Options** | 每个参数节点读取前一个合并好的设置，再加上自己那一项。你可以把链中任意节点拿掉，仍然成立 |
| 4 | **对话.answer** → **预览 Any.source** | 末端输出节点 |
| 5 | **对话.Model 留空** | 自动探测（见上面的规则） |

### 参数链详解

每个 `NInfer - Option*` 节点都有**一个** `Options` 输入（可选）和一个 `Options`
输出。它们就是用来串成链的，而且链上**只有最后那个**节点的 `Options` 接到对话
节点的 **Options** 输入：

- `系统提示词` — 整段对话的指令；`skill` 会从 skills 目录附加一个 markdown 文件。
- `温度`、`Top P`、`Top K`、`最大tokens` — 采样旋钮。
- `思考强度` — `low` / `medium` / `xhigh`；`xhigh` 会在隐藏思考上烧大量 token。
- `种子` — 确定性的采样；0 = 随机。
- `附加Body` — 以原始 JSON 合并进请求体，补足其它节点没暴露的字段。

因为设置是逐节点合并的，你可以随意重排或删掉其中任何一个，不影响图。