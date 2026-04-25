import os
import json
import tempfile
import streamlit as st
from pypdf import PdfReader
from groq import Groq
from pydantic import BaseModel
from typing import List

st.set_page_config(page_title="JD Skill Analyzer", layout="wide")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not GROQ_API_KEY:
    st.warning("Add GROQ_API_KEY in your Hugging Face Space secrets.")
    st.stop()

client = Groq(api_key=GROQ_API_KEY)

class SkillItem(BaseModel):
    skill: str = ""
    priority: str = ""
    evidence: str = ""

class CompanyContext(BaseModel):
    sector: str = ""
    company_stage: str = ""
    culture_signals: List[str] = []
    work_style: List[str] = []
    business_context: str = ""

class JDAnalysis(BaseModel):
    company_context: CompanyContext = CompanyContext()
    ability_skills: List[SkillItem] = []
    personality_skills: List[SkillItem] = []
    role_summary: str = ""
    top_keywords: List[str] = []

class ResumeAnalysis(BaseModel):
    skills: List[str] = []
    tools: List[str] = []
    experience_level: str = ""
    domains: List[str] = []
    strengths: List[str] = []
    behavioral_signals: List[str] = []

class RoleFitAnalysis(BaseModel):
    role_type: str = ""
    ability_weight: float = 0.0
    personality_weight: float = 0.0
    reason: str = ""

class QuestionItem(BaseModel):
    skill: str = ""
    category: str = ""
    question: str = ""
    what_good_looks_like: str = ""

class QuestionsOutput(BaseModel):
    questions: List[QuestionItem] = []

class ResourceItem(BaseModel):
    skill: str = ""
    title: str = ""
    platform: str = ""
    type: str = ""
    url: str = ""
    why_use_it: str = ""

class PrioritySkillItem(BaseModel):
    skill: str = ""
    why_this_first: str = ""
    estimated_time_hours: int = 0
    resources: List[ResourceItem] = []

class WeekPlanItem(BaseModel):
    week: int = 0
    focus: str = ""
    outcomes: List[str] = []

class LearningPlanOutput(BaseModel):
    plan_summary: str = ""
    priority_skills: List[PrioritySkillItem] = []
    strategy: str = ""
    week_1: List[WeekPlanItem] = []
    week_2: List[WeekPlanItem] = []
    week_3: List[WeekPlanItem] = []
    week_4: List[WeekPlanItem] = []

def extract_text_from_pdf(uploaded_file):
    if uploaded_file is None:
        return ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getvalue())
        path = tmp.name
    try:
        reader = PdfReader(path)
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    finally:
        try:
            os.remove(path)
        except:
            pass
    return text

def ask_groq(prompt):
    kwargs = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "Return only valid JSON. Do not add markdown, code fences, or extra commentary."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content

def analyze_role_fit(jd_text):
    prompt = f"""
You are analyzing a job description for hiring fit.
Classify the role as one of:
- ability_heavy
- personality_heavy
- balanced
Return JSON only in this format:
{{
  "role_type": "",
  "ability_weight": 0.0,
  "personality_weight": 0.0,
  "reason": ""
}}
Rules:
- If the role is technical, analytical, or tool-heavy, use ability_heavy.
- If the role is people-facing, leadership-heavy, or communication-heavy, use personality_heavy.
- If both matter equally, use balanced.
- The weights must add up to 1.0.
- The reason must be more detailed and explain why this role is weighted this way.
- Mention at least 2 concrete signals from the JD.
Job description:
{jd_text}
"""
    return RoleFitAnalysis.model_validate_json(ask_groq(prompt))

def analyze_job_description(jd_text):
    prompt = f"""
You are an expert job description analyzer.
Return JSON only with this schema:
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
- Personality skills are behavioral traits, collaboration style, or work preferences.
- Infer company sector and work style from the job description.
- Do not include duplicate skills.
- Keep all values concise.
Job description:
{jd_text}
"""
    return JDAnalysis.model_validate_json(ask_groq(prompt))

def analyze_resume(resume_text):
    prompt = f"""
You are a resume analyst.
Return JSON only with this schema:
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
    return ResumeAnalysis.model_validate_json(ask_groq(prompt))

def score_match(jd_data, resume_data, role_fit):
    resume_pool = " | ".join(
        resume_data.skills + resume_data.tools + resume_data.strengths + resume_data.behavioral_signals + resume_data.domains
    ).lower()

    jd_ability = [x.skill.lower() for x in jd_data.ability_skills]
    jd_personality = [x.skill.lower() for x in jd_data.personality_skills]

    def simple_semantic_match(skill, pool):
        s = skill.lower()
        keywords = [s]
        if "communication" in s:
            keywords += ["communicate", "communication", "stakeholder", "presentation"]
        if "team" in s or "collaboration" in s:
            keywords += ["team", "collaboration", "collaborate", "cross-functional"]
        if "adapt" in s:
            keywords += ["adapt", "flexible", "flexibility", "agile"]
        if "lead" in s:
            keywords += ["lead", "leadership", "managed", "owned"]
        if "analysis" in s:
            keywords += ["analysis", "analyze", "analytics", "analytical"]
        if "problem" in s:
            keywords += ["problem solving", "problem-solving", "solve"]
        return any(k in pool for k in keywords)

    ability_hits = [s for s in jd_ability if simple_semantic_match(s, resume_pool)]
    personality_hits = [s for s in jd_personality if simple_semantic_match(s, resume_pool)]

    ability_score = int((len(ability_hits) / max(len(jd_ability), 1)) * 100)
    personality_score = int((len(personality_hits) / max(len(jd_personality), 1)) * 100)

    overall_score = int(
        (ability_score * role_fit.ability_weight) +
        (personality_score * role_fit.personality_weight)
    )

    missing_ability = [s for s in jd_ability if s not in ability_hits]
    missing_personality = [s for s in jd_personality if s not in personality_hits]

    return {
        "role_type": role_fit.role_type,
        "ability_weight": role_fit.ability_weight,
        "personality_weight": role_fit.personality_weight,
        "role_reason": role_fit.reason,
        "ability_score": ability_score,
        "personality_score": personality_score,
        "overall_score": overall_score,
        "matched_ability": ability_hits,
        "matched_personality": personality_hits,
        "missing_ability": missing_ability,
        "missing_personality": missing_personality
    }

def build_course_recommendations(skill_name):
    skill = skill_name.lower()
    recs = []

    if "sql" in skill:
        recs.append({
            "skill": skill_name,
            "title": "Databases and SQL for Data Science with Python",
            "platform": "Coursera",
            "type": "paid",
            "url": "https://www.coursera.org/learn/sql-data-science",
            "why_use_it": "Good for learning SQL fundamentals and database thinking."
        })
        recs.append({
            "skill": skill_name,
            "title": "SQL Tutorial for Beginners",
            "platform": "YouTube / freeCodeCamp",
            "type": "free",
            "url": "https://www.youtube.com/watch?v=HXV3zeQKqGY",
            "why_use_it": "Free beginner-friendly SQL practice and concepts."
        })
    elif "python" in skill:
        recs.append({
            "skill": skill_name,
            "title": "Python for Data Science and AI",
            "platform": "Coursera",
            "type": "paid",
            "url": "https://www.coursera.org/learn/python-for-applied-data-science-ai",
            "why_use_it": "Useful for applied Python skills in data workflows."
        })
        recs.append({
            "skill": skill_name,
            "title": "Python Full Course",
            "platform": "freeCodeCamp / YouTube",
            "type": "free",
            "url": "https://www.youtube.com/watch?v=rfscVS0vtbw",
            "why_use_it": "A free long-form Python learning resource."
        })
    elif "gen ai" in skill or "generative ai" in skill or "ai" in skill:
        recs.append({
            "skill": skill_name,
            "title": "5-Day Gen AI Intensive Course with Google",
            "platform": "Kaggle",
            "type": "free",
            "url": "https://www.kaggle.com/learn-guide/5-day-genai",
            "why_use_it": "Free hands-on Gen AI training from Kaggle."
        })
        recs.append({
            "skill": skill_name,
            "title": "Generative AI courses",
            "platform": "Coursera / Udemy",
            "type": "paid",
            "url": "",
            "why_use_it": "Structured paid learning for deeper generative AI understanding."
        })
    elif "data analysis" in skill or "analysis" in skill:
        recs.append({
            "skill": skill_name,
            "title": "Google Data Analytics Professional Certificate",
            "platform": "Coursera",
            "type": "paid",
            "url": "https://www.coursera.org/professional-certificates/google-data-analytics",
            "why_use_it": "Structured learning for analyst workflows and business analysis."
        })
        recs.append({
            "skill": skill_name,
            "title": "Kaggle Learn",
            "platform": "Kaggle",
            "type": "free",
            "url": "https://www.kaggle.com/learn",
            "why_use_it": "Free hands-on micro-courses with notebooks."
        })
    elif "dashboard" in skill or "power bi" in skill or "tableau" in skill or "visualization" in skill:
        recs.append({
            "skill": skill_name,
            "title": "Data Visualization with Tableau",
            "platform": "Coursera",
            "type": "paid",
            "url": "https://www.coursera.org/professional-certificates/google-data-analytics",
            "why_use_it": "Helps improve visualization and dashboard design skills."
        })
        recs.append({
            "skill": skill_name,
            "title": "Power BI / Tableau tutorials",
            "platform": "YouTube",
            "type": "free",
            "url": "",
            "why_use_it": "Free practical tutorials for dashboard building."
        })
    elif "communication" in skill or "stakeholder" in skill or "presentation" in skill:
        recs.append({
            "skill": skill_name,
            "title": "Business Communication Skills",
            "platform": "Coursera",
            "type": "paid",
            "url": "https://www.coursera.org/learn/wharton-communication-skills",
            "why_use_it": "Helpful for stakeholder communication and professional messaging."
        })
        recs.append({
            "skill": skill_name,
            "title": "Communication Skills courses",
            "platform": "LinkedIn Learning / YouTube",
            "type": "free",
            "url": "",
            "why_use_it": "Good for presentation and workplace communication practice."
        })
    elif "team" in skill or "collaboration" in skill or "adapt" in skill or "lead" in skill:
        recs.append({
            "skill": skill_name,
            "title": "Workplace Soft Skills",
            "platform": "LinkedIn Learning",
            "type": "paid",
            "url": "",
            "why_use_it": "Useful for collaboration, adaptability, and teamwork."
        })
        recs.append({
            "skill": skill_name,
            "title": "Soft skills learning playlists",
            "platform": "YouTube",
            "type": "free",
            "url": "",
            "why_use_it": "Free content for communication and teamwork improvement."
        })
    else:
        recs.append({
            "skill": skill_name,
            "title": f"Skill learning resources for {skill_name}",
            "platform": "Kaggle / Coursera / YouTube",
            "type": "free",
            "url": "",
            "why_use_it": "Start with a beginner-friendly resource and then move to a structured course."
        })
        recs.append({
            "skill": skill_name,
            "title": f"Professional course for {skill_name}",
            "platform": "Coursera / Udemy",
            "type": "paid",
            "url": "",
            "why_use_it": "Use this for a deeper, structured learning path."
        })

    return recs[:2]

def generate_assessment_questions(jd_data, score_data):
    focus_skills = score_data["missing_ability"][:3] + score_data["missing_personality"][:2]
    if not focus_skills:
        focus_skills = [x.skill for x in jd_data.ability_skills[:3]]

    prompt = f"""
You are a conversational skill assessor.
Create 1 practical question for each skill below.
Return JSON only in this format:
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
Use the missing skills list as the basis for the questions.
Skills:
{json.dumps(focus_skills, indent=2)}
"""
    try:
        return QuestionsOutput.model_validate_json(ask_groq(prompt)).model_dump()
    except:
        return {
            "questions": [
                {
                    "skill": s,
                    "category": "ability",
                    "question": f"Tell me about your experience with {s}. Give one real example.",
                    "what_good_looks_like": "Clear example, specific impact, and correct terminology."
                }
                for s in focus_skills
            ]
        }

def generate_learning_plan(jd_data, score_data, resume_data):
    missing_ability = score_data.get("missing_ability", [])
    missing_personality = score_data.get("missing_personality", [])
    context = jd_data.company_context

    prompt = f"""
You are a career learning planner.
Create a personalized learning plan focused on adjacent skills the candidate can realistically acquire.
Return JSON only with this schema:
{{
  "plan_summary": "",
  "priority_skills": [
    {{
      "skill": "",
      "why_this_first": "",
      "estimated_time_hours": 0,
      "resources": [
        {{
          "skill": "",
          "title": "",
          "platform": "",
          "type": "free|paid",
          "url": "",
          "why_use_it": ""
        }}
      ]
    }}
  ],
  "strategy": "",
  "week_1": [
    {{
      "week": 1,
      "focus": "",
      "outcomes": []
    }}
  ],
  "week_2": [],
  "week_3": [],
  "week_4": []
}}
Instructions:
- Make the plan realistic and personalized.
- Focus on adjacent skills that are the easiest next step.
- Include time estimates in hours for each priority skill.
- Include both free and paid course/platform options for each skill.
- The strategy must be detailed and mention why each missing skill matters.
Job sector: {context.sector}
Culture signals: {context.culture_signals}
Work style: {context.work_style}
Missing ability skills:
{json.dumps(missing_ability, indent=2)}
Missing personality skills:
{json.dumps(missing_personality, indent=2)}
Resume strengths:
{json.dumps(resume_data.strengths, indent=2)}
"""
    try:
        plan = json.loads(ask_groq(prompt))
    except:
        plan = {
            "plan_summary": "Build the nearest missing skills first, then validate progress with small projects and interview practice.",
            "priority_skills": [],
            "strategy": "",
            "week_1": [],
            "week_2": [],
            "week_3": [],
            "week_4": []
        }

    if not plan.get("priority_skills"):
        fallback = []
        for s in (missing_ability + missing_personality)[:4]:
            recs = build_course_recommendations(s)
            fallback.append({
                "skill": s,
                "why_this_first": f"{s} is directly missing from the role requirements.",
                "estimated_time_hours": 8,
                "resources": recs
            })
        plan["priority_skills"] = fallback

    if not plan.get("strategy"):
        strategy_parts = []
        if missing_ability:
            strategy_parts.append(f"First improve technical gaps: {', '.join(missing_ability[:5])}.")
        if missing_personality:
            strategy_parts.append(f"Then strengthen work-style gaps: {', '.join(missing_personality[:5])}.")
        strategy_parts.append("Practice these skills through small projects, mock questions, and portfolio examples.")
        plan["strategy"] = " ".join(strategy_parts)

    return plan

def generate_summary(jd_data, resume_data, score_data):
    prompt = f"""
Write a single plain paragraph evaluation of the candidate.
Use:
- Job role summary: {jd_data.role_summary}
- Sector: {jd_data.company_context.sector}
- Missing ability skills: {score_data.get("missing_ability", [])}
- Missing personality skills: {score_data.get("missing_personality", [])}
- Candidate strengths: {resume_data.strengths}
- Candidate behavioral signals: {resume_data.behavioral_signals}
- Role type: {score_data.get("role_type", "")}
- Role reason: {score_data.get("role_reason", "")}
Rules:
- Return only one paragraph.
- Do not return JSON.
- Do not use bullets.
- Do not use labels.
- Make it natural and readable.
"""
    return ask_groq(prompt)

def scoring_explanation(score_data, jd_data):
    top_keywords = ", ".join(jd_data.top_keywords[:3]) if jd_data.top_keywords else "the main role requirements"
    return (
        f"The overall fit score is calculated by first scoring ability and personality separately, then combining them using role-specific weights. "
        f"This role is treated as {score_data['role_type']} because the job description emphasizes {top_keywords}, "
        f"so ability contributes {score_data['ability_weight']:.2f} and personality contributes {score_data['personality_weight']:.2f} to the final score. "
        f"The ability score comes from matching the resume against the job’s technical and task-based requirements, while the personality score comes from comparing work-style and behavioral signals such as communication, teamwork, adaptability, and leadership. "
        f"So the final score is a weighted comparison of the JD and resume, not a simple keyword count."
    )

def resume_profile_explanation(score_data):
    return (
        f"The resume profile score is based on how well the resume supports the role’s expected skills and behaviors. "
        f"When the resume contains direct evidence such as skills, tools, project work, or collaboration signals, the score improves because those items map more strongly to the job requirements. "
        f"Missing or weakly represented areas lower the score because the resume does not yet show enough evidence for those requirements."
    )

def skill_gap_explanation(score_data, jd_data):
    parts = []
    for s in score_data.get("missing_ability", []):
        ev = next((x.evidence for x in jd_data.ability_skills if x.skill.lower() == s), "not explicitly present in the JD")
        parts.append(f"{s} is missing because it appears in the JD with evidence like: {ev}, but the resume does not show a matching signal.")
    for s in score_data.get("missing_personality", []):
        ev = next((x.evidence for x in jd_data.personality_skills if x.skill.lower() == s), "not explicitly present in the JD")
        parts.append(f"{s} is missing because it appears in the JD with evidence like: {ev}, but the resume does not show a matching signal.")
    if not parts:
        return "No major skill gaps were found because the resume covers the core requirements in the job description."
    return (
        "Skill gaps are identified by comparing the job description requirements against the resume evidence. "
        + " ".join(parts)
        + " This means a gap exists when the JD asks for a capability or behavior and the resume does not provide a clear equivalent."
    )

def question_basis_text(score_data):
    return (
        "The assessment questions are developed from the missing and weakly supported skills in the resume, with priority given to the most important ability gaps and the most relevant personality gaps."
    )

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

    if len(jd_text.strip()) < 30 or len(resume_text.strip()) < 30:
        st.error("The uploaded PDF seems unreadable or too short. Please upload a text-based PDF or paste the text manually.")
        st.stop()

    with st.spinner("Analyzing role fit..."):
        role_fit = analyze_role_fit(jd_text)

    with st.spinner("Analyzing job description..."):
        jd_data = analyze_job_description(jd_text)

    with st.spinner("Analyzing resume..."):
        resume_data = analyze_resume(resume_text)

    with st.spinner("Scoring fit..."):
        score_data = score_match(jd_data, resume_data, role_fit)

    with st.spinner("Creating assessment questions..."):
        questions_data = generate_assessment_questions(jd_data, score_data)

    with st.spinner("Creating narrative summary..."):
        narrative_summary = generate_summary(jd_data, resume_data, score_data)

    with st.spinner("Creating learning plan..."):
        learning_plan = generate_learning_plan(jd_data, score_data, resume_data)

    st.subheader("Role Analysis")
    st.write(f"Role type: {score_data['role_type']}")
    st.write(f"Ability weight: {score_data['ability_weight']}")
    st.write(f"Personality weight: {score_data['personality_weight']}")
    st.write(f"Reason: {score_data['role_reason']}")

    st.subheader("Score Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("Overall Fit", f"{score_data['overall_score']}%")
    c2.metric("Ability Fit", f"{score_data['ability_score']}%")
    c3.metric("Personality Fit", f"{score_data['personality_score']}%")
    st.write(scoring_explanation(score_data, jd_data))

    st.subheader("Summary")
    st.write(narrative_summary)

    st.subheader("Job Description Understanding")
    st.json(jd_data.model_dump())
    st.write(scoring_explanation(score_data, jd_data))

    st.subheader("Resume Profile")
    st.json(resume_data.model_dump())
    st.write(resume_profile_explanation(score_data))

    st.subheader("Skill Gaps")
    gap_col1, gap_col2 = st.columns(2)
    with gap_col1:
        st.write("Ability skills missing")
        st.write(score_data["missing_ability"] or ["None"])
    with gap_col2:
        st.write("Personality skills missing")
        st.write(score_data["missing_personality"] or ["None"])
    st.write(skill_gap_explanation(score_data, jd_data))

    st.subheader("Assessment Questions")
    st.write(question_basis_text(score_data))
    for q in questions_data.get("questions", []):
        with st.container(border=True):
            st.write(f"**Skill:** {q.get('skill', '')}")
            st.write(f"**Category:** {q.get('category', '')}")
            st.write(q.get("question", ""))
            st.caption(q.get("what_good_looks_like", ""))

    st.subheader("Personalized Learning Plan")
    st.write(learning_plan.get("plan_summary", ""))

    st.subheader("Priority Skills")
    for item in learning_plan.get("priority_skills", []):
        with st.container(border=True):
            st.write(f"**Skill:** {item.get('skill', '')}")
            st.write(f"**Why this first:** {item.get('why_this_first', '')}")
            st.write(f"**Estimated time:** {item.get('estimated_time_hours', 0)} hours")
            st.write("**Resources:**")
            for r in item.get("resources", []):
                st.write(f"- {r.get('title', '')} ({r.get('type', '')}, {r.get('platform', '')})")
                if r.get("url"):
                    st.write(f"  {r.get('url')}")
                if r.get("why_use_it"):
                    st.caption(r.get("why_use_it"))

    st.subheader("Detailed Strategy")
    st.write(learning_plan.get("strategy", ""))

    st.subheader("Weekly Plan")
    for week_key in ["week_1", "week_2", "week_3", "week_4"]:
        week_items = learning_plan.get(week_key, [])
        if week_items:
            st.write(f"**{week_key.replace('_', ' ').title()}**")
            for w in week_items:
                st.write(f"- {w.get('focus', '')}")
                for out in w.get("outcomes", []):
                    st.write(f"  - {out}")

    st.subheader("How to interpret this")
    st.write(
        "Ability skills are compared directly against the resume. Personality skills are treated as behavioral signals "
        "and should be validated through conversation, examples, and interview answers rather than keyword matching alone."
    )
