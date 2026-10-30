"""Render the benchmark numbers as a table image for slides.

    python table.py                      -> benchmark_table.png

Edit ROWS as cells are completed: setup, spikes caught, false per second, repeat run.
"""
import matplotlib.pyplot as plt

plt.rcParams.update({"font.family": "Helvetica", "font.size": 14})

ROWS = [
    ["6 kS/s",  "278 µV", "37 µV", "7.5", "99 %", "73 %, 74 %", "0.5 / s"],
    ["10 kS/s", "380 µV", "52 µV", "7.4", "100 %", "89 %, 90 %", "0.3 / s"],
    ["15 kS/s", "408 µV", "53 µV", "7.7", "100 %", "86 %, 87 %", "0.4 / s"],
    ["20 kS/s", "399 µV", "45 µV", "8.8", "100 %", "94 %, 95 %", "0.5 / s"],
    ["30 kS/s", "362 µV", "47 µV", "7.7", "99 %", "77 %, 78 %", "0.6 / s"],
]
HEADER = ["rate", "spike", "noise", "spike / noise", "caught offline", "caught by device", "false"]
fig, ax = plt.subplots(figsize=(11, 1.2 + 0.5 * len(ROWS)))
ax.axis("off")
table = ax.table(cellText=ROWS, colLabels=HEADER, loc="center", cellLoc="center", colLoc="center",
                 colWidths=[0.11, 0.12, 0.11, 0.15, 0.17, 0.2, 0.12])
table.auto_set_font_size(False)
table.set_fontsize(14)
table.scale(1, 2.0)
for (row, col), cell in table.get_celld().items():
    cell.set_edgecolor("0.85")
    if row == 0:
        cell.set_text_props(weight="bold")
        cell.set_facecolor("#eef3f9")
    elif col == 0:
        cell.set_text_props(ha="left")
ax.set_title("One channel, FB128 SYNC, 60 s per run. Spike and noise from the raw stream; caught = share of the 95 spikes per second.",
             loc="left", fontsize=13, pad=10)
fig.tight_layout()
fig.savefig("benchmark_table.png", dpi=200, bbox_inches="tight")
print("saved benchmark_table.png")


# the channel table, 20 kS/s, wired channels pooled over both runs
ROWS_CH = [
    ["1", "20 000", "85 µV", "94 %", "0.5 / s", "0"],
    ["2", "40 000", "136 µV", "23 %", "2.6 / s", "0"],
    ["4", "80 000", "239 µV", "1 %", "4.0 / s", "0"],
    ["6", "120 000", "273 µV", "1 %", "35 / s", "0"],
    ["8", "160 000", "313 µV", "0 %", "5.9 / s", "0"],
    ["12", "240 000", "326 µV", "0 %", "", "0"],
    ["14", "280 000", "397 µV", "0 %", "", "relay drops"],
]
HEADER_CH = ["channels", "conversions / s", "noise", "spikes caught", "false", "dropped"]
fig, ax = plt.subplots(figsize=(11, 1.2 + 0.5 * len(ROWS_CH)))
ax.axis("off")
table = ax.table(cellText=ROWS_CH, colLabels=HEADER_CH, loc="center", cellLoc="center", colLoc="center",
                 colWidths=[0.12, 0.18, 0.14, 0.18, 0.14, 0.18])
table.auto_set_font_size(False); table.set_fontsize(14); table.scale(1, 2.0)
for (row, col), cell in table.get_celld().items():
    cell.set_edgecolor("0.85")
    if row == 0:
        cell.set_text_props(weight="bold"); cell.set_facecolor("#eef3f9")
ax.set_title("20 kS/s per channel, FB128 SYNC, 60 s x 2 per row. Channels 8 to 13 had no FB128 wire.", loc="left", fontsize=13, pad=10)
fig.tight_layout(); fig.savefig("channel_table.png", dpi=200, bbox_inches="tight"); print("saved channel_table.png")
