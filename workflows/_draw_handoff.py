# -*- coding: utf-8 -*-
"""Render the 'chat -> stop -> release VRAM' wiring diagram PNG for the README.

Matches full_ninfer_chat.json topology exactly. Port labels are the real socket
names (same in both locales); annotation text is Chinese (primary README).
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PIL import Image, ImageDraw, ImageFont

CN = r"C:\WINDOWS\Fonts\msyh.ttc"      # 微软雅黑
CNB = r"C:\WINDOWS\Fonts\msyhbd.ttc"   # 微软雅黑 bold

# ---- fonts ---------------------------------------------------------------
def F(path, size):
    return ImageFont.truetype(path, size)

F_SOCK    = F(CN, 16)      # port label on edge
F_SOCK_S  = F(CN, 13)
F_NODE    = F(CNB, 20)     # node main title
F_NODE_S  = F(CN, 15)      # node subtitle / action
F_MUTED   = F(CN, 13)
F_SEQ_H   = F(CNB, 18)     # annotation section header
F_SEQ_B   = F(CN, 13)      # annotation body
F_TITLE   = F(CNB, 26)

# ---- palette ---------------------------------------------------------------
BG       = (247, 249, 252)
INK      = (23, 27, 38)
MUTED    = (108, 117, 135)
EDGE     = (108, 117, 135)
ACCENT   = (99, 91, 255)   # indigo
ACCENT2  = (244, 63, 94)   # red for 'stop'
OK       = (16, 140, 96)   # green for handoff
NODE_FG  = (34, 42, 58)    # node box border/text
NODE_BG  = (255, 255, 255)
CHAIN_BG = (240, 244, 255) # light indigo tint
SEQUENCE_BG = (235, 244, 239) # light green tint

W, H = 1720, 1320
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

def rr(x, y, w, h, r=16, fill=NODE_BG, outline=NODE_FG, width=2):
    d.rounded_rectangle([x, y, x+w, y+h], radius=r, fill=fill, outline=outline, width=width)

def text_cx(cx, y, s, font, fill=INK):
    tw = d.textbbox((0, 0), s, font=font)[2]
    d.text((cx - tw/2, y), s, font=font, fill=fill)

def text_l(x, y, s, font, fill=INK):
    d.text((x, y), s, font=font, fill=fill)

def edge_arrow(x1, y1, x2, y2, color=EDGE, width=3, dash=None):
    """Line from (x1,y1) to (x2,y2) with an arrowhead computed from direction."""
    import math
    dx, dy = x2-x1, y2-y1
    L = math.hypot(dx, dy) or 1
    ux, uy = dx/L, dy/L
    if dash:
        # rough dashed
        step = 14
        tt = 0.0
        nx, ny = -uy, ux
        while tt < L-18:
            xa, ya = x1+ux*tt, y1+uy*tt
            xb, yb = x1+ux*min(tt+step*0.6, L), y1+uy*min(tt+step*0.6, L)
            d.line([(xa, ya), (xb, yb)], fill=color, width=width)
            tt += step
    else:
        d.line([(x1, y1), (x2-ux*16, y2-uy*16)], fill=color, width=width)
    # arrowhead at (x2,y2)
    ah = 12
    ang = math.atan2(dy, dx)
    import math as m
    for a in (ang+m.pi/6, ang-m.pi/6):
        d.line([(x2, y2), (x2-ah*m.cos(a), y2-ah*m.sin(a))], fill=color, width=3)

def socket_dot(x, y, color):
    d.ellipse([x-6, y-6, x+6, y+6], fill=color, outline=BG, width=2)

# ---- title -------------------------------------------------------------
text_l(50, 34, "让显存交接给下游：chat → stop（顺序示意）", F_TITLE, INK)
text_l(50, 74, "以 full_ninfer_chat.json 为例 — 端口名与 ComfyUI 实际一致", F_MUTED, MUTED)

# === upper map: the chat branch + GPU handoff ===
# 容器 A: 客户端; B: 对话; C: 服务控制; D: 吃显存下游; plus 预览小框, 参数链整条

# positions
A = (60, 300)             # 客户端
B = (430, 300)            # 对话
C = (980, 300)            # 服务控制
D = (1330, 300)           # 吃显存下游 (minimax / 图生图)
P = (430, 620)            # 预览 Any (below B)
CH = (60, 620)            # 参数链 (below A, far left)

BOXM = 300                # main box width
BOXH = 150

# 客户端
rr(A[0], A[1], 300, 150)
text_cx(A[0]+150, A[1]+42, "NInfer - 客户端", F_NODE)
text_l(A[0]+20, A[1]+92, "base_url · 自动启动", F_NODE_S, MUTED)
text_l(A[0]+20, A[1]+118, "模型文件 · keep alive", F_NODE_S, MUTED)

# 对话
rr(B[0], B[1], 300, 150)
text_cx(B[0]+150, B[1]+42, "NInfer - 对话", F_NODE)
text_l(B[0]+20, B[1]+92, "prompt · 可选引用图", F_NODE_S, MUTED)
text_l(B[0]+20, B[1]+118, "Model 留空(自动探测)", F_NODE_S, MUTED)

# 服务控制
rr(C[0], C[1], 300, 150, fill=(255, 250, 250), outline=ACCENT2, width=2)
text_cx(C[0]+150, C[1]+40, "NInfer - 服务控制", F_NODE, ACCENT2)
text_cx(C[0]+150, C[1]+78, "action = stop", F_NODE, ACCENT2)
text_l(C[0]+20, C[1]+112, "状态=节点内预览文本", F_NODE_S, MUTED)

# 下游
rr(D[0], D[1], 320, 150, fill=(240, 252, 244), outline=OK, width=2)
text_cx(D[0]+160, D[1]+42, "吃显存节点", F_NODE, OK)
text_l(D[0]+20, D[1]+88, "minimax H3 · 图生图 · 大采样", F_NODE_S, MUTED)
text_l(D[0]+20, D[1]+114, "现在有了整块显存可分配", F_NODE_S, OK)

# 预览
rr(P[0], P[1], 300, 96)
text_cx(P[0]+150, P[1]+36, "预览 Any", F_NODE)
text_cx(P[0]+150, P[1]+66, "(末端输出节点)", F_NODE_S, MUTED)

# 参数链
rr(CH[0], CH[1], 620, 96, fill=CHAIN_BG, outline=(179, 185, 255), width=2)
text_l(CH[0]+20, CH[1]+16, "参数链", F_NODE, ACCENT)
text_l(CH[0]+20, CH[1]+52, "系统→温度→最大tokens→思考→TopP→TopK→种子→附加", F_NODE_S, MUTED)

# ---- edges (from ports, label ports) ----
# A.client -> B.client
edge_arrow(A[0]+300, A[1]+55, B[0], B[1]+55, color=ACCENT, width=3)
socket_dot(A[0]+300, A[1]+55, ACCENT)
text_l((A[0]+300+B[0])//2 - 38, A[1]+42, "Client", F_SOCK, ACCENT)
# B.answer -> P.source (preview)
edge_arrow(B[0]+90, B[1]+150, P[0]+120, P[1], color=EDGE, width=3)
socket_dot(B[0]+90, B[1]+150, EDGE)
socket_dot(P[0]+120, P[1], EDGE)
text_l(B[0]+96, B[1]+152, "answer → 预览.source", F_SOCK_S, MUTED)
# CH.options -> B.options
edge_arrow(CH[0]+620, CH[1]+48, B[0], B[1]+120, color=ACCENT, width=2)
text_l((CH[0]+620+B[0])//2 - 100, (CH[1]+48+B[1]+120)//2 - 12, "Options", F_SOCK_S, ACCENT)
# *** THE KEY EDGE: B.answer -> C.trigger (Run After)  — daisies back ***
edge_arrow(B[0]+280, B[1]+55, C[0], C[1]+55, color=ACCENT2, width=4)
socket_dot(B[0]+280, B[1]+55, ACCENT2)
socket_dot(C[0], C[1]+55, ACCENT2)
text_l((B[0]+280+C[0])//2 - 80, B[1]+42, "answer → Run After", F_SOCK, ACCENT2)
# C.done -> D (hand off)
edge_arrow(C[0]+300, C[1]+55, D[0], D[1]+55, color=OK, width=4)
socket_dot(C[0]+300, C[1]+55, OK)
text_l((C[0]+300+D[0])//2 - 55, C[1]+42, "Done", F_SOCK, OK)

# ---- annotation panels ----
# left: key points; right: sequence timeline
def panel_l(x, y, w, h, fill, outline, title, title_fill):
    rr(x, y, w, h, r=18, fill=fill, outline=outline, width=2)
    text_l(x+22, y+16, title, F_SEQ_H, title_fill)

# panel 1: 这决定了什么
panel_l(60, 800, 760, 440, (255, 255, 255), (179, 185, 255), "这条回折的线做了什么", ACCENT)
bullets = [
    ("1  Run After 决定执行时刻", "显示在唯一输入 Ensure-V 槽位：任意输出接进来，本节点就保证在它之后执行。"),
    ("2  stop 在 chat 一有产出就触发", "对话出完回复 → 服务控制立刻关闭 NInfer 进程，这会儿显存还是满的。"),
    ("3  Done 把控制接力到下游", "吃显存节点等 Done 到达才开工，确保前面已经归还显存。"),
    ("4  旧版误导端口已删除", "Status/Healthy 文本端口没了——不会再有人把它们接进 Model。"),
]
y = 860
for t, s in bullets:
    text_l(80, y, t, F_SEQ_B, NODE_FG)
    text_l(80, y+24, s, F_MUTED, MUTED)
    y += 72

# panel 2: timeline of VRAM ownership
tx = 880; tw_ = 780
panel_l(tx, 800, tw_, 440, SEQUENCE_BG, (120, 196, 160), "显存占用与释放时序", OK)
# three phase bars
base_y = 870
ph = [("① chat 生成中", "~14.8 GiB 被 NInfer 占用", ACCENT2),
      ("② stop 立即关闭", "进程结束，显存归还 ComfyUI", OK),
      ("③ 下游跑起来", "吃显存节点使用整块空闲 24 GiB", OK)]
yy = base_y
for t, s, c in ph:
    # bar
    d.rounded_rectangle([tx+30, yy, tx+30+620, yy+14], radius=7, fill=(220, 228, 224), width=0)
    text_l(tx+30, yy+20, t, F_SEQ_B, NODE_FG)
    text_l(tx+320, yy+20, s, F_MUTED, MUTED)
    yy += 62
text_l(tx+30, base_y+3*62-18, "关键：谁都不需要猜顺序——连线本身就锁定了它。", F_MUTED, MUTED)

img.save(r"D:\AI\ComfyUI\custom_nodes\comfy-ninfer-api\workflows\handoff-vram.png")
print("saved handoff-vram.png", img.size)