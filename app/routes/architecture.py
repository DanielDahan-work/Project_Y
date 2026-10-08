from flask import Blueprint, render_template

architecture_bp = Blueprint("architecture", __name__)

SHARED_DOCUMENT = {
    "filename": "Project_X_Project_Y_Architecture_Documentation_V5.docx",
    "title": "Project X and Project Y Architecture",
    "version": "V5", "format": "Word", "shared": True,
}

PROJECT_X_DOCUMENTS = [
    SHARED_DOCUMENT,
    *[{
        "filename": f"Project_X_Architecture_Documentation_V{version}.docx",
        "title": "Project X Architecture", "version": f"V{version}", "format": "Word",
    } for version in (4, 3, 2)],
    {"filename": "Project_X_Architecture_Documentation.docx",
     "title": "Project X Architecture", "version": "Original", "format": "Word"},
    {"filename": "Project_X_Architecture_Documentation_V2.png",
     "title": "Project X Architecture Diagram", "version": "V2", "format": "PNG"},
]

PROJECT_Y_DOCUMENTS = [
    {"filename": "Project_Y_Architecture_and_Operations_Documentation_V1.docx",
     "title": "Project Y Architecture and Operations", "version": "V1", "format": "Word"},
    SHARED_DOCUMENT,
]


@architecture_bp.route("/architecture")
@architecture_bp.route("/architecture/project-x")
def architecture():
    return render_template("architecture.html", project="X", documents=PROJECT_X_DOCUMENTS)


@architecture_bp.route("/architecture/project-y")
def project_y():
    return render_template("architecture.html", project="Y", documents=PROJECT_Y_DOCUMENTS)
