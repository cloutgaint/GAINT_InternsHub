from __future__ import annotations

import hashlib
import re


TASK_COUNTS = {"FASTTRACK": 1, "45_DAYS": 3, "SEMESTER": 8}
LEARNING_DAYS = {"FASTTRACK": 0, "45_DAYS": 10, "SEMESTER": 30}


TECH_CATALOG = {
    "Python": [
        ("Movie Recommendation Engine", ["dataset preprocessing", "similarity scoring", "personalised recommendations", "evaluation report"]),
        ("Fake News Detection System", ["text cleaning", "feature extraction", "classification model", "prediction API"]),
        ("Data Analytics Dashboard", ["CSV ingestion", "data validation", "statistical analysis", "report generation"]),
    ],
    "Java": [
        ("Student Management API", ["student records", "validation", "REST endpoints", "database persistence"]),
        ("Library Management System", ["book catalogue", "member records", "issue and return workflow", "fine calculation"]),
        ("Employee Leave Portal", ["employee profiles", "leave requests", "approval workflow", "leave balance report"]),
    ],
    "Node.js": [
        ("College Event Management API", ["event catalogue", "student registrations", "seat limits", "organiser reports"]),
        ("Attendance Tracking API", ["student roster", "check-in records", "attendance percentage", "absence reports"]),
        ("Job Portal Backend", ["user accounts", "job listings", "applications", "recruiter dashboard APIs"]),
    ],
    "Next.js": [
        ("College Placement Portal", ["student profiles", "company listings", "application tracking", "placement dashboard"]),
        ("Internship Progress Dashboard", ["student onboarding", "task tracking", "mentor feedback", "progress reports"]),
        ("Real Estate Listing Portal", ["property listings", "filters and search", "enquiries", "responsive dashboard"]),
    ],
    "Django": [
        ("Learning Management System", ["courses", "student enrolment", "lesson progress", "assessment reports"]),
        ("Hospital Appointment System", ["doctor schedules", "patient registration", "appointments", "visit reports"]),
        ("Inventory Management System", ["product catalogue", "stock movement", "low-stock alerts", "inventory reports"]),
    ],
}


VARIANT_CONTEXTS = [
    "Campus Operations", "Healthcare Services", "Retail Operations", "NGO Programs",
    "Local Business", "Smart City Services", "Training Institute", "Community Services",
]


def project_ideas(technology: str, domain: str, count: int) -> list[dict]:
    catalogue = TECH_CATALOG[technology]
    ideas = []
    for index in range(count):
        base_title, base_features = catalogue[index % len(catalogue)]
        title = base_title if domain.lower() == "general" else f"{domain} {base_title}"
        features = [f"{domain} {item}" if domain.lower() != "general" else item for item in base_features]
        ideas.append({
            "title": title,
            "features": features,
            "description": f"Build a production-style {title} using {technology}. The project covers " + ", ".join(features) + ".",
        })
    return ideas


def project_idea_from_prompt(prompt: str, technology: str, domain: str) -> dict:
    """Turn an Admin brief into a reviewable project draft without an external AI dependency."""
    clean = re.sub(r"\s+", " ", prompt).strip()
    first_sentence = re.split(r"[.!?]", clean, maxsplit=1)[0]
    title = re.sub(r"^(please\s+)?(build|create|develop|make|generate)\s+(an?\s+)?", "", first_sentence, flags=re.I)
    title = re.sub(rf"\b(using|with)\s+{re.escape(technology)}\b.*$", "", title, flags=re.I).strip(" :-")
    words = title.split()[:10]
    title = " ".join(words).title() if words else f"{domain} {technology} Project"
    if not re.search(r"\b(system|portal|platform|application|app|dashboard|api|engine)\b", title, re.I):
        title += " System"

    feature_text = ""
    feature_match = re.search(r"\b(?:features?|including|include|with)\s*[:\-]?\s*(.+)", clean, re.I)
    if feature_match:
        feature_text = feature_match.group(1)
    candidates = [
        re.sub(r"^[\d.\-•\s]+", "", item).strip(" .")
        for item in re.split(r"[,;|]|\band\b", feature_text, flags=re.I)
    ]
    features = [item[:90] for item in candidates if 3 <= len(item) <= 120][:6]
    if len(features) < 3:
        features.extend(["secure user workflow", "validated data management", "search and reports", "automated testing"])
    features = list(dict.fromkeys(features))[:6]
    return {
        "title": title[:180],
        "features": features,
        "description": f"Admin project brief: {clean}",
    }


def judge_checkpoint(order_no: int, project_title: str, stage_title: str) -> tuple[str, list[dict]]:
    """Create a domain checkpoint that measures work used by the selected project.

    Each checkpoint has one visible example and two hidden edge cases. The three
    tests are checks inside one task; they are not three separate tasks.
    """
    entity = "record"
    lowered = project_title.lower()
    for keyword, label in {
        "movie": "movie", "student": "student", "library": "book",
        "employee": "employee", "event": "event", "attendance": "attendance record",
        "job": "job", "placement": "application", "internship": "milestone",
        "property": "property", "learning": "course", "hospital": "appointment",
        "inventory": "product", "news": "article", "analytics": "data row",
    }.items():
        if keyword in lowered:
            entity = label
            break

    checkpoints = [
        (
            f"Implement the {entity} intake validator. Read N, then N lines in id|name|category format. Ignore malformed lines and repeated IDs; print the accepted IDs in original order separated by one space, or NONE.",
            [("5\nM1|Alpha|Drama\nM2|Beta|Comedy\nM1|Copy|Drama\nbad\nM3|Gamma|Drama", "M1 M2 M3"),
             ("3\nS7|Asha|CSE\nS8|Ravi|ECE\nS9|Mina|CSE", "S7 S8 S9"),
             ("2\ninvalid\nalso-invalid", "NONE")],
        ),
        (
            f"Implement {entity} category search. Read a category, then N, then N name|category lines. Print matching names alphabetically, one per line; category matching is case-insensitive. Print NONE when no item matches.",
            [("Drama\n4\nAlpha|Drama\nBeta|Comedy\nGamma|drama\nDelta|Action", "Alpha\nGamma"),
             ("CSE\n3\nRavi|ECE\nAsha|CSE\nMina|cse", "Asha\nMina"),
             ("Health\n2\nOne|Retail\nTwo|Education", "NONE")],
        ),
        (
            f"Build the {entity} status summary. Read N and N id|status lines. Valid statuses are ACTIVE, PENDING and CLOSED. Ignore malformed records and print ACTIVE=x PENDING=y CLOSED=z.",
            [("5\nA1|ACTIVE\nA2|PENDING\nA3|ACTIVE\nA4|CLOSED\nbad", "ACTIVE=2 PENDING=1 CLOSED=1"),
             ("3\nX|closed\nY|CLOSED\nZ|pending", "ACTIVE=0 PENDING=1 CLOSED=2"),
             ("0", "ACTIVE=0 PENDING=0 CLOSED=0")],
        ),
        (
            f"Implement {entity} ranking. Read N and N name|score lines. Print the name with the highest numeric score. Break ties alphabetically and print NONE for no valid rows.",
            [("4\nAlpha|82\nBeta|91\nGamma|91\nBad|x", "Beta"),
             ("3\nZed|-2\nAmy|-2\nKim|-5", "Amy"),
             ("2\nbad\nalso-bad", "NONE")],
        ),
        (
            f"Implement the {entity} work queue. Read N commands: ADD id, DONE id or LIST. ADD keeps IDs unique, DONE removes an ID, and each LIST prints the current IDs separated by one space or EMPTY.",
            [("6\nADD A1\nADD A2\nADD A1\nLIST\nDONE A1\nLIST", "A1 A2\nA2"),
             ("4\nLIST\nADD X\nDONE X\nLIST", "EMPTY\nEMPTY"),
             ("5\nADD B\nADD A\nDONE Z\nLIST\nLIST", "B A\nB A")],
        ),
        (
            f"Add role protection for the {entity} module. Read a role and an action. ADMIN allows CREATE, UPDATE, DELETE, VIEW; MENTOR allows UPDATE and VIEW; STUDENT allows VIEW. Print ALLOWED or DENIED.",
            [("MENTOR\nUPDATE", "ALLOWED"), ("STUDENT\nDELETE", "DENIED"), ("ADMIN\nCREATE", "ALLOWED")],
        ),
        (
            f"Create the {entity} metrics calculation. Read space-separated integers and print count|min|max|average, with average rounded to two decimal places. Print EMPTY when no integers are supplied.",
            [("10 20 30 40", "4|10|40|25.00"), ("-5 5", "2|-5|5|0.00"), ("", "EMPTY")],
        ),
        (
            f"Create the final {entity} release gate. Read N check results containing PASS or FAIL. Print READY when every check passes; otherwise print BLOCKED followed by the number of failed checks.",
            [("4\nPASS\nPASS\nPASS\nPASS", "READY"), ("5\nPASS\nFAIL\nPASS\nFAIL\nPASS", "BLOCKED 2"), ("1\nFAIL", "BLOCKED 1")],
        ),
    ]
    base_prompt, values = checkpoints[(order_no - 1) % len(checkpoints)]
    prompt = f"{stage_title} checkpoint for {project_title}: {base_prompt} Complete it in the required local checkpoint file. Judge0 runs 3 checks: 1 visible example and 2 hidden edge cases."
    cases = [
        {"stdin": stdin + "\n", "expected_output": output + "\n", "visible": index == 0}
        for index, (stdin, output) in enumerate(values)
    ]
    return prompt, cases


def task_specs(title: str, technology: str, features: list[str], internship_type: str) -> list[dict]:
    features = features or ["core workflow", "validation", "reports", "testing"]
    count = TASK_COUNTS[internship_type]
    if count == 1:
        stages = [("Complete Project Development", f"Build and deliver the complete {title} in {technology}, including {', '.join(features)}.")]
    elif count == 3:
        stages = [
            ("Foundation and Data Layer", f"Create the {technology} project structure, data model and configuration for {title}. Implement {features[0]} securely."),
            ("Core Features and Integration", f"Continue in the same VS Code project. Implement {', '.join(features[1:3] or features)} and connect them to the existing data layer."),
            ("Testing, Documentation and Final Delivery", f"Complete {features[-1]}, validate all workflows, add automated tests, prepare documentation and produce the final working {title}."),
        ]
    else:
        stages = [
            ("Project Setup and Architecture", f"Create the {technology} workspace for {title}. Document architecture, folders, dependencies and environment setup."),
            ("Data Model and Validation", f"Design the database/data model and implement input validation required for {features[0]}."),
            (f"Implement {features[0].title()}", f"Implement {features[0]} in the existing project and connect it to the data model."),
            (f"Implement {features[1 % len(features)].title()}", f"Implement {features[1 % len(features)]} and integrate it with all earlier work."),
            (f"Implement {features[2 % len(features)].title()}", f"Implement {features[2 % len(features)]} with clear error handling and meaningful user feedback."),
            ("Security and Edge Cases", "Add authentication/authorisation where relevant, validation, error handling and protection for important edge cases."),
            ("Automated Testing and Quality", "Add unit/integration tests, run the complete build, correct failures and document test evidence."),
            ("Final Integration and Local College Submission", f"Integrate every module, finish {features[-1]}, prepare README, screenshots and database schema for direct college submission from the local computer."),
        ]

    project_rules = {
        "Python": (["src", "tests", "README.md"], ["python -m pytest -q"]),
        "Django": (["config", "manage.py", "README.md"], ["python manage.py check"]),
        "Java": (["src", "pom.xml", "README.md"], ["mvn test -q"]),
        "Node.js": (["src", "tests", "package.json", "README.md"], ["npm test"]),
        "Next.js": (["app", "package.json", "README.md"], ["npm run build"]),
    }
    required_paths, local_checks = project_rules[technology]
    tasks = []
    extension = {"Python": "py", "Django": "py", "Java": "java", "Node.js": "js", "Next.js": "js"}[technology]
    for order_no, (stage_title, description) in enumerate(stages, start=1):
        challenge_prompt, judge0_cases = judge_checkpoint(order_no, title, stage_title)
        tasks.append({
            "order_no": order_no,
            "title": stage_title,
            "description": description,
            "deliverables": [
                "Working code saved in the same local VS Code project",
                "README update explaining the completed work",
                "Task checkpoint file submitted through the GAINT VS Code extension",
            ],
            "acceptance_criteria": [
                "Project builds or starts without errors",
                "New work is integrated with previous tasks",
                "Input validation and clear error handling are present",
                "Required local project modules contain the completed work",
            ],
            "visible_tests": ["Run the documented build/start command", "Demonstrate the main success workflow"],
            "hidden_checks": ["Invalid input and edge-case review", "Code similarity and project integration review"],
            "checkpoint_file": f"gaint_checkpoints/task_{order_no}.{extension}",
            "challenge_prompt": challenge_prompt,
            "judge0_cases": judge0_cases,
            "required_paths": required_paths,
            "local_checks": local_checks,
        })
    return tasks


def personalised_variant(student_id: int, project_title: str, domain: str) -> tuple[str, str, str]:
    seed = hashlib.sha256(f"GAINT:{student_id}:{project_title}".encode()).hexdigest()[:12].upper()
    context = VARIANT_CONTEXTS[int(seed[:4], 16) % len(VARIANT_CONTEXTS)]
    variant_title = f"{project_title} – {context} Variant"
    brief = (
        f"Build the project for a {context.lower()} use case. Use assignment reference {seed} in sample data and documentation. "
        f"Include at least three requirements specific to {domain or context}. Your data, naming and screenshots must be your own."
    )
    return variant_title, brief, seed
