"""Generate architecture and ER diagrams as PNG for the README."""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np
from pathlib import Path

ASSETS = Path(__file__).parent.parent / "assets"
ASSETS.mkdir(exist_ok=True)

# ── Colour palette ──────────────────────────────────────────────────────────
C = {
    "bg":        "#0D1117",
    "card":      "#161B22",
    "border":    "#30363D",
    "orange":    "#FF6B35",
    "orange_lt": "#FF8C55",
    "blue":      "#58A6FF",
    "green":     "#3FB950",
    "purple":    "#BC8CFF",
    "yellow":    "#E3B341",
    "teal":      "#39D3C3",
    "red":       "#F85149",
    "white":     "#F0F6FC",
    "grey":      "#8B949E",
    "aws_orange":"#FF9900",
}


def rounded_box(ax, x, y, w, h, color, label, sublabel="", icon="", alpha=0.95, fontsize=9):
    box = FancyBboxPatch((x - w/2, y - h/2), w, h,
                         boxstyle="round,pad=0.02", linewidth=1.5,
                         edgecolor=color, facecolor=C["card"], alpha=alpha, zorder=3)
    ax.add_patch(box)
    if icon:
        ax.text(x, y + h*0.18, icon, ha="center", va="center", fontsize=fontsize+4,
                zorder=4, color=color)
        ax.text(x, y - h*0.08, label, ha="center", va="center", fontsize=fontsize,
                fontweight="bold", color=C["white"], zorder=4)
    else:
        ax.text(x, y + (h*0.1 if sublabel else 0), label, ha="center", va="center",
                fontsize=fontsize, fontweight="bold", color=C["white"], zorder=4)
    if sublabel:
        ax.text(x, y - h*0.22, sublabel, ha="center", va="center", fontsize=fontsize-2,
                color=C["grey"], zorder=4)


def arrow(ax, x1, y1, x2, y2, color=C["grey"], style="->", lw=1.2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                connectionstyle="arc3,rad=0.0"),
                zorder=2)


def label_arrow(ax, x1, y1, x2, y2, label, color=C["grey"]):
    arrow(ax, x1, y1, x2, y2, color=color)
    mx, my = (x1+x2)/2, (y1+y2)/2
    ax.text(mx+0.05, my+0.05, label, fontsize=7, color=C["grey"], zorder=5,
            bbox=dict(boxstyle="round,pad=0.1", facecolor=C["bg"], edgecolor="none", alpha=0.8))


# ════════════════════════════════════════════════════════════════════════════
# 1. ARCHITECTURE DIAGRAM
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(18, 11))
fig.patch.set_facecolor(C["bg"])
ax.set_facecolor(C["bg"])
ax.set_xlim(0, 18)
ax.set_ylim(0, 11)
ax.axis("off")

# Title
ax.text(9, 10.5, "YumBurger  —  Federated Semantic Connector", ha="center",
        fontsize=16, fontweight="bold", color=C["orange"], zorder=5)
ax.text(9, 10.1, "Governed NL→SQL · Apache Iceberg Silver Zone · AWS Lake Formation",
        ha="center", fontsize=10, color=C["grey"], zorder=5)

# ── Layer labels ─────────────────────────────────────────────────────────────
for lx, ly, lw, lh, lc, lt in [
    (0.3, 7.6, 2.3, 2.5, C["blue"],   "PRESENTATION"),
    (0.3, 4.9, 2.3, 2.5, C["orange"], "API GATEWAY"),
    (0.3, 1.5, 2.3, 3.1, C["purple"], "CONNECTOR PLANES"),
    (5.8, 1.5, 1.5, 3.1, C["yellow"], "QUERY ENGINE"),
    (9.4, 1.5, 1.5, 3.1, C["green"],  "DATA LAKE"),
    (13.0,1.5, 1.5, 3.1, C["teal"],   "GOVERNANCE"),
]:
    r = FancyBboxPatch((lx, ly - lh/2), lw, lh,
                       boxstyle="round,pad=0.05", linewidth=1,
                       edgecolor=lc, facecolor=lc, alpha=0.07, zorder=1)
    ax.add_patch(r)
    ax.text(lx + lw/2, ly + lh/2 - 0.15, lt, ha="center", fontsize=7,
            fontweight="bold", color=lc, alpha=0.8, zorder=2)

# ── Presentation layer ────────────────────────────────────────────────────────
rounded_box(ax, 1.4, 8.3, 1.8, 0.7, C["blue"],   "Streamlit UI",   "app.py · port 8501", "[UI]")
rounded_box(ax, 1.4, 7.4, 1.8, 0.7, C["purple"], "Bodhi / Agent",  "bodhi_sim · /ask",   "[AI]")

# ── API layer ─────────────────────────────────────────────────────────────────
rounded_box(ax, 1.4, 5.8, 1.8, 0.7, C["orange"], "FastAPI",        "connector/main.py · :8000", "[API]")
rounded_box(ax, 1.4, 4.9, 1.8, 0.7, C["orange"], "ALB",            "ECS Fargate · us-east-1",   "[ALB]")

# ── Connector planes ─────────────────────────────────────────────────────────
planes = [
    (1.4, 3.9, C["blue"],   "Identity",  "identity.py"),
    (1.4, 3.1, C["orange"], "Metadata",  "metadata.py"),
    (1.4, 2.3, C["purple"], "Semantic",  "ontology.py"),
    (1.4, 1.5, C["green"],  "Query",     "compiler.py"),
    (1.4, 0.7, C["red"],    "Audit",     "audit.py"),
]
for px, py, pc, pn, ps in planes:
    rounded_box(ax, px, py, 1.8, 0.65, pc, pn, ps, fontsize=8)

# ── Query engine ──────────────────────────────────────────────────────────────
rounded_box(ax, 6.5, 3.5, 2.0, 0.75, C["yellow"], "NLToSQLCompiler", "Bedrock Haiku · sqlglot", "[LLM]")
rounded_box(ax, 6.5, 2.5, 2.0, 0.75, C["yellow"], "SQLVerifier",     "AST check · allowlist",   "[AST]")
rounded_box(ax, 6.5, 1.5, 2.0, 0.75, C["yellow"], "AthenaEngine",    "execute · poll · paginate","[ENG]")

# ── AWS Services ──────────────────────────────────────────────────────────────
rounded_box(ax, 10.2, 3.5, 2.0, 0.75, C["aws_orange"], "Amazon Bedrock",  "Claude Haiku · us-east-1", "[AI]")
rounded_box(ax, 10.2, 2.5, 2.0, 0.75, C["aws_orange"], "Amazon Athena",   "Engine v3 · Trino dialect","[SQL]")
rounded_box(ax, 10.2, 1.5, 2.0, 0.75, C["aws_orange"], "AWS STS",         "AssumeRole · 15 min TTL",  "[STS]")

# ── Data Lake ─────────────────────────────────────────────────────────────────
rounded_box(ax, 13.8, 3.5, 2.0, 0.75, C["green"], "Iceberg Silver",   "yumburger_silver · S3",    "[ICE]")
rounded_box(ax, 13.8, 2.5, 2.0, 0.75, C["teal"],  "Iceberg Semantic", "yumburger_semantic · S3",  "[OWL]")
rounded_box(ax, 13.8, 1.5, 2.0, 0.75, C["blue"],  "DynamoDB Audit",   "PRE/POST events · TTL 90d","[DDB]")

# ── Lake Formation ────────────────────────────────────────────────────────────
rounded_box(ax, 16.5, 2.5, 2.2, 0.75, C["teal"], "Lake Formation",   "Column/row policies",      "[LF]")
rounded_box(ax, 16.5, 1.5, 2.2, 0.75, C["teal"], "IAM Personas",     "analyst · admin roles",    "[IAM]")

# ── Arrows ────────────────────────────────────────────────────────────────────
# Presentation → API
arrow(ax, 1.4, 7.95, 1.4, 6.2, C["blue"])
arrow(ax, 1.4, 7.05, 1.4, 6.2, C["purple"])
# API → planes
arrow(ax, 1.4, 5.45, 1.4, 4.22, C["orange"])
# Identity → STS
arrow(ax, 2.3, 3.9, 9.2, 3.5, C["blue"], lw=1)
# Metadata/Semantic → Athena
arrow(ax, 2.3, 3.1, 9.2, 2.5, C["orange"], lw=1)
arrow(ax, 2.3, 2.3, 9.2, 2.5, C["purple"], lw=1)
# Query → Compiler
arrow(ax, 2.3, 1.5, 5.5, 3.5, C["green"], lw=1)
# Audit → DynamoDB
arrow(ax, 2.3, 0.7, 12.8, 1.5, C["red"], lw=1)
# Compiler chain
arrow(ax, 6.5, 3.12, 6.5, 2.87, C["yellow"])
arrow(ax, 6.5, 2.12, 6.5, 1.87, C["yellow"])
# Engine → Bedrock
arrow(ax, 7.5, 3.5, 9.2, 3.5, C["yellow"])
# Engine → Athena
arrow(ax, 7.5, 1.5, 9.2, 2.1, C["yellow"])
# Athena → Iceberg
arrow(ax, 11.2, 2.5, 12.8, 3.1, C["aws_orange"])
arrow(ax, 11.2, 2.5, 12.8, 2.5, C["aws_orange"])
# Athena → LF
arrow(ax, 11.2, 2.5, 15.4, 2.5, C["teal"], lw=0.9)
# LF → IAM
arrow(ax, 16.5, 2.12, 16.5, 1.87, C["teal"])

# ── Legend ─────────────────────────────────────────────────────────────────
legend_items = [
    (C["blue"],   "Presentation / Identity"),
    (C["orange"], "API / Metadata"),
    (C["purple"], "Semantic / Ontology"),
    (C["green"],  "Query / Iceberg"),
    (C["yellow"], "Compiler / Verifier"),
    (C["teal"],   "Governance / LF"),
    (C["red"],    "Audit"),
]
for i, (lc, lt) in enumerate(legend_items):
    ax.plot(0.5 + i*2.4, 0.2, "s", color=lc, markersize=8, zorder=5)
    ax.text(0.7 + i*2.4, 0.2, lt, fontsize=7, color=C["grey"], va="center", zorder=5)

out = ASSETS / "architecture.png"
plt.tight_layout(pad=0.3)
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=C["bg"])
plt.close()
print("Architecture diagram saved to", out)


# ════════════════════════════════════════════════════════════════════════════
# 2. ER DIAGRAM
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(16, 10))
fig.patch.set_facecolor(C["bg"])
ax.set_facecolor(C["bg"])
ax.set_xlim(0, 16)
ax.set_ylim(0, 10)
ax.axis("off")

ax.text(8, 9.6, "YumBurger — Entity Relationship Diagram",
        ha="center", fontsize=15, fontweight="bold", color=C["orange"])
ax.text(8, 9.25, "yumburger_silver · Apache Iceberg · Apache Parquet",
        ha="center", fontsize=9, color=C["grey"])


def er_table(ax, x, y, title, columns, color, width=2.8):
    row_h = 0.35
    header_h = 0.5
    total_h = header_h + len(columns) * row_h + 0.1

    # Header
    hdr = FancyBboxPatch((x, y - header_h), width, header_h,
                         boxstyle="round,pad=0.0", linewidth=2,
                         edgecolor=color, facecolor=color, alpha=0.9, zorder=3)
    ax.add_patch(hdr)
    ax.text(x + width/2, y - header_h/2, title, ha="center", va="center",
            fontsize=10, fontweight="bold", color="white", zorder=4)

    # Body
    body = FancyBboxPatch((x, y - total_h), width, total_h - header_h,
                          boxstyle="round,pad=0.0", linewidth=1.5,
                          edgecolor=color, facecolor=C["card"], alpha=0.95, zorder=3)
    ax.add_patch(body)

    for i, (col_name, col_type, is_pk, is_fk) in enumerate(columns):
        cy = y - header_h - (i + 0.5) * row_h
        icon = "[STS]" if is_pk else ("🔗" if is_fk else "  ")
        col_color = C["yellow"] if is_pk else (C["blue"] if is_fk else C["white"])
        ax.text(x + 0.15, cy, icon, fontsize=7, va="center", zorder=4)
        ax.text(x + 0.4, cy, col_name, fontsize=7.5, va="center",
                color=col_color, fontweight="bold" if is_pk else "normal", zorder=4)
        ax.text(x + width - 0.1, cy, col_type, fontsize=6.5, va="center",
                ha="right", color=C["grey"], zorder=4)
        if i < len(columns) - 1:
            ax.plot([x + 0.1, x + width - 0.1],
                    [cy - row_h/2, cy - row_h/2],
                    color=C["border"], lw=0.5, zorder=3)

    return x + width/2, y - total_h  # bottom center


def fk_line(ax, x1, y1, x2, y2, label=""):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=C["blue"], lw=1.3,
                                connectionstyle="arc3,rad=0.1"),
                zorder=2)
    if label:
        mx, my = (x1+x2)/2+0.05, (y1+y2)/2+0.05
        ax.text(mx, my, label, fontsize=7, color=C["blue"], zorder=5,
                bbox=dict(boxstyle="round,pad=0.1", facecolor=C["bg"],
                          edgecolor="none", alpha=0.85))


# Table definitions: (name, type, is_pk, is_fk)
tables = {
    "supplier": (1.0, 8.8, C["orange"], "SUPPLIER", [
        ("supplier_id",   "VARCHAR",  True,  False),
        ("name",          "VARCHAR",  False, False),
        ("category",      "VARCHAR",  False, False),
        ("region",        "VARCHAR",  False, False),
        ("state",         "VARCHAR",  False, False),
        ("contact_email", "VARCHAR",  False, False),
        ("active",        "BOOLEAN",  False, False),
        ("joined_at",     "TIMESTAMP",False, False),
    ]),
    "menu_item": (5.0, 8.8, C["purple"], "MENU_ITEM", [
        ("item_id",         "VARCHAR",  True,  False),
        ("name",            "VARCHAR",  False, False),
        ("category",        "VARCHAR",  False, False),
        ("price_usd",       "DECIMAL",  False, False),
        ("calories",        "INTEGER",  False, False),
        ("allergens",       "VARCHAR",  False, False),
        ("available",       "BOOLEAN",  False, False),
        ("supplier_id",     "VARCHAR",  False, True),
    ]),
    "customer": (9.0, 8.8, C["green"], "CUSTOMER", [
        ("customer_id",       "VARCHAR",  True,  False),
        ("first_name",        "VARCHAR",  False, False),
        ("last_name",         "VARCHAR",  False, False),
        ("email",             "VARCHAR",  False, False),
        ("tier",              "VARCHAR",  False, False),
        ("region",            "VARCHAR",  False, False),
        ("lifetime_spend_usd","DECIMAL",  False, False),
        ("registered_at",     "TIMESTAMP",False, False),
        ("active",            "BOOLEAN",  False, False),
    ]),
    "order": (5.0, 3.5, C["yellow"], "ORDER", [
        ("order_id",    "VARCHAR",   True,  False),
        ("customer_id", "VARCHAR",   False, True),
        ("order_ts",    "TIMESTAMP", False, False),
        ("channel",     "VARCHAR",   False, False),
        ("region",      "VARCHAR",   False, False),
        ("status",      "VARCHAR",   False, False),
        ("total_usd",   "DECIMAL",   False, False),
    ]),
    "order_line": (9.5, 3.5, C["teal"], "ORDER_LINE", [
        ("line_id",    "VARCHAR", True,  False),
        ("order_id",   "VARCHAR", False, True),
        ("item_id",    "VARCHAR", False, True),
        ("quantity",   "INTEGER", False, False),
        ("unit_price", "DECIMAL", False, False),
        ("subtotal",   "DECIMAL", False, False),
    ]),
}

bottoms = {}
for key, (x, y, color, title, cols) in tables.items():
    cx, by = er_table(ax, x, y, title, cols, color)
    bottoms[key] = (cx, y, by)   # center_x, top_y, bottom_y

# FK relationships
# menu_item.supplier_id → supplier.supplier_id
fk_line(ax, 5.0 + 2.8/2, bottoms["supplier"][1] - 0.6,
            1.0 + 2.8/2, bottoms["supplier"][1] - 0.6, "supplier_id")

# order.customer_id → customer.customer_id
fk_line(ax, 5.0 + 2.8/2, bottoms["order"][1] - 0.1,
            9.0 + 2.8/2, bottoms["customer"][2], "customer_id")

# order_line.order_id → order.order_id
fk_line(ax, 9.5, bottoms["order_line"][1] - 0.5,
            5.0 + 2.8, bottoms["order"][1] - 0.5, "order_id")

# order_line.item_id → menu_item.item_id
fk_line(ax, 9.5 + 2.8/2, bottoms["order_line"][1] - 0.1,
            5.0 + 2.8/2, bottoms["menu_item"][2], "item_id")

# Cardinality legend
ax.text(0.5, 0.6, "Relationships:", fontsize=8, fontweight="bold", color=C["white"])
ax.annotate("", xy=(3.0, 0.6), xytext=(1.8, 0.6),
            arrowprops=dict(arrowstyle="-|>", color=C["blue"], lw=1.3))
ax.text(3.1, 0.6, "Foreign Key (many → one)", fontsize=8, color=C["grey"], va="center")
ax.text(7.0, 0.6, "PK  Primary Key", fontsize=8, color=C["yellow"])
ax.text(10.0, 0.6, "FK  Foreign Key", fontsize=8, color=C["blue"])
ax.text(13.0, 0.6, "Partition: month(order_ts)", fontsize=8, color=C["grey"])

out_er = ASSETS / "er_diagram.png"
plt.tight_layout(pad=0.3)
plt.savefig(out_er, dpi=150, bbox_inches="tight", facecolor=C["bg"])
plt.close()
print("ER diagram saved to", out_er)
