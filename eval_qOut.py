
import os
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.lines import Line2D
import foamlib

def read_phi_file(filename):
    times = []
    phi = []

    with open(filename, "r") as f:
        for line in f:
            line = line.strip()

            # Skip header/comments
            if not line or line.startswith("#"):
                continue

            parts = line.split()

            if len(parts) >= 2:
                times.append(float(parts[0]))
                phi.append(float(parts[1]))

    return np.array(times), np.array(phi)

results = "./examples/runs/radmeridional_optimization/results.jsonl"

failed_cases = []
plot_data = []

# First pass: read results and prepare successful cases
with open(results, "r") as f:
    for line in f:
        entry = json.loads(line)

        candidate_id = entry["candidate_id"]
        status = entry["status"]
        objective = entry["objective"]
        state = entry.get("metadata", {}).get("state")

        if status != "success" or state is None or objective is None:
            failed_cases.append([candidate_id, status])
            continue

        case = os.path.join(
            "examples/testDir",
            candidate_id,
            "radmeridional",
            "of_" + state
        )

        print(f"Processing {candidate_id}: {case}")

        fc = foamlib.FoamCase(case)

        for var in ["U", "U:Transformed", "p"]:
            fc.run(["patchToCsv", var, "dt_mesh_outlet"])

        filename1 = os.path.join(
            case, "postProcessing/Q_dt_mesh_outlet/0/surfaceFieldValue.dat"
        )
        filename2 = os.path.join(
            case, "postProcessing/Q_dt_mesh_outlet/500/surfaceFieldValue.dat"
        )

        time1, phi1 = read_phi_file(filename1)
        time2, phi2 = read_phi_file(filename2)

        time = np.concatenate([time1, time2])
        phi = np.concatenate([phi1, phi2])
        phi_norm = phi / 27.65

        if phi_norm[-1] > 1.5 or phi_norm[-1] < 0.5:
            failed_cases.append([candidate_id, "diverged"])
            continue

        plot_data.append({
            "candidate_id": candidate_id,
            "objective": objective,
            "time": time,
            "phi_norm": phi_norm
        })

# Create green-to-red colors based on objective values
if plot_data:
    objectives = [d["objective"] for d in plot_data]

    norm = mpl.colors.Normalize(
        vmin=min(objectives),
        #vmax=max(objectives)
        vmax=0.04
    )
    cmap = plt.get_cmap("viridis")

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_title("Convergence of Normalized Outlet Discharge")

    for d in plot_data:
        color = cmap(norm(d["objective"]))

        ax.plot(
            d["time"],
            d["phi_norm"],
            color=color,
            label=f'{d["candidate_id"]}, fit: {d["objective"]:.4f}'
        )

    # Colorbar showing the objective scale
    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    fig.colorbar(sm, ax=ax, label="Objective value")

    # Add failed/diverged cases to the legend without plotting curves
    handles, labels = ax.get_legend_handles_labels()

    for candidate_id, reason in failed_cases:
        handles.append(
            Line2D(
                [], [],
                color="gray",
                linestyle="None",
                marker="x",
                label=f"{candidate_id} ({reason})"
            )
        )

    ax.legend(
        handles=handles,
        fontsize=8,
        loc="upper left",
        bbox_to_anchor=(1.18, 1)
    )

    ax.set_xlabel("Time")
    ax.set_ylabel("Normalized discharge")
    ax.grid(True, alpha=0.3)

    fig.subplots_adjust(right=0.65)
    plt.show()
else:
    print("No valid cases to plot.")


"""
import numpy as np
import matplotlib.pyplot as plt
import os
import foamlib
from pyDtOO import *
import json
from matplotlib.lines import Line2D

def read_phi_file(filename):
    times = []
    phi = []

    with open(filename, "r") as f:
        for line in f:
            line = line.strip()

            # Skip header/comments
            if not line or line.startswith("#"):
                continue

            parts = line.split()

            if len(parts) >= 2:
                times.append(float(parts[0]))
                phi.append(float(parts[1]))

    return np.array(times), np.array(phi)

results = "./examples/runs/radmeridional_optimization/results.jsonl"

# Read successful cases from JSONL
failed_cases = []

fig, ax = plt.subplots(figsize=(10, 6))
ax.set_title("Convergence of Normalized Outlet Discharge")

with open(results, "r") as f:
    for line in f:
        entry = json.loads(line)

        candidate_id = entry["candidate_id"]
        status = entry["status"]
        objective = entry["objective"]
        state = entry.get("metadata", {}).get("state")
        
        
        if status == "failed":
            failed_cases.append([candidate_id,status])
            continue

        if status != "success" or state is None:
            continue

        case = os.path.join(
            "examples/testDir",
            candidate_id,
            "radmeridional",
            "of_"+state
        )

        print(f"Processing {candidate_id}: {case}")

        fc = foamlib.FoamCase(case)

        for var in ["U", "U:Transformed", "p"]:
            fc.run(["patchToCsv", var, "dt_mesh_outlet"])

        filename1 = os.path.join(
            case, "postProcessing/Q_dt_mesh_outlet/0/surfaceFieldValue.dat"
        )
        filename2 = os.path.join(
            case, "postProcessing/Q_dt_mesh_outlet/500/surfaceFieldValue.dat"
        )

        time1, phi1 = read_phi_file(filename1)
        time2, phi2 = read_phi_file(filename2)

        time = np.concatenate([time1, time2])
        phi = np.concatenate([phi1, phi2])

        phi_norm = phi / 27.65
        
        if phi_norm[-1] > 1.5 or phi_norm[-1] < 0.5:
            failed_cases.append([candidate_id,"diverged"])
        else:
            ax.plot(time, phi_norm, label=f"{candidate_id}, fit: {objective:.4f}")

handles, labels = ax.get_legend_handles_labels()

for failure in failed_cases:
    handles.append(
        Line2D([], [], color="none", label=f"{failure[0]} ({failure[1]})")
    )

ax.legend(handles=handles, fontsize=8, loc="upper left",
          bbox_to_anchor=(1.02, 1))

ax.set_xlabel("Time")
ax.set_ylabel("Normalized discharge")
#ax.legend(fontsize=8, loc="best")
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()
"""
