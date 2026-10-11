# NInfer 示例工作流 — 接线说明

**中文** | [English](README.md)

两份可直接运行的图。把 `.json` 拖到 ComfyUI 画布，或 **Workflow → Open** 打开。

图用 ComfyUI 的 API（可运行）格式保存，加载后连线的形状和每个节点的默认值都能
直接看到、可编辑。

## 一条规则避免所有接线 bug

天真的第一版把 Server Control 的 **Status / Healthy 输出**设成可连接的文本/布尔端口，
结果有人错把它们接到 **Model** 输入，请求就报：
`model '运行中\n健康: 是\n...' not found` —— 服务器把一段状态报告当成了模型 id。

这个坑已经从源头堵死了：**Server Control 不再输出可连接的文本数据**。状态报告只在
节点体内以预览文本显示；它的唯一输出是专用控制信号（**Done**），只能用来标记"本节点
已执行完"以控制执行顺序，物理上接不进任何数据输入。

**仍然要记住：让对话节点的 Model 留空**，它会自动探测服务器第一个模型 id。

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
NInfer - 客户端 ──Client──▶ NInfer - 对话 ──answer──▶ 预览 Any
                                    ▲ options              │
                                    │                     Run After（可折返接回服务控制）
  系统提示词 ─▶ 温度 ─▶ 最大tokens ─▶ 思考强度 ─▶ Top P ─▶ Top K ─▶ 种子 ─▶ 附加Body
```

| 步骤 | 连接 | 为什么 |
|---|---|---|
| 1 | **对话.answer** → **服务控制.Run After** | 让 Server Control 在对话产出回复后才执行。此例 action 设为 `stop`：对话一跑完就关掉 NInfer，把显存交还（适合立刻要跑吃显存下游的场景）。**注意：这条线要"绕回去"，从对话绕过来接** |
| 2 | **客户端.Client** → **对话.Client** | 同最小图 |
| 3 | 参数节点**从左到右串联**，最后一个的 **Options** 输出 → **对话.Options** | 每个参数节点读取前一个合并好的设置，再加上自己那一项。你可以把链中任意节点拿掉，仍然成立 |
| 4 | **对话.answer** → **预览 Any.source** | 末端输出节点 |
| 5 | **对话.Model 留空** | 自动探测（见上面的规则） |

> ⚠️ 这个示例把 `action` 设成了 `stop`，是为了示范"对话后归还显存"。
> 如果你只是想跑一次对话不求立刻释放，把 `action` 改回 `ensure running`，
> 并把服务控制的 **Run After** 断开即可——那时它就是一个独立节点。

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