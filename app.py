from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from prism.config import get_settings
from prism.pipeline import ExplainPipeline, OfflineDataUnavailable
from prism.pr_url import InvalidPullRequestURL
from prism.rendering.mermaid import render_mermaid, render_mermaid_html


DEMO_PR_URL = "https://github.com/acme-inc/checkout-platform/pull/42"


st.set_page_config(
    page_title="PRism — Pull requests, explained visually",
    page_icon="◆",
    layout="wide",
)

st.markdown(
    """
<style>
  .block-container { max-width: 1280px; padding-top: 2rem; }
  .prism-eyebrow { color: #6941c6; font-weight: 700; letter-spacing: .08em; font-size: .78rem; }
  .prism-title { font-size: 3rem; line-height: 1; margin: .35rem 0 .8rem; }
  .prism-subtitle { color: #475467; font-size: 1.15rem; max-width: 760px; }
  .evidence-card { border: 1px solid #e4e7ec; border-radius: 12px; padding: 12px 14px; margin: 8px 0; }
  .source-pill { color: #6941c6; font-size: .75rem; font-weight: 700; text-transform: uppercase; }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="prism-eyebrow">LIVING FEATURE MAPS</div>', unsafe_allow_html=True)
st.markdown('<h1 class="prism-title">PRism</h1>', unsafe_allow_html=True)
st.markdown(
    '<div class="prism-subtitle">Paste a pull request to see where it fits, how it works, '
    "and why it changed—without reading the implementation line by line.</div>",
    unsafe_allow_html=True,
)


@st.cache_resource
def build_pipeline() -> ExplainPipeline:
    return ExplainPipeline(get_settings())


settings = get_settings()

with st.form("explain-pr"):
    pr_url = st.text_input("GitHub pull-request URL", value=DEMO_PR_URL)
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        offline = st.checkbox(
            "Offline demo",
            value=settings.prism_offline_demo,
            help="Uses only cached or bundled data and does not fetch arbitrary PRs.",
        )
    with col2:
        refresh = st.checkbox(
            "Refresh live data",
            value=False,
            disabled=offline,
            help="Ignores the cached analysis and queries Greptile and Claude-Mem again.",
        )
    with col3:
        st.caption(
            "Cached data only" if offline else "Live: GitHub + Greptile + Codex CLI"
        )
        submitted = st.form_submit_button(
            "Explain this PR", type="primary", use_container_width=True
        )

if submitted:
    with st.spinner("Tracing the feature through code and memory…"):
        try:
            st.session_state["analysis"] = build_pipeline().explain(
                pr_url, offline=offline, refresh=refresh
            )
            st.session_state.pop("analysis_error", None)
        except (InvalidPullRequestURL, OfflineDataUnavailable) as exc:
            st.session_state["analysis_error"] = str(exc)
            st.session_state.pop("analysis", None)
        except Exception as exc:
            st.session_state["analysis_error"] = f"Analysis failed: {exc}"
            st.session_state.pop("analysis", None)

if error := st.session_state.get("analysis_error"):
    st.error(error)

if result := st.session_state.get("analysis"):
    diagram = result.diagram
    mermaid = render_mermaid(diagram)

    st.divider()
    repo_col, source_col = st.columns([4, 1])
    with repo_col:
        st.caption(
            f"{result.pull_request.reference.slug} · PR #{result.pull_request.reference.number}"
        )
        st.header(diagram.title)
    with source_col:
        st.metric("Analysis source", result.source.value.title())

    type_col, reason_col = st.columns([1, 3])
    with type_col:
        st.subheader(diagram.diagram_type.value.replace("_", " ").title())
    with reason_col:
        st.info(diagram.selection_reason)

    diagram_tab, explanation_tab, evidence_tab, memory_tab = st.tabs(
        ["Diagram", "Explanation", "Code evidence", "Memory"]
    )

    with diagram_tab:
        components.html(render_mermaid_html(mermaid), height=660, scrolling=True)
        with st.expander("View Mermaid source"):
            st.code(mermaid, language="mermaid")

    with explanation_tab:
        st.markdown(f"### What changed\n\n{diagram.summary}")
        changed = result.pull_request.changed_files
        if changed:
            additions = sum(item.additions for item in changed)
            deletions = sum(item.deletions for item in changed)
            st.caption(f"{len(changed)} changed files · +{additions} / -{deletions}")

    with evidence_tab:
        for item in diagram.evidence:
            location = item.file_path or item.observation_id or "Supporting context"
            link = f'<a href="{item.url}" target="_blank">Open source</a>' if item.url else ""
            st.markdown(
                f'<div class="evidence-card"><div class="source-pill">{item.source.value}</div>'
                f"<strong>{location}</strong><br>{item.description}<br>{link}</div>",
                unsafe_allow_html=True,
            )
            if item.excerpt:
                with st.expander(f"Excerpt: {location}"):
                    st.code(item.excerpt)

    with memory_tab:
        if diagram.memories:
            for memory in diagram.memories:
                with st.expander(memory.title):
                    st.write(memory.relevance)
                    if memory.narrative:
                        st.caption(memory.narrative)
                    st.caption(f"Observation {memory.observation_id}")
        else:
            memory_warning = next(
                (warning for warning in result.warnings if "Claude-Mem" in warning),
                "No relevant Claude-Mem observations were available for this analysis.",
            )
            st.info(memory_warning)

    download_col1, download_col2, link_col = st.columns([1, 1, 2])
    with download_col1:
        st.download_button(
            "Download Mermaid",
            data=mermaid + "\n",
            file_name=f"prism-pr-{result.pull_request.reference.number}.mmd",
            mime="text/plain",
            use_container_width=True,
        )
    with download_col2:
        st.download_button(
            "Download analysis",
            data=result.model_dump_json(indent=2),
            file_name=f"prism-pr-{result.pull_request.reference.number}.json",
            mime="application/json",
            use_container_width=True,
        )
    with link_col:
        st.link_button(
            "Open pull request",
            result.pull_request.html_url,
            use_container_width=True,
        )

    for warning in result.warnings:
        if "Claude-Mem" not in warning:
            st.warning(warning)
