from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime


db = SQLAlchemy()

class Therapist(db.Model, UserMixin):
    __tablename__ = "therapists"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    credentials = db.Column(db.String(80))
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20))

    def __repr__(self):
        return f"<Therapist {self.first_name} {self.last_name}>"

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    dob = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(10), nullable=True)
    ot_notes = db.Column(db.Text, default="")

class PTNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('therapists.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    doc_type = db.Column(db.String(50), default="Evaluation")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    patient = db.relationship("Patient", backref="pt_notes")

def get_pt_note_for_patient(patient_id):
    return {
        "pt_name": "",
        "pt_age": "",
        "med_diag": "",
        "med_history": "",
        "subjective": "",
        "pain": {
            "area": "",
            "onset": "",
            "condition": "",
            "mechanism": "",
            "rating": "",
            "freq": "",
            "desc": "",
            "aggravate": "",
            "relieved": "",
            "interfere": "",
            "meds": "",
            "tests": "",
            "dme": "",
            "plof": ""
        },
        "objective": {
            "posture": "",
            "rom": [],
            "strength": [],
            "palpation": "",
            "functional_tests": [],
            "special_tests": [],
            "mobility_impairments": ""
        },
        "assessment": "",
        "goals_st": [],
        "goals_lt": [],
        "frequency": "",
        "interventions": "",
        "procedures": []
    }
