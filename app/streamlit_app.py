"""Local demo for the Food.com recipe-shortlisting study.

Local use only. Public deployment is not authorised by the specification: data
redistribution rights and access control must be settled first.

This demo collects nothing. No names, no emails, no surveys, no confidence ratings, no
decision timers, no persistent record of what a visitor clicks. Review text is never
rendered.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(ROOT), str(ROOT / "src")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.components import dataload as dl  # noqa: E402
from app.components import screens  # noqa: E402
from app.components import theme as th  # noqa: E402

SCREENS = [
    "Overview",
    "Historical profile",
    "Recommendations",
    "Method comparison",
    "OR inspector",
    "Scenario controls",
    "Evidence",
]


def main() -> None:
    st.set_page_config(
        page_title="Recipe shortlisting — LP study",
        page_icon="◆",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    th.inject()

    state = dl.load_demo_state()

    if state.is_synthetic:
        # Impossible to miss, on every screen. A fixture must never be mistaken for the
        # real study, however briefly.
        st.markdown(
            '<div class="notice notice-block" style="font-size:.95rem">'
            "<strong>SYNTHETIC FIXTURE — NOT RESEARCH DATA.</strong> This demo is pointed "
            "at a generated test dataset, not the Food.com files. Every number, recipe "
            "name and shortlist on screen is fabricated for software testing. Nothing here "
            "may be cited, screenshotted into the paper, or shown as a result."
            "</div>",
            unsafe_allow_html=True,
        )

    with st.sidebar:
        st.markdown(
            '<div class="eyebrow">Food.com study</div>'
            '<div style="font-weight:600;font-size:1.02rem;line-height:1.3;margin-bottom:1rem">'
            "Recipe shortlisting<br>with linear programming</div>",
            unsafe_allow_html=True,
        )
        screen = st.radio("Screen", SCREENS, label_visibility="collapsed")
        st.markdown('<div class="rule"></div>', unsafe_allow_html=True)

        label = None
        k = state.cfg.research.protocol.shortlist_size_k
        cap = state.cfg.research.protocol.band_cap_b

        if state.available and screen in (
            "Historical profile", "Recommendations", "Method comparison", "OR inspector",
            "Scenario controls",
        ):
            labels = state.labels()
            if labels:
                label = st.selectbox("Profile", labels, index=0)
                th.muted(
                    f"{len(labels)} warm profiles available at the "
                    f"{state.split.window.history_end_exclusive} cutoff. Labels are mapped; "
                    "raw Food.com user ids are not shown."
                )
            if screen in ("Recommendations", "Method comparison", "OR inspector"):
                st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
                th.muted(
                    f"Protocol settings: k = {k}, per-band cap b = {cap}. To vary them, use "
                    "the Scenario controls screen — those are labelled what-if runs, not "
                    "research results."
                )

        st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
        th.muted(
            "Secondary data only. No participants, no surveys, no decision timers. "
            "Choice overload is the motivation for shortlisting, not an outcome measured "
            "here."
        )

    if not state.available:
        th.eyebrow("Not ready")
        st.markdown("# The demo has no processed data to show")
        th.notice(state.reason or "Processed data is missing.", "block")
        gate = state.gate or {}
        if not gate.get("passed"):
            st.markdown("### Data gate")
            st.json(
                {
                    "files_present": gate.get("files_present"),
                    "missing_files": gate.get("missing_files"),
                    "provenance_complete": gate.get("provenance_complete"),
                    "missing_provenance_fields": gate.get("missing_provenance_fields"),
                    "raw_dir": gate.get("raw_dir"),
                }
            )
            if gate.get("instructions"):
                st.code(gate["instructions"], language="text")
        th.notice(
            "Nothing is simulated to fill this screen. The demo shows real processed "
            "Food.com data or it shows this page.",
            "info",
        )
        return

    if screen == "Overview":
        screens.overview(state)
        return
    if screen == "Evidence":
        screens.evidence(state)
        return

    if label is None:
        th.notice(
            "No warm profile is available at this cutoff. Check the split denominators in "
            "the latest splits run.",
            "block",
        )
        return

    {
        "Historical profile": lambda: screens.profile(state, label),
        "Recommendations": lambda: screens.recommendations(state, label, k, cap),
        "Method comparison": lambda: screens.method_comparison(state, label, k, cap),
        "OR inspector": lambda: screens.or_inspector(state, label, k, cap),
        "Scenario controls": lambda: screens.scenario(state, label),
    }[screen]()


if __name__ == "__main__":
    main()
