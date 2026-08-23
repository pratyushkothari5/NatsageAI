# Project Summary Document

**Cisco AICTE VIP Program 2026 — AI Track**

- **Name:** [Your Name]
- **College Name:** [Your College]
- **Technology Track:** AI
- **AICTE Number:** [Your AICTE Number]
- **Team Members:** [List all group members]
- **File naming for submission:** `Name-CollegeName-AI`

---

## 1. Project Title
NetSage AI — Build an AI Troubleshooting Helper with Human Review

## 2. Problem Statement (brief)
Junior network engineers can operate individual Cisco commands but often
struggle to connect a symptom to its true root cause. This project builds an
AI-assisted troubleshooting tool for Cisco-style lab networks that reads
symptoms and `show`-command output, suggests a likely fault, OSI layer, and
fix — with a mandatory human review step before any diagnosis is accepted.

## 3. My Individual Contribution
[Describe specifically what YOU worked on — be precise. Examples below,
replace with your actual work:]

- [ ] Designed and populated the case dataset (`data/cases.csv`) — specify
      how many cases / which fault categories you authored
- [ ] Wrote/refined the AI prompt library (`prompts/diagnose_prompt.md`) —
      describe the schema design and few-shot examples you created
- [ ] Built the deterministic rule checker (`scripts/rule_checker.py`) —
      list which specific checks you implemented
- [ ] Built the Streamlit application (`app.py`) — describe which pages/
      features (Diagnose Cases / Dashboard / Responsible AI Log)
- [ ] Ran the AI diagnosis across cases and performed human review —
      state how many cases you personally reviewed and your Accept/
      Edit/Reject decisions
- [ ] Documented the Responsible AI log — describe the corrected cases you
      analyzed and why the AI was wrong
- [ ] Built the Packet Tracer topology (`.pkt` file) and captured the
      real `show`-command evidence used in the dataset
- [ ] Recorded/edited the demo video

## 4. Technology Stack Used
- Python 3, Streamlit, Anthropic Claude API (`anthropic` SDK), pandas,
  matplotlib, Cisco Packet Tracer

## 5. Key Results
- Total cases in dataset: 32
- Fault categories covered: VLAN, Gateway, DHCP, DNS, Routing, ACL, NAT,
  Wireless
- AI ↔ Human agreement rate achieved: [fill in from your Dashboard, e.g. 78%]
- Number of cases where AI was corrected (Edited/Rejected): [fill in, ≥5]

## 6. Responsible AI / Safety Rule Implementation
Explain, in your own words, how the "human review" safety rule was enforced
in your build (e.g., the app requires a reviewer decision + notes before a
diagnosis is saved as final; nothing is auto-applied to a device).

## 7. Challenges Faced & How I Solved Them
[Write 3–5 sentences on real challenges — e.g., getting the AI to stick to
strict JSON output, designing realistic show-command evidence, deciding on
deterministic rule thresholds, etc.]

## 8. What I Learned
[2–4 sentences — technical and/or process learnings]

## 9. Links
- GitHub Repository: [your repo URL]
- Demo Video: [your video URL, e.g. YouTube/Drive link]
- Packet Tracer file: `packet_tracer/netsage_topology.pkt` (submitted separately per group)

---
*Submit this document individually as `.docx` or `.pdf`, named
`YourName-CollegeName-AI`, via the official submission Google Form, along
with your course certificate and the group's `.pkt` file.*
