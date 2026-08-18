"""
Phase 0 knowledge graph builder — manual curation pass over the raw sources
pulled into ingestion/raw/ (GitHub, Kaggle, Medium).

This is deterministic, hand-curated data entry (per CHANDLEROS_BLUEPRINT.md
Section "Knowledge Ingestion": manual curation is one of the legitimate
deterministic paths, alongside rule/LLM extraction). Every entity/relationship
below was placed here by reading the actual raw source content, not inferred
by a model.

Schema follows CHANDLEROS_BLUEPRINT.md Section 8 exactly: entities,
relationships, evidence, each versioned with KNOWLEDGE_VERSION.
"""

import sqlite3
import json
import datetime

DB_PATH = "knowledge.db"
KNOWLEDGE_VERSION = "2026.08.0"
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases TEXT,
    attributes TEXT,
    knowledge_version TEXT,
    created_at TEXT,
    updated_at TEXT,
    status TEXT DEFAULT 'active',
    merged_into TEXT
);

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES entities(id),
    target_id TEXT NOT NULL REFERENCES entities(id),
    type TEXT NOT NULL,
    confidence REAL,
    temporal_start TEXT,
    temporal_end TEXT,
    knowledge_version TEXT,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    relationship_id TEXT REFERENCES relationships(id),
    entity_id TEXT REFERENCES entities(id),
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    excerpt TEXT,
    extraction_method TEXT NOT NULL,
    extracted_at TEXT
);
"""

VALID_ENTITY_TYPES = {
    "Person", "Organization", "Company", "Role", "Education", "Degree",
    "Project", "Publication", "Book", "Blog", "ResearchTopic", "Skill",
    "Technology", "ProgrammingLanguage", "Framework", "Dataset", "Model",
    "Achievement", "Certification", "Event", "Concept",
}

VALID_REL_TYPES = {
    "WORKED_AT", "AUTHORED", "BUILT", "USES", "DEMONSTRATES", "STUDIED",
    "RESEARCHES", "PUBLISHED", "TEACHES", "RELATED_TO", "IMPLEMENTED_WITH",
    "DEPENDS_ON", "INSPIRED_BY", "PART_OF", "CONTRIBUTED_TO", "LEARNED_FROM",
}


class GraphBuilder:
    def __init__(self, conn):
        self.conn = conn
        self._eid_counter = 0
        self._rid_counter = 0
        self._evid_counter = 0

    def entity(self, type_, name, aliases=None, **attrs):
        assert type_ in VALID_ENTITY_TYPES, f"bad entity type {type_}"
        self._eid_counter += 1
        eid = f"{type_.lower()}_{self._eid_counter:03d}"
        self.conn.execute(
            "INSERT INTO entities (id, type, canonical_name, aliases, attributes, "
            "knowledge_version, created_at, updated_at, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (eid, type_, name, json.dumps(aliases or []), json.dumps(attrs),
             KNOWLEDGE_VERSION, NOW, NOW, "active"),
        )
        return eid

    def rel(self, source_id, rel_type, target_id, confidence=1.0,
            evidence_list=None, temporal_start=None, temporal_end=None,
            status="active"):
        assert rel_type in VALID_REL_TYPES, f"bad relationship type {rel_type}"
        self._rid_counter += 1
        rid = f"rel_{self._rid_counter:04d}"
        self.conn.execute(
            "INSERT INTO relationships (id, source_id, target_id, type, confidence, "
            "temporal_start, temporal_end, knowledge_version, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (rid, source_id, target_id, rel_type, confidence, temporal_start,
             temporal_end, KNOWLEDGE_VERSION, status),
        )
        for ev in (evidence_list or []):
            self._evid_counter += 1
            evid = f"ev_{self._evid_counter:04d}"
            self.conn.execute(
                "INSERT INTO evidence (id, relationship_id, entity_id, source_type, "
                "source_ref, excerpt, extraction_method, extracted_at) VALUES (?,?,?,?,?,?,?,?)",
                (evid, rid, None, ev["source_type"], ev["source_ref"],
                 ev.get("excerpt"), ev.get("extraction_method", "manual"), NOW),
            )
        return rid

    def entity_evidence(self, entity_id, ev):
        self._evid_counter += 1
        evid = f"ev_{self._evid_counter:04d}"
        self.conn.execute(
            "INSERT INTO evidence (id, relationship_id, entity_id, source_type, "
            "source_ref, excerpt, extraction_method, extracted_at) VALUES (?,?,?,?,?,?,?,?)",
            (evid, None, entity_id, ev["source_type"], ev["source_ref"],
             ev.get("excerpt"), ev.get("extraction_method", "manual"), NOW),
        )
        return evid


def build():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    g = GraphBuilder(conn)

    # ---------------------------------------------------------------
    # CORE PERSON / EDUCATION / ORGANIZATION
    # ---------------------------------------------------------------
    person = g.entity("Person", "N Sai Harshith Varma",
                       aliases=["Harshith", "Harshith Varma", "harshithvarma007"])
    g.entity_evidence(person, {
        "source_type": "medium", "source_ref": "medium/profile/about.html",
        "excerpt": "final-year Computer Science student at PES University...",
    })

    pes = g.entity("Organization", "PES University")
    education = g.entity("Education", "B.Tech Computer Science and Engineering (Data Science focus)",
                          institution="PES University", status="final-year")
    g.rel(person, "STUDIED", education, confidence=1.0, evidence_list=[{
        "source_type": "medium", "source_ref": "medium/profile/about.html",
        "excerpt": "final-year Computer Science student at PES University, currently pursuing my "
                   "Bachelor's degree with a focus on Data Science, Machine Learning, and AI.",
    }])
    g.rel(education, "PART_OF", pes, confidence=1.0, evidence_list=[{
        "source_type": "medium", "source_ref": "medium/profile/about.html",
    }])

    # GitHub profile "company" field said "Conlfuent" — confirmed by owner (2026-08-17)
    # to be a typo for "Confluent". Corrected, no longer disputed.
    confluent = g.entity("Organization", "Confluent")
    g.rel(person, "WORKED_AT", confluent, confidence=1.0, status="active", evidence_list=[{
        "source_type": "github_profile", "source_ref": "https://api.github.com/users/Harshithvarma007",
        "excerpt": "\"company\": \"Conlfuent\" (typo for Confluent, confirmed by owner)",
        "extraction_method": "rule_extracted",
    }, {
        "source_type": "manual_curation", "source_ref": "owner confirmation, 2026-08-17",
        "excerpt": "Owner confirmed 'Conlfuent' in GitHub profile is a typo for 'Confluent'.",
    }])

    # ---------------------------------------------------------------
    # PUBLICATION (found in TDL_309_312_330_368 README)
    # ---------------------------------------------------------------
    pub = g.entity("Publication", "Usability Assessment of Gesture Controlled Interfaces in "
                                   "Gaming Applications for Parkinson's Disease Patients")
    g.rel(person, "AUTHORED", pub, confidence=1.0, evidence_list=[{
        "source_type": "github_readme", "source_ref": "github/readmes/TDL_309_312_330_368.md",
        "excerpt": "Authors: 1. N Sai Harshith Varma 2. Murari B Deshpande 3. Netra D Patel "
                   "4. Patel Kashish Harshadbhai. Affiliation: Department of Computer Science "
                   "and Engineering, PES University, Bengaluru, India.",
    }])
    for coauthor_name in ["Murari B Deshpande", "Netra D Patel", "Patel Kashish Harshadbhai"]:
        cid = g.entity("Person", coauthor_name)
        g.rel(cid, "CONTRIBUTED_TO", pub, confidence=1.0, evidence_list=[{
            "source_type": "github_readme", "source_ref": "github/readmes/TDL_309_312_330_368.md",
        }])
    g.rel(pub, "PART_OF", pes, confidence=1.0, evidence_list=[{
        "source_type": "github_readme", "source_ref": "github/readmes/TDL_309_312_330_368.md",
        "excerpt": "Affiliation: Department of Computer Science and Engineering, PES University",
    }])

    # ---------------------------------------------------------------
    # TECHNOLOGIES / PROGRAMMING LANGUAGES (created once, reused)
    # ---------------------------------------------------------------
    tech = {}
    def get_tech(type_, name):
        key = (type_, name)
        if key not in tech:
            tech[key] = g.entity(type_, name)
        return tech[key]

    # ---------------------------------------------------------------
    # PROJECTS — consolidated across GitHub / Kaggle / Medium
    # Each tuple: (canonical_name, description, [languages], [(rel_type, source_type, ref, excerpt)])
    # ---------------------------------------------------------------

    def make_project(name, description, languages=None, urls=None, source_ref=None, excerpt=None):
        pid = g.entity("Project", name, description=description, urls=urls or [])
        base_ev = [{
            "source_type": "github_repo",
            "source_ref": source_ref or (urls[0] if urls else "manual_curation"),
            "excerpt": excerpt,
            "extraction_method": "manual" if excerpt else "rule_extracted",
        }]
        g.rel(person, "BUILT", pid, confidence=1.0, evidence_list=base_ev)
        for lang in (languages or []):
            tid = get_tech("ProgrammingLanguage", lang)
            g.rel(pid, "USES", tid, confidence=1.0, evidence_list=[{
                "source_type": "github_repo_languages",
                "source_ref": (urls[0] if urls else "manual_curation") + " (languages API)",
                "extraction_method": "rule_extracted",
            }])
        return pid

    # 1. LLM Text Detection — GitHub + Kaggle + Medium
    p_llmdet = make_project(
        "LLM-Generated Text Detection",
        "Detects whether text was generated by an LLM; 99.47% accuracy Kaggle notebook, "
        "GitHub repo, and a Medium write-up.",
        languages=["Python"],
        urls=["https://github.com/Harshithvarma007/LLM_Text_Detection",
              "https://www.kaggle.com/code/harshithvarma007/llm-text-detection-99-47-accuracy"],
    )
    for ev in [
        {"source_type": "github_repo", "source_ref": "github/readmes/LLM_Text_Detection.md",
         "excerpt": "Detection of Large-Language Model (LLM) Generated Text"},
        {"source_type": "kaggle_kernel", "source_ref": "kaggle/kernels.json#llm-text-detection-99-47-accuracy",
         "excerpt": "LLM_Text_Detection(99.47 % Accuracy), 83 votes"},
        {"source_type": "medium_post", "source_ref": "medium/posts_parsed.json#2024-07-11",
         "excerpt": "📝 LLM Text Detection (46,395 chars, full write-up)"},
    ]:
        g.entity_evidence(p_llmdet, ev)
    g.rel(p_llmdet, "DEMONSTRATES", g.entity("Concept", "Natural Language Processing"), confidence=0.9,
          evidence_list=[{"source_type": "manual_curation",
                           "source_ref": "inferred from project domain (text classification)",
                           "extraction_method": "manual"}])

    # 2. Spam Email Classification — GitHub (2 repos) + Kaggle + Medium
    p_spam = make_project(
        "Spam Email Classification",
        "Neural network classifier for spam email detection, 98% accuracy, deployed on AWS "
        "end-to-end (data collection through deployment).",
        languages=["Python"],
        urls=["https://github.com/Harshithvarma007/Spam-email",
              "https://github.com/Harshithvarma007/Sapm-mail-Deployment",
              "https://www.kaggle.com/code/harshithvarma007/spam-email-classification-98-accuracy"],
    )
    for ev in [
        {"source_type": "github_repo", "source_ref": "github/readmes/Spam-email.md",
         "excerpt": "Neural Network Classifier for Spam Classification, achieving 98% accuracy "
                    "and deployed on AWS. Covers the complete lifecycle of an ML project."},
        {"source_type": "kaggle_kernel", "source_ref": "kaggle/kernels.json#spam-email-classification-98-accuracy",
         "excerpt": "Spam Email Classification 98% Accuracy, 19 votes"},
        {"source_type": "medium_post", "source_ref": "medium/posts_parsed.json#2024-07-15",
         "excerpt": "End-To-End ML Project: Spam Classification"},
    ]:
        g.entity_evidence(p_spam, ev)
    g.rel(p_spam, "IMPLEMENTED_WITH", get_tech("Technology", "AWS"), confidence=1.0, evidence_list=[{
        "source_type": "github_repo", "source_ref": "github/readmes/Spam-email.md",
    }])
    g.rel(p_spam, "USES", get_tech("Technology", "Docker"), confidence=0.8, evidence_list=[{
        "source_type": "github_repo", "source_ref": "github/raw/repos_enriched.json (Dockerfile present)",
    }])

    # 3. Spotify Dashboard — GitHub + Medium
    p_spotify = make_project(
        "Spotify Dashboard (Power BI)",
        "Advanced Power BI dashboard visualizing the most-streamed Spotify songs of 2023.",
        languages=["Python"],
        urls=["https://github.com/Harshithvarma007/Spotify-Dashboard"],
    )
    for ev in [
        {"source_type": "github_repo", "source_ref": "github/readmes/Spotify-Dashboard.md",
         "excerpt": "Advanced Power BI application showcasing the most streamed Spotify songs of 2023"},
        {"source_type": "medium_post", "source_ref": "medium/posts_parsed.json#2024-07-16",
         "excerpt": "Spotify Dashboard: Advanced Power BI Project"},
    ]:
        g.entity_evidence(p_spotify, ev)
    g.rel(p_spotify, "USES", get_tech("Technology", "Power BI"), confidence=1.0, evidence_list=[{
        "source_type": "github_repo", "source_ref": "github/readmes/Spotify-Dashboard.md",
        "excerpt": "an advanced Power BI application"}])

    # 4. ChatPDF — GitHub + Medium
    p_chatpdf = make_project(
        "ChatPDF",
        "End-to-end generative AI project: chat interface over PDF documents.",
        languages=["Python"],
        urls=["https://github.com/Harshithvarma007/ChatPDF"],
    )
    for ev in [
        {"source_type": "github_repo", "source_ref": "github/raw/repos_enriched.json#ChatPDF"},
        {"source_type": "medium_post", "source_ref": "medium/posts_parsed.json#2024-08-13",
         "excerpt": "ChatPdf: End to End Gen AI Project"},
    ]:
        g.entity_evidence(p_chatpdf, ev)
    g.rel(p_chatpdf, "DEMONSTRATES", g.entity("Concept", "Retrieval-Augmented Generation"), confidence=0.7,
          evidence_list=[{"source_type": "manual_curation",
                           "source_ref": "inferred from project name/purpose ('chat over PDFs'); "
                                         "not independently confirmed to use a RAG architecture specifically",
                           "extraction_method": "manual"}])

    # 5. Toxic Comment Detection — GitHub + Kaggle
    p_toxic = make_project(
        "Toxic Comment Detection",
        "Classifier for toxic comments, 98.1% accuracy, deployed with a live backend.",
        languages=["Python"],
        urls=["https://github.com/Harshithvarma007/Toxic-Comments",
              "https://toxic-comments-backend.onrender.com"],
    )
    for ev in [
        {"source_type": "github_repo", "source_ref": "github/readmes/Toxic-Comments.md"},
        {"source_type": "kaggle_kernel", "source_ref": "kaggle/kernels.json#toxic-comment-detection-98-1",
         "excerpt": "Toxic Comment Detection (98.1%), 60 votes"},
    ]:
        g.entity_evidence(p_toxic, ev)

    # 6. Wine Quality Prediction — GitHub only
    p_wine = make_project(
        "Wine Quality Prediction",
        "ML pipeline (config/schema/params/pipeline pattern) predicting wine quality.",
        languages=["Python"],
        urls=["https://github.com/Harshithvarma007/Wine-quality-Prediction"],
    )
    g.entity_evidence(p_wine, {"source_type": "github_repo",
                                "source_ref": "github/readmes/Wine-quality-Prediction.md"})

    # 7. Text Summarization — GitHub only
    p_textsum = make_project(
        "Text Summarization",
        "Modular NLP pipeline (config/component/pipeline pattern) for text summarization.",
        languages=["Python"],
        urls=["https://github.com/Harshithvarma007/Text_Summarization"],
    )
    g.entity_evidence(p_textsum, {"source_type": "github_repo",
                                   "source_ref": "github/readmes/Text_Summarization.md"})
    g.rel(p_textsum, "USES", g.entity("Dataset", "summarizer-data (custom)"), confidence=0.9,
          evidence_list=[{"source_type": "github_repo",
                           "source_ref": "github/readmes/Text_Summarization.md",
                           "excerpt": "Dataset: github.com/Harshithvarma007/Datasets/raw/main/summarizer-data.zip"}])

    # 8. Tennis Analysis — GitHub only (no README, low detail)
    p_tennis = make_project(
        "Tennis Analysis",
        "Computer-vision based tennis match analysis project (no README available; "
        "details inferred from repo name and language only — needs owner input to enrich).",
        languages=["Python"],
        urls=["https://github.com/Harshithvarma007/Tennis-Analysis"],
    )
    g.entity_evidence(p_tennis, {"source_type": "github_repo",
                                  "source_ref": "github/raw/repos_enriched.json#Tennis-Analysis",
                                  "extraction_method": "rule_extracted"})

    # 9. Amazon Dashboard — GitHub only, no README
    p_amazon = make_project(
        "Amazon Dashboard",
        "Dashboard project on Amazon-related data (no README available — needs owner input).",
        languages=["Python"],
        urls=["https://github.com/Harshithvarma007/Amazon-dashboard"],
    )
    g.entity_evidence(p_amazon, {"source_type": "github_repo",
                                  "source_ref": "github/raw/repos_enriched.json#Amazon-dashboard",
                                  "extraction_method": "rule_extracted"})

    # 10. EduScorer — GitHub (team software engineering project)
    p_edu = make_project(
        "EduScorer",
        "Software engineering team project for automated exam/answer scoring "
        "(database entry management, mark calculation, keyword highlighting).",
        languages=["Python"],
        urls=["https://github.com/Harshithvarma007/EduScorer"],
    )
    g.entity_evidence(p_edu, {"source_type": "github_repo",
                               "source_ref": "github/readmes/EduScorer.md",
                               "excerpt": "Software Engineering project 'Eduscorer' — implement proper database "
                                          "entry management, calculation for marks updation, keyword highlighting."})

    # 11. ml-from-scratch — GitHub (TS/Next.js book/learning project)
    p_mlscratch = make_project(
        "ML From Scratch",
        "Derivation-first, browser-native interactive machine learning curriculum "
        "('learn ML by building it'), built with Next.js/TypeScript.",
        languages=["TypeScript", "JavaScript", "CSS"],
        urls=["https://github.com/Harshithvarma007/ml-from-scratch"],
    )
    g.entity_evidence(p_mlscratch, {
        "source_type": "github_repo", "source_ref": "github/readmes/ml-from-scratch.md",
        "excerpt": "Learn machine learning by building it — derivation-first, browser-native, no hand-waving.",
    })
    g.rel(p_mlscratch, "USES", get_tech("Framework", "Next.js"), confidence=1.0, evidence_list=[{
        "source_type": "github_repo", "source_ref": "github/readmes/ml-from-scratch.md",
        "excerpt": "[![Next.js](https://img.shields.io/badge/Next.js-14-black?logo=next.js)]"}])
    # Related Medium posts that are clearly part of the same "from scratch" content line
    for mid, ref, excerpt in [
        ("2026-04-19", "medium/posts_parsed.json#2026-04-19", "Gradient Descent from Scratch"),
        ("2025-09-23", "medium/posts_parsed.json#2025-09-23", "Building an LLM from Scratch"),
    ]:
        blog = g.entity("Blog", excerpt, date=mid)
        g.rel(person, "AUTHORED", blog, confidence=1.0, evidence_list=[
            {"source_type": "medium_post", "source_ref": ref}])
        g.rel(blog, "RELATED_TO", p_mlscratch, confidence=0.6, evidence_list=[{
            "source_type": "manual_curation", "source_ref": "topical association, not an explicit link",
        }])

    # 12. Trace The Ace — Kaggle only (kernels + dataset), no GitHub repo found
    p_trace = g.entity("Project", "Trace The Ace",
                        description="ML project with feature engineering, featurization, and "
                                     "fine-tuning stages (Kaggle-only; no GitHub repo located).")
    g.rel(person, "BUILT", p_trace, confidence=0.9, evidence_list=[{
        "source_type": "kaggle_kernel", "source_ref": "kaggle/kernels.json#trace-the-ace-finetuneing",
        "extraction_method": "rule_extracted"}])
    for ev in [
        {"source_type": "kaggle_kernel", "source_ref": "kaggle/kernels.json#trace-the-ace-finetuneing"},
        {"source_type": "kaggle_kernel", "source_ref": "kaggle/kernels.json#trace-the-ace-featurization"},
        {"source_type": "kaggle_kernel", "source_ref": "kaggle/kernels.json#trace-the-ace-feature-list"},
        {"source_type": "kaggle_dataset", "source_ref": "kaggle/datasets.json#trace-the-ace"},
    ]:
        g.entity_evidence(p_trace, ev)

    # 13. Detox — Medium only (matches local ARCHIVE/Detox git repo seen on disk,
    # but that repo has no remote configured, so it's not independently confirmed
    # as the same codebase — noted as high-confidence inference, not proven identity)
    p_detox = g.entity("Project", "Detox",
                        description="AI product built from scratch (per Medium post title); "
                                     "a local repo named 'Detox' also exists on disk under "
                                     "Desktop/ARCHIVE/Detox but has no git remote configured, "
                                     "so this identity link is inferred, not proven.")
    g.rel(person, "BUILT", p_detox, confidence=0.8, evidence_list=[{
        "source_type": "medium_post", "source_ref": "medium/posts_parsed.json#2026-07-29"}])
    g.entity_evidence(p_detox, {
        "source_type": "medium_post", "source_ref": "medium/posts_parsed.json#2026-07-29",
        "excerpt": "Building an AI Product From Scratch: Why Detox?",
    })

    # 14. Cricket Batsmen AI — Medium only
    p_cricket = g.entity("Project", "AI Batsman Reader (Cricket Computer Vision)",
                          description="Computer vision model reading/classifying batsmen, "
                                       "described as achieving state-of-the-art accuracy.")
    g.rel(person, "BUILT", p_cricket, confidence=0.9, evidence_list=[{
        "source_type": "medium_post", "source_ref": "medium/posts_parsed.json#2025-10-21"}])
    g.entity_evidence(p_cricket, {
        "source_type": "medium_post", "source_ref": "medium/posts_parsed.json#2025-10-21",
        "excerpt": "How I built an AI to Read Batsmen — and It Hit a State-of-the-Art Accuracy",
    })
    g.rel(p_cricket, "DEMONSTRATES", g.entity("Concept", "Computer Vision"), confidence=0.9,
          evidence_list=[{"source_type": "manual_curation",
                           "source_ref": "inferred from project domain (reading images of batsmen)",
                           "extraction_method": "manual"}])

    # ---------------------------------------------------------------
    # KAGGLE DATASETS not already linked to a project above — kept as
    # standalone Dataset entities pending owner clarification of context.
    # ---------------------------------------------------------------
    standalone_dataset_titles = [
        "Breast Cancer Dataset", "Disaster Tweets", "salary", "Admission Chance",
        "Car evaluation Dataset", "MALLORN Dataset", "URL_DATASET_Combined",
        "Build LLM from Scratch", "train_data", "BSC_GRU_93.47%", "Shot Classification",
        "Amazon ML challenge", "Face_Recognisition", "TDL_111", "TDL_gesture", "lfw.tgz",
        "Final_Dataset", "Enterprise Threat Severity Detection 2",
        "Enterprise Threat Severity Detection", "Classifying Prompt Instructions",
        "ATP Heuristic Efficiency Distribution Regression",
        "English QA Decision-Aware Quality Challenge", "HVAC Efficiency & Setpoint Adherence",
        "Dual Feedback",
    ]
    for title in standalone_dataset_titles:
        did = g.entity("Dataset", title,
                        note="Published on Kaggle; not yet linked to a specific Project entity "
                             "— likely coursework, competition, or exploratory work. Needs "
                             "owner review to classify/link or exclude.")
        g.rel(person, "PUBLISHED", did, confidence=0.7, evidence_list=[{
            "source_type": "kaggle_dataset", "source_ref": f"kaggle/datasets.json#{title}",
            "extraction_method": "rule_extracted",
        }])

    # ---------------------------------------------------------------
    # RESEARCH PUBLICATION (TDL_309...) already covers gesture-interface research.
    # PES gaming/Parkinson's research topic
    # ---------------------------------------------------------------
    g.rel(pub, "RESEARCHES", g.entity("ResearchTopic", "Human-Computer Interaction for Accessibility"),
          confidence=0.8, evidence_list=[{
              "source_type": "github_readme", "source_ref": "github/readmes/TDL_309_312_330_368.md"}])

    # ---------------------------------------------------------------
    # BLOG entities for the other major Medium articles not already created above
    # ---------------------------------------------------------------
    other_posts = [
        ("2024-06-25", "End To End Machine Learning Project-Part I"),
        ("2024-07-02", "End To End Machine Learning Project-Part II"),
        ("2025-11-12", "An AI's 'Brain' Isn't One Thing"),
        ("2025-07-18", "I Analyzed 141,000 Data Jobs"),
        ("2026-01-21", "The Serial Killer: Why I Trust Data Over Intuition"),
        ("2025-11-01", "The Village That Learned to Think"),
        ("2025-11-12b", "Why Are Lawyers Risking Their Careers for AI?"),
        ("2025-10-26", "SQL on LeetCode retrospective"),
        ("2025-10-31", "The $5 Trillion Moment"),
        ("2025-10-30", "How AI Sees the World"),
        ("2025-03-03", "Polymath"),
        ("2025-10-27", "10 Mistakes I Made While Learning ML"),
    ]
    for date_key, title in other_posts:
        bid = g.entity("Blog", title, date=date_key.rstrip("b"))
        g.rel(person, "AUTHORED", bid, confidence=1.0, evidence_list=[{
            "source_type": "medium_post", "source_ref": f"medium/posts_parsed.json#{date_key}",
        }])

    conn.commit()
    return conn


def validate(conn):
    print("\n=== VALIDATION ===")
    issues = 0

    # orphan entities: entities with no relationship and no evidence at all
    cur = conn.execute("""
        SELECT e.id, e.type, e.canonical_name FROM entities e
        WHERE e.id NOT IN (SELECT source_id FROM relationships)
          AND e.id NOT IN (SELECT target_id FROM relationships)
          AND e.id NOT IN (SELECT entity_id FROM evidence WHERE entity_id IS NOT NULL)
    """)
    orphans = cur.fetchall()
    if orphans:
        print(f"[WARN] {len(orphans)} orphan entities (no relationship, no evidence):")
        for o in orphans:
            print("   ", o)
        issues += len(orphans)

    # dangling references
    cur = conn.execute("""
        SELECT r.id FROM relationships r
        WHERE r.source_id NOT IN (SELECT id FROM entities)
           OR r.target_id NOT IN (SELECT id FROM entities)
    """)
    dangling = cur.fetchall()
    if dangling:
        print(f"[FAIL] {len(dangling)} relationships with dangling entity references")
        issues += len(dangling)

    # evidence completeness: every active, non-disputed relationship should have >=1 evidence row
    cur = conn.execute("""
        SELECT r.id, r.type FROM relationships r
        WHERE r.status = 'active'
          AND r.id NOT IN (SELECT relationship_id FROM evidence WHERE relationship_id IS NOT NULL)
    """)
    no_evidence = cur.fetchall()
    if no_evidence:
        print(f"[WARN] {len(no_evidence)} active relationships with NO evidence row:")
        for r in no_evidence:
            print("   ", r)
        issues += len(no_evidence)

    # relationship type / entity type compatibility spot-check (a couple of key rules)
    cur = conn.execute("""
        SELECT r.id, s.type, r.type, t.type FROM relationships r
        JOIN entities s ON r.source_id = s.id
        JOIN entities t ON r.target_id = t.id
        WHERE r.type = 'WORKED_AT' AND NOT (s.type='Person' AND t.type IN ('Organization','Company'))
    """)
    bad_worked_at = cur.fetchall()
    if bad_worked_at:
        print(f"[FAIL] {len(bad_worked_at)} WORKED_AT relationships with wrong entity types")
        issues += len(bad_worked_at)

    n_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    n_rels = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
    n_evidence = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    n_disputed = conn.execute("SELECT COUNT(*) FROM relationships WHERE status='disputed'").fetchone()[0]

    print(f"\nTotals: {n_entities} entities, {n_rels} relationships, {n_evidence} evidence rows, "
          f"{n_disputed} disputed relationship(s)")
    print(f"Total validation issues flagged: {issues} (warnings are informational, not release-blocking "
          f"for this draft version; a real CI gate per the blueprint would fail the release on [FAIL] items only)")
    return issues


def sample_queries(conn):
    print("\n=== SAMPLE QUERIES (proving the graph is queryable) ===")

    print("\n-- Q: What projects has Harshith built? --")
    for row in conn.execute("""
        SELECT e.canonical_name FROM relationships r
        JOIN entities e ON r.target_id = e.id
        WHERE r.type='BUILT' ORDER BY e.canonical_name
    """):
        print("  -", row[0])

    print("\n-- Q: Which projects use Python? --")
    for row in conn.execute("""
        SELECT p.canonical_name FROM relationships r
        JOIN entities p ON r.source_id = p.id
        JOIN entities t ON r.target_id = t.id
        WHERE r.type='USES' AND t.canonical_name='Python' AND p.type='Project'
    """):
        print("  -", row[0])

    print("\n-- Q: What research/publications exist, and who co-authored them? --")
    for row in conn.execute("""
        SELECT pub.canonical_name, GROUP_CONCAT(pe.canonical_name, ', ')
        FROM entities pub
        JOIN relationships r ON r.target_id = pub.id AND r.type IN ('AUTHORED','CONTRIBUTED_TO')
        JOIN entities pe ON r.source_id = pe.id
        WHERE pub.type='Publication'
        GROUP BY pub.id
    """):
        print("  -", row[0], "| co-authors:", row[1])

    print("\n-- Q: What is Harshith's educational background? (with evidence) --")
    for row in conn.execute("""
        SELECT ed.canonical_name, ev.source_ref, ev.excerpt
        FROM relationships r
        JOIN entities ed ON r.target_id = ed.id
        JOIN evidence ev ON ev.relationship_id = r.id
        WHERE r.type='STUDIED'
    """):
        print("  -", row[0])
        print("    evidence:", row[1], "|", row[2])

    print("\n-- Q: Which facts are marked disputed / low-confidence (need owner review)? --")
    for row in conn.execute("""
        SELECT s.canonical_name, r.type, t.canonical_name, r.confidence, r.status
        FROM relationships r
        JOIN entities s ON r.source_id = s.id
        JOIN entities t ON r.target_id = t.id
        WHERE r.status='disputed' OR r.confidence < 0.7
    """):
        print("  -", row)


if __name__ == "__main__":
    import os
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = build()
    issues = validate(conn)
    sample_queries(conn)
    conn.close()
    print(f"\nKnowledge graph written to {DB_PATH} (knowledge_version={KNOWLEDGE_VERSION})")
