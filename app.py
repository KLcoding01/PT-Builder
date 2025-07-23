import os, io, json
from datetime import datetime, date
from flask import (
    Flask, request, jsonify, redirect, url_for, flash, render_template,
    send_file
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from openai import OpenAI
from io import BytesIO
from docx import Document
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Import templates and parsers
from pt_templates import PT_TEMPLATES, OT_TEMPLATES, pt_parse_template, ot_parse_template

from models import db, Therapist

# ENV & CONFIG
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key_change_me")
db_path = '/tmp/db.sqlite3'
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# --- OPENAI SETUP ---
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
client = OpenAI(api_key=OPENAI_API_KEY)
MODEL = "gpt-4o-mini"

# --- LOGIN MANAGER ---
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return Therapist.query.get(int(user_id))

# --- CREATE TABLES & ADMIN IF NONE ---
with app.app_context():
    db.create_all()
    if not Therapist.query.filter_by(username="admin").first():
        hashed_pw = generate_password_hash("admin123")
        admin = Therapist(
            username="admin",
            password=hashed_pw,
            first_name="Admin",
            last_name="User",
            credentials="PT",
            email="admin@example.com",
            phone="555-555-5555",
        )
        db.session.add(admin)
        db.session.commit()
        print("Default admin user created: username=admin, password=admin123")

# --- INDEX REDIRECT ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# --- LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = Therapist.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password", "danger")
    return render_template('login.html')

# --- LOGOUT ---
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- DASHBOARD ---
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# --- REGISTER ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        if Therapist.query.filter_by(username=username).first():
            flash("Username already exists", "danger")
            return render_template('register.html')
        if Therapist.query.filter_by(email=email).first():
            flash("Email already registered", "danger")
            return render_template('register.html')

        hashed_pw = generate_password_hash(password)
        therapist = Therapist(
            username=username,
            password=hashed_pw,
            email=email,
        )
        db.session.add(therapist)
        db.session.commit()
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

# --- FORGOT PASSWORD ---
s = URLSafeTimedSerializer(app.secret_key)

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        user = Therapist.query.filter_by(email=email).first()
        if user:
            token = s.dumps(user.id, salt='password-reset')
            reset_url = url_for('reset_password', token=token, _external=True)
            print(f"Reset link for {email}: {reset_url}")  # Send by email in production
        flash("If this email exists, a reset link has been sent.", "success")
        return redirect(url_for('forgot_password'))
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        user_id = s.loads(token, salt='password-reset', max_age=3600)
    except SignatureExpired:
        flash("Reset link expired. Please try again.", "danger")
        return redirect(url_for('forgot_password'))
    except BadSignature:
        flash("Invalid or tampered link.", "danger")
        return redirect(url_for('forgot_password'))

    user = Therapist.query.get(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form['password']
        confirm = request.form['confirm']
        if not password or password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template('reset_password.html')
        user.password = generate_password_hash(password)
        db.session.commit()
        flash("Password reset successful. You can log in now.", "success")
        return redirect(url_for('login'))
    return render_template('reset_password.html')

# ==== PT & OT Endpoints (NO DUPLICATE ROUTES) ====

@app.route("/pt_load_template", methods=["POST"])
@login_required
def pt_load_template():
    data = request.get_json()
    template_name = data.get("template", "")
    if not template_name:
        return jsonify(list(PT_TEMPLATES.keys()))
    else:
        return jsonify(PT_TEMPLATES.get(template_name, {}))

@app.route("/ot_load_template", methods=["POST"])
@login_required
def ot_load_template():
    name = request.json.get("template", "")
    text = OT_TEMPLATES.get(name, "")
    return jsonify(ot_parse_template(text))

# ==== Export Section ====

@app.route('/pt_export_word', methods=['POST'])
@login_required
def pt_export_word():
    data = request.json
    doc = pt_export_to_word(data)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        as_attachment=True,
        download_name='PT_Eval.docx'
    )

def pt_export_to_word(data):
    doc = Document()
    def add_separator():
        doc.add_paragraph('-' * 114)
    doc.add_paragraph(f"Medical Diagnosis: {data.get('meddiag', '')}")
    add_separator()
    doc.add_paragraph(f"Medical History/HNP:\n{data.get('history', '')}")
    add_separator()
    doc.add_paragraph(f"Subjective:\n{data.get('subjective', '')}")
    add_separator()
    doc.add_paragraph("Pain:")
    pain_fields = [
        ("Area/Location of Injury", "pain_location"),
        ("Onset/Exacerbation Date", "pain_onset"),
        ("Condition of Injury", "pain_condition"),
        ("Mechanism of Injury", "pain_mechanism"),
        ("Pain Rating (Present/Best/Worst)", "pain_rating"),
        ("Frequency", "pain_frequency"),
        ("Description", "pain_description"),
        ("Aggravating Factor", "pain_aggravating"),
        ("Relieved By", "pain_relieved"),
        ("Interferes With", "pain_interferes"),
    ]
    for label, key in pain_fields:
        doc.add_paragraph(f"{label}: {data.get(key, '')}")
    doc.add_paragraph(f"Current Medication(s): {data.get('meds', '')}")
    doc.add_paragraph(f"Diagnostic Test(s): {data.get('tests', '')}")
    doc.add_paragraph(f"DME/Assistive Device: {data.get('dme', '')}")
    doc.add_paragraph(f"PLOF: {data.get('plof', '')}")
    add_separator()
    doc.add_paragraph("Objective:")
    obj_fields = [
        ("Posture", "posture"),
        ("ROM", "rom"),
        ("Muscle Strength Test", "strength"),
        ("Palpation", "palpation"),
        ("Functional Test(s)", "functional"),
        ("Special Test(s)", "special"),
        ("Current Functional Mobility Impairment(s)", "impairments"),
    ]
    for label, key in obj_fields:
        doc.add_paragraph(f"{label}:")
        doc.add_paragraph(f"{data.get(key, '')}")
    add_separator()
    doc.add_paragraph("Assessment Summary:")
    doc.add_paragraph(data.get('summary', ''))
    add_separator()
    doc.add_paragraph("Goals:")
    doc.add_paragraph(data.get('goals', ''))
    add_separator()
    doc.add_paragraph("Frequency:")
    doc.add_paragraph(data.get('frequency', ''))
    add_separator()
    doc.add_paragraph("Intervention:")
    doc.add_paragraph(data.get('intervention', ''))
    add_separator()
    doc.add_paragraph("Treatment Procedures:")
    doc.add_paragraph(data.get('procedures', ''))
    add_separator()
    return doc

@app.route("/pt_export_pdf", methods=["POST"])
@login_required
def pt_export_pdf():
    data = request.get_json()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40

    def add_section(title, value):
        nonlocal y
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, y, title)
        y -= 18
        c.setFont("Helvetica", 11)
        for line in (value or "").split('\n'):
            c.drawString(48, y, line)
            y -= 14
            if y < 60:
                c.showPage()
                y = height - 40
        y -= 8
        c.setLineWidth(0.5)
        c.line(40, y, width - 40, y)
        y -= 16

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Physical Therapy Evaluation")
    y -= 30

    add_section("Medical Diagnosis:", data.get("meddiag", ""))
    add_section("Medical History/HNP:", data.get("history", ""))
    add_section("Subjective:", data.get("subjective", ""))
    pain_lines = [
        f"Area/Location of Injury: {data.get('pain_location','')}",
        f"Onset/Exacerbation Date: {data.get('pain_onset','')}",
        f"Condition of Injury: {data.get('pain_condition','')}",
        f"Mechanism of Injury: {data.get('pain_mechanism','')}",
        f"Pain Rating (Present/Best/Worst): {data.get('pain_rating','')}",
        f"Frequency: {data.get('pain_frequency','')}",
        f"Description: {data.get('pain_description','')}",
        f"Aggravating Factor: {data.get('pain_aggravating','')}",
        f"Relieved By: {data.get('pain_relieved','')}",
        f"Interferes With: {data.get('pain_interferes','')}",
        "",
        f"Current Medication(s): {data.get('meds','')}",
        f"Diagnostic Test(s): {data.get('tests','')}",
        f"DME/Assistive Device: {data.get('dme','')}",
        f"PLOF: {data.get('plof','')}",
    ]
    add_section("Pain:", "\n".join(pain_lines))
    obj_lines = [
        f"Posture: {data.get('posture','')}",
        "",
        f"ROM: \n{data.get('rom','')}",
        "",
        f"Muscle Strength Test: \n{data.get('strength','')}",
        "",
        f"Palpation: \n{data.get('palpation','')}",
        "",
        f"Functional Test(s): \n{data.get('functional','')}",
        "",
        f"Special Test(s): \n{data.get('special','')}",
        "",
        f"Current Functional Mobility Impairment(s): \n{data.get('impairments','')}",
    ]
    add_section("Objective:", "\n".join(obj_lines))
    add_section("Assessment Summary:", data.get("summary", ""))
    add_section("Goals:", data.get("goals", ""))
    add_section("Frequency:", data.get("frequency", ""))
    add_section("Intervention:", data.get("intervention", ""))
    add_section("Treatment Procedures:", data.get("procedures", ""))

    c.save()
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="PT_Eval.pdf",
        mimetype="application/pdf"
    )

# ====== OT Section ======

@app.route("/pt_generate_diffdx", methods=["POST"])
@login_required
def pt_generate_diffdx():
    f = request.json.get("fields", {})
    pain = "; ".join(f"{lbl}: {f.get(key,'')}"
                      for lbl,key in [
                          ("Area/Location", "pain_location"),
                          ("Onset", "pain_onset"),
                          ("Condition", "pain_condition"),
                          ("Mechanism", "pain_mechanism"),
                          ("Rating", "pain_rating"),
                          ("Frequency", "pain_frequency"),
                          ("Description", "pain_description"),
                          ("Aggravating", "pain_aggravating"),
                          ("Relieved", "pain_relieved"),
                          ("Interferes", "pain_interferes"),
                      ])
    prompt = (
        "You are a PT clinical assistant. Provide the single best-fit and/or closely associated with diagnosis. Keep it clean.:\n\n"
        f"Subjective:\n{f.get('subjective','')}\n\n"
        f"Pain:\n{pain}\n\n"
        f"Objective:\nPosture: {f.get('posture','')}\n"
        f"ROM: {f.get('rom','')}\n"
        f"Strength: {f.get('strength','')}\n"
    )
    result = gpt_call(prompt, max_tokens=250)
    return jsonify({"result": result})

def calculate_age(dob):
    """Calculate age in years from date of birth (as string or date)."""
    if not dob:
        return "X"
    if isinstance(dob, str):
        try:
            # Accept 'YYYY-MM-DD' or similar
            dob = datetime.strptime(dob, "%m-%d-%Y").date()
        except Exception:
            # fallback: handle other common formats, or return "X"
            try:
                dob = datetime.strptime(dob, "%m/%d/%Y").date()
            except Exception:
                return "X"
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    

def pt_generate_summary():
    f = request.json.get("fields", {})
    # Patient Name logic: search all possible name keys
    name = (
        f.get("name")
        or f.get("pt_patient_name")
        or f.get("patient_name")
        or f.get("full_name")
        or "Pt"
    )
    # DOB to Age calculation with multiple formats
    dob = f.get("dob")
    age = "X"
    if dob:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
            try:
                dob_dt = datetime.strptime(dob, fmt)
                today_dt = date.today()
                age = today_dt.year - dob_dt.year - ((today_dt.month, today_dt.day) < (dob_dt.month, dob_dt.day))
                break
            except Exception:
                continue
    else:
        age = f.get("age", "X")
    gender = f.get("gender", "patient").lower()
    pmh = f.get("history", "no significant history")
    today = f.get("currentdate", date.today().strftime("%m/%d/%Y"))
    subj = f.get("subjective", "")
    moi = f.get("pain_mechanism", "")
    meddiag = f.get("meddiag", "") or f.get("medical_diagnosis", "")
    dx = f.get("diffdx", "")
    strg = f.get("strength", "")
    rom = f.get("rom", "")
    impair = f.get("impairments", "")
    func = f.get("functional", "")

    prompt = (
        "Generate a concise, 7-8 sentence Physical Therapy assessment summary that is Medicare compliant for PT documentation. "
        "Use only abbreviations (e.g., HEP, ADLs, LBP, STM, TherEx) and NEVER spell out abbreviations. "
        "Never use 'the patient'; use 'Pt' as the subject. "
        "Do NOT state or conclude a medical diagnosis. Use the following clinical phrasing ONLY: "
        "'Pt's symptoms and clinical findings are associated with the referring medical dx and PT differential dx as described.' "
        f"Start with: \"{name}, a {age} y/o {gender} with relevant history of {pmh}.\" "
        f"Include: PT initial eval on {today} for {subj}. "
        f"If available, mention the mechanism of injury ({moi}). "
        f"Then: Pt's symptoms and clinical findings are associated with the referring medical dx ({meddiag}) and PT differential dx ({dx}). "
        f"Summarize current impairments (strength: {strg}; ROM: {rom}; balance/mobility: {impair}). "
        f"Summarize functional/activity limitations: {func}. "
        "End with a professional prognosis stating that skilled PT is medically necessary to address impairments and support return to PLOF. "
        "Do NOT use bulleted or numbered lists—compose a single, well-written summary paragraph."
    )
    result = gpt_call(prompt, max_tokens=500)
    return jsonify({"result": result})

@app.route('/pt_generate_goals', methods=['POST'])
@login_required
def pt_generate_goals():
    fields = request.json.get("fields", {})
    prompt = """
    You are a clinical assistant helping a PT write documentation.
    Using ONLY the provided eval info (summary, objective findings, strength, ROM, impairments, and functional limitations),
    generate clinically-appropriate, Medicare-compliant short-term and long-term PT goals.
    ALWAYS follow this exact format—do not add, skip, reorder, or alter any lines or labels.
    DO NOT add any explanations, introductions, dashes, bullets, or extra indentation. Output ONLY this structure:

    Short-Term Goals (1–12 visits):
    1. [goal statement]
    2. [goal statement]
    3. [goal statement]
    4. [goal statement]

    Long-Term Goals (13–25 visits):
    1. [goal statement]
    2. [goal statement]
    3. [goal statement]
    4. [goal statement]
    """

    result = gpt_call(prompt, max_tokens=350)
    return jsonify({"result": result})

@app.route('/pt_generate_daily_summary', methods=['POST'])
@login_required
def pt_generate_daily_summary():
    data = request.json
    prompt = (
        "You are a physical therapist. "
        "Write a 6-sentence daily PT note summary in paragraph form. "
        "Use professional tone, refer to 'patient' (not 'the patient' or 'patient reported'). "
        "Summarize the following:\n"
        f"Diagnosis: {data.get('diagnosis','')}\n"
        f"Interventions: {data.get('interventions','')}\n"
        f"Tx Tolerance: {data.get('tolerance','')}\n"
        f"Current Progress: {data.get('progress','')}\n"
        f"Next Visit Plan: {data.get('plan','')}\n"
        "Do not use the phrases 'patient reported' or 'the patient'. "
        "Do not spell out, use abbreviation only, avoid using both next to each other. "
        "After summarizes skip a row write a 1-2 sentences for next visit plan of care utilizing something along Focusing on PT POC to improve strength, endurance, mechanics, activity tolerance with manual therapy, ther-ex, ther-act, IASTM. Improve activity tolerance to return to safe ADLs and community participation and ambulation."
    )
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250
        )
        summary = completion.choices[0].message.content.strip()
        return jsonify({"result": summary})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@app.route('/ot_export_word', methods=['POST'])
@login_required
def ot_export_word():
    data = request.json
    doc = ot_export_to_word(data)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        as_attachment=True,
        download_name='OT_Eval.docx'
    )

def ot_export_to_word(data):
    doc = Document()
    def add_separator():
        doc.add_paragraph('-' * 114)
    doc.add_paragraph(f"Medical Diagnosis: {data.get('ot_meddiag', '')}")
    add_separator()
    doc.add_paragraph(f"Medical History/HNP:\n{data.get('ot_history', '')}")
    add_separator()
    doc.add_paragraph(f"Subjective:\n{data.get('ot_subjective', '')}")
    add_separator()
    doc.add_paragraph("Pain:")
    pain_fields = [
        ("Area/Location of Injury", "ot_pain_location"),
        ("Onset/Exacerbation Date", "ot_pain_onset"),
        ("Condition of Injury", "ot_pain_condition"),
        ("Mechanism of Injury", "ot_pain_mechanism"),
        ("Pain Rating (Present/Best/Worst)", "ot_pain_rating"),
        ("Frequency", "ot_pain_frequency"),
        ("Description", "ot_pain_description"),
        ("Aggravating Factor", "ot_pain_aggravating"),
        ("Relieved By", "ot_pain_relieved"),
        ("Interferes With", "ot_pain_interferes"),
    ]
    for label, key in pain_fields:
        doc.add_paragraph(f"{label}: {data.get(key, '')}")
    doc.add_paragraph(f"Current Medication(s): {data.get('ot_meds', '')}")
    doc.add_paragraph(f"Diagnostic Test(s): {data.get('ot_tests', '')}")
    doc.add_paragraph(f"DME/Assistive Device: {data.get('ot_dme', '')}")
    doc.add_paragraph(f"PLOF: {data.get('ot_plof', '')}")
    add_separator()
    doc.add_paragraph("Objective:")
    obj_fields = [
        ("Posture", "ot_posture"),
        ("ROM", "ot_rom"),
        ("Muscle Strength Test", "ot_strength"),
        ("Palpation", "ot_palpation"),
        ("Functional Test(s)", "ot_functional"),
        ("Special Test(s)", "ot_special"),
        ("Current Functional Mobility Impairment(s)", "ot_impairments"),
    ]
    for label, key in obj_fields:
        doc.add_paragraph(f"{label}:")
        doc.add_paragraph(f"{data.get(key, '')}")
    add_separator()
    doc.add_paragraph("Assessment Summary:")
    doc.add_paragraph(data.get('ot_summary', ''))
    add_separator()
    doc.add_paragraph("Goals:")
    doc.add_paragraph(data.get('ot_goals', ''))
    add_separator()
    doc.add_paragraph("Frequency:")
    doc.add_paragraph(data.get('ot_frequency', ''))
    add_separator()
    doc.add_paragraph("Intervention:")
    doc.add_paragraph(data.get('ot_intervention', ''))
    add_separator()
    doc.add_paragraph("Treatment Procedures:")
    doc.add_paragraph(data.get('ot_procedures', ''))
    add_separator()
    return doc

@app.route("/ot_export_pdf", methods=["POST"])
@login_required
def ot_export_pdf():
    data = request.get_json()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40

    def add_section(title, value):
        nonlocal y
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, y, title)
        y -= 18
        c.setFont("Helvetica", 11)
        for line in (value or "").split('\n'):
            c.drawString(48, y, line)
            y -= 14
            if y < 60:
                c.showPage()
                y = height - 40
        y -= 8
        c.setLineWidth(0.5)
        c.line(40, y, width - 40, y)
        y -= 16

    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Occupational Therapy Evaluation")
    y -= 30

    add_section("Medical Diagnosis:", data.get("ot_meddiag", ""))
    add_section("Medical History/HNP:", data.get("ot_history", ""))
    add_section("Subjective:", data.get("ot_subjective", ""))
    pain_lines = [
        f"Area/Location of Injury: {data.get('ot_pain_location','')}",
        f"Onset/Exacerbation Date: {data.get('ot_pain_onset','')}",
        f"Condition of Injury: {data.get('ot_pain_condition','')}",
        f"Mechanism of Injury: {data.get('ot_pain_mechanism','')}",
        f"Pain Rating (Present/Best/Worst): {data.get('ot_pain_rating','')}",
        f"Frequency: {data.get('ot_pain_frequency','')}",
        f"Description: {data.get('ot_pain_description','')}",
        f"Aggravating Factor: {data.get('ot_pain_aggravating','')}",
        f"Relieved By: {data.get('ot_pain_relieved','')}",
        f"Interferes With: {data.get('ot_pain_interferes','')}",
        "",
        f"Current Medication(s): {data.get('ot_meds','')}",
        f"Diagnostic Test(s): {data.get('ot_tests','')}",
        f"DME/Assistive Device: {data.get('ot_dme','')}",
        f"PLOF: {data.get('ot_plof','')}",
    ]
    add_section("Pain:", "\n".join(pain_lines))
    obj_lines = [
        f"Posture: {data.get('ot_posture','')}",
        "",
        f"ROM: \n{data.get('ot_rom','')}",
        "",
        f"Muscle Strength Test: \n{data.get('ot_strength','')}",
        "",
        f"Palpation: \n{data.get('ot_palpation','')}",
        "",
        f"Functional Test(s): \n{data.get('ot_functional','')}",
        "",
        f"Special Test(s): \n{data.get('ot_special','')}",
        "",
        f"Current Functional Mobility Impairment(s): \n{data.get('ot_impairments','')}",
    ]
    add_section("Objective:", "\n".join(obj_lines))
    add_section("Assessment Summary:", data.get("ot_summary", ""))
    add_section("Goals:", data.get("ot_goals", ""))
    add_section("Frequency:", data.get("ot_frequency", ""))
    add_section("Intervention:", data.get("ot_intervention", ""))
    add_section("Treatment Procedures:", data.get("ot_procedures", ""))

    c.save()
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="OT_Eval.pdf",
        mimetype="application/pdf"
    )
    
# ========== GPT HELPER ==========

def gpt_call(prompt, max_tokens=700):
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"OpenAI error: {e}"

# ========== MAIN ==========
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
