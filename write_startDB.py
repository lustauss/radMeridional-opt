
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

nInit = 0
db = {}

# First pass: read results and prepare successful cases
with open(results, "r") as f:
    for line in f:
        result = json.loads(line)

        candidate_id = result["candidate_id"]
        status = result["status"]
        objective = result["objective"]
        state = result.get("metadata", {}).get("state")
        evaDir = result.get("metadata", {}).get("evaluation_dir")

        if status == "success" and objective < 1:
            
            evaluation_file = os.path.join(evaDir, "evaluation.json")

            if os.path.exists(evaluation_file):

                with open(evaDir + "/evaluation.json", "r") as f:
                    evaluation = json.load(f)

                parameters = evaluation["candidate"]["parameters"]

                # Convert dictionary values into a list
                parameter_list = list(parameters.values())
                
                db["initial_"+str(int(nInit))] = [
                    parameter_list,
                    objective
                ]

                nInit += 1

print("nInit = "+str(nInit))        
        
# Write results to JSON
with open("start_db.json", "w") as f:
    json.dump(db, f, indent=4)
