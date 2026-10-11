# NInfer API

[English](README.md) | **中文**

在 ComfyUI 里调用 [NInfer](https://github.com/Ryan-gsq/ninfer-16g-5070ti-5080-5090-qwen3.8-27b-gsq-rco) ——
一个本地跑的 Qwen3.8-27B 服务，带 OpenAI 兼容接口和视觉能力。

这个包做三件事：

1. **跟 NInfer 对话** —— chat completions，支持系统提示词、参考图，以及一堆
   按参数拆分的调节节点。
2. **管理 NInfer 进程** —— 用到时启动，闲置时关闭，把显存让给 ComfyUI 的其他工作。
3. **加载 skill** —— 纯 markdown 文件直接变成系统提示词，工作流挑 skill 就像挑
   模型一样自然。

因为服务是从工作流内部启停的，这个包的价值就在于：**让 27B 本地大模型和 ComfyUI
共存在同一张 24 GB 卡上**。请求在飞的时候 NInfer 占约 14.8 GiB，请求结束就降到零。

## 依赖

- **NInfer 本体不随包提供。** 需要你自己编译或下载，然后把 `NINFER_SERVE_EXE`
  指向那个可执行文件 —— 见下方[配置](#配置)。
- **Windows。** 进程控制用 `GenerateConsoleCtrlEvent` 投递干净退出信号，这是
  Windows 专有做法。聊天与参数节点在服务能跑的任何平台上应该都可用。
- 一个 OpenAI 兼容端点。NInfer **完全忽略 `Authorization` 头**，所以本地场景下
  API key 输入框只是占位 —— 它的存在是为了让同一批节点也能驱动那些真的校验凭据
  的端点。

## 安装

把文件夹放进 `ComfyUI/custom_nodes/` 然后重启 ComfyUI。没有额外依赖：用的是
ComfyUI 自带的 `openai`。

## 配置

路径默认相对本文件推导，可用环境变量覆盖。

| 变量 | 默认值 | 含义 |
|---|---|---|
| `NINFER_SERVE_EXE` | `<Ninfer-gsq>/build-win/apps/ninfer-serve.exe` | 服务端可执行文件 |
| `NINFER_MODELS_DIR` | `<Ninfer>/models` | `.ninfer` 模型文件所在目录 |
| `NINFER_SKILLS_DIR` | 见下 | markdown skill（支持子文件夹） |
| `NINFER_BASE_URL` | `http://127.0.0.1:8080/v1` | 已在运行的服务 |
| `NINFER_ROOT` | `Ninfer-gsq` 检出目录 | 日志文件位置 |

如果路径不对，随便加载一个节点看 tooltip —— 模型和 skill 下拉框都是从文件系统
实时读取的，**空列表就说明目录没找到**。

## 节点

### NInfer - 客户端

保存端点信息。`auto_start` 让客户端在服务无响应时把它拉起来。如果你自己已经
启动了服务（比如用 `infer.ps1`），它会**接管现成的**而不是再起一个。

`api_key` 是 NInfer 根本不看的占位符。留空会让 `openai` 客户端连接失败，所以
默认值 `ninfer-local` 是刻意给的。

`max_retries` 和 `timeout` 是常规客户端旋钮。默认超时给到 900 秒，因为这边
带思考的生成动辄要几分钟。

`idle_seconds` 是关闭计时器：连续这么多秒没有生成，后台回收线程就停掉进程。
`keep_alive` 直接关掉计时器，让服务在 ComfyUI 运行期间一直留着。**ComfyUI 队列里
有任务时计时器不走**，所以起一个长图任务不会把模型从工作流中间踢掉。

### NInfer - 对话

一次 completion。`prompt` 是用户这一轮；输出端口分别给出可见回复、模型的隐藏
思考、以及至今为止的对话历史。

**图像**是四个级联端口。接上 `image_1`；`image_2` 只有在 `image_1` 接了之后才
有意义，依此类推。每张 512px 图约 256 prompt tokens，注意给上下文留预算 ——
四张参考图是很舒服的工作集，在 4090 上做颜色角色绑定到十张左右仍准确。

**Force Regen** 控制 ComfyUI 的缓存。关掉时，输入没变的重跑会直接返回缓存答案，
不花一次生成的钱。

### NInfer - 服务控制

给想自己管显存的工作流用：`ensure running`、`stop`、`keep alive`、`status`。

### NInfer - 参数 / \*

一个参数一个节点，通过 `Options` 端口串起来。**顺序无所谓**，每个节点都往它拿到
的东西上合并。

| 节点 | 作用 |
|---|---|
| 系统提示词 | 文本、skill 文件，或两者 |
| 温度 | 0.0–2.0 |
| 最大生成数 | 回复长度上限 |
| 思考强度 | `low`、`medium`、`xhigh` |
| Top P / Top K | 采样 |
| 随机种子 | 支持 `control_after_generate` |
| 额外参数 | 未覆盖项的原始 JSON |

`思考强度` 默认给 `low` 是刻意的。Qwen3.8-27B **默认会思考**，`max_tokens` 小的时候
所有 token 都进思考通道，可见回复就是空的。节点返回空内容时，调大 `最大生成数`
或调低思考强度。

## Skill

一个 skill 就是 skill 目录里的 markdown 或文本文件。下拉框列出文件名，选中后它的
正文会被拼到系统提示词后面 —— 排在你填进 `system_prompt` 的文本之后。

### 用子文件夹分组

skill 一多，就按模型各建一个文件夹：

```
<skills>/
  qwen-image-2.1/
    prompt_enhancer.md
    prompt_enhancer_cn.md
  minimax-h3/
    camera-motion.md
  krea-2/
    lora-trigger.md
  cinematic-still.md          <- 平铺文件照旧可用
```

下拉框显示相对 skill 根目录的路径（`qwen-image-2.1/prompt_enhancer.md`），所以
两个组里可以有同名文件。排序按目录优先，同一组在列表里是连成一块的。最多支持
`SKILL_MAX_DEPTH = 3` 层（`a/b/c.md` 可用，`a/b/c/d.md` 被忽略），隐藏文件夹
跳过，只列 `.md` / `.txt`。**ComfyUI 会缓存节点定义，加完或改名后要重启它**。

### skill 目录到底在哪

设了 `NINFER_SKILLS_DIR` 就直接用它。否则按顺序取第一个存在的：

1. `NINFER_SKILLS_DIR`
2. `<ComfyUI>/input/skills`
3. `<ComfyUI>/../Input/skills` —— 适用于 `--input-directory` 指到 ComfyUI
   目录之外的布局

三个都不存在时，报 `<ComfyUI>/input/skills`，这样 tooltip 指向的位置合理，
在那里建目录就能立刻生效。

**刻意不用** `folder_paths.get_input_directory()`：它永远返回内置的
`<ComfyUI>/input`，哪怕服务器是用 `--input-directory` 指到别处启动的 —— 只靠它
推导会静默读到一个空目录。这个问题在本包历史上真实发生过。

```markdown
# NInfer Skill: Cinematic Still

Use this skill when the user asks for a cinematic look.

Compose the prompt as: shot type, subject, environment, light, grade, finishing.
Never use the words "beautiful" or "masterpiece".
```

写短一点，当成给模型的指令来写。

## 多语言

本文档提供中英两个版本：[English](README.md) 和本文件。

节点本身也做了中英双语。节点名、分类、以及每一个输入标签和 tooltip 都跟随
ComfyUI 自己的语言设置（`Comfy.Locale`）—— 所以把界面切成中文，这个包也跟着
变，**不需要单独设置**。

另外有两个节点会在执行期打印文本：**NInfer - 对话**输出 token 用量预览，
**NInfer - 服务控制**输出状态报告。ComfyUI 没有把界面语言暴露给后端，所以这两个
节点带一个显式的 `language` 控件（`zh` / `en`）。它只影响节点预览框里打印的内容
——模型实际回复什么取决于提示词。

要加一门语言，就复制 `locales/en/` 成 `locales/<code>/`，翻译 `nodeDefs.json`
和 `main.json`。ComfyUI 会自动发现 `locales/` 并由 `/i18n` 提供；合并结果有缓存，
改完要重启。两个坑，都是踩出来的：

- `nodeDefs.json` 的**顶层键直接是节点 id**。把它包进 `"nodeDefs"` 键里 —— 本包
  初版就是这么写的 —— 会让节点**静默消失**，因为 loader 自己已经把这个文件挂在
  那个键下了。
- `nodeCategories` 属于 `main.json`，不属于 `nodeDefs.json`。

运行期字符串在 `i18n.py`。加语言就扩展 `LANGUAGES` 和那些 `(english, chinese)` 元组。

## 与 ComfyUI 共存

NInfer 是单进程单模型服务：权重和 KV arena 都在启动时建好，**没有卸载 API**。
想把显存还回来，只能停进程。在一张 24 GiB 卡上这是实打实的取舍，所以本包按取舍
来处理。

本机实测，IQ3_S 模型，16384 token 上下文，`rk4v4-e8` KV：

| 状态 | 显存占用 | ComfyUI 出图 |
|---|---|---|
| NInfer 已停 | 约 3.7 GiB | 10–12 s |
| NInfer 常驻 | 约 18.0 GiB | 约 28 s |
| 启动 / 停止耗时 | — | 8.7 s / 0.7 s |

结论：只出一张图，就让 NInfer 留着；要批量出图，0.7 秒的停止加 8.7 秒的启动
差不多一张图就赚回来了。无论如何，设好 `idle_seconds` 交给回收线程判断。

## 注意事项与限制

- 服务端的 model id 随模型文件变化（`qwen3.8-27b`、
  `huihui-qwen3.8-27b-abliterated-swift15-gsq-rco-iq3s`……）。Model 字段留空即可
  使用服务端上报的那个。
- 模型名写错会返回 HTTP 404 —— **跟路由不存在是同一个状态码**，容易误判。
- NInfer 默认**不开** `--vision`。本包会传上，因为 vision tower 很小，而
  `--vision-residency overlay` 只在编码图片期间临时借显存。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
