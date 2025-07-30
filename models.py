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
    pt_notes = db.Column(db.Text, default="")
    ot_notes = db.Column(db.Text, default="")
    # Add any other fields you want!

class PTNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    patient = db.relationship('Patient', backref='pt_notes')  # <-- add this line!
    user_id = db.Column(db.Integer, db.ForeignKey('therapists.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    doc_type = db.Column(db.String(30), default="Evaluation")   # <-- NEW: document type
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

