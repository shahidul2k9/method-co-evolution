#%%
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path.cwd()

def run_module(module_name: str):
    print(f"\n===== Running {module_name} =====")
    subprocess.run_module(
        [sys.executable, "-m", module_name],
        check=True,
        cwd=ROOT_DIR,
    )
# #%%
# run_module("ptc.generator.generate_fan")

#%%
run_module("ptc.generator.generate_change")

#%%
run_module("ptc.generator.generate_m2m_confidence")


#%%
run_module("ptc.generator.generate_t2p_link")

#%%
run_module("ptc.generator.generate_t2p_change")

#%%
run_module("ptc.generator.aggregate_csv_file")
