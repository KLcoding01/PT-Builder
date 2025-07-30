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
    
# ==== Add Patients ====
@app.route('/patients', methods=['GET'])
@login_required
def view_patients():
    patients = Patient.query.order_by(Patient.name).all()
    return render_template('patients.html', patients=patients)

@app.route('/add_patient', methods=['GET', 'POST'])
@login_required
def add_patient():
    if request.method == 'POST':
        name = request.form['name']
        dob = request.form['dob']
        gender = request.form['gender']
        pt_notes = request.form.get('pt_notes', '')
        ot_notes = request.form.get('ot_notes', '')

        patient = Patient(
            name=name,
            dob=datetime.strptime(dob, '%Y-%m-%d'),
            gender=gender,
            pt_notes=pt_notes,
            ot_notes=ot_notes
        )
        db.session.add(patient)
        db.session.commit()
        flash("Patient added successfully!", "success")
        return redirect(url_for('view_patients'))

    return render_template('add_patient.html')

#======Patient Search ======
@app.route('/patients', methods=['GET'])
@login_required
def view_single_patient():
    query = request.args.get('q', '').strip().lower()

    if query:
        patients = Patient.query.filter(Patient.name.ilike(f"%{query}%")).order_by(
            db.func.split_part(Patient.name, ' ', -1), Patient.name
        ).all()
    else:
        patients = Patient.query.order_by(
            db.func.split_part(Patient.name, ' ', -1), Patient.name
        ).all()

    return render_template('patients.html', patients=patients, query=query)

#======Show Full PT and OT Notes =======
@app.route('/patient/<int:patient_id>/pt_notes')
@login_required
def view_pt_notes(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    return render_template('pt_notes.html', patient=patient)

@app.route('/patient/<int:patient_id>/ot_notes')
@login_required
def view_ot_notes(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    return render_template('ot_notes.html', patient=patient)
    
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
    req = request.get_json() or {}
    template = req.get("template", "")
    if template:
        return jsonify(OT_TEMPLATES.get(template, {}))
    else:
        return jsonify(list(OT_TEMPLATES.keys()))
        


# ====== PT Section ======

@app.route("/pt_generate_diffdx", methods=["POST"])
@login_required
def pt_generate_diffdx():
    f = request.json.get("fields", {})
    pain = "; ".join(f"{lbl}: {f.get(key,'')}"
                      for lbl, key in [
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
        "You are a PT clinical assistant. Based on the following evaluation details, "
        "provide a concise statement of the most clinically-associated PT differential diagnosis. "
        "Do NOT state as fact or as a medical diagnosis—use only language such as 'symptoms and clinical findings are associated with or consistent with' the diagnosis. "
        "Keep the statement clean and PT-relevant:\n\n"
        f"Subjective:\n{f.get('subjective','')}\n\n"
        f"Pain:\n{pain}\n\n"
        f"Objective:\nPosture: {f.get('posture','')}\n"
        f"ROM: {f.get('rom','')}\n"
        f"Strength: {f.get('strength','')}\n"
    )
    result = gpt_call(prompt, max_tokens=250)
    return jsonify({"result": result})

@app.route("/pt_generate_summary", methods=["POST"])
@login_required
def pt_generate_summary():
    f = request.json.get("fields", {})
    name = (
        f.get("name")
        or f.get("pt_patient_name")
        or f.get("patient_name")
        or f.get("full_name")
        or "Pt"
    )
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
        "Do NOT use parentheses, asterisks, or markdown formatting in your response. "
        "Do NOT use 'Diagnosis:' as a label—refer directly to the diagnosis in clinical sentences. "
        "Do NOT state or conclude a medical diagnosis—use clinical phrasing such as 'symptoms and clinical findings are associated with' the medical diagnosis and PT clinical impression. "
        f"Start with: \"{name}, a {age} y/o {gender} with relevant history of {pmh}.\" "
        f"Include: PT initial eval on {today} for {subj}. "
        f"If available, mention the mechanism of injury: {moi}. "
        f"State: Pt has symptoms and clinical findings associated with the referring medical diagnosis of {meddiag}. Clinical findings are consistent with PT differential diagnosis of {dx} based on assessment. "
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

    summary = fields.get("summary", "")
    strength = fields.get("strength", "")
    rom = fields.get("rom", "")
    impairments = fields.get("impairments", "")
    functional = fields.get("functional", "")
    meddiag = fields.get("meddiag", "")
    pain_location = fields.get("pain_location", "")

    prompt = f"""
You are a clinical assistant helping a PT write documentation.
Below is a summary of the patient's evaluation and findings:
Diagnosis/Region: {meddiag or pain_location}
Summary: {summary}
Strength: {strength}
ROM: {rom}
Impairments: {impairments}
Functional Limitations: {functional}

Using ONLY the above provided eval info, generate clinically-appropriate, Medicare-compliant short-term and long-term PT goals for the region/problem described.
Each goal must be functionally focused and follow this EXACT format, time frame, and language example (do NOT copy example content, use it as a style guide):

Short-Term Goals (1–12 visits):
1. Pt will report [symptom, e.g., neck pain] ≤[target]/10 with [functional activity].
2. Pt will improve [objective finding, e.g., cervical rotation] by ≥[measurable target] to allow [activity].
3. Pt will demonstrate ≥[percent]% adherence to [strategy/technique] during [ADL].
4. Pt will perform HEP, transfer, or mobility] with [level of independence] to support [function].

Long-Term Goals (13–25 visits):
1. Pt will increase [strength or ability] by ≥[amount] to support safe [ADL/task].
2. Pt will restore [ROM/ability] to within [target] of normal, enabling [activity].
3. Pt will demonstrate 100% adherence to [technique/precaution] during [ADL/IADL].
4. Pt will independently perform [home program or self-management] to maintain function and prevent recurrence.

ALWAYS use this structure, always begin each statement with 'Pt will', and do NOT add any extra text, dashes, bullets, or lines. Use only info from the above findings.
"""

    result = gpt_call(prompt, max_tokens=400)
    return jsonify({"result": result})

# ====== PT Export ======
def pt_export_to_word(data):
    doc = Document()

    def add_separator():
        doc.add_paragraph('-' * 114)

    # Add demographic header line
    gender = data.get('gender', '')
    dob = data.get('dob', '')
    weight = data.get('weight', '')
    height = data.get('height', '')
    bmi = data.get('bmi', '')
    bmi_category = data.get('bmi_category', '')

    header_line = f"Gender: {gender}    DOB: {dob}    Weight: {weight} lbs    Height: {height}     BMI: {bmi} ({bmi_category})"
    doc.add_paragraph(header_line)
    add_separator()

    doc.add_paragraph(f"Medical Diagnosis: {data.get('meddiag', '')}")
    add_separator()

    doc.add_paragraph("Medical History/HNP:")
    doc.add_paragraph(data.get('history', ''))
    add_separator()

    doc.add_paragraph("Subjective:")
    doc.add_paragraph(data.get('subjective', ''))
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
    doc.add_paragraph("Posture:")
    doc.add_paragraph(data.get('posture', ''))
    doc.add_paragraph("ROM:")
    doc.add_paragraph(data.get('rom', ''))
    doc.add_paragraph("Muscle Strength Test:")
    doc.add_paragraph(data.get('strength', ''))
    doc.add_paragraph("Palpation:")
    doc.add_paragraph(data.get('palpation', ''))
    doc.add_paragraph("Functional Test(s):")
    doc.add_paragraph(data.get('functional', ''))
    doc.add_paragraph("Special Test(s):")
    doc.add_paragraph(data.get('special', ''))
    doc.add_paragraph("Current Functional Mobility Impairment(s):")
    doc.add_paragraph(data.get('impairments', ''))
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

    def add_separator():
        nonlocal y
        y -= 8
        c.setLineWidth(0.5)
        c.line(40, y, width - 40, y)
        y -= 16

    def add_paragraph_block(title, text):
        nonlocal y
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, y, title)
        y -= 18
        c.setFont("Helvetica", 11)
        for line in (text or "").split('\n'):
            c.drawString(48, y, line)
            y -= 14
            if y < 60:
                c.showPage()
                y = height - 40
        add_separator()

    def add_multiline_section(title, lines):
        nonlocal y
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, y, title)
        y -= 18
        c.setFont("Helvetica", 11)
        for line in lines:
            for subline in line.split('\n'):
                c.drawString(48, y, subline)
                y -= 14
                if y < 60:
                    c.showPage()
                    y = height - 40
        add_separator()

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Physical Therapy Evaluation")
    y -= 30

    # Demographic Header
    gender = data.get('gender', '')
    dob = data.get('dob', '')
    weight = data.get('weight', '')
    height_val = data.get('height', '')
    bmi = data.get('bmi', '')
    bmi_category = data.get('bmi_category', '')
    demographic = f"Gender: {gender}    DOB: {dob}    Weight: {weight} lbs    Height: {height_val}     BMI: {bmi} ({bmi_category})"

    c.setFont("Helvetica", 11)
    c.drawString(40, y, demographic)
    y -= 20
    add_separator()

    # Sections
    add_paragraph_block("Medical Diagnosis:", data.get("meddiag", ""))
    add_paragraph_block("Medical History/HNP:", data.get("history", ""))
    add_paragraph_block("Subjective:", data.get("subjective", ""))

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
    add_multiline_section("Pain:", pain_lines)

    objective_lines = [
        f"Posture:",
        data.get('posture', ''),
        "",
        f"ROM:",
        data.get('rom', ''),
        "",
        f"Muscle Strength Test:",
        data.get('strength', ''),
        "",
        f"Palpation:",
        data.get('palpation', ''),
        "",
        f"Functional Test(s):",
        data.get('functional', ''),
        "",
        f"Special Test(s):",
        data.get('special', ''),
        "",
        f"Current Functional Mobility Impairment(s):",
        data.get('impairments', '')
    ]
    add_multiline_section("Objective:", objective_lines)

    add_paragraph_block("Assessment Summary:", data.get("summary", ""))
    add_paragraph_block("Goals:", data.get("goals", ""))
    add_paragraph_block("Frequency:", data.get("frequency", ""))
    add_paragraph_block("Intervention:", data.get("intervention", ""))
    add_paragraph_block("Treatment Procedures:", data.get("procedures", ""))

    c.save()
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="PT_Eval.pdf",
        mimetype="application/pdf"
    )


# ====== OT Section ======
@app.route("/ot_generate_diffdx", methods=["POST"])
@login_required
def ot_generate_diffdx():
    f = request.json.get("fields", {})   # <-- define f here
    dx = f.get("diffdx", "")
    if not dx:
        pain = "; ".join(f"{lbl}: {f.get(key,'')}"
            for lbl, key in [
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
        dx_prompt = (
            "You are an OT clinical assistant. Based on the following OT evaluation details, "
            "provide a concise statement of the most clinically-associated OT differential diagnosis. "
            "Do NOT state as fact or as a medical diagnosis—use only language such as 'symptoms and clinical findings are associated with or consistent with' the diagnosis. "
            f"Subjective:\n{f.get('subjective','')}\nPain:\n{pain}\n"
        )
        dx = gpt_call(dx_prompt, max_tokens=200)
    return jsonify({"result": dx})


@app.route("/ot_generate_summary", methods=["POST"])
@login_required
def ot_generate_summary():
    f = request.json.get("fields", {})
    name = (
        f.get("name") or f.get("ot_patient_name") or f.get("patient_name") or f.get("full_name") or "Pt"
    )
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
    # Optional: auto-generate dx if not present
    if not dx:
        pain = "; ".join(f"{lbl}: {f.get(key,'')}"
            for lbl, key in [
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
        dx_prompt = (
            "You are an OT clinical assistant. Based on the following OT evaluation details, "
            "provide a concise statement of the most clinically-associated OT differential diagnosis. "
            "Do NOT state as fact or as a medical diagnosis—use only language such as 'symptoms and clinical findings are associated with or consistent with' the diagnosis. "
            f"Subjective:\n{subj}\nPain:\n{pain}\n"
        )
        dx = gpt_call(dx_prompt, max_tokens=200)
    strg = f.get("strength", "")
    rom = f.get("rom", "")
    impair = f.get("impairments", "")
    func = f.get("functional", "")

    prompt = (
        "Generate a concise, 7-8 sentence Occupational Therapy assessment summary that is Medicare compliant for OT documentation. "
        "Use only abbreviations (e.g., HEP, ADLs, IADLs, STM, TherEx) and NEVER spell out abbreviations. "
        "Never use 'the patient'; use 'Pt' as the subject. "
        "Do NOT use parentheses, asterisks, or markdown formatting in your response. "
        "Do NOT use 'Diagnosis:' as a label—refer directly to the diagnosis in clinical sentences. "
        "Confirm/Conclude a medical diagnosis—use clinical phrasing such as 'symptoms and clinical findings are associated with' the medical diagnosis and OT clinical impression. "
        f"Start with: \"{name}, a {age} y/o {gender} with relevant history of {pmh}.\" "
        f"Include: OT initial eval on {today} for {subj}. "
        f"If available, mention the mechanism of injury: {moi}. "
        f"State: Pt has symptoms and clinical findings associated with the referring medical diagnosis of {meddiag}. Clinical findings are consistent with OT differential diagnosis of {dx} based on assessment. "
        f"Summarize current impairments (strength: {strg}; ROM: {rom}; balance/mobility: {impair}). "
        f"Summarize functional/activity limitations: {func}. "
        "End with a professional prognosis stating that skilled OT is medically necessary to address impairments and support return to PLOF. "
        "Do NOT use bulleted or numbered lists—compose a single, well-written summary paragraph."
    )
    result = gpt_call(prompt, max_tokens=500)
    return jsonify({"result": result})

@app.route('/ot_generate_goals', methods=['POST'])
@login_required
def ot_generate_goals():
    fields = request.json.get("fields", {})
    summary = fields.get("summary", "") or "Pt evaluated for functional deficits impacting ADLs/IADLs."
    strength = fields.get("strength", "") or "N/A"
    rom = fields.get("rom", "") or "N/A"
    impairments = fields.get("impairments", "") or "N/A"
    functional = fields.get("functional", "") or "N/A"

    prompt = f"""
You are a clinical assistant helping an occupational therapist write documentation.
Below is a summary of the patient's evaluation and findings:
Summary: {summary}
Strength: {strength}
ROM: {rom}
Impairments: {impairments}
Functional Limitations: {functional}

Using ONLY the above provided eval info, generate clinically-appropriate, Medicare-compliant short-term and long-term OT goals. Focus on ADLs, IADLs, functional participation, use of adaptive equipment, and safety (e.g., dressing, bathing, toileting, home management, transfers, community integration). Each goal must use the "Pt will..." format, specify an activity and level of independence, and be functionally/measurably stated.

ALWAYS follow this exact format—do not add, skip, reorder, or alter any lines or labels.
DO NOT add any explanations, introductions, dashes, bullets, or extra indentation. Output ONLY this structure:

Short-Term Goals (1–12 visits):
1. Pt will [specific ADL/IADL task] with [level of assistance/adaptive strategy] to promote functional independence.
2. Pt will improve [ROM/strength/endurance] by [amount or %] to support [specific functional task].
3. Pt will independently use [adaptive equipment or compensatory technique] during [ADL/IADL].
4. Pt will report pain ≤[target]/10 during [functional task or ADL].

Long-Term Goals (13–25 visits):
1. Pt will complete all [ADL/IADL] independently or with AE as needed.
2. Pt will demonstrate safe performance of [home/community management task] using proper body mechanics and adaptive strategies.
3. Pt will participate in [community activity/home management/transfer] with [level of independence].
4. Pt will maintain functional gains and independently implement all learned safety/adaptive strategies in daily routines.
"""

    result = gpt_call(prompt, max_tokens=400)
    return jsonify({"result": result})

# ====== OT Export ======

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

    def add_section(title, content):
        doc.add_paragraph(f"{title}")
        doc.add_paragraph(content or "")
        add_separator()

    def add_multiline_section(title, lines):
        doc.add_paragraph(title)
        for line in lines:
            doc.add_paragraph(line)
        add_separator()

    # Demographic line
    gender = data.get('gender', '')
    dob = data.get('dob', '')
    weight = data.get('weight', '')
    height_val = data.get('height', '')
    bmi = data.get('bmi', '')
    bmi_category = data.get('bmi_category', '')
    demographics = f"Gender: {gender}    DOB: {dob}    Weight: {weight} lbs    Height: {height_val}     BMI: {bmi} ({bmi_category})"
    doc.add_paragraph(demographics)
    add_separator()

    # Sections
    add_section("Medical Diagnosis:", data.get('meddiag', ''))
    add_section("Medical History/HNP:", data.get('history', ''))
    add_section("Subjective:", data.get('ot_subjective', ''))

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
    add_multiline_section("Pain:", pain_lines)

    objective_lines = [
        "Posture:",
        data.get('posture', ''),
        "",
        "ROM:",
        data.get('rom', ''),
        "",
        "Muscle Strength Test:",
        data.get('strength', ''),
        "",
        "Palpation:",
        data.get('palpation', ''),
        "",
        "Functional Test(s):",
        data.get('functional', ''),
        "",
        "Special Test(s):",
        data.get('special', ''),
        "",
        "Current Functional Mobility Impairment(s):",
        data.get('impairments', ''),
    ]
    add_multiline_section("Objective:", objective_lines)

    add_section("Assessment Summary:", data.get('summary', ''))
    add_section("Goals:", data.get('goals', ''))
    add_section("Frequency:", data.get('frequency', ''))
    add_section("Intervention:", data.get('intervention', ''))
    add_section("Treatment Procedures:", data.get('procedures', ''))

    return doc

@app.route("/ot_export_pdf", methods=["POST"])
@login_required
def ot_export_pdf():
    data = request.get_json()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40

    def add_separator():
        nonlocal y
        y -= 8
        c.setLineWidth(0.5)
        c.line(40, y, width - 40, y)
        y -= 16

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
        add_separator()

    def add_multiline_section(title, lines):
        nonlocal y
        c.setFont("Helvetica-Bold", 13)
        c.drawString(40, y, title)
        y -= 18
        c.setFont("Helvetica", 11)
        for line in lines:
            for sub_line in line.split('\n'):
                c.drawString(48, y, sub_line)
                y -= 14
                if y < 60:
                    c.showPage()
                    y = height - 40
        add_separator()

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Occupational Therapy Evaluation")
    y -= 30

    # Demographic Line
    gender = data.get("gender", "")
    dob = data.get("dob", "")
    weight = data.get("weight", "")
    height_val = data.get("height", "")
    bmi = data.get("bmi", "")
    bmi_category = data.get("bmi_category", "")
    demo_line = f"Gender: {gender}    DOB: {dob}    Weight: {weight} lbs    Height: {height_val}     BMI: {bmi} ({bmi_category})"

    c.setFont("Helvetica", 11)
    c.drawString(40, y, demo_line)
    y -= 18
    add_separator()

    # Main Sections
    add_section("Medical Diagnosis:", data.get("meddiag", ""))
    add_section("Medical History/HNP:", data.get("history", ""))
    add_section("Subjective:", data.get("ot_subjective", ""))

    # Pain Section
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
    add_multiline_section("Pain:", pain_lines)

    # Objective Section
    obj_lines = [
        f"Posture:",
        data.get('posture', ''),
        "",
        f"ROM:",
        data.get('rom', ''),
        "",
        f"Muscle Strength Test:",
        data.get('strength', ''),
        "",
        f"Palpation:",
        data.get('palpation', ''),
        "",
        f"Functional Test(s):",
        data.get('functional', ''),
        "",
        f"Special Test(s):",
        data.get('special', ''),
        "",
        f"Current Functional Mobility Impairment(s):",
        data.get('impairments', ''),
    ]
    add_multiline_section("Objective:", obj_lines)

    # Remaining Sections
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
