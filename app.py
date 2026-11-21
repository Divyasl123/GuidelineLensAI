
import os
import re
import json
import sqlite3
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify, render_template
from pypdf import PdfReader


# --------------------------------------------------
# APP CONFIGURATION
# --------------------------------------------------

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent

database_setting = os.environ.get("DATABASE_PATH", "database.db")
DATABASE_PATH = Path(database_setting)

if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = BASE_DIR / DATABASE_PATH


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

def now():
    return datetime.now().isoformat(timespec="seconds")


def db():
    connection = sqlite3.connect(str(DATABASE_PATH))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def table_columns(connection, table_name):
    rows = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {row["name"] for row in rows}


def add_missing_columns(connection, table_name, columns):
    existing = table_columns(connection, table_name)

    for column_name, column_type in columns.items():
        if column_name not in existing:
            connection.execute(
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN {column_name} {column_type}"
            )


# --------------------------------------------------
# DATABASE INITIALIZATION
# --------------------------------------------------

def initialize_database():
    connection = db()

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS guidelines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                category TEXT,
                description TEXT,
                rules TEXT,
                created_at TEXT
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                findings TEXT,
                created_at TEXT,
                status TEXT
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER,
                finding_index INTEGER,
                decision TEXT,
                decision_time TEXT,
                FOREIGN KEY(review_id) REFERENCES reviews(id)
            )
        """)

        add_missing_columns(connection, "guidelines", {
            "name": "TEXT",
            "category": "TEXT",
            "description": "TEXT",
            "rules": "TEXT",
            "created_at": "TEXT"
        })

        add_missing_columns(connection, "reviews", {
            "content": "TEXT",
            "findings": "TEXT",
            "created_at": "TEXT",
            "status": "TEXT"
        })

        add_missing_columns(connection, "decisions", {
            "review_id": "INTEGER",
            "finding_index": "INTEGER",
            "decision": "TEXT",
            "decision_time": "TEXT"
        })

        connection.commit()

    finally:
        connection.close()


initialize_database()


# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------

def parse_json(value, fallback=None):
    if fallback is None:
        fallback = []

    if not value:
        return fallback

    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return fallback


def clean_text(value):
    return str(value or "").strip()


def make_guideline_display_name(name, description, guideline_id):
    name = clean_text(name)

    if name and name.lower() not in (
        "untitled",
        "untitled guideline"
    ):
        return name

    description = clean_text(description)

    if description:
        words = description.split()
        generated = " ".join(words[:6])

        if len(generated) > 55:
            generated = generated[:52].rstrip() + "..."

        return generated

    return f"Guideline #{guideline_id}"


def get_guidelines_rows():
    connection = db()

    try:
        rows = connection.execute(
            "SELECT * FROM guidelines ORDER BY id DESC"
        ).fetchall()

        result = []

        for row in rows:
            item = dict(row)

            description = clean_text(item.get("description"))
            name = clean_text(item.get("name"))
            category = clean_text(item.get("category"))

            # Support older records that stored their rule
            # information in a JSON rules column.
            stored_rules = parse_json(item.get("rules"), {})

            if isinstance(stored_rules, dict):
                description = (
                    description
                    or clean_text(stored_rules.get("description"))
                    or clean_text(stored_rules.get("rule_description"))
                )

                name = (
                    name
                    or clean_text(stored_rules.get("name"))
                    or clean_text(stored_rules.get("rule_name"))
                )

                category = (
                    category
                    or clean_text(stored_rules.get("category"))
                )

            elif isinstance(stored_rules, list):
                description = description or " ".join(
                    clean_text(rule) for rule in stored_rules
                )

            if not category:
                category = "Other"

            display_name = make_guideline_display_name(
                name,
                description,
                item.get("id")
            )

            result.append({
                "id": item.get("id"),
                "rule_name": display_name,
                "category": category,
                "rule_description": description,
                "created_at": item.get("created_at")
            })

        return result

    finally:
        connection.close()


# --------------------------------------------------
# FINDING HELPERS
# --------------------------------------------------

def make_finding(
    finding_type,
    severity,
    phrase,
    explanation,
    rule_name,
    suggestion
):
    return {
        "type": finding_type,
        "severity": severity,
        "phrase": phrase,
        "explanation": explanation,
        "rule_name": rule_name,
        "suggestion": suggestion,
        "decision": "Pending"
    }


def add_matches(
    findings,
    content,
    pattern,
    finding_type,
    severity,
    explanation,
    rule_name,
    suggestion
):
    try:
        matches = re.finditer(
            pattern,
            content,
            flags=re.IGNORECASE
        )
    except re.error:
        return

    for match in matches:
        phrase = match.group(0).strip()

        if not phrase:
            continue

        findings.append(
            make_finding(
                finding_type,
                severity,
                phrase,
                explanation,
                rule_name,
                suggestion
            )
        )


# --------------------------------------------------
# BUILT-IN CONTENT CHECKS
# --------------------------------------------------

BUILT_IN_RULES = [
    {
        "pattern": r"\bguarantee(?:d|s)?\b",
        "type": "Unverified Guarantee",
        "severity": "high",
        "explanation": "Guarantee-related wording may create an unsupported promise.",
        "suggestion": "Use qualified language that accurately describes the product."
    },
    {
        "pattern": r"\b100\s*%(?!\w)",
        "type": "Absolute Performance Claim",
        "severity": "high",
        "explanation": "A 100% claim may be misleading without reliable supporting evidence.",
        "suggestion": "Use a specific, verifiable statement supported by evidence."
    },
    {
        "pattern": r"\b(?:cure|cures|cured|treat|treats|treatment)\b",
        "type": "Medical Claim",
        "severity": "high",
        "explanation": "Medical claims may require appropriate evidence and regulatory approval.",
        "suggestion": "Avoid unsupported medical claims and use approved product wording."
    },
    {
        "pattern": r"\binstant(?:ly)?\b",
        "type": "Unverified Speed Claim",
        "severity": "medium",
        "explanation": "Instant results may imply a performance promise.",
        "suggestion": "Describe the actual expected process or time."
    },
    {
        "pattern": r"\bno side effects\b",
        "type": "Absolute Safety Claim",
        "severity": "high",
        "explanation": "Absolute safety claims can be misleading without appropriate evidence.",
        "suggestion": "Use accurate, evidence-supported safety information."
    },
    {
        "pattern": r"\bclinically proven\b",
        "type": "Evidence-Based Claim",
        "severity": "high",
        "explanation": "This phrase implies clinical evidence that should be available and verifiable.",
        "suggestion": "Use only when supported by appropriate clinical evidence."
    },
    {
        "pattern": r"\b(?:best|number one|no\.?\s*1|#1)\b",
        "type": "Superiority Claim",
        "severity": "medium",
        "explanation": "Superiority claims may require clear and reliable comparative evidence.",
        "suggestion": "Use a measurable product benefit instead."
    },
    {
        "pattern": r"\b(?:zero effort|effortless)\b",
        "type": "Unrealistic Effort Claim",
        "severity": "medium",
        "explanation": "This wording may create unrealistic expectations.",
        "suggestion": "Describe the actual ease of use without absolute promises."
    },
    {
        "pattern": r"\bguys\b",
        "type": "Inclusive Language",
        "severity": "low",
        "explanation": "This informal expression may not match inclusive brand communication.",
        "suggestion": "Consider using 'everyone', 'customers' or 'team'."
    },
    {
        "pattern": r"\bcrazy deal\b",
        "type": "Informal Promotional Language",
        "severity": "low",
        "explanation": "This expression may not match a professional brand tone.",
        "suggestion": "Use a clear promotional description."
    },
    {
        "pattern": r"\bsuper cheap\b",
        "type": "Unapproved Price Wording",
        "severity": "medium",
        "explanation": "This phrase may not align with a professional brand voice.",
        "suggestion": "Consider using 'affordable' or 'cost-effective'."
    }
]


def analyze_text(content):
    findings = []

    # Built-in checks
    for rule in BUILT_IN_RULES:
        add_matches(
            findings=findings,
            content=content,
            pattern=rule["pattern"],
            finding_type=rule["type"],
            severity=rule["severity"],
            explanation=rule["explanation"],
            rule_name="Built-in Brand Safety Rule",
            suggestion=rule["suggestion"]
        )

    # Quantified performance claims
    add_matches(
        findings,
        content,
        r"\b(save|earn|increase|reduce)\s+\d+(?:\.\d+)?\s*%",
        "Quantified Performance Claim",
        "high",
        "A numerical performance claim should be supported by reliable evidence.",
        "Evidence Verification",
        "Include verifiable data or qualify the claim."
    )

    # Universal claims
    add_matches(
        findings,
        content,
        r"\b(?:everyone|all customers|every customer|always|never)\b",
        "Universal Claim",
        "medium",
        "Universal wording may overstate the product's capabilities or audience.",
        "Universal Claims",
        "Use more specific and accurate wording."
    )

    # Custom brand guidelines
    guidelines = get_guidelines_rows()

    for guideline in guidelines:
        description = guideline["rule_description"]
        rule_name = guideline["rule_name"]

        if not description:
            continue

        # Find prohibited phrases.
        blocked_patterns = [
            r"""(?:do not use|don't use|never use|avoid|prohibited)\s+['"]?([^.'";]+)"""
        ]

        for blocked_pattern in blocked_patterns:
            blocked_matches = re.finditer(
                blocked_pattern,
                description,
                flags=re.IGNORECASE
            )

            for blocked_match in blocked_matches:
                phrase = blocked_match.group(1).strip().strip("'\"")

                if not phrase:
                    continue

                pattern = r"\b" + re.escape(phrase) + r"\b"

                add_matches(
                    findings,
                    content,
                    pattern,
                    "Brand Guideline Violation",
                    "high",
                    f"The phrase '{phrase}' is restricted by a saved brand guideline.",
                    rule_name,
                    "Replace it with wording that follows the saved brand guideline."
                )

        # Find required phrases.
        required_patterns = [
            r"""(?:must include|always include|should include|required phrase:|must use|always use)\s*['"]?([^.'";]+)"""
        ]

        for required_pattern in required_patterns:
            required_matches = re.finditer(
                required_pattern,
                description,
                flags=re.IGNORECASE
            )

            for required_match in required_matches:
                phrase = required_match.group(1).strip().strip("'\"")

                if not phrase:
                    continue

                if not re.search(
                    re.escape(phrase),
                    content,
                    flags=re.IGNORECASE
                ):
                    findings.append(
                        make_finding(
                            "Missing Required Phrase",
                            "medium",
                            phrase,
                            f"The saved guideline requires the phrase '{phrase}', but it was not found in the content.",
                            rule_name,
                            f"Consider including the approved phrase: {phrase}"
                        )
                    )

        # Check quoted phrases in guideline descriptions.
        quoted_phrases = re.findall(
            r"""['"]([^'"]{2,60})['"]""",
            description
        )

        for phrase in quoted_phrases:
            if re.search(
                r"(?:do not use|don't use|never use|avoid|prohibited)",
                description,
                flags=re.IGNORECASE
            ):
                continue

            if re.search(
                r"(?:must include|always include|should include|required phrase:|must use|always use)",
                description,
                flags=re.IGNORECASE
            ):
                continue

            # Quoted terms can be checked as restricted terminology
            # when the guideline uses prohibition language.
            if re.search(
                r"\b(?:avoid|prohibited|do not use|don't use|never use)\b",
                description,
                flags=re.IGNORECASE
            ):
                add_matches(
                    findings,
                    content,
                    r"\b" + re.escape(phrase) + r"\b",
                    "Restricted Terminology",
                    "medium",
                    f"The term '{phrase}' appears in a restricted terminology instruction.",
                    rule_name,
                    "Use approved alternative terminology."
                )

    # Remove duplicate findings.
    unique_findings = []
    seen = set()

    for finding in findings:
        key = (
            finding["type"].lower(),
            finding["phrase"].lower(),
            finding["rule_name"].lower()
        )

        if key not in seen:
            seen.add(key)
            unique_findings.append(finding)

    return unique_findings


# --------------------------------------------------
# REVIEW STATUS
# --------------------------------------------------

def calculate_review_status(findings):
    if not findings:
        return "clear"

    decisions = [
        finding.get("decision", "Pending")
        for finding in findings
    ]

    approved = decisions.count("Approved")
    rejected = decisions.count("Rejected")

    if approved == len(findings):
        return "approved"

    if rejected == len(findings):
        return "rejected"

    if approved + rejected == 0:
        return "pending_review"

    return "partially_reviewed"


# --------------------------------------------------
# HOME AND HEALTH ROUTES
# --------------------------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "application": "GuidelineLens AI",
        "time": now()
    })


# --------------------------------------------------
# GUIDELINE ROUTES
# --------------------------------------------------

@app.route("/api/guidelines", methods=["GET"])
def list_guidelines():
    return jsonify({
        "items": get_guidelines_rows()
    })


@app.route("/api/guidelines", methods=["POST"])
def add_guideline():
    data = request.get_json(silent=True) or {}

    name = clean_text(data.get("name"))
    category = clean_text(data.get("category")) or "Other"
    description = clean_text(data.get("description"))

    if not name or not description:
        return jsonify({
            "error": "Guideline name and description are required."
        }), 400

    if len(name) > 100 or len(description) > 5000:
        return jsonify({
            "error": "Guideline name or description is too long."
        }), 400

    connection = db()

    try:
        cursor = connection.execute("""
            INSERT INTO guidelines
            (name, category, description, rules, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            category,
            description,
            json.dumps({
                "name": name,
                "category": category,
                "description": description
            }),
            now()
        ))

        connection.commit()

        return jsonify({
            "message": "Guideline saved successfully.",
            "id": cursor.lastrowid
        }), 201

    finally:
        connection.close()


@app.route("/api/guidelines/<int:guideline_id>", methods=["DELETE"])
def delete_guideline(guideline_id):
    connection = db()

    try:
        cursor = connection.execute(
            "DELETE FROM guidelines WHERE id = ?",
            (guideline_id,)
        )

        connection.commit()

        if cursor.rowcount == 0:
            return jsonify({
                "error": "Guideline not found."
            }), 404

        return jsonify({
            "message": "Guideline deleted successfully."
        })

    finally:
        connection.close()


# --------------------------------------------------
# PDF GUIDELINE EXTRACTION
# --------------------------------------------------

@app.route("/api/guidelines/extract-pdf", methods=["POST"])
def extract_guideline_pdf():
    if "file" not in request.files:
        return jsonify({
            "error": "Please upload a PDF file."
        }), 400

    uploaded_file = request.files["file"]

    if not uploaded_file.filename:
        return jsonify({
            "error": "No file selected."
        }), 400

    if not uploaded_file.filename.lower().endswith(".pdf"):
        return jsonify({
            "error": "Only PDF files are supported."
        }), 400

    try:
        reader = PdfReader(uploaded_file)

        if reader.is_encrypted:
            return jsonify({
                "error": "Encrypted PDFs are not supported."
            }), 400

        extracted_pages = []

        for page in reader.pages:
            extracted_pages.append(page.extract_text() or "")

        extracted_text = "\n".join(extracted_pages).strip()

        if not extracted_text:
            return jsonify({
                "error": "No selectable text was found. This PDF may contain scanned images."
            }), 400

        suggested_rules = []

        for line in extracted_text.splitlines():
            line = re.sub(r"\s+", " ", line).strip()

            if len(line) < 12 or len(line) > 500:
                continue

            instruction_pattern = (
                r"\b("
                r"must|should|always|never|avoid|"
                r"do not|don't|prohibited|required|"
                r"ensure|use|include|exclude"
                r")\b"
            )

            if re.search(
                instruction_pattern,
                line,
                flags=re.IGNORECASE
            ):
                suggested_rules.append(line)

        # Remove duplicate suggestions while preserving order.
        unique_suggestions = []
        seen = set()

        for rule in suggested_rules:
            key = rule.lower()

            if key not in seen:
                seen.add(key)
                unique_suggestions.append(rule)

        return jsonify({
            "suggested_rules": unique_suggestions[:100],
            "extracted_text": extracted_text[:50000]
        })

    except Exception:
        app.logger.exception("PDF extraction failed")

        return jsonify({
            "error": "Could not read this PDF. Please check the file and try again."
        }), 400


# --------------------------------------------------
# CONTENT ANALYSIS ROUTE
# --------------------------------------------------

@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True) or {}

    content = clean_text(data.get("content"))

    if not content:
        return jsonify({
            "error": "Please provide content for analysis."
        }), 400

    if len(content) > 50000:
        return jsonify({
            "error": "Content exceeds the maximum length of 50,000 characters."
        }), 400

    findings = analyze_text(content)
    review_status = calculate_review_status(findings)

    connection = db()

    try:
        cursor = connection.execute("""
            INSERT INTO reviews
            (content, findings, created_at, status)
            VALUES (?, ?, ?, ?)
        """, (
            content,
            json.dumps(findings),
            now(),
            review_status
        ))

        connection.commit()

        return jsonify({
            "review_id": cursor.lastrowid,
            "findings": findings,
            "status": review_status
        })

    finally:
        connection.close()


# --------------------------------------------------
# APPROVE / REJECT DECISIONS
# --------------------------------------------------

@app.route("/api/decisions", methods=["POST"])
def save_decision():
    data = request.get_json(silent=True) or {}

    review_id = data.get("review_id")
    finding_index = data.get("finding_index")
    decision = clean_text(data.get("decision"))

    if decision not in ("Approved", "Rejected"):
        return jsonify({
            "error": "Decision must be Approved or Rejected."
        }), 400

    try:
        review_id = int(review_id)
        finding_index = int(finding_index)
    except (TypeError, ValueError):
        return jsonify({
            "error": "Invalid review or finding identifier."
        }), 400

    connection = db()

    try:
        review = connection.execute(
            "SELECT * FROM reviews WHERE id = ?",
            (review_id,)
        ).fetchone()

        if not review:
            return jsonify({
                "error": "Review not found."
            }), 404

        findings = parse_json(review["findings"], [])

        if not isinstance(findings, list):
            return jsonify({
                "error": "Review findings are invalid."
            }), 400

        if finding_index < 0 or finding_index >= len(findings):
            return jsonify({
                "error": "Finding not found."
            }), 404

        decision_time = now()

        findings[finding_index]["decision"] = decision
        findings[finding_index]["decision_time"] = decision_time

        status = calculate_review_status(findings)

        connection.execute("""
            INSERT INTO decisions
            (review_id, finding_index, decision, decision_time)
            VALUES (?, ?, ?, ?)
        """, (
            review_id,
            finding_index,
            decision,
            decision_time
        ))

        connection.execute("""
            UPDATE reviews
            SET findings = ?, status = ?
            WHERE id = ?
        """, (
            json.dumps(findings),
            status,
            review_id
        ))

        connection.commit()

        return jsonify({
            "message": "Decision recorded successfully.",
            "decision": decision,
            "decision_time": decision_time,
            "status": status
        })

    finally:
        connection.close()


# --------------------------------------------------
# AUDIT HISTORY ROUTE
# --------------------------------------------------

@app.route("/api/history", methods=["GET"])
def history():
    connection = db()

    try:
        rows = connection.execute("""
            SELECT * FROM reviews
            ORDER BY id DESC
        """).fetchall()

        items = []

        for row in rows:
            item = dict(row)

            findings = parse_json(item.get("findings"), [])

            if not isinstance(findings, list):
                findings = []

            items.append({
                "id": item.get("id"),
                "content": item.get("content") or "",
                "findings": findings,
                "created_at": item.get("created_at") or "",
                "status": item.get("status") or calculate_review_status(findings)
            })

        return jsonify({
            "items": items
        })

    finally:
        connection.close()


# --------------------------------------------------
# DASHBOARD STATISTICS
# --------------------------------------------------

@app.route("/api/stats", methods=["GET"])
def stats():
    connection = db()

    try:
        total_reviews = connection.execute(
            "SELECT COUNT(*) FROM reviews"
        ).fetchone()[0]

        total_guidelines = connection.execute(
            "SELECT COUNT(*) FROM guidelines"
        ).fetchone()[0]

        total_decisions = connection.execute(
            "SELECT COUNT(*) FROM decisions"
        ).fetchone()[0]

        return jsonify({
            "total_reviews": total_reviews,
            "total_guidelines": total_guidelines,
            "total_decisions": total_decisions
        })

    finally:
        connection.close()


# --------------------------------------------------
# ERROR HANDLERS
# --------------------------------------------------

@app.errorhandler(413)
def file_too_large(error):
    return jsonify({
        "error": "File is too large. Maximum upload size is 10 MB."
    }), 413


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({
            "error": "API endpoint not found."
        }), 404

    return "Page not found.", 404


@app.errorhandler(500)
def internal_error(error):
    app.logger.exception("Internal server error")

    if request.path.startswith("/api/"):
        return jsonify({
            "error": "An internal server error occurred."
        }), 500

    return "An internal server error occurred.", 500


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
