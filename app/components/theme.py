"""Visual system for the demo.

No eyebrow or kicker labels: a heading carries its own weight, and the label above it
is the first thing to cut. The helper was removed rather than left unused so the
pattern cannot creep back in.

Editorial black-and-white foundation, generous spacing, one restrained blue accent used
only where it carries meaning (the proposed method, a selected state, a live value). No
decorative motion: this is a research instrument that has to be legible on a projector.
"""

from __future__ import annotations

import streamlit as st

ACCENT = "#2563eb"
INK = "#0b0d10"
MUTED = "#6b7280"

CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap');

  :root {
    --ink: #0b0d10;
    --ink-2: #1f2937;
    --muted: #6b7280;
    --line: #e5e7eb;
    --paper: #ffffff;
    --wash: #f7f8fa;
    --accent: #2563eb;
    --accent-wash: #eff4ff;
    --glass: rgba(255,255,255,0.72);
  }

  .stApp { background: var(--wash); }
  html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, sans-serif; }

  .block-container { padding-top: 2.6rem; padding-bottom: 5rem; max-width: 1180px; }

  h1, h2, h3 { color: var(--ink); letter-spacing: -0.021em; font-weight: 600; }
  h1 { font-size: 2.45rem; line-height: 1.12; margin-bottom: .35rem; }
  h2 { font-size: 1.42rem; margin-top: 2.4rem; }
  h3 { font-size: 1.06rem; margin-top: 1.5rem; }

  .lede {
    font-family: 'Newsreader', Georgia, serif; font-size: 1.16rem; line-height: 1.62;
    color: var(--ink-2); max-width: 68ch; margin-bottom: 1.1rem;
  }
  .muted { color: var(--muted); font-size: .875rem; line-height: 1.6; }
  .rule { height: 1px; background: var(--line); margin: 2.1rem 0 1.7rem; }

  /* --- surfaces --- */
  .card {
    background: var(--glass); backdrop-filter: blur(9px);
    border: 1px solid var(--line); border-radius: 14px;
    padding: 1.15rem 1.25rem; margin-bottom: .85rem;
  }
  .card-accent { border-left: 3px solid var(--accent); }

  /* --- recipe card --- */
  .recipe { display: flex; gap: 1rem; align-items: flex-start; }
  .recipe-rank {
    font-variant-numeric: tabular-nums; font-size: 1.55rem; font-weight: 300;
    color: var(--muted); min-width: 2.1rem; line-height: 1.15;
  }
  .recipe-name {
    font-size: 1.02rem; font-weight: 600; color: var(--ink); line-height: 1.35;
    margin-bottom: .34rem;
  }
  .recipe-meta { font-size: .8rem; color: var(--muted); margin-bottom: .5rem; }
  .recipe-why { font-size: .855rem; color: var(--ink-2); line-height: 1.55; }

  .pill {
    display: inline-block; padding: .16rem .58rem; border-radius: 999px;
    font-size: .7rem; font-weight: 600; letter-spacing: .03em;
    background: #f1f3f6; color: var(--ink-2); border: 1px solid var(--line);
    margin-right: .35rem;
  }
  .pill-accent { background: var(--accent-wash); color: var(--accent); border-color: #dbe6ff; }
  .pill-warn { background: #fff7ed; color: #9a3412; border-color: #fed7aa; }

  .score {
    font-variant-numeric: tabular-nums; font-weight: 600; color: var(--accent);
    font-size: .82rem;
  }

  /* --- notices --- */
  .notice {
    border-radius: 12px; padding: .95rem 1.1rem; font-size: .87rem; line-height: 1.6;
    border: 1px solid var(--line); background: var(--paper); margin-bottom: 1rem;
  }
  .notice-scenario { background: #fffbeb; border-color: #fde68a; color: #78350f; }
  .notice-block { background: #fef2f2; border-color: #fecaca; color: #7f1d1d; }
  .notice-info { background: var(--accent-wash); border-color: #dbe6ff; color: #1e3a8a; }

  .stat-label {
    font-size: .68rem; letter-spacing: .13em; text-transform: uppercase;
    color: var(--muted); font-weight: 600;
  }
  .stat-value {
    font-size: 1.5rem; font-weight: 600; color: var(--ink);
    font-variant-numeric: tabular-nums; line-height: 1.2;
  }
  .stat-note { font-size: .74rem; color: var(--muted); }

  code, pre, .mono { font-family: 'SFMono-Regular', Consolas, monospace; font-size: .8rem; }

  section[data-testid="stSidebar"] { background: var(--paper); border-right: 1px solid var(--line); }
  section[data-testid="stSidebar"] .block-container { padding-top: 1.6rem; }

  .stButton>button {
    border-radius: 9px; border: 1px solid var(--line); font-weight: 500;
    background: var(--paper); color: var(--ink);
  }
  .stButton>button:hover { border-color: var(--accent); color: var(--accent); }

  div[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 10px; }
  footer, #MainMenu { visibility: hidden; }
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def lede(text: str) -> None:
    st.markdown(f'<p class="lede">{text}</p>', unsafe_allow_html=True)


def muted(text: str) -> None:
    st.markdown(f'<p class="muted">{text}</p>', unsafe_allow_html=True)


def rule() -> None:
    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)


def notice(text: str, kind: str = "info") -> None:
    st.markdown(f'<div class="notice notice-{kind}">{text}</div>', unsafe_allow_html=True)


def stat(label: str, value: str, note: str = "") -> None:
    st.markdown(
        f'<div class="stat-label">{label}</div>'
        f'<div class="stat-value">{value}</div>'
        f'<div class="stat-note">{note}</div>',
        unsafe_allow_html=True,
    )
