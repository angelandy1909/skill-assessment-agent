import os
import json
import re
import tempfile
import streamlit as st
from pypdf import PdfReader
from groq import Groq

st.set_page_config(page_title="JD Skill Analyzer", layout="wide")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not GROQ_API_KEY:
    st.warning("Add GROQ_API_KEY in your Hugging Face Space secrets.")

client = Groq(api_key=GROQ_API_KEY)

def extract_text_from_pdf(uploaded_file):
    if uploaded_file is None:
        return ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getvalue())
        path = tmp.name
    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    try:
        os.remove(path)
    except:
        pass
    return text.strip()

def safe_json_from_text(text):
    text = text.strip()
    try:
        return json.loads(text)
    except:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return None

def ask_groq(prompt):
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": "You are a helpful assistant that returns only valid JSON when asked."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    return response.choices[0].message.content

def analyze_job_description(jd_text):
    prompt = f"""
You are an expert job description analyzer.

Return ONLY valid JSON with this schema:
{{
  "company_context": {{
    "sector": "",
    "company_stage": "",
    "culture_signals": [],
    "work_style": [],
    "business_context": ""
  }},
  "ability_skills": [
    {{
      "skill": "",
      "priority": "high|medium|low",
      "evidence": ""
    }}
  ],
  "personality_skills": [
    {{
      "skill": "",
      "priority": "high|medium|low",
      "evidence": ""
    }}
  ],
  "role_summary": "",
  "top_keywords": []
}}

Rules:
- Ability skills are technical, task-based, or measurable capabilities.
- Personality skills are behavioral traits, communication style, collaboration style, or working preferences.
- Infer company sector, culture, and work style from the text.
- Do not include duplicate skills.
- Do not add explanations outside JSON.

Job description:
{jd_text}
"""
    response_text = ask_groq(prompt)
    parsed = safe_json_from_text(response_text)
    if parsed:
        return parsed
    return {
        "company_context": {"sector": "", "company_stage": "", "culture_signals": [], "work_style": [], "business_context": ""},
        "ability_skills": [],
        "personality_skills": [],
        "role_summary": "",
        "top_keywords": []
    }

def analyze_resume(resume_text):
    prompt = f"""
You are a resume analyst.

Return ONLY valid JSON with this schema:
{{
  "skills": [],
  "tools": [],
  "experience_level": "",
  "domains": [],
  "strengths": [],
  "behavioral_signals": []
}}

Resume:
{resume_text}
"""
    response_text = ask_groq(prompt)
    parsed = safe_json_from_text(response_text)
    if parsed:
        return parsed
    return {
        "skills": [],
        "tools": [],
        "experience_level": "",
        "domains": [],
        "strengths": [],
        "behavioral_signals": []
    }

def score_match(jd_data, resume_data):
    jd_ability = [x["skill"].lower() for x in jd_data.get("ability_skills", [])]
    jd_personality = [x["skill"].lower() for x in jd_data.get("personality_skills", [])]
    resume_skills = [x.lower() for x in resume_data.get("skills", []) + resume_data.get("tools", []) + resume_data.get("strengths", []) + resume_data.get("behavioral_signals", [])]

    ability_hits = [s for s in jd_ability if any(s in r or r in s for r in resume_skills)]
    personality_hits = [s for s in jd_personality if any(s in r or r in s for r in resume_skills)]

    ability_score = int((len(ability_hits) / max(len(jd_ability), 1)) * 100)
    personality_score = int((len(personality_hits) / max(len(jd_personality), 1)) * 100)
    overall_score = int((ability_score * 0.7) + (personality_score * 0.3))

    missing_ability = [s for s in jd_ability if s not in ability_hits]
    missing_personality = [s for s in jd_personality if s not in personality_hits]

    return {
        "ability_score": ability_score,
        "personality_score": personality_score,
        "overall_score": overall_score,
        "matched_ability": ability_hits,
        "matched_personality": personality_hits,
        "missing_ability": missing_ability,
        "missing_personality": missing_personality
    }

def generate_assessment_questions(jd_data, score_data):
    focus_skills = score_data["missing_ability"][:3] + score_data["missing_personality"][:2]
    if not focus_skills:
        focus_skills = [x["skill"] for x in jd_data.get("ability_skills", [])[:3]]

    prompt = f"""
You are a conversational skill assessor.

Create 1 practical question for each skill below.
Return ONLY valid JSON in this format:
{{
  "questions": [
    {{
      "skill": "",
      "category": "ability|personality",
      "question": "",
      "what_good_looks_like": ""
    }}
  ]
}}

Skills:
{json.dumps(focus_skills, indent=2)}
"""
    response_text = ask_groq(prompt)
    parsed = safe_json_from_text(response_text)
    if parsed:
        return parsed

    fallback_questions = []
    for skill in focus_skills:
        fallback_questions.append({
            "skill": skill,
            "category": "ability",
            "question": f"Tell me about your experience with {skill}. Give one real example.",
            "what_good_looks_like": "Clear example, specific impact, and correct terminology."
        })
    return {"questions": fallback_questions}

def generate_learning_plan(jd_data, score_data, resume_data):
    missing_ability = score_data.get("missing_ability", [])
    context = jd_data.get("company_context", {})
    sector = context.get("sector", "")
    culture = ", ".join(context.get("culture_signals", []))
    work_style = ", ".join(context.get("work_style", []))

    prompt = f"""
You are a career learning planner.

Create a personalized learning plan focused on adjacent skills the candidate can realistically acquire.
Return ONLY valid JSON with this schema:
{{
  "plan_summary": "",
  "priority_skills": [
    {{
      "skill": "",
      "why_this_first": "",
      "estimated_time_hours": 0,
      "resources": [
        {{
          "title": "",
          "type": "",
          "url": ""
        }}
      ]
    }}
  ],
  "4_week_plan": [
    {{
      "week": 1,
      "focus": "",
      "outcomes": []
    }}
  ],
  "strategy": ""
}}

Job sector: {sector}
Culture signals: {culture}
Work style: {work_style}

Missing ability skills:
{json.dumps(missing_ability, indent=2)}

Resume strengths:
{json.dumps(resume_data.get("strengths", []), indent=2)}
"""
    response_text = ask_groq(prompt)
    parsed = safe_json_from_text(response_text)
    if parsed:
        return parsed

    fallback = {
        "plan_summary": "Focus on the highest-priority missing skills and build evidence through small projects.",
        "priority_skills": [],
        "4_week_plan": [],
        "strategy": "Start with the closest adjacent skill, then expand to the full stack."
    }
    for s in missing_ability[:3]:
        fallback["priority_skills"].append({
            "skill": s,
            "why_this_first": "It is a direct gap in the JD.",
            "estimated_time_hours": 10,
            "resources": []
        })
    return fallback

def generate_summary(jd_data, resume_data, score_data):
    jd_company = jd_data.get("company_context", {})
    prompt = f"""
Write a concise paragraph summary for a candidate evaluation.

Use the following information:
- Job role summary: {jd_data.get("role_summary", "")}
- Sector: {jd_company.get("sector", "")}
- Culture signals: {jd_company.get("culture_signals", [])}
- Work style: {jd_company.get("work_style", [])}
- Missing ability skills: {score_data.get("missing_ability", [])}
- Missing personality skills: {score_data.get("missing_personality", [])}
- Candidate strengths: {resume_data.get("strengths", [])}
- Candidate behavioral signals: {resume_data.get("behavioral_signals", [])}

Return 2 short paragraphs:
1. Explain what key skills the candidate lacks.
2. Explain whether this organization is a good fit or not based on personality and work-style alignment.

Be balanced, direct, and practical. Do not use bullet points.
"""
    return ask_groq(prompt)

st.title("AI-Powered Skill Assessment & Personalized Learning Plan")
st.caption("Upload a job description and a resume to analyze fit, skill gaps, and a realistic learning path.")

col1, col2 = st.columns(2)
with col1:
    jd_file = st.file_uploader("Upload Job Description PDF", type=["pdf"])
    jd_text_manual = st.text_area("Or paste Job Description text", height=220)
with col2:
    resume_file = st.file_uploader("Upload Resume PDF", type=["pdf"])
    resume_text_manual = st.text_area("Or paste Resume text", height=220)

run = st.button("Analyze")

if run:
    jd_text = extract_text_from_pdf(jd_file) if jd_file else jd_text_manual
    resume_text = extract_text_from_pdf(resume_file) if resume_file else resume_text_manual

    if not jd_text.strip() or not resume_text.strip():
        st.error("Please provide both a job description and a resume.")
        st.stop()

    with st.spinner("Analyzing job description..."):
        jd_data = analyze_job_description(jd_text)

    with st.spinner("Analyzing resume..."):
        resume_data = analyze_resume(resume_text)

    with st.spinner("Scoring fit..."):
        score_data = score_match(jd_data, resume_data)

    with st.spinner("Creating assessment questions..."):
        questions_data = generate_assessment_questions(jd_data, score_data)

    with st.spinner("Creating narrative summary..."):
        narrative_summary = generate_summary(jd_data, resume_data, score_data)

    with st.spinner("Creating learning plan..."):
        learning_plan = generate_learning_plan(jd_data, score_data, resume_data)

    st.subheader("Score Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("Overall Fit", f"{score_data['overall_score']}%")
    c2.metric("Ability Fit", f"{score_data['ability_score']}%")
    c3.metric("Personality Fit", f"{score_data['personality_score']}%")

    st.subheader("Summary")
    st.write(narrative_summary)

    st.subheader("Job Description Understanding")
    st.json(jd_data)

    st.subheader("Resume Profile")
    st.json(resume_data)

    st.subheader("Skill Gaps")
    gap_col1, gap_col2 = st.columns(2)
    with gap_col1:
        st.write("Ability skills missing")
        st.write(score_data["missing_ability"] or ["None"])
    with gap_col2:
        st.write("Personality skills missing")
        st.write(score_data["missing_personality"] or ["None"])

    st.subheader("Assessment Questions")
    for q in questions_data.get("questions", []):
        with st.container(border=True):
            st.write(f"**Skill:** {q.get('skill', '')}")
            st.write(f"**Category:** {q.get('category', '')}")
            st.write(q.get("question", ""))
            st.caption(q.get("what_good_looks_like", ""))

    st.subheader("Personalized Learning Plan")
    st.json(learning_plan)

    st.subheader("How to interpret this")
    st.write(
        "Ability skills are compared directly against the resume. Personality skills are treated as behavioral signals "
        "and should be validated through conversation, examples, and interview answers rather than keyword matching alone."
    )
