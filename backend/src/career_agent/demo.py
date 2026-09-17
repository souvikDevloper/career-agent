"""Fictional example workspace data. Clearly labelled; never presented as a real person or employer."""

from __future__ import annotations

import zlib

DEMO_RESUME_TEXT = """Aarav Mehta (fictional example applicant)
aarav.mehta@example.com | +91 90000 00000 | Pune, India
github.com/aarav-example | linkedin.com/in/aarav-example

EDUCATION
Deccan Institute of Technology (fictional), B.Tech in Computer Science, expected graduation 2027. CGPA 8.4/10

EXPERIENCE
Software Engineering Intern, Lotus Fintech (fictional), May 2026 - July 2026
- Built a Python FastAPI service for loan document status deployed on AWS Lambda with DynamoDB
- Wrote REST APIs and unit tests with pytest; reduced p95 latency from 900 ms to 350 ms by adding caching
- Set up GitHub Actions CI and infrastructure as code with AWS SAM

PROJECTS
CampusRide - React and TypeScript web app for sharing rides between students; Node.js API with PostgreSQL; 300 monthly users
Resume Radar - Python tool that parses resumes and ranks job descriptions using TF-IDF and scikit-learn
Serverless Notes - AWS Lambda, API Gateway, DynamoDB and S3 notes app with Cognito authentication

SKILLS
Python, TypeScript, JavaScript, React, Node.js, FastAPI, SQL, PostgreSQL, DynamoDB, AWS Lambda, Amazon S3, Docker, Git, REST APIs, pytest

ACHIEVEMENTS
Finalist, college hackathon 2025 (team of 4)
"""

DEMO_FACTS = {
    "name": "Aarav Mehta", "email": "aarav.mehta@example.com", "phone": "+91 90000 00000", "location": "Pune, India",
    "links": {"github": "https://github.com/aarav-example", "linkedin": "https://linkedin.com/in/aarav-example", "portfolio": None},
    "headline": "Final-year CS student building serverless backends", "summary": None,
    "education": [{"school": "Deccan Institute of Technology (fictional)", "degree": "B.Tech", "field": "Computer Science",
                   "graduation_year": 2027, "evidence": "B.Tech in Computer Science, expected graduation 2027", "verified": True}],
    "experience": [{"title": "Software Engineering Intern", "company": "Lotus Fintech (fictional)", "start": "2026-05", "end": "2026-07",
                    "highlights": ["Built a Python FastAPI service on AWS Lambda with DynamoDB", "Reduced p95 latency from 900 ms to 350 ms"],
                    "evidence": "Built a Python FastAPI service for loan document status deployed on AWS Lambda with DynamoDB", "verified": True}],
    "projects": [
        {"name": "CampusRide", "description": "React and TypeScript ride sharing app with Node.js API and PostgreSQL",
         "skills": ["React", "TypeScript", "Node.js", "PostgreSQL"], "evidence": "CampusRide - React and TypeScript web app", "verified": True},
        {"name": "Resume Radar", "description": "Python resume parser ranking jobs with TF-IDF", "skills": ["Python", "scikit-learn"],
         "evidence": "Resume Radar - Python tool that parses resumes", "verified": True},
        {"name": "Serverless Notes", "description": "Lambda, API Gateway, DynamoDB, S3 and Cognito notes app",
         "skills": ["AWS Lambda", "DynamoDB", "Cognito"], "evidence": "Serverless Notes - AWS Lambda, API Gateway, DynamoDB and S3", "verified": True},
    ],
    "skills": [{"name": s, "evidence": s, "verified": True} for s in
               ["Python", "TypeScript", "JavaScript", "React", "Node.js", "FastAPI", "SQL", "PostgreSQL", "DynamoDB", "AWS Lambda",
                "Amazon S3", "Docker", "Git", "REST APIs", "pytest"]],
    "years_experience": 0,
    "work_authorization": {"value": "Yes, authorized to work in India (fictional example data)", "verified": True, "source": "example"},
    "suggestions": [
        {"issue": "Hackathon achievement lacks detail", "suggestion": "What did your team build and what was your part?", "section": "Achievements"},
        {"issue": "CampusRide bullet mixes stack and outcome", "suggestion": "Lead with the problem solved, then the stack.", "section": "Projects"},
    ],
    "example_workspace": True,
}

DEMO_SAVED_ANSWERS = {
    "I confirm the information in this application is accurate": "yes",
    "Consent to processing of application data": "yes",
}

DEMO_PREFERENCES = {"roles": ["intern"], "locations": ["Bengaluru", "Pune", "Remote"], "work_modes": ["remote", "hybrid"],
                    "excluded_companies": [], "min_salary": None}


def minimal_pdf(text: str) -> bytes:
    """Tiny dependency-free text PDF so the example resume is a real uploadable file."""
    lines = [l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for l in text.splitlines()]
    stream_lines = ["BT", "/F1 10 Tf", "13 TL", "50 800 Td"]
    for l in lines:
        stream_lines.append(f"({l.encode('latin-1', 'replace').decode('latin-1')}) Tj T*")
    stream_lines.append("ET")
    content = zlib.compress("\n".join(stream_lines).encode("latin-1", "replace"))
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" /Filter /FlateDecode >>\nstream\n" + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


PORTAL_SEED_JOBS = [
    {"slug": "backend-intern", "title": "Backend Engineer Intern", "location": "Bengaluru (Hybrid)", "work_mode": "hybrid",
     "team": "Payments Platform", "salary_min": 40000, "salary_max": 60000,
     "description": "Join the Payments Platform team to build reliable Python services on AWS. You will design REST APIs, write tests, and ship to production with serverless tooling.",
     "requirements": {"required_skills": ["Python", "REST APIs", "AWS Lambda", "DynamoDB"], "preferred_skills": ["FastAPI", "Docker"],
                      "min_years": None, "graduation_years": [2026, 2027], "work_authorization_required": True,
                      "responsibilities": ["Build backend APIs with Python", "Write unit tests", "Operate serverless services on AWS"]}},
    {"slug": "frontend-intern", "title": "Frontend Engineer Intern", "location": "Remote (India)", "work_mode": "remote",
     "team": "Merchant Dashboard", "salary_min": 35000, "salary_max": 50000,
     "description": "Build accessible React interfaces for merchants. TypeScript, component design and performance matter here.",
     "requirements": {"required_skills": ["React", "TypeScript", "CSS", "Accessibility"], "preferred_skills": ["Next.js"],
                      "min_years": None, "graduation_years": [2026, 2027], "work_authorization_required": True,
                      "responsibilities": ["Build React components", "Improve web accessibility"]}},
    {"slug": "data-analyst-intern", "title": "Data Analyst Intern", "location": "Mumbai (Onsite)", "work_mode": "onsite",
     "team": "Risk Analytics", "salary_min": 30000, "salary_max": 45000,
     "description": "Analyse transaction data with SQL and Python and present insights with dashboards.",
     "requirements": {"required_skills": ["SQL", "Python", "Tableau", "Statistics"], "preferred_skills": ["Power BI"],
                      "min_years": None, "graduation_years": [2026], "work_authorization_required": True,
                      "responsibilities": ["Write SQL queries", "Build dashboards"]}},
    {"slug": "senior-ml-engineer", "title": "Senior Machine Learning Engineer", "location": "Bengaluru (Hybrid)", "work_mode": "hybrid",
     "team": "Fraud ML", "salary_min": 2500000, "salary_max": 4000000,
     "description": "Own fraud detection models end to end. Requires 5+ years of production ML experience.",
     "requirements": {"required_skills": ["Python", "PyTorch", "MLOps", "Feature Stores"], "preferred_skills": ["Spark"],
                      "min_years": 5, "graduation_years": [], "work_authorization_required": True,
                      "responsibilities": ["Train and deploy ML models", "Lead ML architecture"]}},
]

PUBLISHABLE_TEMPLATES = [
    {"slug": "cloud-intern", "title": "Cloud Engineer Intern (AWS)", "location": "Pune (Hybrid)", "work_mode": "hybrid",
     "team": "Cloud Foundations", "salary_min": 45000, "salary_max": 65000,
     "description": "Automate AWS infrastructure with SAM/CloudFormation, build Lambda functions in Python, and improve CI/CD pipelines with GitHub Actions.",
     "requirements": {"required_skills": ["Python", "AWS Lambda", "GitHub Actions", "AWS SAM"], "preferred_skills": ["DynamoDB", "Docker"],
                      "min_years": None, "graduation_years": [2026, 2027], "work_authorization_required": True,
                      "responsibilities": ["Build Lambda functions in Python", "Maintain infrastructure as code", "Improve CI/CD pipelines"]}},
    {"slug": "fullstack-intern", "title": "Full-Stack Engineer Intern", "location": "Remote (India)", "work_mode": "remote",
     "team": "Growth", "salary_min": 40000, "salary_max": 55000,
     "description": "Ship features across a React + TypeScript frontend and Node.js APIs backed by PostgreSQL.",
     "requirements": {"required_skills": ["React", "TypeScript", "Node.js", "PostgreSQL"], "preferred_skills": ["AWS"],
                      "min_years": None, "graduation_years": [2026, 2027], "work_authorization_required": True,
                      "responsibilities": ["Build React features", "Write Node.js APIs"]}},
    {"slug": "sre-intern", "title": "Site Reliability Intern", "location": "Hyderabad (Onsite)", "work_mode": "onsite",
     "team": "Reliability", "salary_min": 40000, "salary_max": 55000,
     "description": "Improve observability and incident response using Go, Kubernetes and Prometheus.",
     "requirements": {"required_skills": ["Go", "Kubernetes", "Prometheus", "Linux"], "preferred_skills": ["Terraform"],
                      "min_years": None, "graduation_years": [2026, 2027], "work_authorization_required": True,
                      "responsibilities": ["Build monitoring dashboards", "Participate in on-call"]}},
]
