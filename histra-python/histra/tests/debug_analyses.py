import sys
import os
import threading
sys.path.insert(0, r"C:\Users\mbonatte\Documents\Coding\histra-python")
from histra.io.hr_loader import load_model
from histra.solver.nonlinear_solver import solve_static_nonlinear

hrx_path = r"C:\Users\mbonatte\Documents\Coding\histra-python\model-output\model.hrx"
model = load_model(hrx_path)

analysis = model.collections.analyses[1]
analysis.method = "ModifiedNewtonRaphson"
if analysis.load_function_key in model.collections.load_functions:
    lf = model.collections.load_functions[analysis.load_function_key]
    analysis.load_function = lf

lines = []
def on_log(msg):
    lines.append(f"  {msg}")

result = [None]
def run():
    try:
        result[0] = solve_static_nonlinear(model, analysis, combination=1, on_log=on_log)
    except Exception as e:
        result[0] = e

t = threading.Thread(target=run, daemon=True)
t.start()
t.join(timeout=30)

with open(r"C:\Users\mbonatte\AppData\Local\Temp\opencode\lc_test_out.txt", "w") as f:
    for line in lines:
        f.write(line + "\n")
    r = result[0]
    if t.is_alive():
        f.write("TIMEOUT\n")
    elif isinstance(r, Exception):
        f.write(f"ERROR: {r}\n")
    else:
        exit_code, step_data = r
        f.write(f"\nExit code: {exit_code}, steps: {len(step_data)}\n")
        for i, sd in enumerate(step_data):
            f.write(f"  Step {i+1}: {sd.get('status','?')}, exit={sd.get('exit_code','?')}, iters={sd.get('iterations','?')}, lambda={sd.get('load_factor','?'):.6f}\n")
