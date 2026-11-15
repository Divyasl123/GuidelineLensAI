
from flask import Flask, render_template, request, jsonify
import sqlite3
import json
import re
from datetime import datetime

app = Flask(__name__)

DATABASE = "database.db"


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guidelines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_name TEXT NOT NULL,
            category TEXT NOT NULL,
            rule_description TEXT NOT NULL,
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            findings TEXT NOT NULL,
            status TEXT DEFAULT 'Reviewed',
            created_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER NOT NULL,
            finding_index INTEGER NOT NULL,
            decision TEXT NOT NULL,
            created_at TEXT,
            FOREIGN KEY (review_id) REFERENCES reviews(id)
        )
    """)

    conn.commit()
    conn.close()


# --------------------------------------------------
# FINDING MANAGEMENT
# --------------------------------------------------

def add_finding(findings, issue, severity, phrase,
                explanation, suggestion, source="Built-in rule"):

    phrase = phrase.strip()

    if not phrase:
        return

    # Prevent duplicate findings for the same issue and phrase.
    key = (issue.lower(), phrase.lower())

    existing = {
        (item["type"].lower(), item["phrase"].lower())
        for item in findings
    }

    if key in existing:
        return

    findings.append({
        "type": issue,
        "severity": severity,
        "phrase": phrase,
        "explanation": explanation,
        "suggestion": suggestion,
        "rule_name": source
    })


# --------------------------------------------------
# CONTENT ANALYSIS
# --------------------------------------------------

def analyze_content(content, guidelines):

    findings = []
    text = content.lower()

    # Built-in content checks.
    checks = [
        {
            "pattern": r"\bguarantee(?:d|s)?\b",
            "issue": "Unsupported Promotional Guarantee",
            "severity": "high",
            "explanation": "The content makes a guarantee that may require supporting evidence and approval.",
            "suggestion": "Remove the guarantee unless it has been verified and approved."
        },
        {
            "pattern": r"\b100\s*%",
            "issue": "Absolute Promotional Claim",
            "severity": "high",
            "explanation": "An absolute 100% claim may mislead audiences if it is not supported by evidence.",
            "suggestion": "Use a specific, verifiable statement instead."
        },
        {
            "pattern": r"\bcures?\s+(?:all\s+)?diseases?\b",
            "issue": "Unsupported Health Claim",
            "severity": "high",
            "explanation": "The content makes a medical claim that requires reliable evidence and appropriate approval.",
            "suggestion": "Remove the medical claim unless it has been properly substantiated and approved."
        },
        {
            "pattern": r"\bworks?\s+instantly\b|\binstant\s+(?:results?|perfection|success)\b",
            "issue": "Unsupported Instant-Result Claim",
            "severity": "high",
            "explanation": "The content promises immediate results without supporting evidence.",
            "suggestion": "Replace the promise with a realistic, verifiable product benefit."
        },
        {
            "pattern": r"\bzero\s+effort\b",
            "issue": "Exaggerated Promotional Claim",
            "severity": "medium",
            "explanation": "The phrase suggests results without any effort and may create unrealistic expectations.",
            "suggestion": "Describe the actual effort or convenience accurately."
        },
        {
            "pattern": r"\bno\s+side\s+effects\b",
            "issue": "Unsupported Safety Claim",
            "severity": "high",
            "explanation": "An absolute safety statement requires strong supporting evidence.",
            "suggestion": "Use only approved and substantiated safety information."
        },
        {
            "pattern": r"\bclinically\s+proven\b",
            "issue": "Evidence-Required Claim",
            "severity": "high",
            "explanation": "This phrase implies clinical evidence that should be available and verified.",
            "suggestion": "Include approved evidence or remove the claim."
        },
        {
            "pattern": r"\bbest\s+in\s+the\s+world\b",
            "issue": "Unsubstantiated Superlative",
            "severity": "medium",
            "explanation": "This broad superiority claim needs supporting evidence.",
            "suggestion": "Use a specific, measurable product benefit."
        },
        {
            "pattern": r"\bcrazy\s+deal\b",
            "issue": "Exaggerated Promotional Language",
            "severity": "medium",
            "explanation": "This expression may not match a professional brand voice.",
            "suggestion": "Use a clear and professional description of the offer."
        },
        {
            "pattern": r"\bguys\b",
            "issue": "Informal Tone",
            "severity": "low",
            "explanation": "This informal address may not suit every brand communication channel.",
            "suggestion": "Use an audience-appropriate greeting."
        }
    ]

    for check in checks:
        for match in re.finditer(check["pattern"], content, re.IGNORECASE):
            add_finding(
                findings,
                check["issue"],
                check["severity"],
                match.group(),
                check["explanation"],
                check["suggestion"]
            )

    # Check saved brand guidelines.
    for rule in guidelines:

        name = rule["rule_name"]
        category = rule["category"].lower()
        description = rule["rule_description"]
        desc = description.lower()

        # Detect prohibited terminology and optional replacement.
        blocked_match = re.search(
            r"""(?:do not use|don't use|avoid)\s+["']?([^"'.]+?)["']?(?:\.\s*use\s+["']?([^"'.]+?)["']?)?(?:\s+instead)?(?:\.|$)""",
            desc
        )

        if blocked_match:
            blocked = blocked_match.group(1).strip()
            replacement = blocked_match.group(2)

            if blocked and re.search(
                r"\b" + re.escape(blocked) + r"\b",
                text
            ):
                suggestion = (
                    f"Replace '{blocked}' with '{replacement.strip()}'."
                    if replacement else
                    f"Remove or revise '{blocked}'."
                )

                add_finding(
                    findings,
                    "Brand Guideline Violation",
                    "medium",
                    blocked,
                    f"Content conflicts with '{name}': {description}",
                    suggestion,
                    name
                )

        # Detect required phrases.
        required_match = re.search(
            r"""(?:must include|always include|should include)\s+["']?([^"'.]+?)["']?(?:\.|$)""",
            desc
        )

        if required_match:
            required = required_match.group(1).strip()

            if required and required not in text:
                add_finding(
                    findings,
                    "Missing Required Brand Message",
                    "medium",
                    required,
                    f"The required phrase from '{name}' is missing: {description}",
                    f"Include the approved phrase: '{required}'.",
                    name
                )

        # Check claims-related guidelines.
        if (
            category in ["claims & facts", "claims", "facts"]
            and any(term in desc for term in [
                "unsupported guarantee",
                "unsupported claims",
                "absolute promotional claims",
                "promotional claims"
            ])
        ):
            match = re.search(
                r"\b(guarantee(?:d|s)?|100\s*%|instant|zero effort)\b",
                content,
                re.IGNORECASE
            )

            if match:
                add_finding(
                    findings,
                    "Saved Promotional Claims Rule",
                    "high",
                    match.group(),
                    f"Potential conflict with '{name}': {description}",
                    "Verify the claim with approved evidence or revise the wording.",
                    name
                )

        # Check tone-related guidelines.
        if (
            category in ["tone of voice", "tone"]
            and any(term in desc for term in [
                "professional",
                "avoid exaggerated",
                "avoid informal"
            ])
        ):
            for term in ["crazy deal", "super cheap", "hey guys"]:
                if term in text:
                    add_finding(
                        findings,
                        "Tone of Voice Violation",
                        "medium",
                        term,
                        f"Potential conflict with '{name}': {description}",
                        "Rewrite the expression using clear, friendly and professional language.",
                        name
                    )

    return findings


# --------------------------------------------------
# WEBSITE
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# --------------------------------------------------
# GUIDELINES
# --------------------------------------------------

@app.route("/api/guidelines", methods=["GET", "POST"])
def guidelines_api():

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":

        data = request.get_json(silent=True) or {}

        name = data.get("name", "").strip()
        category = data.get("category", "Other").strip()
        description = data.get("description", "").strip()

        if not name or not description:
            conn.close()
            return jsonify({
                "error": "Rule name and description are required."
            }), 400

        cursor.execute("""
            INSERT INTO guidelines
            (rule_name, category, rule_description, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            category,
            description,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        conn.close()

        return jsonify({
            "message": "Guideline saved successfully."
        }), 201

    cursor.execute("SELECT * FROM guidelines ORDER BY id DESC")
    items = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({"items": items})


@app.route("/api/guidelines/<int:rule_id>", methods=["DELETE"])
def delete_guideline(rule_id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM guidelines WHERE id = ?",
        (rule_id,)
    )

    deleted = cursor.rowcount

    conn.commit()
    conn.close()

    if not deleted:
        return jsonify({"error": "Guideline not found."}), 404

    return jsonify({"message": "Guideline deleted successfully."})


# --------------------------------------------------
# ANALYSE CONTENT
# --------------------------------------------------

@app.route("/api/analyze", methods=["POST"])
def analyze_api():

    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()

    if not content:
        return jsonify({"error": "Please provide content to analyse."}), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM guidelines ORDER BY id")
    guidelines = [dict(row) for row in cursor.fetchall()]

    findings = analyze_content(content, guidelines)

    status = "Needs Review" if findings else "No Issues Detected"

    cursor.execute("""
        INSERT INTO reviews
        (content, findings, status, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        content,
        json.dumps(findings),
        status,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    review_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return jsonify({
        "review_id": review_id,
        "findings": findings,
        "total_findings": len(findings),
        "status": status
    })


# --------------------------------------------------
# APPROVAL / REJECTION
# --------------------------------------------------

@app.route("/api/decisions", methods=["POST"])
def decisions_api():

    data = request.get_json(silent=True) or {}

    try:
        review_id = int(data.get("review_id"))
        finding_index = int(data.get("finding_index"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid review or finding ID."}), 400

    decision = data.get("decision", "").strip()

    if decision not in ["Approved", "Rejected"]:
        return jsonify({
            "error": "Decision must be Approved or Rejected."
        }), 400

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT findings FROM reviews WHERE id = ?",
        (review_id,)
    )

    review = cursor.fetchone()

    if not review:
        conn.close()
        return jsonify({"error": "Review not found."}), 404

    findings = json.loads(review["findings"])

    if finding_index < 0 or finding_index >= len(findings):
        conn.close()
        return jsonify({"error": "Finding not found."}), 404

    # Keep the latest decision for each finding.
    cursor.execute("""
        DELETE FROM decisions
        WHERE review_id = ? AND finding_index = ?
    """, (review_id, finding_index))

    cursor.execute("""
        INSERT INTO decisions
        (review_id, finding_index, decision, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        review_id,
        finding_index,
        decision,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "message": f"Decision recorded: {decision}."
    })


# --------------------------------------------------
# REVIEW HISTORY WITH DECISIONS
# --------------------------------------------------

@app.route("/api/history", methods=["GET"])
def history_api():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM reviews ORDER BY id DESC")
    rows = cursor.fetchall()

    items = []

    for row in rows:

        review = dict(row)

        try:
            review["findings"] = json.loads(review["findings"])
        except (TypeError, json.JSONDecodeError):
            review["findings"] = []

        cursor.execute("""
            SELECT finding_index, decision, created_at
            FROM decisions
            WHERE review_id = ?
            ORDER BY id DESC
        """, (review["id"],))

        decisions = {
            str(d["finding_index"]): {
                "decision": d["decision"],
                "created_at": d["created_at"]
            }
            for d in cursor.fetchall()
        }

        for index, finding in enumerate(review["findings"]):
            finding["decision"] = decisions.get(
                str(index), {}
            ).get("decision", "Pending")

            finding["decision_time"] = decisions.get(
                str(index), {}
            ).get("created_at")

        review["decisions"] = decisions

        items.append(review)

    conn.close()

    return jsonify({"items": items})


# --------------------------------------------------
# DASHBOARD STATISTICS
# --------------------------------------------------

@app.route("/api/stats", methods=["GET"])
def stats_api():

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM reviews")
    total_reviews = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM guidelines")
    total_guidelines = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM decisions")
    total_decisions = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        "total_reviews": total_reviews,
        "total_guidelines": total_guidelines,
        "total_decisions": total_decisions
    })


# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

initialize_database()

if __name__ == "__main__":
    app.run(debug=True)
