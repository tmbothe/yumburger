"""Generate YumBurger logo PNG."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Circle, Arc
from pathlib import Path

ASSETS = Path(__file__).parent.parent / "assets"

fig, ax = plt.subplots(figsize=(4, 4))
fig.patch.set_facecolor("#0D1117")
ax.set_facecolor("#0D1117")
ax.set_xlim(0, 4)
ax.set_ylim(0, 4)
ax.axis("off")

# Outer circle
circle_bg = Circle((2, 2.1), 1.6, color="#FF6B35", zorder=1)
ax.add_patch(circle_bg)
circle_inner = Circle((2, 2.1), 1.5, color="#161B22", zorder=2)
ax.add_patch(circle_inner)

# Bun top
bun_top = FancyBboxPatch((0.7, 2.6), 2.6, 0.9,
                          boxstyle="round,pad=0.3", facecolor="#FF8C55",
                          edgecolor="#FF6B35", linewidth=2, zorder=3)
ax.add_patch(bun_top)

# Sesame seeds
for sx, sy in [(1.3, 3.2), (2.0, 3.35), (2.7, 3.2), (1.65, 3.05), (2.35, 3.05)]:
    seed = FancyBboxPatch((sx-0.08, sy-0.04), 0.16, 0.08,
                          boxstyle="round,pad=0.02",
                          facecolor="#E8C88A", edgecolor="none", zorder=4)
    ax.add_patch(seed)

# Lettuce
lettuce = FancyBboxPatch((0.6, 2.35), 2.8, 0.3,
                         boxstyle="round,pad=0.05", facecolor="#3FB950",
                         edgecolor="#2EA043", linewidth=1, zorder=3)
ax.add_patch(lettuce)

# Cheese
cheese = FancyBboxPatch((0.65, 2.1), 2.7, 0.28,
                        boxstyle="round,pad=0.02", facecolor="#E3B341",
                        edgecolor="#D4A017", linewidth=1, zorder=3)
ax.add_patch(cheese)

# Patty
patty = FancyBboxPatch((0.7, 1.75), 2.6, 0.38,
                       boxstyle="round,pad=0.05", facecolor="#8B4513",
                       edgecolor="#6B3410", linewidth=1.5, zorder=3)
ax.add_patch(patty)

# Bun bottom
bun_bot = FancyBboxPatch((0.7, 1.35), 2.6, 0.42,
                         boxstyle="round,pad=0.2", facecolor="#FF8C55",
                         edgecolor="#FF6B35", linewidth=2, zorder=3)
ax.add_patch(bun_bot)

# Company name
ax.text(2, 0.75, "YumBurger", ha="center", fontsize=14, fontweight="bold",
        color="#FF6B35", zorder=5)
ax.text(2, 0.38, "A N A L Y T I C S", ha="center", fontsize=7, fontweight="bold",
        color="#8B949E", zorder=5)

out = ASSETS / "logo_yumburger.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="#0D1117")
plt.close()
print("Logo saved to", out)
