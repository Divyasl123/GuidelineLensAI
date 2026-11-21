# GuidelineLens AI

## Self-Improving Brand Governance & Guideline Intelligence Platform

**Detect Inconsistencies. Understand the Rules. Improve Brand Trust.**

## About the Project

GuidelineLens AI is a web-based brand governance platform designed to help organisations maintain consistent brand communication.

It reviews marketing content against built-in checks and custom brand guidelines, identifies potential violations, explains detected issues, and provides suggestions for improvement.

The platform also supports PDF-based guideline extraction, allowing users to upload guideline documents, review extracted text and select suggested rules to save.

Human reviewers can approve or reject findings, while the Audit History maintains a record of review activities and decisions.

## Live Application

**Live Demo:** https://guidelinelensai.onrender.com

**Source Code:** https://github.com/Divyasl123/GuidelineLensAI

## Key Features

- **Content Review:** Submit marketing content for guideline compliance checks.
- **Brand Guideline Management:** Create, organise and manage custom brand guidelines.
- **Rule-Based Detection:** Identify potential content violations using predefined checks and saved guidelines.
- **Severity Classification:** Classify detected issues as High, Medium or Low.
- **PDF Guideline Extraction:** Upload PDF documents and extract their text for guideline review.
- **Suggested Corrections:** Display explanations and recommendations for detected issues.
- **Human Review:** Approve or reject detected findings.
- **Guideline Intelligence:** Access guideline-related information through a dedicated section.
- **Audit History:** Track previous reviews and reviewer decisions.
- **Dashboard Statistics:** View an overview of reviews, guidelines and decisions.

## Technology Stack

| Component | Technologies |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, Flask |
| Database | SQLite |
| PDF Processing | pypdf |
| Deployment | Render |
| Server | Gunicorn |
| Version Control | GitHub |

## How It Works

1. **Submit Content:** Enter the marketing content that needs to be reviewed.
2. **Check Guidelines:** The system compares the submitted content against built-in checks and saved brand guidelines.
3. **Detect Issues:** Potential violations are identified and classified by severity.
4. **Review Suggestions:** Users receive explanations and suggested corrections.
5. **Make Decisions:** Human reviewers can approve or reject the findings.
6. **Track History:** Review activities and decisions are available through Audit History.

### PDF Guideline Workflow

1. Upload a PDF containing brand guideline information.
2. Extract the text from the uploaded document.
3. Review the extracted content and suggested guideline rules.
4. Select relevant suggestions and save them to Brand Guidelines.

## Project Structure

```text
GuidelineLensAI/
│
├── app.py
├── requirements.txt
├── .gitignore
├── README.md
│
└── templates/
    └── index.html
```

## Installation and Execution

### 1. Clone the Repository

```bash
git clone https://github.com/Divyasl123/GuidelineLensAI.git
```

### 2. Navigate to the Project Directory

```bash
cd GuidelineLensAI
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Application

```bash
python app.py
```

### 5. Open in Browser

```text
http://127.0.0.1:5000/
```

## Future Enhancements

- **Advanced Semantic Analysis:** Integrate language models to understand content context beyond rule-based matching.
- **Visual Brand Compliance:** Introduce image analysis to check logos, colours, typography and visual consistency.
- **Advanced Guideline Intelligence:** Improve guideline extraction and identify conflicting or outdated rules.
- **Compliance Report Export:** Generate downloadable reports of review results.
- **Multi-User Collaboration:** Introduce authentication, user roles and collaborative review workflows.
- **Before-and-After Comparison:** Provide a clearer comparison of original and corrected content.

## Project Status

**Working Web Application – Deployed on Render**

GuidelineLens AI currently supports text-based content review, custom brand guideline management, PDF text extraction, human review decisions and audit history.

The platform uses rule-based analysis and is being developed further with advanced semantic and visual compliance capabilities.

---

*GuidelineLens AI – Building Consistent and Trustworthy Brand Communication.*
