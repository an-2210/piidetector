"""Document privacy case-study workflow: P1 extraction, optional P2 OCR, P3 rules, P4 NER, P5 redaction."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import streamlit as st

from src.pipeline import extract_document
from src.detectors.pipeline import run_detectors_pipeline
from src.p5 import redact_blocks, build_exposure_report, check_llm_safety


def _safe_p3_export(report: Dict[str, Any]) -> Dict[str, Any]:
    """Export P3 metadata without raw detected values or surrounding context."""
    findings = []
    for item in report.get("findings", []):
        findings.append({
            "detector": item.get("detector"),
            "category": item.get("category"),
            "identifier_type": item.get("identifier_type"),
            "start_offset": item.get("start_offset"),
            "end_offset": item.get("end_offset"),
            "text_block_id": item.get("text_block_id"),
            "confidence": item.get("confidence"),
        })
    return {key: value for key, value in report.items() if key != "findings"} | {"findings": findings}


def _safe_p4_export(report: Any) -> Any:
    """Export P4 spans and diagnostics without names, raw spans, or identity records."""
    if not isinstance(report, dict):
        return report
    findings = []
    for item in report.get("findings", []):
        findings.append({
            "block_id": item.get("block_id"),
            "start": item.get("start"),
            "end": item.get("end"),
            "pii_type": item.get("pii_type"),
            "detector": item.get("detector"),
            "confidence": item.get("confidence"),
            "sources": item.get("sources", []),
            "identity_id": item.get("identity_id"),
        })
    return {
        "findings": findings,
        "warnings": report.get("warnings", []),
        "backends": report.get("backends", []),
        "counts": report.get("counts", {}),
        "conflict_count": len(report.get("conflicts", [])),
        "identity_count": len(report.get("identities", [])),
    }


st.set_page_config(
    page_title="Document Privacy | Case Study",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# White-and-blue visual system; scoped to Streamlit's rendered UI.
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');

    :root {
      --case-blue: #2563EB;
      --case-blue-dark: #1D4ED8;
      --case-ink: #10213A;
      --case-muted: #64748B;
      --case-line: #E2E8F0;
      --case-bg: #F5F8FC;
    }
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .stApp { background: var(--case-bg); color: var(--case-ink); }
    [data-testid="stHeader"] { background: rgba(245,248,252,0.88); }
    [data-testid="stMainBlockContainer"] { padding-top: 1.35rem; padding-bottom: 3rem; max-width: 1480px; }
    [data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid var(--case-line); }
    [data-testid="stSidebar"] > div:first-child { padding-top: 1.5rem; }
    h1, h2, h3 { font-family: 'Manrope', sans-serif !important; color: var(--case-ink); letter-spacing: -0.035em; }
    h1 { font-weight: 800 !important; }
    h2, h3 { font-weight: 750 !important; }
    p, label, li { color: #334155; }
    .case-brand {
      display: flex; align-items: center; gap: 12px; margin: 0 0 1.25rem 0;
    }
    .case-mark {
      width: 43px; height: 43px; border-radius: 13px; display: flex; align-items: center;
      justify-content: center; background: linear-gradient(145deg, #3B82F6, #1D4ED8);
      color: white; font-size: 23px; box-shadow: 0 7px 18px rgba(37,99,235,.22);
    }
    .case-wordmark { font-family: 'Manrope', sans-serif; font-size: 22px; line-height: 1.1; font-weight: 800; color: #10213A; letter-spacing: -.04em; }
    .case-wordmark span { color: #2563EB; }
    .optiv-eyebrow { color: #2563EB; font-size: 11px; font-weight: 800; letter-spacing: .15em; text-transform: uppercase; margin-bottom: 9px; }
    .optiv-hero {
      position: relative; overflow: hidden; padding: 39px 40px; border: 1px solid #D8E5F8; border-radius: 24px;
      background:
        radial-gradient(ellipse at 88% 20%, rgba(59,130,246,.22), transparent 25%),
        radial-gradient(ellipse at 100% 100%, rgba(147,197,253,.22), transparent 35%),
        linear-gradient(120deg, #FFFFFF 0%, #F8FBFF 55%, #EAF2FF 100%);
      box-shadow: 0 16px 45px rgba(30,64,175,.075); margin-bottom: 24px;
    }
    .optiv-hero:after {
      content: ""; position: absolute; right: -42px; top: -60px; width: 245px; height: 245px;
      border: 1px solid rgba(37,99,235,.12); border-radius: 50%;
      box-shadow: 0 0 0 22px rgba(37,99,235,.035), 0 0 0 46px rgba(37,99,235,.025);
      pointer-events: none;
    }
    .optiv-hero h1 { font-size: clamp(34px, 4vw, 54px); line-height: 1.06; margin: 0 0 15px 0; max-width: 760px; }
    .optiv-hero h1 span { color: #2563EB; }
    .optiv-hero p { color: #536780; max-width: 760px; font-size: 15px; line-height: 1.8; margin: 0; }
    .hero-meta { display:flex; flex-wrap:wrap; gap:8px; margin-top:22px; }
    .hero-meta span { padding:7px 10px; border:1px solid #D8E5F8; border-radius:8px; color:#3B5678; background:rgba(255,255,255,.72); font-size:11px; font-weight:700; }
    .optiv-chip {
      display: inline-flex; align-items: center; gap: 7px; padding: 6px 10px; margin-bottom: 15px;
      border-radius: 999px; background: #EAF2FF; color: #1D4ED8; font-size: 11px;
      font-weight: 800; letter-spacing: .07em; text-transform: uppercase;
      border: 1px solid #D4E4FF;
    }
    .optiv-chip-dot { width: 7px; height: 7px; background: #2563EB; border-radius: 50%; }
    .optiv-section-label { font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .13em; color: #64748B; margin: 1.4rem 0 .55rem; }
    .optiv-upload-note { font-size: 13px; color: #64748B; line-height: 1.6; }
    [data-testid="stFileUploader"] {
      background: white; border: 1px dashed #A9C4F5; border-radius: 16px; padding: 10px;
    }
    [data-testid="stFileUploader"]:hover { border-color: #2563EB; background: #FBFDFF; }
    [data-testid="stFileUploaderDropzone"] { background: #F8FBFF; border: 0; border-radius: 12px; }
    [data-testid="stFileUploaderDropzone"] button {
      border: 1px solid #C7D8F4 !important; background: white !important; color: #1D4ED8 !important;
      border-radius: 9px !important; font-weight: 700 !important;
    }
    .stButton > button, .stDownloadButton > button {
      border-radius: 10px !important; font-weight: 700 !important; min-height: 43px;
      transition: all .15s ease; border: 1px solid #D5DFEC;
    }
    .stButton > button[kind="primary"] {
      background: linear-gradient(135deg, #3478F6, #1D4ED8) !important; color: white !important;
      border: 1px solid #2563EB !important; box-shadow: 0 5px 12px rgba(37,99,235,.18);
    }
    .stButton > button[kind="primary"]:hover { background: #1D4ED8 !important; box-shadow: 0 7px 16px rgba(37,99,235,.24); transform: translateY(-1px); }
    .stDownloadButton > button { background: white !important; color: #1D4ED8 !important; border-color: #C7D8F4 !important; }
    .stDownloadButton > button:hover { background: #EFF6FF !important; border-color: #93B4F4 !important; }
    [data-testid="stMetric"] {
      background: white; border: 1px solid #E0E8F2; border-radius: 15px;
      padding: 17px 18px; box-shadow: 0 3px 12px rgba(15,42,80,.025);
    }
    [data-testid="stMetricLabel"] { color: #64748B !important; font-size: 12px !important; font-weight: 700 !important; }
    [data-testid="stMetricValue"] { color: #10213A !important; font-family: 'Manrope', sans-serif; font-weight: 800; }
    [data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid #DCE5F0; }
    [data-testid="stTabs"] button[data-baseweb="tab"] {
      border-radius: 9px 9px 0 0; padding: 11px 15px; color: #64748B; font-weight: 700;
    }
    [data-testid="stTabs"] button[aria-selected="true"] { color: #1D4ED8; background: #EAF2FF; }
    [data-testid="stTabs"] [data-baseweb="tab-highlight"] { background: #2563EB; height: 3px; }
    [data-testid="stExpander"] { background: white; border: 1px solid #E1E8F1; border-radius: 12px; overflow: hidden; }
    [data-testid="stAlert"] { border-radius: 12px; }
    [data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {
      background: white; border: 1px solid #D8E2EF; border-radius: 10px;
    }
    [data-testid="stJson"] { background: white; border: 1px solid #E2E8F0; border-radius: 12px; padding: 10px; }
    hr { border-color: #E2E8F0; }
    [data-testid="stMetric"] { transition: transform .16s ease, box-shadow .16s ease; }
    [data-testid="stMetric"]:hover { transform: translateY(-2px); box-shadow: 0 9px 22px rgba(30,64,175,.07); }
    [data-testid="stTabs"] [data-baseweb="tab"]:hover { color:#1D4ED8; }
    .optiv-footer { margin-top: 38px; padding-top: 17px; border-top: 1px solid #E2E8F0; color: #94A3B8; font-size: 11px; letter-spacing:.08em; }
    .stage-card { background:white; border:1px solid #E0E8F2; border-radius:14px; padding:15px; min-height:105px; }
    .stage-number { font-size:10px; color:#2563EB; letter-spacing:.12em; font-weight:800; }
    .stage-title { margin-top:8px; font-size:14px; font-weight:800; color:#10213A; }
    .stage-sub { margin-top:4px; color:#718198; font-size:11px; line-height:1.5; }
    .mini-status { display:inline-flex; align-items:center; gap:7px; border-radius:99px; padding:6px 10px; background:#ECFDF5; color:#047857; font-size:11px; font-weight:800; border:1px solid #BBF7D0; }
    @media (max-width: 760px) { .optiv-hero { padding: 25px 21px; } .optiv-hero:after { opacity:.35; } }
    @media (max-width: 760px) {
      [data-testid="stMainBlockContainer"] { padding: 1rem 1rem 2rem; }
      .optiv-hero { padding: 22px 20px; border-radius: 16px; }
      .optiv-hero h1 { font-size: 29px; }
    }

    .optiv-hero {
      display:grid; grid-template-columns:minmax(0,1.15fr) minmax(300px,.85fr);
      align-items:center; gap:18px; min-height:350px;
      padding:38px 42px;
      background:
        radial-gradient(ellipse at 78% 20%, rgba(59,130,246,.13), transparent 32%),
        linear-gradient(120deg,#FFFFFF 0%,#F8FBFF 54%,#EAF2FF 100%);
    }
    .hero-copy { position:relative; z-index:2; }
    .hero-art { position:relative; min-height:260px; display:flex; align-items:center; justify-content:center; }
    .hero-art svg { width:100%; max-width:430px; height:auto; overflow:visible; filter:drop-shadow(0 18px 25px rgba(37,99,235,.12)); }
    .optiv-hero h1 { font-size:clamp(37px,4.1vw,58px); line-height:1.02; max-width:640px; letter-spacing:-.055em; }
    .optiv-hero p { font-size:15px; max-width:590px; }
    .hero-kicker { display:flex; align-items:center; gap:8px; color:#2563EB; font-size:11px; font-weight:800; letter-spacing:.16em; text-transform:uppercase; margin-bottom:18px; }
    .hero-kicker:before { content:""; display:inline-block; width:24px; height:2px; background:#2563EB; }
    .hero-meta { margin-top:25px; gap:7px; }
    .hero-meta span { font-size:10px; letter-spacing:.04em; padding:8px 10px; box-shadow:0 2px 5px rgba(15,42,80,.025); }
    .hero-cta-note { margin-top:18px; color:#7A8AA1; font-size:11px; }
    .section-heading { display:flex; align-items:end; justify-content:space-between; gap:15px; margin:28px 0 13px; }
    .section-heading h3 { margin:0; font-size:19px; }
    .section-heading p { margin:0; font-size:12px; color:#7A8AA1; }
    .pipeline-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; margin:0 0 25px; }
    .pipeline-card { position:relative; background:rgba(255,255,255,.92); border:1px solid #E0E8F2; border-radius:14px; padding:15px 13px; min-height:123px; box-shadow:0 5px 16px rgba(15,42,80,.025); transition:all .18s ease; }
    .pipeline-card:hover { transform:translateY(-3px); border-color:#B8D0F8; box-shadow:0 12px 25px rgba(37,99,235,.08); }
    .pipeline-card .num { font-size:10px; font-weight:900; color:#2563EB; letter-spacing:.13em; }
    .pipeline-card .ico { width:32px; height:32px; display:flex; align-items:center; justify-content:center; background:linear-gradient(145deg,#EEF5FF,#DCEAFF); color:#2563EB; border-radius:10px; margin:10px 0 9px; font-size:17px; }
    .pipeline-card strong { display:block; color:#142743; font-size:12px; }
    .pipeline-card small { display:block; margin-top:5px; color:#7A8AA1; font-size:10px; line-height:1.4; }
    .micro-banner { display:flex; align-items:center; justify-content:space-between; gap:15px; padding:15px 18px; background:#10213A; border-radius:13px; color:#fff; margin:12px 0 22px; }
    .micro-banner strong { color:white; font-size:13px; }
    .micro-banner span { color:#C3D4ED; font-size:11px; }
    .micro-badge { border:1px solid rgba(191,219,254,.25); background:rgba(59,130,246,.15); color:#DBEAFE !important; padding:6px 9px; border-radius:7px; white-space:nowrap; }
    @media (max-width: 900px) {
      .optiv-hero { grid-template-columns:1fr; padding:29px 25px; }
      .hero-art { min-height:180px; }
      .hero-art svg { max-width:320px; }
      .pipeline-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
    }
    @media (max-width: 540px) {
      .pipeline-grid { grid-template-columns:1fr 1fr; }
      .optiv-hero h1 { font-size:35px; }
      .micro-banner { align-items:flex-start; flex-direction:column; }
    }


    .stApp { background:linear-gradient(145deg,#F9FBFF 0%,#F0F6FF 52%,#F8FAFD 100%) !important; }
    [data-testid="stMainBlockContainer"] { max-width:1500px !important; padding-top:1.1rem !important; }
    [data-testid="stSidebar"] { background:linear-gradient(180deg,#FFFFFF 0%,#F5F9FF 100%) !important; box-shadow:6px 0 28px rgba(26,65,124,.05); }
    [data-testid="stFileUploader"] { border:1px dashed #6599EC !important; background:linear-gradient(135deg,#FFFFFF,#EAF3FF) !important; border-radius:18px !important; box-shadow:0 9px 24px rgba(37,99,235,.055); }
    [data-testid="stFileUploaderDropzone"] { background:transparent !important; }
    [data-testid="stMetric"] { background:linear-gradient(150deg,#FFFFFF 0%,#F7FAFF 100%) !important; border:1px solid #D5E4F9 !important; border-top:3px solid #4B86EC !important; box-shadow:0 8px 22px rgba(24,63,130,.065) !important; }
    [data-testid="stMetricValue"] { color:#1749A5 !important; }
    .stButton > button[kind="primary"] { background:linear-gradient(120deg,#4A8DF8,#1D4ED8) !important; border:0 !important; box-shadow:0 8px 20px rgba(37,99,235,.26) !important; }
    .stButton > button[kind="primary"]:hover { box-shadow:0 12px 27px rgba(37,99,235,.32) !important; transform:translateY(-1px); }
    [data-testid="stTabs"] button[aria-selected="true"] { background:linear-gradient(180deg,#F3F8FF,#DCEAFF) !important; }
    @media (max-width: 850px) { [data-testid="stMainBlockContainer"] { padding-left:1rem !important;padding-right:1rem !important; } }

    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown('<div class="optiv-eyebrow">CASE STUDY / DOCUMENT PRIVACY</div>', unsafe_allow_html=True)
    st.markdown("### Analysis controls")
    st.caption("Choose which analysis stages to run on your document.")
    enable_ocr = st.toggle(
        "P2 · OCR for scanned pages",
        value=False,
        help="Requires the Tesseract system application to be installed.",
    )
    enable_ner = st.toggle(
        "P4 · Named entity recognition",
        value=True,
        help="Uses configured spaCy/Presidio backends when available.",
    )
    st.divider()
    st.markdown("**Pipeline**")
    st.markdown(
        """
        <div style="font-size:13px;line-height:2.05;color:#52627A">
          <div> <span style="color:#2563EB;font-weight:800">01</span> &nbsp; Text extraction</div>
          <div> <span style="color:#2563EB;font-weight:800">02</span> &nbsp; OCR enhancement</div>
          <div> <span style="color:#2563EB;font-weight:800">03</span> &nbsp; Rule-based detection</div>
          <div> <span style="color:#2563EB;font-weight:800">04</span> &nbsp; Entity recognition</div>
          <div> <span style="color:#2563EB;font-weight:800">05</span> &nbsp; Redaction &amp; safety</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()
    st.caption("Supported formats")
    st.markdown("`PDF`  `DOCX`  `PPTX`")
    st.caption("Privacy-first document analysis")

st.markdown(
    """
    <div style="position:relative;overflow:hidden;display:grid;grid-template-columns:minmax(0,1.12fr) minmax(280px,.88fr);align-items:center;gap:18px;min-height:365px;padding:42px 42px;border:1px solid #CFE0FA;border-radius:25px;background:radial-gradient(ellipse at 79% 18%,rgba(59,130,246,.24),transparent 30%),radial-gradient(ellipse at 98% 100%,rgba(96,165,250,.22),transparent 38%),linear-gradient(118deg,#FFFFFF 0%,#F6FAFF 48%,#DCEBFF 100%);box-shadow:0 20px 55px rgba(37,99,235,.12);margin-bottom:22px;">
      <div style="position:relative;z-index:2;">
        <div style="display:flex;align-items:center;gap:9px;color:#1D4ED8;font-size:11px;font-weight:900;letter-spacing:.16em;text-transform:uppercase;margin-bottom:20px;">
          <span style="display:inline-block;width:26px;height:2px;background:#2563EB;"></span> CADENCE CASE STUDY&nbsp; / &nbsp;DOCUMENT PRIVACY
        </div>
        <div style="font-family:Arial,sans-serif;font-size:clamp(38px,4.4vw,61px);font-weight:800;line-height:.99;letter-spacing:-.055em;color:#10213A;margin-bottom:20px;">
          Sensitive data,<br><span style="color:#2563EB;">under control.</span>
        </div>
        <div style="max-width:580px;color:#526782;font-size:15px;line-height:1.8;">
          Detect personal information across documents. Combine rule-based checks and named-entity recognition, then create redacted output for safer downstream use.
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:25px;">
          <span style="background:#FFFFFFD9;border:1px solid #D5E4FA;border-radius:7px;padding:8px 10px;color:#315274;font-size:10px;font-weight:800;letter-spacing:.04em;">01 &nbsp; EXTRACT</span>
          <span style="background:#FFFFFFD9;border:1px solid #D5E4FA;border-radius:7px;padding:8px 10px;color:#315274;font-size:10px;font-weight:800;letter-spacing:.04em;">02 &nbsp; DETECT</span>
          <span style="background:#FFFFFFD9;border:1px solid #D5E4FA;border-radius:7px;padding:8px 10px;color:#315274;font-size:10px;font-weight:800;letter-spacing:.04em;">03 &nbsp; FUSE</span>
          <span style="background:#FFFFFFD9;border:1px solid #D5E4FA;border-radius:7px;padding:8px 10px;color:#315274;font-size:10px;font-weight:800;letter-spacing:.04em;">04 &nbsp; REDACT</span>
        </div>
        <div style="margin-top:18px;font-size:10px;color:#7A8DA7;letter-spacing:.11em;font-weight:700;">PDF &nbsp;·&nbsp; DOCX &nbsp;·&nbsp; PPTX &nbsp;&nbsp; / &nbsp;&nbsp; OCR + RULES + NER</div>
      </div>
      <div style="position:relative;min-height:275px;display:flex;align-items:center;justify-content:center;">
        <svg viewBox="0 0 440 340" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:440px;height:auto;overflow:visible;filter:drop-shadow(0 18px 25px rgba(37,99,235,.15));">
          <defs>
            <linearGradient id="docblue" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#EAF2FF"/></linearGradient>
            <linearGradient id="shieldblue" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#60A5FA"/><stop offset="1" stop-color="#1D4ED8"/></linearGradient>
            <linearGradient id="scanbeam" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#60A5FA" stop-opacity="0"/><stop offset=".5" stop-color="#2563EB" stop-opacity=".95"/><stop offset="1" stop-color="#60A5FA" stop-opacity="0"/></linearGradient>
          </defs>
          <circle cx="242" cy="166" r="137" fill="#BFDBFE" opacity=".45"/>
          <circle cx="242" cy="166" r="117" fill="none" stroke="#93C5FD" stroke-dasharray="3 8" stroke-width="1.5"/>
          <circle cx="242" cy="166" r="93" fill="none" stroke="#FFFFFF" stroke-width="2" opacity=".9"/>
          <g transform="translate(93 37) rotate(-7 83 112)">
            <rect x="0" y="0" width="165" height="225" rx="15" fill="url(#docblue)" stroke="#C2D8F8" stroke-width="1.5"/>
            <path d="M118 0 L165 47 L118 47 Z" fill="#D9E8FF"/>
            <rect x="20" y="27" width="50" height="7" rx="3.5" fill="#2563EB"/>
            <rect x="20" y="44" width="93" height="4" rx="2" fill="#CBD9EC"/>
            <rect x="20" y="58" width="118" height="4" rx="2" fill="#CBD9EC"/>
            <rect x="20" y="72" width="104" height="4" rx="2" fill="#CBD9EC"/>
            <rect x="18" y="91" width="128" height="27" rx="6" fill="#FEE2E2" stroke="#FCA5A5"/>
            <rect x="25" y="101" width="80" height="7" rx="3.5" fill="#EF4444" opacity=".72"/>
            <rect x="20" y="130" width="115" height="4" rx="2" fill="#CBD9EC"/>
            <rect x="20" y="144" width="93" height="4" rx="2" fill="#CBD9EC"/>
            <rect x="18" y="160" width="128" height="27" rx="6" fill="#DBEAFE" stroke="#93C5FD"/>
            <rect x="25" y="170" width="66" height="7" rx="3.5" fill="#2563EB" opacity=".7"/>
            <rect x="20" y="199" width="76" height="4" rx="2" fill="#CBD9EC"/>
          </g>
          <g transform="translate(265 53)">
            <rect width="145" height="56" rx="12" fill="#FFFFFF" stroke="#D5E4FA"/>
            <circle cx="21" cy="28" r="10" fill="#DCFCE7"/>
            <path d="M16 28 l4 4 l7 -8" fill="none" stroke="#16A34A" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <text x="39" y="23" font-family="Arial,sans-serif" font-size="10" fill="#64748B">DETECTION</text>
            <text x="39" y="38" font-family="Arial,sans-serif" font-size="12" font-weight="700" fill="#10213A">PII identified</text>
          </g>
          <g transform="translate(249 139)">
            <path d="M0 -49 L44 -32 L40 9 Q34 39 0 57 Q-34 39 -40 9 L-44 -32 Z" fill="#BFDBFE" opacity=".6"/>
            <path d="M0 -41 L36 -27 L33 7 Q27 31 0 46 Q-27 31 -33 7 L-36 -27 Z" fill="url(#shieldblue)" stroke="#FFFFFF" stroke-width="2"/>
            <path d="M-15 1 L-4 12 L17 -12" fill="none" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
          </g>
          <rect x="75" y="184" width="295" height="4" rx="2" fill="url(#scanbeam)"/>
          <g transform="translate(280 232)">
            <rect width="125" height="43" rx="10" fill="#FFFFFF" stroke="#D5E4FA"/>
            <rect x="11" y="12" width="19" height="18" rx="5" fill="#DBEAFE"/>
            <path d="M16 18 h9 M16 23 h9" stroke="#2563EB" stroke-width="1.5" stroke-linecap="round"/>
            <text x="39" y="17" font-family="Arial,sans-serif" font-size="9" fill="#64748B">OUTPUT</text>
            <text x="39" y="30" font-family="Arial,sans-serif" font-size="11" font-weight="700" fill="#10213A">Redacted</text>
          </g>
          <circle cx="366" cy="144" r="5" fill="#60A5FA"/><circle cx="83" cy="121" r="4" fill="#2563EB"/><circle cx="331" cy="300" r="4" fill="#93C5FD"/>
        </svg>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div style="display:flex;justify-content:space-between;align-items:end;gap:12px;margin:28px 0 13px;">
      <div style="font-family:Arial,sans-serif;font-size:20px;font-weight:800;color:#10213A;">One workflow. Five protection stages.</div>
      <div style="font-size:12px;color:#7A8AA1;">From raw file to safer output</div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:0 0 22px;">
      <div style="background:#FFFFFF;border:1px solid #DCE7F5;border-radius:14px;padding:15px 13px;min-height:126px;box-shadow:0 7px 18px rgba(15,42,80,.04);"><div style="font-size:10px;font-weight:900;color:#2563EB;letter-spacing:.13em;">STAGE 01</div><div style="width:34px;height:34px;border-radius:10px;background:#EAF2FF;color:#2563EB;display:flex;align-items:center;justify-content:center;margin:10px 0;font-size:18px;">▤</div><strong style="display:block;color:#142743;font-size:13px;">Extract</strong><small style="display:block;margin-top:5px;color:#7A8AA1;font-size:10px;">Read document structure</small></div>
      <div style="background:#FFFFFF;border:1px solid #DCE7F5;border-radius:14px;padding:15px 13px;min-height:126px;box-shadow:0 7px 18px rgba(15,42,80,.04);"><div style="font-size:10px;font-weight:900;color:#2563EB;letter-spacing:.13em;">STAGE 02</div><div style="width:34px;height:34px;border-radius:10px;background:#EAF2FF;color:#2563EB;display:flex;align-items:center;justify-content:center;margin:10px 0;font-size:18px;">⌕</div><strong style="display:block;color:#142743;font-size:13px;">Enhance</strong><small style="display:block;margin-top:5px;color:#7A8AA1;font-size:10px;">Recover scanned text</small></div>
      <div style="background:#FFFFFF;border:1px solid #DCE7F5;border-radius:14px;padding:15px 13px;min-height:126px;box-shadow:0 7px 18px rgba(15,42,80,.04);"><div style="font-size:10px;font-weight:900;color:#2563EB;letter-spacing:.13em;">STAGE 03</div><div style="width:34px;height:34px;border-radius:10px;background:#EAF2FF;color:#2563EB;display:flex;align-items:center;justify-content:center;margin:10px 0;font-size:18px;">⌘</div><strong style="display:block;color:#142743;font-size:13px;">Detect</strong><small style="display:block;margin-top:5px;color:#7A8AA1;font-size:10px;">Find identifiers with rules</small></div>
      <div style="background:#FFFFFF;border:1px solid #DCE7F5;border-radius:14px;padding:15px 13px;min-height:126px;box-shadow:0 7px 18px rgba(15,42,80,.04);"><div style="font-size:10px;font-weight:900;color:#2563EB;letter-spacing:.13em;">STAGE 04</div><div style="width:34px;height:34px;border-radius:10px;background:#EAF2FF;color:#2563EB;display:flex;align-items:center;justify-content:center;margin:10px 0;font-size:18px;">◎</div><strong style="display:block;color:#142743;font-size:13px;">Understand</strong><small style="display:block;margin-top:5px;color:#7A8AA1;font-size:10px;">Recognize and fuse entities</small></div>
      <div style="background:#FFFFFF;border:1px solid #DCE7F5;border-radius:14px;padding:15px 13px;min-height:126px;box-shadow:0 7px 18px rgba(15,42,80,.04);"><div style="font-size:10px;font-weight:900;color:#2563EB;letter-spacing:.13em;">STAGE 05</div><div style="width:34px;height:34px;border-radius:10px;background:#EAF2FF;color:#2563EB;display:flex;align-items:center;justify-content:center;margin:10px 0;font-size:18px;">✓</div><strong style="display:block;color:#142743;font-size:13px;">Protect</strong><small style="display:block;margin-top:5px;color:#7A8AA1;font-size:10px;">Redact and review exposure</small></div>
    </div>
    <div style="display:flex;align-items:center;justify-content:space-between;gap:15px;padding:16px 19px;background:linear-gradient(110deg,#10213A,#173C72);border-radius:13px;color:#FFFFFF;margin:12px 0 22px;box-shadow:0 10px 22px rgba(16,33,58,.12);">
      <div><div style="font-size:13px;font-weight:800;color:#FFFFFF;">Built for responsible document handling</div><div style="font-size:11px;color:#C3D4ED;margin-top:4px;">Inspect findings, review redacted content, export analysis artifacts.</div></div>
      <div style="border:1px solid #3F5D85;background:#204577;color:#DBEAFE;padding:7px 10px;border-radius:7px;font-size:10px;font-weight:800;white-space:nowrap;">RULES + NER + OCR</div>
    </div>
    """,
    unsafe_allow_html=True,
)

left, right = st.columns([1.5, 1], gap="large")
with left:
    st.markdown('<div class="optiv-section-label">01 / SOURCE DOCUMENT</div>', unsafe_allow_html=True)
    upload = st.file_uploader(
        "Upload a PDF, Word document, or PowerPoint",
        type=["pdf", "docx", "pptx"],
        help="Choose a file to analyze through the five-stage privacy workflow.",
        label_visibility="collapsed",
    )
    st.markdown(
        '<div class="optiv-upload-note">PDF · DOCX · PPTX &nbsp; / &nbsp; Turn on OCR for image-based pages.</div>',
        unsafe_allow_html=True,
    )
    process = st.button(
        "Analyze document  →",
        type="primary",
        disabled=upload is None,
        use_container_width=True,
    )
with right:
    st.markdown('<div class="optiv-section-label">02 / ANALYSIS OUTPUTS</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div style="background:#fff;border:1px solid #E0E8F2;border-radius:16px;padding:19px 20px;min-height:180px">
          <div style="display:flex;gap:12px;margin-bottom:15px">
            <div style="width:35px;height:35px;border-radius:10px;background:#EAF2FF;color:#2563EB;display:flex;align-items:center;justify-content:center;font-weight:800">01</div>
            <div><div style="font-weight:750;color:#10213A">PII detection</div><div style="font-size:12px;color:#64748B;line-height:1.5">Rule-based matches and entity recognition.</div></div>
          </div>
          <div style="display:flex;gap:12px;margin-bottom:15px">
            <div style="width:35px;height:35px;border-radius:10px;background:#EAF2FF;color:#2563EB;display:flex;align-items:center;justify-content:center;font-weight:800">02</div>
            <div><div style="font-weight:750;color:#10213A">Redacted output</div><div style="font-size:12px;color:#64748B;line-height:1.5">Review protected text and exposure details.</div></div>
          </div>
          <div style="display:flex;gap:12px">
            <div style="width:35px;height:35px;border-radius:10px;background:#EAF2FF;color:#2563EB;display:flex;align-items:center;justify-content:center;font-weight:800">03</div>
            <div><div style="font-weight:750;color:#10213A">Exportable results</div><div style="font-size:12px;color:#64748B;line-height:1.5">Download redacted text and JSON metadata.</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if process and upload is not None:
    st.session_state.pop("optiv_result", None)
    suffix = Path(upload.name).suffix.lower()
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp.write(upload.getvalue())
            temp_path = Path(temp.name)

        with st.spinner("Extracting text and running detection stages…"):
            extraction = extract_document(str(temp_path), enable_ocr=enable_ocr, enable_ner=enable_ner)
            p3 = run_detectors_pipeline(blocks=extraction.blocks, source_file=upload.name)
            p4 = extraction.metadata.get("p4", {}) if isinstance(extraction.metadata, dict) else {}
            p4_findings = p4.get("findings", []) if isinstance(p4, dict) else []

            # P5 consumes P4's fused findings when available; otherwise use P3 as fallback.
            redaction_findings = list(p4_findings) if p4_findings else [
                {
                    "block_id": f.text_block_id,
                    "start": f.start_offset,
                    "end": f.end_offset,
                    "text": f.value,
                    "pii_type": {"EMP": "EMP_ID", "DIR": "DIR_ID", "MER-IN": "MER_IN_ID", "MER-PH": "MER_PH_ID"}.get(f.identifier_type, f.identifier_type),
                    "confidence": f.confidence,
                }
                for f in p3.findings
            ]
            redaction = redact_blocks(extraction.blocks, redaction_findings)
            exposure = build_exposure_report(redaction)

        st.session_state["optiv_result"] = {
            "filename": upload.name,
            "extraction": extraction.to_dict(),
            "p3": p3.to_dict(),
            "p4": p4,
            "redaction": redaction,
            "exposure": exposure,
        }
    except Exception as exc:
        st.error(f"Processing failed: {type(exc).__name__}: {exc}")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

result = st.session_state.get("optiv_result")
if result:
    st.markdown("---")
    st.markdown('<div class="optiv-eyebrow">Analysis complete</div>', unsafe_allow_html=True)
    st.subheader(f"Results · {result['filename']}")
    st.caption("Review each stage below. Detection counts are indicators for review, not a guarantee that every sensitive item has been found.")
    extraction = result["extraction"]
    p3 = result["p3"]
    p4 = result["p4"]
    redaction = result["redaction"]
    exposure = result["exposure"]

    cols = st.columns(5, gap="small")
    cols[0].metric("P1 · Text blocks", len(extraction.get("blocks", [])))
    p2_stats = extraction.get("metadata", {}).get("p2_ocr", {})
    cols[1].metric("P2 · OCR blocks", p2_stats.get("ocr_blocks_added", 0))
    cols[2].metric("P3 · Rule findings", p3.get("total_findings", len(p3.get("findings", []))))
    cols[3].metric("P4 · Fused findings", len(p4.get("findings", [])) if isinstance(p4, dict) else 0)
    cols[4].metric("P5 · Redactions", len(redaction.findings))

    tab1, tab_p2, tab2, tab3, tab4, tab5 = st.tabs(
        ["Overview", "P2 · OCR", "P3 · Rules", "P4 · NER", "P5 · Redaction", "Export"]
    )
    with tab1:
        if extraction.get("errors"):
            st.warning("Processing warnings/errors:")
            for error in extraction["errors"]:
                st.write(f"- {error}")
        st.markdown("#### Extraction summary")
        detail1, detail2 = st.columns(2)
        detail1.markdown(f"**Source type**  \n`{extraction.get('source_type', 'Unknown')}`")
        detail2.markdown(f"**Extracted blocks**  \n`{len(extraction.get('blocks', []))}`")
        p2_stats = extraction.get("metadata", {}).get("p2_ocr", {})
        if enable_ocr or p2_stats:
            st.caption(
                f"OCR engine: {p2_stats.get('engine', 'Not reported')} · "
                f"Images processed: {p2_stats.get('images_processed', 0)} · "
                f"Pages with OCR additions: {len(p2_stats.get('pages_with_new_ocr_blocks', []))}"
            )
        with st.expander("View extracted text blocks"):
            for i, block in enumerate(extraction.get("blocks", []), start=1):
                st.markdown(f"**Block {i} · {block.get('block_type', 'text')}**")
                st.text((block.get("text") or "")[:5000])
    with tab_p2:
        st.markdown("#### OCR extraction")
        if not enable_ocr and not p2_stats:
            st.info("P2 OCR was off for this run. Turn on 'P2 · OCR for scanned pages' in the sidebar and re-run.")
        else:
            st.write(f"**OCR engine:** {p2_stats.get('engine', 'Not reported')}")
            st.write(f"**Images processed:** {p2_stats.get('images_processed', 0)}")
            st.write(f"**OCR blocks added:** {p2_stats.get('ocr_blocks_added', 0)}")
            st.write(f"**Pages with OCR additions:** {p2_stats.get('pages_with_new_ocr_blocks', [])}")
            ocr_flags = extraction.get("ocr_needed_pages", [])
            st.write(f"**Pages flagged as needing OCR:** {len(ocr_flags)}")
            if ocr_flags:
                st.json(ocr_flags)
            ocr_blocks = [b for b in extraction.get("blocks", []) if (b.get("metadata") or {}).get("source") == "image_ocr"]
            if not ocr_blocks:
                st.info("OCR ran but produced no text blocks for this document.")
            for i, block in enumerate(ocr_blocks, start=1):
                confidence = (block.get("metadata") or {}).get("confidence")
                label = f"OCR block {i}" + (f" · confidence {confidence:.1f}" if isinstance(confidence, (int, float)) else "")
                st.markdown(f"**{label}**")
                st.text((block.get("text") or "")[:5000])
    with tab2:
        st.markdown("#### Rule-based detection")
        st.write(f"**Total P3 findings:** {p3.get('total_findings', 0)}")
        if not p3.get("findings"):
            st.info("P3 found no matches in the extracted text. Check the extracted blocks in Overview to confirm the document contains detectable identifiers.")
        st.json(p3.get("findings", []))
    with tab3:
        if isinstance(p4, dict):
            st.markdown("#### Named-entity recognition and fusion")
            backend_names = ", ".join(p4.get("backends", [])) or "None"
            st.write(f"**Backends loaded:** {backend_names}")
            st.write(f"**P4 counts:** {p4.get('counts', {})}")
            if not p4.get("findings"):
                st.info("No P4 findings were reported for this document.")
            st.json(p4.get("findings", []))
            for warning in p4.get("warnings", []):
                st.warning(warning)
        else:
            st.info("P4 was disabled for this run.")
    with tab4:
        st.markdown("#### Redaction review")
        safety = check_llm_safety(redaction)
        if safety["safe"]:
            st.success("LLM safety gate: PASS — no unresolved findings reported by P5.")
        else:
            st.error("LLM safety gate: BLOCKED — unresolved findings remain. Do not send this content to an LLM until reviewed.")
        st.markdown("**Exposure report**")
        st.json(exposure)
        st.markdown("**Redacted document text**")
        st.caption("Review the redacted output before sharing. Automated detection can miss sensitive content.")
        st.text_area("Redacted output", redaction.redacted_text, height=300, label_visibility="collapsed")
        st.download_button(
            "Download redacted text",
            redaction.redacted_text,
            file_name=f"{Path(result['filename']).stem}_redacted.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with tab5:
        st.markdown("#### Export analysis")
        st.caption("The export omits raw detected values and surrounding context from P3/P4 findings.")
        export_payload = {
            "source_file": result["filename"],
            "p1": {
                "source_type": extraction.get("source_type"),
                "total_blocks": len(extraction.get("blocks", [])),
                "ocr_needed_pages": extraction.get("ocr_needed_pages", []),
                "errors": extraction.get("errors", []),
            },
            "p3": _safe_p3_export(p3),
            "p4": _safe_p4_export(p4),
            "p5_exposure_report": exposure,
            "redacted_blocks": redaction.redacted_blocks,
        }
        st.download_button(
            "Download results JSON",
            json.dumps(export_payload, indent=2, ensure_ascii=False),
            file_name=f"{Path(result['filename']).stem}_case_study_results.json",
            mime="application/json",
            use_container_width=True,
        )
        st.caption("The results JSON includes redacted blocks and detection metadata. Raw detected values, surrounding context, and identity names are omitted from the export.")

st.markdown(
    '<div class="optiv-footer">DOCUMENT PRIVACY CASE STUDY &nbsp; • &nbsp; P1–P5 ANALYSIS</div>',
    unsafe_allow_html=True,
)
