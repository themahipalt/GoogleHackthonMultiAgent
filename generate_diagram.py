import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(16, 10))
ax.set_xlim(0, 16)
ax.set_ylim(0, 10)
ax.axis("off")
fig.patch.set_facecolor("#0f172a")
ax.set_facecolor("#0f172a")

def box(x, y, w, h, color, label, sublabel=None, radius=0.3):
    fancy = FancyBboxPatch((x, y), w, h,
                           boxstyle=f"round,pad=0.05,rounding_size={radius}",
                           linewidth=1.5, edgecolor=color,
                           facecolor=color + "22")
    ax.add_patch(fancy)
    ty = y + h / 2 + (0.15 if sublabel else 0)
    ax.text(x + w / 2, ty, label,
            ha="center", va="center", fontsize=10, fontweight="bold",
            color="white", fontfamily="monospace")
    if sublabel:
        ax.text(x + w / 2, y + h / 2 - 0.22, sublabel,
                ha="center", va="center", fontsize=7.5,
                color=color, fontfamily="monospace")

def arrow(x1, y1, x2, y2, color="#94a3b8"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=1.5, mutation_scale=14))

# ── Title ────────────────────────────────────────────────────────────────────
ax.text(8, 9.5, "AI Productivity Assistant — Architecture",
        ha="center", va="center", fontsize=14, fontweight="bold",
        color="white", fontfamily="monospace")

# ── User ─────────────────────────────────────────────────────────────────────
box(0.4, 4.2, 2.2, 1.4, "#38bdf8", "USER", "types message")

# ── FastAPI Backend ───────────────────────────────────────────────────────────
box(3.2, 4.2, 2.4, 1.4, "#818cf8", "FastAPI", "Cloud Run · Port 8080")

# ── Orchestrator ──────────────────────────────────────────────────────────────
box(6.6, 4.2, 2.8, 1.4, "#f59e0b", "ORCHESTRATOR", "Gemini 2.5 Flash")

# ── Agents row ────────────────────────────────────────────────────────────────
box(3.0, 1.5, 2.4, 1.3, "#34d399", "CALENDAR", "Calendar Agent")
box(6.6, 1.5, 2.4, 1.3, "#f87171", "TASK", "Task Agent")
box(10.2, 1.5, 2.4, 1.3, "#a78bfa", "NOTES", "Notes Agent")

# ── Google Services ───────────────────────────────────────────────────────────
box(2.4, 0.1, 3.2, 1.0, "#34d399", "Google Calendar API", "gcal events")
box(6.2, 0.1, 3.2, 1.0, "#f87171", "Cloud Firestore", "tasks · notes")
box(9.8, 0.1, 3.2, 1.0, "#a78bfa", "Cloud Firestore", "notes store")

# ── Cloud infra panel ─────────────────────────────────────────────────────────
box(10.4, 4.2, 2.6, 1.4, "#64748b", "Google Cloud", "Secret Manager\nArtifact Registry")
box(13.2, 4.2, 2.4, 1.4, "#64748b", "Cloud Build", "CI/CD Pipeline")

# ── Arrows ────────────────────────────────────────────────────────────────────
# User → FastAPI
arrow(2.6, 4.9, 3.2, 4.9, "#38bdf8")
# FastAPI → Orchestrator
arrow(5.6, 4.9, 6.6, 4.9, "#818cf8")
# Orchestrator → Agents
arrow(7.5, 4.2, 4.2, 2.8, "#f59e0b")
arrow(8.0, 4.2, 7.8, 2.8, "#f59e0b")
arrow(8.8, 4.2, 11.4, 2.8, "#f59e0b")
# Agents → Services
arrow(4.2, 1.5, 4.0, 1.1, "#34d399")
arrow(7.8, 1.5, 7.8, 1.1, "#f87171")
arrow(11.4, 1.5, 11.4, 1.1, "#a78bfa")
# Response back
arrow(6.6, 4.9, 5.6, 4.9, "#94a3b8")
arrow(3.2, 4.9, 2.6, 4.9, "#94a3b8")

# ── SSE label ─────────────────────────────────────────────────────────────────
ax.text(4.4, 5.25, "SSE stream", ha="center", fontsize=7, color="#94a3b8",
        fontstyle="italic")

# ── Legend ───────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(color="#38bdf8", label="User / Frontend"),
    mpatches.Patch(color="#818cf8", label="FastAPI Backend"),
    mpatches.Patch(color="#f59e0b", label="Gemini Orchestrator"),
    mpatches.Patch(color="#34d399", label="Calendar Agent"),
    mpatches.Patch(color="#f87171", label="Task Agent"),
    mpatches.Patch(color="#a78bfa", label="Notes Agent"),
    mpatches.Patch(color="#64748b", label="GCP Infrastructure"),
]
ax.legend(handles=legend_items, loc="upper left", fontsize=8,
          facecolor="#1e293b", edgecolor="#334155", labelcolor="white",
          framealpha=0.9, bbox_to_anchor=(0.01, 0.88))

plt.tight_layout()
plt.savefig("architecture_diagram.png", dpi=180, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print("Saved: architecture_diagram.png")
