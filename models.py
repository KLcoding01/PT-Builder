from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text

db = SQLAlchemy()

class Patient(db.Model):
    __tablename__ = "patients"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(64), nullable=False)
    last_name = db.Column(db.String(64), nullable=False)
    mrn = db.Column(db.String(7), unique=True, nullable=False)  # Only once here
    dob = db.Column(db.Date)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.String(256))
    city = db.Column(db.String(100))
    state = db.Column(db.String(20))
    zip_code = db.Column(db.String(20))
    insurance_id = db.Column(db.Integer, db.ForeignKey("insurances.id"))
    physician_id = db.Column(db.Integer, db.ForeignKey("physicians.id"))
    other_notes = db.Column(db.Text, nullable=True)
    # Relationships
    visits = db.relationship("Visit", back_populates="patient", cascade="all, delete-orphan")
    insurance = db.relationship("Insurance", back_populates="patients")
    physician = db.relationship("Physician", back_populates="patients")
    attachments = db.relationship("Attachment", back_populates="patient", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Patient {self.first_name} {self.last_name}>"

class Therapist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    first_name = db.Column(db.String(80))
    last_name = db.Column(db.String(80))
    credentials = db.Column(db.String(80))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    availability = db.Column(db.String(255))
    npi = db.Column(db.String(20))          
    pt_license = db.Column(db.String(50))

    visits = db.relationship("Visit", back_populates="therapist", cascade="all, delete-orphan")
    schedule_events = db.relationship('ScheduleEvent', back_populates='therapist', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Therapist {self.first_name} {self.last_name}>"

class Physician(db.Model):
    __tablename__ = "physicians"
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(64), nullable=False)
    last_name = db.Column(db.String(64), nullable=False)
    specialty = db.Column(db.String(128))
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20))

    patients = db.relationship("Patient", back_populates="physician", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Physician Dr. {self.first_name} {self.last_name}>"

class Insurance(db.Model):
    __tablename__ = "insurances"
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(128), nullable=False)
    plan_name = db.Column(db.String(128))
    phone = db.Column(db.String(20))

    patients = db.relationship("Patient", back_populates="insurance", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Insurance {self.company_name}>"

class CPTCode(db.Model):
    __tablename__ = "cpt_codes"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    description = db.Column(db.String(256))

    def __repr__(self):
        return f"<CPT {self.code}>"

class ICD10Code(db.Model):
    __tablename__ = "icd10_codes"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    description = db.Column(db.String(256))

    def __repr__(self):
        return f"<ICD10 {self.code}>"

class Visit(db.Model):
    __tablename__ = "visits"
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    therapist_id = db.Column(db.Integer, db.ForeignKey("therapists.id"), nullable=False)
    visit_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    duration = db.Column(db.Integer, default=60)
    visit_type = db.Column(db.String(64))
    status = db.Column(db.String(32), default="Scheduled")
    cpt_code_id = db.Column(db.Integer, db.ForeignKey("cpt_codes.id"), nullable=True)
    icd10_code_id = db.Column(db.Integer, db.ForeignKey("icd10_codes.id"), nullable=True)
    notes = db.Column(db.Text)
    google_event_id = db.Column(db.String(128), nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
    billing = db.relationship("Billing", uselist=False, back_populates="visit", cascade="all, delete-orphan")
    attachments = db.relationship("Attachment", back_populates="visit", cascade="all, delete-orphan")
    patient = db.relationship("Patient", back_populates="visits")
    therapist = db.relationship("Therapist", back_populates="visits")
    cpt_code = db.relationship("CPTCode")
    icd10_code = db.relationship("ICD10Code")

    def __repr__(self):
        return f"<Visit {self.visit_type} for {self.patient.first_name} {self.patient.last_name}>"

class Billing(db.Model):
    __tablename__ = "billings"
    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey("visits.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid = db.Column(db.Boolean, default=False)
    payment_date = db.Column(db.DateTime)
    payment_method = db.Column(db.String(64))
    notes = db.Column(db.Text)

    visit = db.relationship("Visit", back_populates="billing")

    def __repr__(self):
        return f"<Billing visit_id={self.visit_id} amount={self.amount} paid={self.paid}>"

class Attachment(db.Model):
    __tablename__ = "attachments"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200))
    filepath = db.Column(db.String(300))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=True)
    visit_id = db.Column(db.Integer, db.ForeignKey('visits.id'), nullable=True)

    patient = db.relationship('Patient', back_populates='attachments')
    visit = db.relationship('Visit', back_populates='attachments')

    def __repr__(self):
        return f"<Attachment {self.filename}>"

class ScheduleEvent(db.Model):
    __tablename__ = "schedule_event"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128))
    start = db.Column(db.DateTime)
    end = db.Column(db.DateTime)
    therapist_id = db.Column(db.Integer, db.ForeignKey('therapists.id'))
    color = db.Column(db.String(16), default="#1e90ff")
    therapist = db.relationship('Therapist', back_populates='schedule_events')

    def __repr__(self):
        return f"<ScheduleEvent {self.title}>"

class PTNote(db.Model):
    __tablename__ = "pt_notes"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    therapist_id = Column(Integer, ForeignKey("therapists.id"), nullable=True)
    visit_id = Column(Integer, ForeignKey("visits.id"), nullable=True)

    date_created = Column(DateTime, default=datetime.utcnow, nullable=False)
    note_type = Column(String(64), default="SOAP", nullable=False)  # e.g., "SOAP", "Eval", "Progress", "DC"
    content = Column(Text, nullable=False)

    # Soft delete columns
    deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    # Relationships for easy access
    patient = db.relationship('Patient', backref=db.backref('pt_notes', lazy='dynamic'))
    therapist = db.relationship('Therapist', backref=db.backref('pt_notes', lazy='dynamic'))
    visit = db.relationship('Visit', backref=db.backref('pt_notes', lazy='dynamic'))

    def __repr__(self):
        return f"<PTNote {self.id} Patient:{self.patient_id} Type:{self.note_type} Deleted:{self.deleted}>"
