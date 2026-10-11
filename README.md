# NInfer API

**English** | [中文](README.zh.md)

ComfyUI nodes for [NInfer](https://github.com/Ryan-gsq/ninfer-16g-5070ti-5080-5090-qwen3.8-27b-gsq-rco),
a local Qwen3.8-27B server with an OpenAI-compatible API and vision.

The pack does three things:

1. **Talks to NInfer** — chat completions with system prompts, reference images,
   and per-parameter tuning nodes.
2. **Manages the process** — starts NInfer on demand and stops it when idle, so
   the card is free for whatever else ComfyUI is doing.
3. **Loads skills** — plain markdown files that become the system prompt, so a
   workflow can pick a behaviour the same way it picks a checkpoint.

Because the server is started and stopped from inside a workflow, this pack is
how you run a 27B local LLM and ComfyUI on the same 24 GB card: NInfer holds
~14.8 GiB while a request is in flight, and drops to zero between them.

## Requirements

- **NInfer itself is not bundled.** Build or download it separately and point
  `NINFER_SERVE_EXE` at the binary — see [Configuration](#configuration).
- **Windows.** Process control uses `GenerateConsoleCtrlEvent` to deliver a
  clean shutdown, which is Windows-specific. The chat and option nodes should
  work anywhere the server runs.
- An OpenAI-compatible endpoint. NInfer ignores the `Authorization` header
  entirely, so the API key input is a placeholder locally — it exists so the
  same nodes can drive any endpoint that does check credentials.

## Install

Copy the folder into `ComfyUI/custom_nodes/` and restart ComfyUI. There are no
extra dependencies: it uses `openai`, which ComfyUI already ships.

## Example workflows

Ready-to-run graphs live in [`workflows/`](workflows/). Open one by dragging the
`.json` file onto the ComfyUI canvas (or **Workflow → Open**).

| File | What it shows |
|---|---|
| [`workflows/minimal_ninfer_chat.json`](workflows/minimal_ninfer_chat.json) | Smallest correct wiring: Client → Chat → preview |
| [`workflows/full_ninfer_chat.json`](workflows/full_ninfer_chat.json) | All nodes connected, including the options chain and Server |

**The #1 wiring mistake:** the Server Control node's **Status** output and the
Chat node's **Model** input are *both* text. If you connect Status → Model, the
request fails with an `openai.NotFoundError` (`model_not_found` — the server
recieves the status text instead of a model id). Leave **Model empty** and the
chat node auto-detects the first model the server reports, or connect a real
model id from the Client's model files.

See [`workflows/README.md`](workflows/README.md) for a step-by-step diagram of
both graphs.

## Configuration

Paths are discovered relative to this file and can be overridden with
environment variables.

| Variable | Default | Meaning |
|---|---|---|
| `NINFER_SERVE_EXE` | `<Ninfer-gsq>/build-win/apps/ninfer-serve.exe` | Server binary |
| `NINFER_MODELS_DIR` | `<Ninfer>/models` | Where `.ninfer` files live |
| `NINFER_SKILLS_DIR` | see below | Markdown skills (sub-folders allowed) |
| `NINFER_BASE_URL` | `http://127.0.0.1:8080/v1` | An already-running server |
| `NINFER_ROOT` | the `Ninfer-gsq` checkout | Log file location |

If the paths are wrong, load any node and read the tooltip — the model and
skill dropdowns are populated from the filesystem, so an empty list means the
directory was not found.

## Nodes

### NInfer - Client

Holds the endpoint. `auto_start` makes the client start the server if it is not
answering. It adopts a server you started yourself (for example with
`infer.ps1`) rather than spawning a second one.

`api_key` is a placeholder that NInfer ignores — it never checks the header.
It exists so the same nodes can point at any OpenAI-compatible endpoint that
does check credentials. Leave it empty and the `openai` client fails to connect,
so the default `ninfer-local` is deliberate.

`max_retries` and `timeout` are the usual client-side knobs. The default timeout
is 900 s because reasoning-heavy generations here run for minutes.

`idle_seconds` is the shutdown timer: after this many seconds with no
generation, the background reaper stops the process. `keep_alive` disables the
timer entirely and leaves the server up while ComfyUI runs. The timer does not
run while ComfyUI has a prompt in its queue, so starting a long image job does
not evict the model mid-workflow.

### NInfer - Chat

One completion. `prompt` is the user turn; the output sockets carry the visible
reply, the model's hidden reasoning, and the conversation so far.

**Images** are four cascading sockets. Connect `image_1`; `image_2` becomes
useful only once `image_1` is wired, and so on. Each 512px image costs about
256 prompt tokens, so budget the context window accordingly — four reference
images is a comfortable working set, and colour-role conditioning stayed
accurate to about ten on a 4090.

**Force Regen** controls ComfyUI's cache. Left off, re-running a graph with
unchanged inputs returns the cached answer instead of paying for a new
generation.

### NInfer - Server Control

Explicit control for workflows that want to manage the GPU themselves: `ensure
running`, `stop`, `keep alive`, and `status`.

### NInfer - Options / \*

One node per setting, chained through the `Options` socket. Order does not
matter; each node merges into whatever it was handed.

| Node | Effect |
|---|---|
| System Prompt | Text, a skill file, or both |
| Temperature | 0.0–2.0 |
| Max Tokens | Upper bound on the reply |
| Reasoning Effort | `low`, `medium`, `xhigh` |
| Top P / Top K | Sampling |
| Seed | `control_after_generate` supported |
| Extra Body | Raw JSON for anything not covered |

`Reasoning Effort` defaults to `low` on purpose. Qwen3.8-27B thinks by default,
and with a small `max_tokens` every token goes into the reasoning channel,
leaving the visible reply empty. If a node returns nothing, raise `Max Tokens`
or lower the effort.

## Skills

A skill is a markdown or text file in the skills directory. The dropdown lists
the filenames; selecting one prepends its contents to the system prompt, after
any text you typed into the `system_prompt` field.

### Grouping skills in sub-folders

With more than a handful of skills, group them one folder per model:

```
<skills>/
  qwen-image-2.1/
    prompt_enhancer.md
    prompt_enhancer_cn.md
  minimax-h3/
    camera-motion.md
  krea-2/
    lora-trigger.md
  cinematic-still.md          <- flat files still work
```

The dropdown shows the path relative to the skills root
(`qwen-image-2.1/prompt_enhancer.md`), so two groups may each hold a file of the
same name. Directory order is preserved, which keeps a group together in the
list. Up to `SKILL_MAX_DEPTH = 3` path components are offered (`a/b/c.md` works,
`a/b/c/d.md` is ignored), hidden folders are skipped, and only `.md` / `.txt`
files are listed. ComfyUI caches node definitions, so **restart it after adding
or renaming a skill**.

### Where the skills directory is

Set `NINFER_SKILLS_DIR` to choose it outright. Otherwise the first of these that
exists wins:

1. `NINFER_SKILLS_DIR`
2. `<ComfyUI>/input/skills`
3. `<ComfyUI>/../Input/skills` — for layouts where `--input-directory` points
   outside the ComfyUI tree

If none exist, the pack reports `<ComfyUI>/input/skills` so the tooltip points
somewhere sensible and creating it there starts working immediately.

This is deliberately **not** taken from `folder_paths.get_input_directory()`.
That always reports the built-in `<ComfyUI>/input`, even when the server was
started with `--input-directory` pointing somewhere else — so deriving from it
alone silently reads an empty tree. That was a real bug in this pack's history.

```markdown
# NInfer Skill: Cinematic Still

Use this skill when the user asks for a cinematic look.

Compose the prompt as: shot type, subject, environment, light, grade, finishing.
Never use the words "beautiful" or "masterpiece".
```

Keep them short and written as instructions to the model.

## Language

The README ships in English and Chinese: this file and [README.zh.md](README.zh.md).

The nodes themselves are translated into English and Chinese too. Node names,
categories, and every input label and tooltip follow ComfyUI's own language
setting (`Comfy.Locale`), so switching the interface to 中文 translates this pack
as well — no separate setting.

Two nodes also print text at execution time: **NInfer - Chat** writes a token
usage preview, and **NInfer - Server Control** writes a status report. ComfyUI
does not expose the interface language to the backend, so those two carry an
explicit `language` widget (`zh` / `en`). It affects only what the node prints in
its preview — the model's actual reply is whatever the prompt asks for.

Adding a language means copying `locales/en/` to `locales/<code>/` and
translating `nodeDefs.json` plus `main.json`. ComfyUI discovers `locales/`
directly and serves it from `/i18n`; the merge is cached, so restart ComfyUI
after editing. Two gotchas, both learned the hard way:

- `nodeDefs.json` holds node ids at the **top level**. Wrapping them in a
  `"nodeDefs"` key — as this pack's first draft did — silently buries them,
  because the loader already wraps the file under that key itself.
- `nodeCategories` belongs in `main.json`, not in `nodeDefs.json`.

`i18n.py` holds the runtime strings. Add a language there by extending
`LANGUAGES` and the `(english, chinese)` tuples.

## Coexisting with ComfyUI

NInfer is a single-process, single-model server: the weights and the KV arena
are built at startup and there is no unload API. Releasing VRAM means stopping
the process. On a 24 GiB card that is a real tradeoff, so the pack treats it
as one.

Measured on this machine, IQ3_S model, 16384-token context, `rk4v4-e8` KV:

| State | VRAM used | ComfyUI image |
|---|---|---|
| NInfer stopped | ~3.7 GiB | 10–12 s |
| NInfer resident | ~18.0 GiB | ~28 s |
| Start / stop cost | — | 8.7 s / 0.7 s |

So: for a single image, leave NInfer running. For a batch, the 0.7 s stop plus
8.7 s start pays for itself after roughly one image. Either way, set
`idle_seconds` and let the reaper decide.

## Notes and limits

- The server's model id changes with the artifact (`qwen3.8-27b`,
  `huihui-qwen3.8-27b-abliterated-swift15-gsq-rco-iq3s`, ...). Leave the Model
  field empty to use whatever the server reports.
- A wrong model name returns HTTP 404, the same status as a missing route.
- `--vision` is off in NInfer by default. This pack passes it, because the
  vision tower is small and `--vision-residency overlay` borrows VRAM only
  while an image is being encoded.

## License

MIT — see [LICENSE](LICENSE).
