"""
NetSage AI — Streamlit App
Cisco AICTE VIP Program 2026 | AI Track

An AI-assisted troubleshooter for Packet Tracer lab problems with mandatory
human review before any diagnosis is accepted.

Run:
    streamlit run app.py

API key resolution order (no key is ever shown in the UI):
    1. st.secrets["GROQ_API_KEY"]   <- used automatically on Streamlit Cloud
                                        once you set it in App Settings > Secrets
    2. environment variable GROQ_API_KEY   <- used automatically for local dev
    3. .streamlit/secrets.toml (local)     <- copy from secrets.toml.example

If none of these are found, the app shows a friendly setup notice instead of
degrading silently — but it never asks the end user to type a key.
"""

import json
import os
import re
from datetime import datetime

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

from scripts.rule_checker import run_all_checks

try:
    from groq import Groq
except ImportError:
    Groq = None

# --------------------------------------------------------------------------
# Paths & constants
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CASES_PATH = os.path.join(BASE_DIR, "data", "cases.csv")
RESULTS_PATH = os.path.join(BASE_DIR, "results", "results.csv")
LOG_PATH = os.path.join(BASE_DIR, "responsible_ai_log.md")
FALLBACK_MODELS = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-8b-instant"]

SYSTEM_PROMPT = """You are NetSage AI, a network troubleshooting assistant for Cisco-style
Packet Tracer labs. You are used by junior network engineers, and every
diagnosis you produce will be reviewed by a human before any action is taken.

Given a symptom description, a topology note, and Cisco IOS show-command
output, identify the most likely root cause.

Strict rules:
- Base your answer only on the evidence provided. Do not invent commands,
  interfaces, or output that were not given to you.
- Respond with ONLY a single JSON object, matching this schema exactly:
  {
    "root_cause": "...",
    "osi_layer": "...",
    "confidence": "low|medium|high",
    "evidence": "...",
    "next_command": "...",
    "fix_steps": ["...", "..."]
  }
- No text before or after the JSON. No markdown code fences.
- Keep "confidence" at "medium" or lower unless the evidence directly and
  unambiguously proves the root cause.
- fix_steps must be concrete, actionable IOS-style configuration steps.
"""

FEW_SHOT_EXAMPLES = """
### Example 1
Symptom: PC gets an IP but cannot reach server in VLAN 30; gateway ping works.
Show output:
R1# show ip route
C    192.168.30.0/24 is directly connected, GigabitEthernet0/0.30
R1# show access-lists
Extended IP access list SERVER_ACL
 10 deny ip 192.168.10.0 0.0.0.255 192.168.30.0 0.0.0.255
 20 permit ip any any

Expected output:
{"root_cause": "ACL SERVER_ACL denies traffic from the PC's subnet to the VLAN 30 server subnet", "osi_layer": "Layer 3/4", "confidence": "medium", "evidence": "SERVER_ACL line 10 explicitly denies IP from 192.168.10.0/24 to 192.168.30.0/24", "next_command": "show ip interface gi0/0.30 | include access list", "fix_steps": ["Confirm which interface SERVER_ACL is applied to and in which direction", "Add a permit line for the required traffic above the deny statement, or remove the deny line if unintended", "Re-apply and test connectivity with ping and the actual application traffic"]}

### Example 2
Symptom: Guest Wi-Fi can reach the internal server.
Show output:
R1# show access-lists
Extended IP access list GUEST_ISOLATION
 10 permit ip 192.168.50.0 0.0.0.255 any
R1# show run interface gi0/0.50 | include access
(no access-group applied)

Expected output:
{"root_cause": "Guest isolation ACL exists but is not applied to the guest VLAN interface, and it permits rather than denies traffic", "osi_layer": "Layer 3", "confidence": "high", "evidence": "GUEST_ISOLATION permits all traffic and no access-group is applied on gi0/0.50", "next_command": "show running-config interface gigabitEthernet0/0.50", "fix_steps": ["Rewrite GUEST_ISOLATION to deny traffic from 192.168.50.0/24 toward internal subnets and permit only internet-bound traffic", "Apply the ACL inbound on GigabitEthernet0/0.50 with 'ip access-group GUEST_ISOLATION in'", "Verify with ping/traceroute from a guest device to an internal host (should fail) and to the internet gateway (should succeed)"]}
"""

RESULTS_COLUMNS = [
    "case_id", "category", "severity", "expected_fault",
    "ai_root_cause", "ai_osi_layer", "ai_confidence", "ai_evidence",
    "ai_next_command", "ai_fix_steps", "ai_match_expected",
    "rule_flags",
    "review_status", "review_notes", "reviewed_at",
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def load_cases() -> pd.DataFrame:
    return pd.read_csv(CASES_PATH)


def load_results() -> pd.DataFrame:
    if os.path.exists(RESULTS_PATH):
        return pd.read_csv(RESULTS_PATH)
    return pd.DataFrame(columns=RESULTS_COLUMNS)


def save_results(df: pd.DataFrame):
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    df.to_csv(RESULTS_PATH, index=False)


def extract_json(text: str) -> dict:
    """Best-effort extraction of a JSON object from model output,
    even if it accidentally wraps it in code fences."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


def call_ai_diagnosis(api_key: str, case: dict) -> dict:
    """Try each candidate model in order; providers periodically retire/rename
    model IDs, so this keeps the app working without code changes."""
    user_content = f"""{FEW_SHOT_EXAMPLES}

Now diagnose this new case:

Symptom: {case['symptom']}
Topology note: {case['topology_note']}
Show output:
{case['show_output']}
"""
    client = Groq(api_key=api_key)

    # Reuse a previously confirmed-working model for this session if we have one
    candidates = [st.session_state["working_model"]] if "working_model" in st.session_state else []
    candidates += [m for m in FALLBACK_MODELS if m not in candidates]

    last_error = None
    for model_name in candidates:
        try:
            response = client.chat.completions.create(
                model=model_name,
                max_tokens=1000,
                temperature=0.3,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            )
            text = response.choices[0].message.content
            st.session_state["working_model"] = model_name
            st.session_state["active_model_name"] = model_name
            return extract_json(text)
        except Exception as e:
            last_error = e
            continue

    raise RuntimeError(
        f"All candidate Groq models failed (tried: {candidates}). "
        f"Last error: {last_error}. Check console.groq.com/docs/models for the "
        f"current model IDs and update FALLBACK_MODELS in app.py."
    )


def rule_flags_to_str(result) -> str:
    if not result.has_flags:
        return "No deterministic flags"
    return " | ".join(f"[{f.rule}] {f.message}" for f in result.flags)


# --------------------------------------------------------------------------
# Streamlit UI
def resolve_api_key() -> str | None:
    """Look for the key server-side only — never ask the end user to type one.
    Order: Streamlit Cloud secrets -> local secrets.toml -> environment variable.
    """
    try:
        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY")


st.set_page_config(page_title="NetSage AI", page_icon="🛰️", layout="wide")

# ---- Custom styling: dark control-room theme, badges, card containers ----
st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(180deg, #0b1220 0%, #0e1626 100%); }
    section[data-testid="stSidebar"] { background: #0a0f1a; border-right: 1px solid #1c2b45; }
    h1, h2, h3, h4 { color: #e8edf7 !important; }
    p, li, span, label, .stMarkdown { color: #c3ccdd; }
    .netsage-hero {
        padding: 1.4rem 1.6rem; border-radius: 14px; margin-bottom: 1.2rem;
        background: linear-gradient(120deg, #10213f 0%, #142a52 60%, #0f1d3a 100%);
        border: 1px solid #24406e;
    }
    .netsage-hero h1 { margin: 0; font-size: 1.65rem; }
    .netsage-hero p { margin: 0.3rem 0 0 0; color: #93a5c9; font-size: 0.92rem; }
    .status-pill {
        display: inline-block; padding: 3px 12px; border-radius: 999px;
        font-size: 0.78rem; font-weight: 600; letter-spacing: .02em;
    }
    .status-ok { background: #12351f; color: #4ade80; border: 1px solid #1f5c33; }
    .status-off { background: #3a1414; color: #f87171; border: 1px solid #6b1f1f; }
    .badge {
        display: inline-block; padding: 2px 10px; border-radius: 6px;
        font-size: 0.76rem; font-weight: 600; margin-right: 4px;
    }
    .badge-high { background: #3a1414; color: #fca5a5; }
    .badge-medium { background: #402a0f; color: #fbbf24; }
    .badge-low { background: #10321f; color: #6ee7b7; }
    .conf-high { color: #4ade80; font-weight: 600; }
    .conf-medium { color: #fbbf24; font-weight: 600; }
    .conf-low { color: #f87171; font-weight: 600; }
    div[data-testid="stMetric"] {
        background: #101a30; border: 1px solid #1e2f4f; border-radius: 12px; padding: 0.8rem 1rem;
    }
    .stButton>button {
        border-radius: 8px; border: 1px solid #2a4470; font-weight: 600;
    }
    .stButton>button[kind="primary"] {
        background: linear-gradient(90deg,#2563eb,#3b82f6); border: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="netsage-hero">
        <h1>🛰️ NetSage AI</h1>
        <p>AI-assisted troubleshooting for Cisco Packet Tracer labs · Human review required on every case</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Resolve the API key entirely server-side — no input box, ever
groq_api_key = resolve_api_key()

model = None
if groq_api_key and Groq is not None:
    model = True  # key present — actual model resolution happens per-call with fallback

with st.sidebar:
    st.markdown("### Navigation")
    page = st.radio("Go to", ["🔍 Diagnose Cases", "📊 Dashboard", "🧾 Responsible AI Log"], label_visibility="collapsed")
    st.divider()
    st.markdown("### AI Engine Status")
    if model is not None:
        st.markdown('<span class="status-pill status-ok">● Connected</span>', unsafe_allow_html=True)
        st.caption(f"Model: {st.session_state.get('active_model_name', FALLBACK_MODELS[0])}")
    else:
        st.markdown('<span class="status-pill status-off">● Not configured</span>', unsafe_allow_html=True)
        st.caption(
            "Ask the project owner to set `GROQ_API_KEY` in "
            "**App settings → Secrets** (Streamlit Cloud) or a local "
            "`.streamlit/secrets.toml`. No key is ever entered here."
        )
    st.divider()
    st.caption("Cisco AICTE VIP Program 2026 — AI Track\nProject: NetSage AI")

if not os.path.exists(CASES_PATH):
    st.error(f"cases.csv not found at {CASES_PATH}. Run `python scripts/generate_cases.py` first.")
    st.stop()

cases_df = load_cases()
results_df = load_results()

# --------------------------------------------------------------------------
# Page: Diagnose Cases
# --------------------------------------------------------------------------
if page == "🔍 Diagnose Cases":
    st.subheader("Case Browser & AI Diagnosis")

    col_filter1, col_filter2 = st.columns([1, 3])
    with col_filter1:
        category_filter = st.selectbox("Filter by category", ["All"] + sorted(cases_df["category"].unique().tolist()))

    filtered = cases_df if category_filter == "All" else cases_df[cases_df["category"] == category_filter]

    case_id = st.selectbox("Select a case", filtered["case_id"].tolist())
    case = cases_df[cases_df["case_id"] == case_id].iloc[0].to_dict()

    sev_class = {"High": "badge-high", "Medium": "badge-medium", "Low": "badge-low"}.get(case["severity"], "badge-medium")
    st.markdown(
        f"### {case['case_id']} — {case['category']} "
        f"<span class='badge {sev_class}'>{case['severity']}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(f"**Symptom:** {case['symptom']}")
    st.markdown(f"**Topology note:** {case['topology_note']}")
    with st.expander("📟 Show-command output (evidence)", expanded=True):
        st.code(case["show_output"], language="text")

    already_done = not results_df[results_df["case_id"] == case_id].empty
    existing_row = results_df[results_df["case_id"] == case_id].iloc[0].to_dict() if already_done else None

    run_col, _ = st.columns([1, 3])
    with run_col:
        run_clicked = st.button("▶️ Run AI Diagnosis + Rule Checker", type="primary", use_container_width=True)

    if run_clicked:
        if model is None:
            st.error(
                "AI engine is not connected. This is a backend configuration issue — "
                "the project owner needs to set `GROQ_API_KEY` in Streamlit Cloud secrets."
            )
        else:
            with st.spinner("Calling NetSage AI and running deterministic checks..."):
                try:
                    ai_result = call_ai_diagnosis(groq_api_key, case)
                except Exception as e:
                    st.error(f"AI call failed: {e}")
                    ai_result = None

                rule_result = run_all_checks(case)

            if ai_result:
                match = ai_result.get("root_cause", "").strip().lower() in case["expected_fault"].strip().lower() \
                    or case["expected_fault"].strip().lower() in ai_result.get("root_cause", "").strip().lower()

                st.session_state["last_ai_result"] = ai_result
                st.session_state["last_rule_result"] = rule_result
                st.session_state["last_case_id"] = case_id
                st.session_state["last_match"] = match

    # Display AI + rule checker results if available for this case
    if st.session_state.get("last_case_id") == case_id and "last_ai_result" in st.session_state:
        ai_result = st.session_state["last_ai_result"]
        rule_result = st.session_state["last_rule_result"]
        match = st.session_state["last_match"]

        st.markdown("---")
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("#### 🤖 AI Diagnosis")
            conf = str(ai_result.get("confidence", "")).lower()
            conf_class = {"low": "conf-low", "medium": "conf-medium", "high": "conf-high"}.get(conf, "")
            st.markdown(f"**Root cause:** {ai_result.get('root_cause')}")
            st.markdown(f"**OSI layer:** {ai_result.get('osi_layer')}")
            st.markdown(f"**Confidence:** <span class='{conf_class}'>{conf}</span>", unsafe_allow_html=True)
            st.markdown(f"**Evidence cited:** {ai_result.get('evidence')}")
            st.markdown(f"**Next command:** `{ai_result.get('next_command')}`")
            st.markdown("**Fix steps:**")
            for step in ai_result.get("fix_steps", []):
                st.markdown(f"- {step}")
            if match:
                st.success("✅ AI root cause appears consistent with expected fault")
            else:
                st.warning("⚠️ AI root cause may NOT match expected fault — review carefully")

        with c2:
            st.markdown("#### 🧮 Deterministic Rule Checker")
            if rule_result.has_flags:
                for flag in rule_result.flags:
                    st.markdown(f"- **[{flag.rule}]** {flag.message}")
            else:
                st.info("No deterministic rule flags triggered for this case.")
            st.markdown("---")
            st.markdown(f"**Ground truth (expected fault):** {case['expected_fault']}")

        st.markdown("---")
        st.markdown("#### 👤 Human Review (required)")
        review_status = st.radio("Reviewer decision", ["Accepted", "Edited", "Rejected"], horizontal=True, key=f"status_{case_id}")
        review_notes = st.text_area(
            "Reviewer notes (required if Edited or Rejected — explain what was wrong)",
            key=f"notes_{case_id}",
            placeholder="e.g. AI said DHCP exhaustion, but evidence actually shows a missing ip helper-address on the sub-interface.",
        )

        if st.button("💾 Save Review", key=f"save_{case_id}"):
            if review_status in ("Edited", "Rejected") and not review_notes.strip():
                st.error("Please explain why in the notes field before saving an Edited/Rejected review.")
            else:
                new_row = {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "severity": case["severity"],
                    "expected_fault": case["expected_fault"],
                    "ai_root_cause": ai_result.get("root_cause"),
                    "ai_osi_layer": ai_result.get("osi_layer"),
                    "ai_confidence": ai_result.get("confidence"),
                    "ai_evidence": ai_result.get("evidence"),
                    "ai_next_command": ai_result.get("next_command"),
                    "ai_fix_steps": " | ".join(ai_result.get("fix_steps", [])),
                    "ai_match_expected": match,
                    "rule_flags": rule_flags_to_str(rule_result),
                    "review_status": review_status,
                    "review_notes": review_notes,
                    "reviewed_at": datetime.now().isoformat(timespec="seconds"),
                }
                results_df = results_df[results_df["case_id"] != case_id]
                results_df = pd.concat([results_df, pd.DataFrame([new_row])], ignore_index=True)
                save_results(results_df)
                st.success(f"Review saved for {case_id}. Go to Dashboard or Responsible AI Log to see it reflected.")

    elif already_done:
        st.info(f"This case already has a saved review: **{existing_row['review_status']}**. Run diagnosis again to update it.")

# --------------------------------------------------------------------------
# Page: Dashboard
# --------------------------------------------------------------------------
elif page == "📊 Dashboard":
    st.subheader("📊 Review Dashboard")
    results_df = load_results()

    if results_df.empty:
        st.info("No reviewed cases yet. Go to 'Diagnose Cases', run diagnoses, and save reviews first.")
    else:
        total = len(results_df)
        accepted = (results_df["review_status"] == "Accepted").sum()
        edited = (results_df["review_status"] == "Edited").sum()
        rejected = (results_df["review_status"] == "Rejected").sum()
        agreement_rate = round(100 * accepted / total, 1) if total else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Reviewed", total)
        m2.metric("Accepted", accepted)
        m3.metric("Edited", edited)
        m4.metric("Rejected", rejected)

        st.metric("AI ↔ Human Agreement Rate", f"{agreement_rate}%")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Cases by Fault Category**")
            fig1, ax1 = plt.subplots()
            results_df["category"].value_counts().plot(kind="bar", ax=ax1, color="#4C72B0")
            ax1.set_ylabel("Count")
            ax1.set_xlabel("")
            st.pyplot(fig1)

        with col2:
            st.markdown("**Review Outcome Split**")
            fig2, ax2 = plt.subplots()
            results_df["review_status"].value_counts().plot(
                kind="pie", ax=ax2, autopct="%1.0f%%", ylabel="", colors=["#55a868", "#dd8452", "#c44e52"]
            )
            st.pyplot(fig2)

        col3, col4 = st.columns(2)
        with col3:
            st.markdown("**Severity Distribution**")
            fig3, ax3 = plt.subplots()
            results_df["severity"].value_counts().plot(kind="bar", ax=ax3, color="#8172B2")
            ax3.set_ylabel("Count")
            st.pyplot(fig3)

        with col4:
            st.markdown("**AI Root Cause vs Expected Fault Match**")
            fig4, ax4 = plt.subplots()
            results_df["ai_match_expected"].value_counts().plot(
                kind="pie", ax=ax4, autopct="%1.0f%%", ylabel="", colors=["#55a868", "#c44e52"]
            )
            st.pyplot(fig4)

        st.markdown("---")
        st.markdown("**Full results table**")
        st.dataframe(results_df, use_container_width=True)

        csv_bytes = results_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download results.csv", csv_bytes, "results.csv", "text/csv")

# --------------------------------------------------------------------------
# Page: Responsible AI Log
# --------------------------------------------------------------------------
elif page == "🧾 Responsible AI Log":
    st.subheader("🧾 Responsible AI Log")
    st.caption("Documented cases where a human reviewer corrected or rejected the AI's diagnosis.")

    results_df = load_results()
    corrected = results_df[results_df["review_status"].isin(["Edited", "Rejected"])] if not results_df.empty else pd.DataFrame()

    if corrected.empty:
        st.info("No Edited/Rejected cases logged yet. This section needs at least 5 for submission.")
    else:
        st.markdown(f"**{len(corrected)} case(s) logged** (minimum 5 required for submission)")
        for _, row in corrected.iterrows():
            with st.expander(f"{row['case_id']} — {row['category']} — {row['review_status']}"):
                st.markdown(f"**AI said:** {row['ai_root_cause']}")
                st.markdown(f"**Expected fault:** {row['expected_fault']}")
                st.markdown(f"**Reviewer notes:** {row['review_notes']}")
                st.markdown(f"**Reviewed at:** {row['reviewed_at']}")

        if st.button("📝 Export to responsible_ai_log.md"):
            lines = [
                "# Responsible AI Log — NetSage AI\n",
                "Cases where the AI's diagnosis was corrected or rejected by a human reviewer.\n",
                f"_Generated: {datetime.now().isoformat(timespec='seconds')}_\n",
                "---\n",
            ]
            for _, row in corrected.iterrows():
                lines.append(f"## {row['case_id']} — {row['category']} ({row['review_status']})\n")
                lines.append(f"- **AI diagnosis:** {row['ai_root_cause']}")
                lines.append(f"- **Expected fault (ground truth):** {row['expected_fault']}")
                lines.append(f"- **Reviewer notes:** {row['review_notes']}")
                lines.append(f"- **Reviewed at:** {row['reviewed_at']}\n")
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            st.success(f"Exported to {LOG_PATH}")
