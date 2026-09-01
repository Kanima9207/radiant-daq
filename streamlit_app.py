"""RADIANT-DAQ Streamlit supervisory dashboard demo.

Run with: streamlit run streamlit_app.py
The displayed values are deterministic simulation telemetry unless replaced by
a hardware/backend integration in a later stage.
"""
import streamlit as st

from radiant.telemetry import SupervisoryDemoBackend
from radiant.telemetry.dashboard import (
    state_label,
    alarm_rows,
    recovery_rows,
    history_rows,
    journal_rows,
)


st.set_page_config(page_title="RADIANT-DAQ Supervisor", layout="wide")
st.title("RADIANT-DAQ Supervisory Console")
st.caption("Deterministic software-simulation telemetry — not hardware validation")

if "radiant_backend" not in st.session_state:
    st.session_state.radiant_backend = SupervisoryDemoBackend(capacity=128)
backend = st.session_state.radiant_backend

with st.sidebar:
    st.header("Demo controls")
    advance = st.button("Advance one frame", use_container_width=True)
    advance_8 = st.button("Advance 8 frames", use_container_width=True)
    if st.button("Reset demo", use_container_width=True):
        backend.reset()
        st.rerun()

if backend.latest is None:
    backend.next_frame()
if advance:
    backend.next_frame()
if advance_8:
    backend.run(8)

snapshot = backend.latest

state = state_label(snapshot.health_state)
st.subheader(f"System state: {state}")

cols = st.columns(5)
metrics = snapshot.metrics
cols[0].metric("Sample rate", f"{metrics.get('sample_rate_hz', 0):,.0f} Hz")
cols[1].metric("Active channels", f"{metrics.get('active_channels', 0):.0f}")
cols[2].metric("Buffer fill", f"{metrics.get('buffer_fill_pct', 0):.1f}%")
cols[3].metric("Timing RMS", f"{metrics.get('timing_rms_ns', 0):,.1f} ns")
cols[4].metric("Processing", f"{metrics.get('processing_utilization_pct', 0):.1f}%")

left, right = st.columns(2)
with left:
    st.subheader("Active alarms")
    alarms = alarm_rows(snapshot)
    if alarms:
        st.dataframe(alarms, use_container_width=True, hide_index=True)
    else:
        st.success("No active alarms")

with right:
    st.subheader("Recovery actions")
    recoveries = recovery_rows(snapshot)
    if recoveries:
        st.dataframe(recoveries, use_container_width=True, hide_index=True)
    else:
        st.info("No recovery action in this frame")

st.subheader("Operational trends")
history = history_rows(backend.history)
if history:
    chart_rows = [
        {
            "time_ms": row["time_ms"],
            "timing_rms_ns": row.get("timing_rms_ns", 0.0),
            "processing_utilization_pct": row.get("processing_utilization_pct", 0.0),
            "buffer_fill_pct": row.get("buffer_fill_pct", 0.0),
        }
        for row in history
    ]
    st.line_chart(chart_rows, x="time_ms", y=["timing_rms_ns", "processing_utilization_pct", "buffer_fill_pct"])
    st.dataframe(history, use_container_width=True, hide_index=True)

st.subheader("Alarm & recovery journal")
events = journal_rows(backend.journal.events)
if events:
    st.dataframe(list(reversed(events)), use_container_width=True, hide_index=True)
else:
    st.info("Journal is empty")

st.caption(
    f"Node {snapshot.node_id} · telemetry sequence {snapshot.sequence} · "
    f"simulation time {snapshot.timestamp_ns / 1e9:.3f} s"
)
