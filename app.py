# app.py
import streamlit as st
import time
import json
import io
import math
import textwrap
import matplotlib.pyplot as plt
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any

st.set_page_config(page_title="Advanced NCL Design Tool", layout="wide")
st.title("🔷 Advanced NULL Convention Logic (NCL) Design Tool")
# -------------------------------
# Basic NCL primitives & helpers
# -------------------------------
Signal = Tuple[int, int]  # (rail1, rail0) or extended for quad as (high,low) semantics we keep dual-coded

def encode_dual(s: str) -> Signal:
    return {"NULL": (0,0), "DATA1": (1,0), "DATA0": (0,1)}.get(s, (0,0))

def encode_quad(s: str) -> Signal:
    # quad represented as (msb,lsb) for visualization only
    mapping = {"NULL(00)": (0,0), "01": (0,1), "10": (1,0), "11": (1,1)}
    return mapping.get(s, (0,0))

def is_null(sig: Signal) -> bool:
    return sig == (0,0)

def is_data(sig: Signal) -> bool:
    return sig != (0,0)

def signal_repr(sig: Signal) -> str:
    if sig == (0,0): return "NULL(00)"
    if sig == (1,0): return "DATA1(10)"
    if sig == (0,1): return "DATA0(01)"
    if sig == (1,1): return "QUAD(11)"
    return str(sig)

def time_stamp():
    return round(time.time(),3)

# Generic threshold gate TH_m_n: fires when >= m inputs are DATA
def thmn(inputs: List[Signal], m: int) -> Signal:
    count = sum(1 for x in inputs if is_data(x))
    return (1,0) if count >= m else (0,0)

# Prebuilt gates
def th22(a,b): return thmn([a,b],2)
def th12(a,b): return thmn([a,b],1)
def th23(a,b,c): return thmn([a,b,c],2)

# -------------------------------
# Data classes for user circuits
# -------------------------------
@dataclass
class Gate:
    id: str
    kind: str  # TH22, TH12, TH23, CUSTOM
    inputs: List[str] = field(default_factory=list)  # list of source node ids or inputs
    delay: float = 1.0  # simulated delay

@dataclass
class Circuit:
    inputs: Dict[str, Signal] = field(default_factory=dict)  # name -> signal
    gates: Dict[str, Gate] = field(default_factory=dict)     # gate_id -> Gate
    outputs: Dict[str, str] = field(default_factory=dict)    # output name -> source gate id or input name

# -------------------------------
# Sidebar: project, mode selection
# -------------------------------
st.sidebar.header("Project Controls")
project_name = st.sidebar.text_input("Project name", value="NCL_Advanced_Project")
mode = st.sidebar.selectbox("Mode",
    ["Circuit Builder & Simulator", "FSM (Moore / Mealy) Builder", "Pipeline Designer", "MTCMOS / Transistor View", "VHDL NCL Generator & Export", "Quick Demos / Examples"]
)
st.sidebar.markdown("---")
if st.sidebar.button("Reset Workspace"):
    st.session_state.clear()
    st.experimental_rerun()

# Initialize session storage objects
if "circuit" not in st.session_state:
    st.session_state.circuit = Circuit()
if "wave_history" not in st.session_state:
    st.session_state.wave_history = []  # list of dicts: timestep-> node states
if "fsm" not in st.session_state:
    st.session_state.fsm = {"type":"Moore","states":{}, "start":"S0", "transitions":[]}  # simple structure

# -------------------------------
# Utility: display circuit summary
# -------------------------------
def display_circuit_summary(circ: Circuit):
    st.subheader("Circuit Summary")
    st.write(f"Inputs: {list(circ.inputs.keys())}")
    st.write(f"Gates: {list(circ.gates.keys())}")
    st.write(f"Outputs: {circ.outputs}")

# -------------------------------
# Mode: Circuit Builder & Simulator
# -------------------------------
if mode == "Circuit Builder & Simulator":
    st.header("Circuit Builder & Step-by-Step Wavefront Simulator")
    with st.expander("1) Define Inputs"):
        cols = st.columns(3)
        with cols[0]:
            n_inp = st.number_input("Number of Dual-Rail Inputs", min_value=1, max_value=8, value=2, key="n_inp")
        with cols[1]:
            add_name = st.text_input("Add input name", value="A")
            if st.button("Add Input"):
                name = add_name.strip() or f"in{len(st.session_state.circuit.inputs)+1}"
                st.session_state.circuit.inputs[name] = (0,0)
                st.experimental_rerun()
        with cols[2]:
            if st.button("Auto-generate inputs"):
                for i in range(1, n_inp+1):
                    st.session_state.circuit.inputs[f"I{i}"] = (0,0)
                st.experimental_rerun()
    if st.session_state.circuit.inputs:
        with st.expander("Set input values (Dual-Rail & Quad)"):
            for name in list(st.session_state.circuit.inputs.keys()):
                choice = st.selectbox(f"{name} value", ["NULL","DATA1","DATA0","11(quads)"], key=f"inp_{name}")
                if choice == "11(quads)":
                    st.session_state.circuit.inputs[name] = (1,1)
                else:
                    st.session_state.circuit.inputs[name] = encode_dual(choice if choice!="11(quads)" else "NULL")

    with st.expander("2) Add Gate"):
        gkind = st.selectbox("Gate kind", ["TH22","TH12","TH23","CUSTOM - THmn"])
        gid = st.text_input("Gate id (e.g. G1)", value=f"G{len(st.session_state.circuit.gates)+1}")
        if gkind.startswith("CUSTOM"):
            m = st.number_input("Threshold m (fire when >= m inputs are DATA)", min_value=1, max_value=8, value=2)
        else:
            m = None
        inputs_raw = st.text_input("Comma-separated input names or gate ids (ex: I1,I2 or G1,G2)", value="")
        gdelay = st.slider("Gate delay (simulated time units)", min_value=0.1, max_value=3.0, value=1.0, step=0.1)
        if st.button("Add Gate"):
            input_list = [s.strip() for s in inputs_raw.split(",") if s.strip()]
            if gkind == "CUSTOM - THmn":
                kindname = f"THm{m}"
            else:
                kindname = gkind
            st.session_state.circuit.gates[gid] = Gate(id=gid, kind=kindname, inputs=input_list, delay=gdelay)
            st.success(f"Added {gid} : {kindname} inputs={input_list}")
            st.experimental_rerun()

    with st.expander("3) Map Outputs"):
        out_name = st.text_input("Output name", value="OUT")
        src = st.text_input("Source (input name or gate id)", value="G1")
        if st.button("Add Output"):
            st.session_state.circuit.outputs[out_name.strip() or f"OUT{len(st.session_state.circuit.outputs)+1}"] = src.strip()
            st.success("Output mapped")
            st.experimental_rerun()

    display_circuit_summary(st.session_state.circuit)

    # Simple simulator engine
    def evaluate_gate(g: Gate, state_signals: Dict[str,Signal]) -> Signal:
        # gather input signal values from state_signals (inputs & gate outputs)
        sigs = []
        for src in g.inputs:
            if src in state_signals:
                sigs.append(state_signals[src])
            else:
                # undefined -> NULL
                sigs.append((0,0))
        if g.kind.startswith("THm"):
            # parse m
            try:
                m = int(g.kind.replace("THm",""))
            except:
                m = max(1, len(sigs))
            return thmn(sigs, m)
        if g.kind == "TH22": return th22(*sigs[:2])
        if g.kind == "TH12": return th12(*sigs[:2])
        if g.kind == "TH23": return th23(*sigs[:3])
        # fallback OR-like
        return thmn(sigs, 1)

    if st.button("Run Step-by-Step Simulation"):
        circ: Circuit = st.session_state.circuit
        # initialize state with inputs
        state = {k:v for k,v in circ.inputs.items()}
        history = []
        t = 0.0
        changed = True
        st.session_state.wave_history = []
        while changed and t < 20:
            step_snapshot = {"time": round(t,3), "signals": dict(state)}
            st.session_state.wave_history.append(step_snapshot)
            history.append(step_snapshot)
            changed = False
            # evaluate each gate in topological-ish order (in insertion order)
            for gid, gate in circ.gates.items():
                out_sig = evaluate_gate(gate, state)
                # store under gate id
                prev = state.get(gid, (None,None))
                if out_sig != prev:
                    state[gid] = out_sig
                    changed = True
            t += 0.5
        # final outputs mapping
        final_outputs = {out: state.get(src, state.get(src, (0,0))) for out,src in circ.outputs.items()}
        st.success("Simulation complete")
        st.write("Final output signals:")
        for oname, sig in final_outputs.items():
            st.write(f"{oname} → {signal_repr(sig)}")
        # display wave history as a timeline plot for each node (simple)
        # prepare nodes
        nodes = list(set(list(circ.inputs.keys()) + list(circ.gates.keys()) + list(circ.outputs.keys())))
        # map timeline
        times = [h["time"] for h in st.session_state.wave_history]
        fig, ax = plt.subplots(figsize=(10, max(3, len(nodes)*0.3)))
        for i, node in enumerate(nodes):
            vals = []
            for h in st.session_state.wave_history:
                sig = h["signals"].get(node, (0,0))
                # map to numeric: NULL=0, DATA1=1, DATA0=0.5, QUAD=1.5
                if sig == (0,0): v = 0.0
                elif sig == (1,0): v = 1.0
                elif sig == (0,1): v = 0.5
                else: v = 1.5
                vals.append(v)
            ax.step(times, vals, where='post', label=node)
        ax.set_yticks([0,0.5,1.0,1.5])
        ax.set_yticklabels(["NULL","DATA0","DATA1","QUAD"])
        ax.set_xlabel("Simulated time")
        ax.set_title("Wavefront Timeline (step plot)")
        ax.legend(loc='upper right', bbox_to_anchor=(1.35,1))
        st.pyplot(fig)

    st.markdown("---")
    st.info("Tips: Use small circuits first. Add more gates then run the step-by-step to see NULL→DATA→NULL wavefronts. The plot uses numeric mapping for visualization.")

# -------------------------------
# Mode: FSM (Moore / Mealy) Builder
# -------------------------------
elif mode == "FSM (Moore / Mealy) Builder":
    st.header("Finite State Machine (Moore / Mealy) Designer — NCL-friendly")
    with st.expander("Define FSM"):
        ftype = st.selectbox("FSM type", ["Moore","Mealy"])
        st.session_state.fsm["type"] = ftype
        nstates = st.number_input("Number of states", min_value=1, max_value=12, value=max(1,len(st.session_state.fsm.get("states",{}))))
        # quick state creation
        if st.button("Auto-create states"):
            for i in range(nstates):
                st.session_state.fsm["states"][f"S{i}"] = {"output": (0,0) if ftype=="Moore" else None}
            st.session_state.fsm["start"] = "S0"
            st.success("States created")
        # show editable states table
        for sname, sdata in list(st.session_state.fsm["states"].items()):
            cols = st.columns([2,2,1])
            with cols[0]:
                newname = st.text_input("State name", value=sname, key=f"state_name_{sname}")
            with cols[1]:
                if ftype == "Moore":
                    out_choice = st.selectbox(f"Output for {sname}", ["NULL","DATA1","DATA0"], key=f"out_{sname}")
                    st.session_state.fsm["states"][newname] = {"output": encode_dual(out_choice)}
                else:
                    # Mealy: outputs on transitions
                    st.session_state.fsm["states"][newname] = {"output": None}
            with cols[2]:
                if st.button(f"Delete {sname}", key=f"del_{sname}"):
                    st.session_state.fsm["states"].pop(sname, None)
                    st.experimental_rerun()
        # transitions: simple text area JSON format for ease
        st.write("Define transitions (JSON array). For Mealy include 'out' on each transition.")
        sample = [
            {"from":"S0", "in":"1", "to":"S1", "out":"DATA1"},
            {"from":"S1", "in":"1", "to":"S0", "out":"DATA0"}
        ]
        txt = st.text_area("Transitions JSON", value=json.dumps(st.session_state.fsm.get("transitions", sample), indent=2), height=200)
        try:
            parsed = json.loads(txt)
            st.session_state.fsm["transitions"] = parsed
            st.success("Transitions parsed")
        except Exception as e:
            st.error("Invalid JSON for transitions")

    with st.expander("Simulate FSM"):
        steps = st.number_input("Simulation steps", min_value=1, max_value=20, value=6)
        inps = st.text_input("Input sequence (comma separated values, use 1/0)", value="1,1,0,1")
        if st.button("Run FSM Simulation"):
            seq = [s.strip() for s in inps.split(",") if s.strip()]
            state = st.session_state.fsm.get("start", list(st.session_state.fsm["states"].keys())[0] if st.session_state.fsm["states"] else "S0")
            out_log = []
            for i, inp in enumerate(seq[:steps]):
                # find transition
                matched = None
                for tr in st.session_state.fsm.get("transitions",[]):
                    if tr.get("from") == state and tr.get("in") == inp:
                        matched = tr
                        break
                if matched:
                    if st.session_state.fsm["type"] == "Mealy":
                        out_log.append(matched.get("out", "NULL"))
                    else:
                        out_log.append(signal_repr(st.session_state.fsm["states"].get(state,{}).get("output",(0,0))))
                    state = matched.get("to", state)
                else:
                    out_log.append("NULL")
                st.write(f"Step {i}: input={inp} -> state={state} -> out={out_log[-1]}")
            st.success("FSM simulation done")

    st.markdown("---")
    st.info("You can export FSM as a small VHDL process — use the VHDL generator mode to auto-create templates.")

# -------------------------------
# Mode: Pipeline Designer
# -------------------------------
elif mode == "Pipeline Designer":
    st.header("Multi-stage NCL Pipeline Designer / NULL-cycle Reduction")
    nstage = st.number_input("Number of pipeline stages", min_value=1, max_value=8, value=3)
    default_gates = ["TH12","TH22","TH23","THm2"]
    stages = []
    cols = st.columns((1,1,1,1))
    for i in range(nstage):
        with cols[i % len(cols)]:
            st.subheader(f"Stage {i+1}")
            gate = st.selectbox(f"Gate (Stage {i+1})", default_gates, key=f"pgate_{i}")
            latency = st.slider(f"Latency (Stage {i+1})", 0.1, 3.0, 1.0, 0.1, key=f"plat_{i}")
            stages.append((gate, latency))
    if st.button("Simulate Pipeline (NULL cycles & early completion)"):
        st.write("Simulating pipeline wavefronts...")
        # naive simulation: propagate an input DATA through stages; NULL injection after completion
        infile = encode_dual(st.selectbox("Pipeline input signal", ["NULL","DATA1","DATA0"], key="pip_in"))
        wave = infile
        timeline = []
        null_cycle_count = 0
        for idx, (g,lat) in enumerate(stages):
            # determine gate behavior
            if g == "TH12":
                out = th12(wave, wave)  # degenerate usage
            elif g == "TH22":
                out = th22(wave, wave)
            elif g == "TH23":
                out = th23(wave, wave, wave)
            else:
                out = thmn([wave],2)  # THm2 with single -> will be NULL
            timeline.append((f"Stage{idx+1}_{g}", signal_repr(out)))
            if is_null(out):
                null_cycle_count += 1
            wave = out
        st.write("Pipeline timeline:")
        for t in timeline:
            st.write(t[0], "→", t[1])
        st.write(f"NULL cycles encountered: {null_cycle_count}")
        if null_cycle_count > 0:
            st.warning("NULL-cycle reduction advice: try early-completion gates or inserting completion signals between stages.")
        else:
            st.success("No NULL cycles — pipeline is efficiently feeding DATA.")

    st.markdown("---")
    st.info("For a rigorous pipeline, you can add embedded registers (handshake-like) — extend by mapping inter-stage completion signals (I can add this automatically on request).")

# -------------------------------
# Mode: MTCMOS / Transistor View
# -------------------------------
elif mode == "MTCMOS / Transistor View":
    st.header("MTCMOS Power Gating Visualizer & Transistor-level View")
    st.write("This view simulates the effect of a sleep transistor on an NCL gate and estimates power/leakage/time tradeoffs.")
    sleep_enabled = st.checkbox("Enable sleep transistor (power gated)", value=False)
    wake_time = st.slider("Wake-up latency (simulated, ns)", min_value=0.1, max_value=50.0, value=5.0)
    gate_count = st.number_input("Number of logic gates protected", min_value=1, max_value=32, value=4)
    tech_vt = st.selectbox("MTCMOS threshold style", ["High-Vt sleep", "Dynamic body-bias"])
    if st.button("Estimate power & timing"):
        base_leak_per_gate = 1.0  # arbitrary units
        leakage = base_leak_per_gate * gate_count
        if sleep_enabled:
            leakage_after = leakage * 0.08  # assume 92% reduction
            energy_saved = leakage - leakage_after
            st.write(f"Estimated steady-state leakage before gating: {leakage:.2f} u")
            st.write(f"Estimated leakage with MTCMOS gating: {leakage_after:.2f} u")
            st.write(f"Estimated energy saved (steady-state): {energy_saved:.2f} u")
            st.write(f"Wakeup latency (adds to critical path): {wake_time} ns")
            st.info("Tradeoff: save leakage energy while paying wakeup latency and area for sleep transistors.")
        else:
            st.write(f"Estimated steady-state leakage (no gating): {leakage:.2f} u")
            st.info("Gating disabled — faster response, higher static power.")
        # transistor-level schematic ASCII (educational)
        st.subheader("Transistor-level sketch (conceptual)")
        trans_ascii = """
        PMOS pull-up network
        |--|<>|-- (logic network)
             |
           Sleep PMOS
             |
           Vdd

        NMOS pull-down network
        |--|__|-- (logic network)
             |
           Sleep NMOS
             |
           GND
        """
        st.code(textwrap.dedent(trans_ascii))

    st.markdown("---")
    st.info("This is a conceptual simulator useful for lab reports. For transistor-accurate SPICE-level simulation, generate netlists using the VHDL/Verilog path and use SPICE offline.")

# -------------------------------
# Mode: VHDL NCL Generator & Export
# -------------------------------
elif mode == "VHDL NCL Generator & Export":
    st.header("VHDL Generator — NCL gate templates & library exporter")
    st.write("Auto-generate VHDL components (THmn style) and a wrapper NCL library for dual-rail signals.")
    # designer inputs
    gen_gates = st.multiselect("Select gates to generate", ["TH12","TH22","TH23","THm2","THm3","THm4"], default=["TH12","TH22","TH23"])
    entity_name = st.text_input("Top-level entity name", value="ncl_top")
    generate_button = st.button("Generate VHDL Library and Download")
    def vhdl_thmn_template(name:str, m:int, n:int):
        # simple behavioral template representing threshold behavior
        return f"""
library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity {name} is
  port(
    {' ,'.join([f"in{i}: in STD_LOGIC_VECTOR(1 downto 0)" for i in range(1,n+1)])},
    outp: out STD_LOGIC_VECTOR(1 downto 0)
  );
end entity;

architecture BEH of {name} is
begin
  process({', '.join([f"in{i}" for i in range(1,n+1)])})
    variable cnt : integer := 0;
  begin
    cnt := 0;
    {"".join([f"if in{i} /= \"00\" then cnt := cnt + 1; end if;\\n    " for i in range(1,n+1)])}
    if cnt >= {m} then
      outp <= \"10\"; -- DATA1
    else
      outp <= \"00\"; -- NULL
    end if;
  end process;
end architecture;
"""
    if generate_button:
        files = {}
        for g in gen_gates:
            if g.startswith("THm"):
                m = int(g.replace("THm",""))
                n = max(m,2)
                name = f"{g}_comp"
                files[f"{name}.vhd"] = vhdl_thmn_template(name,m,n)
            else:
                # parse numbers from THxy
                try:
                    # TH22 -> m=2 n=2
                    m = int(g[2])
                    n = int(g[3])
                except:
                    m,n = 2,2
                name = f"{g}_comp"
                files[f"{name}.vhd"] = vhdl_thmn_template(name,m,n)
        # create top-level wrapper
        top = f"-- Auto-generated NCL library: {project_name}\n-- Top entity: {entity_name}\n"
        files[f"{entity_name}_lib.vhd"] = top
        # create zip in-memory
        import zipfile, io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for fname, content in files.items():
                z.writestr(fname, content)
        buf.seek(0)
        st.download_button("Download VHDL Library (zip)", data=buf, file_name=f"{entity_name}_ncl_vhdl.zip", mime="application/zip")
        st.success("VHDL library prepared for download")

    st.markdown("---")
    st.info("Generated VHDL is behavioral and intended as a starting point for NCL gate libraries and for conversion to synthesizable constructs as needed. Use the code as a template for lab submissions; I can extend this to full synthesizable VHDL on request.")

# -------------------------------
# Mode: Quick Demos / Examples
# -------------------------------
elif mode == "Quick Demos / Examples":
    st.header("Ready Examples, GitHub README & Deployment Helpers")
    st.markdown("Use these quick demos to populate your project repo. Click to auto-fill a sample circuit and download README / deploy script.")
    if st.button("Load Example: Dual-rail XOR-ish via TH22 chain"):
        # create example circuit
        st.session_state.circuit = Circuit()
        st.session_state.circuit.inputs = {"A":(1,0), "B":(0,1)}
        st.session_state.circuit.gates = {
            "G1": Gate("G1","TH12",["A","B"], delay=1.0),
            "G2": Gate("G2","TH22",["A","B"], delay=1.2)
        }
        st.session_state.circuit.outputs = {"OUT": "G2"}
        st.success("Example loaded into workspace")
    if st.button("Download Example README (GitHub-ready)"):
        readme = f"# {project_name}\n\nAdvanced NCL Design Tool\n\nRun locally:\n```\nstreamlit run app.py\n```\n\nProject includes:\n- NCL simulator\n- FSM builder\n- Pipeline designer\n- MTCMOS visualizer\n- VHDL generator\n\nDeploy on Streamlit Cloud: push to GitHub and connect the repo.\n"
        st.download_button("Download README.md", data=readme, file_name="README.md", mime="text/markdown")

    st.markdown("---")
    st.info("Tip: Push this repo to GitHub, enable Streamlit Cloud, and set the main file to app.py. I can create a CI workflow (GitHub Actions) on request to auto-deploy on push.")

# -------------------------------
# Footer / quick help
# -------------------------------
st.markdown("---")
