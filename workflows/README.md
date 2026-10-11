# NInfer example workflows — wiring guide

**English** | [中文](README.zh.md)

Two ready-to-run graphs. Open them by dragging the `.json` onto the ComfyUI
canvas, or **Workflow → Open**.

The graphs are stored in ComfyUI's API (runnable) format, so both the connection
shape and every node's default value are visible and editable once loaded.

## The one rule that prevents every wiring bug

The Server Control node's **Status** output and the Chat node's **Model** input
are *both plain text.* If you drag a wire from Status to Model, ComfyUI happily
accepts it and your request fails with:

```
openai.NotFoundError: model '运行中\n健康: 是\n进程号: ...' not found
```

The server received a status *report* where it expected a *model id*.

**Never connect Status → Model.** Leaves **Model empty**; the chat node
auto-detects the first model the server reports. Or connect a real model id from
the Client's model files.

## `minimal_ninfer_chat.json` — the smallest correct graph

Three nodes, three hooks:

```text
NInfer - Client ──Client──▶ NInfer - Chat ──answer──▶ Preview Any
```

| Step | Connection | Why |
|---|---|---|
| 1 | **Client.Client** → **Chat.Client** | Gives the chat node the server endpoint (base URL + auto-start + model file). |
| 2 | **Chat.answer** → **Preview Any.source** | ComfyUI refuses to run a graph with no output node, so this terminal node displays the reply. |
| 3 | Leave **Chat.Model** blank | Auto-detects the first model the server reports. |

Everything else is defaults. This is the baseline to debug against: if a run
feels broken, reduce to this graph first.

## `full_ninfer_chat.json` — all nodes connected

Adds the Server Control node and the full options chain:

```text
NInfer - Server Control                (standalone: ensure running)

NInfer - Client ──Client──▶ NInfer - Chat ──answer──▶ Preview Any
                                  ▲ options
   System Prompt ─▶ Temperature ─▶ Max Tokens ─▶ Reasoning Effort ─▶ Top P ─▶ Top K ─▶ Seed ─▶ Extra Body
```

| Step | Connection | Why |
|---|---|---|
| 1 | **Server Control** set to `ensure running` | Makes sure NInfer is up before the chat node fires. Its wires are **Status / healthy** — read-only outputs, do not connect them to anything |
| 2 | **Client.Client** → **Chat.Client** | As in the minimal graph. |
| 3 | Options **chained left → right**, last one's **Options** output → **Chat.Options** | Each option node reads the previous node's merged settings and adds its own. You can drop any node from the middle of the chain and it still works. |
| 4 | **Chat.answer** → **Preview Any.source** | Terminal output node. |
| 5 | Leave **Chat.Model** blank | Auto-detect (see the rule above). |

### The options chain in detail

Every `NInfer - Option*` node has one `Options` input (optional) and one
`Options` output. They are meant to be daisy-chained, and only the *last* node
in the chain feeds the Chat node's **Options** input:

- `System Prompt` — conversation-wide instructions; `skill` appends a markdown
  file from the skills directory.
- `Temperature`, `Top P`, `Top K`, `Max Tokens` — sampling knobs.
- `Reasoning Effort` — `low` / `medium` / `xhigh`; `xhigh` spends many tokens on
  hidden reasoning.
- `Seed` — deterministic sampling; 0 = random.
- `Extra Body` — raw JSON merged into the request body for anything the others
  don't expose.

Because settings are merged node by node, you can reorder or remove any of them
without breaking the graph.