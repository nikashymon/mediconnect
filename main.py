from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask import send_from_directory
from sqlalchemy import or_
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
from flask import send_file
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
import os
import random
import json
import base64
from werkzeug.utils import secure_filename

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'DataBase.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.urandom(24)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    user_type = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship('Patient', backref='user', uselist=False, cascade='all, delete-orphan')
    doctor = db.relationship('Doctor', backref='user', uselist=False, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    birthdate = db.Column(db.Date, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.String(200))
    blood_type = db.Column(db.String(10))
    allergies = db.Column(db.Text)
    chronic_diseases = db.Column(db.Text)
    gender = db.Column(db.String(10))
    avatar = db.Column(db.String(255))

    appointments = db.relationship('Appointment', backref='patient', lazy=True)
    medical_records = db.relationship('MedicalRecord', backref='patient', lazy=True)

    def created_at(self):
        return self.user.created_at

class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    specialization = db.Column(db.String(100), nullable=False)
    license_number = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    bio = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    avatar = db.Column(db.String(255))

    appointments = db.relationship('Appointment', backref='doctor', lazy=True)
    working_hours = db.relationship('WorkingHours', backref='doctor', lazy=True)
    medical_records = db.relationship('MedicalRecord', backref='doctor', lazy=True)


class WorkingHours(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False, index=True)
    appointment_date = db.Column(db.Date, nullable=False, index=True)
    appointment_time = db.Column(db.Time, nullable=False)
    duration = db.Column(db.Integer, default=30)
    status = db.Column(db.String(20), default='scheduled')
    reason = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MedicalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    record_date = db.Column(db.DateTime, default=datetime.utcnow)
    diagnosis = db.Column(db.Text)
    treatment = db.Column(db.Text)
    prescriptions = db.Column(db.Text)
    notes = db.Column(db.Text)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'))


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user_type = request.form.get('user_type', 'patient')

        user = User.query.filter_by(email=email).first()

        if user:
            if user.check_password(password):
                if user.user_type == user_type:
                    session['user_id'] = user.id
                    session['user_type'] = user.user_type
                    if user_type == 'doctor':
                        doctor = Doctor.query.filter_by(user_id=user.id).first()
                        if not doctor:
                            flash('Обліковий запис лікаря не знайдено', 'error')
                            return redirect(url_for('login'))
                        return redirect(url_for('doctor_dashboard'))
                    else:
                        patient = Patient.query.filter_by(user_id=user.id).first()
                        if not patient:
                            flash('Обліковий запис пацієнта не знайдено', 'error')
                            return redirect(url_for('login'))
                        return redirect(url_for('patient_dashboard'))
                else:
                    flash('Невірний тип облікового запису', 'error')
            else:
                flash('Невірний пароль', 'error')
        else:
            flash('Користувача з таким email не знайдено', 'error')

    return render_template('login.html')


@app.route('/register/patient', methods=['GET', 'POST'])
def register_patient():
    form_data = {}
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm-password')
        first_name = request.form.get('first-name')
        last_name = request.form.get('last-name')
        birthdate_str = request.form.get('birthdate')
        phone = request.form.get('phone')
        address = request.form.get('address', '')
        blood_type = request.form.get('blood-type', '')
        allergies = request.form.get('allergies', '')
        chronic_diseases = request.form.get('chronic-diseases', '')
        gender = request.form.get('gender', '')

        form_data = {
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'birthdate': birthdate_str,
            'phone': phone,
            'address': address,
            'blood_type': blood_type,
            'allergies': allergies,
            'chronic_diseases': chronic_diseases,
            'gender': gender
        }

        if not all([email, password, confirm_password, first_name, last_name, birthdate_str, phone]):
            flash('Будь ласка, заповніть всі обов\'язкові поля', 'error')
            return render_template('p-sign-up.html', form_data=form_data)

        if password != confirm_password:
            flash('Паролі не співпадають', 'error')
            return render_template('p-sign-up.html', form_data=form_data)

        if len(password) < 8:
            flash('Пароль повинен містити мінімум 8 символів', 'error')
            return render_template('p-sign-up.html', form_data=form_data)

        if User.query.filter_by(email=email).first():
            flash('Користувач з таким email вже існує', 'error')
            return render_template('p-sign-up.html', form_data=form_data)

        try:
            birthdate = datetime.strptime(birthdate_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Невірний формат дати', 'error')
            return render_template('p-sign-up.html', form_data=form_data)

        try:
            user = User(email=email, user_type='patient')
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            patient = Patient(
                user_id=user.id,
                first_name=first_name,
                last_name=last_name,
                birthdate=birthdate,
                phone=phone,
                address=address,
                blood_type=blood_type,
                allergies=allergies,
                chronic_diseases=chronic_diseases,
                gender=gender
            )
            db.session.add(patient)
            db.session.commit()

            flash('Реєстрація успішна! Тепер увійдіть у систему.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            db.session.rollback()
            flash(f'Сталася помилка під час реєстрації: {str(e)}', 'error')
            return render_template('p-sign-up.html', form_data=form_data)

    return render_template('p-sign-up.html', form_data=form_data)


@app.route('/register/doctor', methods=['GET', 'POST'])
def register_doctor():
    if request.method == 'POST':
        try:

            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            specialization = request.form.get('specialization')
            license_number = request.form.get('license')
            phone = request.form.get('phone')
            bio = request.form.get('bio')

            print(f"Отримані дані лікаря: {email}, {first_name}, {specialization}")

            if not all([email, password, first_name, last_name, specialization, license_number, phone]):
                flash('Будь ласка, заповніть всі обов\'язкові поля', 'error')
                return render_template('d-sign-up.html')

            if password != confirm_password:
                flash('Паролі не співпадають', 'error')
                return render_template('d-sign-up.html')

            if len(password) < 8:
                flash('Пароль повинен містити мінімум 8 символів', 'error')
                return render_template('d-sign-up.html')

            if User.query.filter_by(email=email).first():
                flash('Користувач з таким email вже існує', 'error')
                return render_template('d-sign-up.html')

            user = User(email=email, user_type='doctor')
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            doctor = Doctor(
                user_id=user.id,
                first_name=first_name,
                last_name=last_name,
                specialization=specialization,
                license_number=license_number,
                phone=phone,
                bio=bio
            )
            db.session.add(doctor)
            db.session.commit()

            flash('Реєстрація успішна! Тепер увійдіть у систему.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            db.session.rollback()
            print(f"Помилка при реєстрації лікаря: {str(e)}")
            flash('Сталася помилка під час реєстрації', 'error')
            return render_template('d-sign-up.html')

    return render_template('d-sign-up.html')

@app.route('/api/doctor/patients')
def api_doctor_patients():
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    patient_ids = set([app.patient_id for app in appointments])

    patients = Patient.query.filter(Patient.id.in_(patient_ids)).all() if patient_ids else []

    patients_data = []
    for patient in patients:
        last_appointment = Appointment.query.filter_by(
            patient_id=patient.id,
            doctor_id=doctor.id
        ).order_by(Appointment.appointment_date.desc()).first()

        patients_data.append({
            'id': patient.id,
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'email': patient.user.email,
            'phone': patient.phone,
            'last_visit': last_appointment.appointment_date.strftime('%Y-%m-%d') if last_appointment else 'Never',
            'blood_type': patient.blood_type or 'Not specified'
        })

    return jsonify(patients_data)


@app.route('/api/doctor/available-patients')
def api_doctor_available_patients():
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    all_patients = Patient.query.all()

    doctor_patient_ids = {record.patient_id for record in MedicalRecord.query.filter_by(doctor_id=doctor.id).all()}
    doctor_patient_ids.update({app.patient_id for app in Appointment.query.filter_by(doctor_id=doctor.id).all()})

    available_patients = [
        patient for patient in all_patients
        if patient.id not in doctor_patient_ids
    ]

    patients_data = []
    for patient in available_patients:
        patients_data.append({
            'id': patient.id,
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'email': patient.user.email,
            'phone': patient.phone
        })

    return jsonify(patients_data)

@app.route('/api/doctor/add-patient', methods=['POST'])
def api_doctor_add_patient():
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    data = request.get_json()

    existing_user = User.query.filter_by(email=data.get('email')).first()
    if existing_user:
        return jsonify({'error': 'Patient with this email already exists'}), 400

    try:
        user = User(
            email=data.get('email'),
            user_type='patient'
        )
        user.set_password('temp_password')
        db.session.add(user)
        db.session.flush()

        patient = Patient(
            user_id=user.id,
            first_name=data.get('first_name'),
            last_name=data.get('last_name'),
            birthdate=datetime.strptime(data.get('birthdate'), '%Y-%m-%d').date(),
            phone=data.get('phone'),
            address=data.get('address', ''),
            blood_type=data.get('blood_type', ''),
            allergies=data.get('allergies', ''),
            chronic_diseases=data.get('chronic_diseases', '')
        )
        db.session.add(patient)
        db.session.flush()

        medical_record = MedicalRecord(
            patient_id=patient.id,
            doctor_id=doctor.id,
            diagnosis='Initial consultation',
            treatment='',
            prescriptions='',
            notes=f'Patient added by Dr. {doctor.first_name} {doctor.last_name} on {datetime.now().strftime("%Y-%m-%d")}'
        )
        db.session.add(medical_record)

        appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            appointment_date=datetime.now().date(),
            appointment_time=datetime.now().time(),
            reason='Initial consultation',
            status='completed',
            notes='Initial patient registration'
        )
        db.session.add(appointment)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Patient added successfully',
            'patient_id': patient.id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/doctor/patients/<int:patient_id>/appointments')
def api_doctor_patient_appointments(patient_id):
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    has_treated = MedicalRecord.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).first() is not None

    if not has_treated:
        return jsonify({'error': 'Access denied'}), 403

    appointments = Appointment.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).order_by(Appointment.appointment_date.desc()).all()

    appointments_data = []
    for appointment in appointments:
        appointments_data.append({
            'id': appointment.id,
            'date': appointment.appointment_date.strftime('%Y-%m-%d'),
            'time': appointment.appointment_time.strftime('%H:%M'),
            'reason': appointment.reason,
            'status': appointment.status,
            'notes': appointment.notes,
            'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M')
        })

    return jsonify(appointments_data)


@app.route('/api/doctor/appointments/<int:appointment_id>', methods=['DELETE'])
def api_doctor_delete_appointment(appointment_id):
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    appointment = Appointment.query.get_or_404(appointment_id)

    if appointment.doctor_id != doctor.id:
        return jsonify({'error': 'Access denied'}), 403

    try:
        patient = Patient.query.get(appointment.patient_id)
        notification = Notification(
            user_id=patient.user_id,
            title='Appointment Cancelled',
            message=f'Your appointment with Dr. {doctor.first_name} {doctor.last_name} on {appointment.appointment_date} at {appointment.appointment_time.strftime("%H:%M")} has been cancelled'
        )
        db.session.add(notification)

        db.session.delete(appointment)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Appointment deleted successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/doctor/appointments/<int:appointment_id>', methods=['PUT'])
def api_doctor_update_appointment(appointment_id):
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    appointment = Appointment.query.get_or_404(appointment_id)

    if appointment.doctor_id != doctor.id:
        return jsonify({'error': 'Access denied'}), 403

    data = request.get_json()

    try:
        if 'status' in data:
            appointment.status = data['status']

        if 'notes' in data:
            appointment.notes = data['notes']

        if 'reason' in data:
            appointment.reason = data['reason']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Appointment updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/doctor/appointments', methods=['POST'])
def api_doctor_create_appointment():
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    data = request.get_json()

    patient_id = data.get('patient_id')
    appointment_date = data.get('appointment_date')
    has_treated = MedicalRecord.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).first() is not None

    if not has_treated:
        return jsonify({'error': 'Patient is not associated with this doctor'}), 403
    appointment_time = data.get('appointment_time')
    reason = data.get('reason', '')
    notes = data.get('notes', '')

    if not all([patient_id, appointment_date, appointment_time]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        appointment_date = datetime.strptime(appointment_date, '%Y-%m-%d').date()
        appointment_time = datetime.strptime(appointment_time, '%H:%M').time()

        patient = Patient.query.get(patient_id)
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404

        has_treated = MedicalRecord.query.filter_by(
            doctor_id=doctor.id,
            patient_id=patient_id
        ).first() is not None

        if not has_treated:
            pass

        existing_appointment = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date == appointment_date,
            Appointment.appointment_time == appointment_time,
            Appointment.status == 'scheduled'
        ).first()

        if existing_appointment:
            return jsonify({'error': 'Time slot is already taken'}), 400

        appointment = Appointment(
            patient_id=patient_id,
            doctor_id=doctor.id,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            reason=reason,
            notes=notes,
            status='scheduled'
        )

        db.session.add(appointment)

        notification = Notification(
            user_id=patient.user_id,
            title='New Appointment Scheduled',
            message=f'Dr. {doctor.first_name} {doctor.last_name} has scheduled an appointment for you on {appointment_date} at {appointment_time.strftime("%H:%M")}'
        )
        db.session.add(notification)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Appointment created successfully',
            'appointment_id': appointment.id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/doctor/add-prescription', methods=['POST'])
def api_doctor_add_prescription():
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    data = request.get_json()
    patient_id = data.get('patient_id')

    has_treated = MedicalRecord.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).first() is not None

    if not has_treated:
        return jsonify({'error': 'Patient is not associated with this doctor'}), 403

    try:
        medical_record = MedicalRecord(
            patient_id=patient_id,
            doctor_id=doctor.id,
            diagnosis=data.get('diagnosis', ''),
            treatment=data.get('treatment', ''),
            prescriptions=f"{data.get('medication')} - {data.get('dosage')} - {data.get('duration')}",
            notes=data.get('instructions', '')
        )

        db.session.add(medical_record)
        db.session.commit()
        patient = Patient.query.get(patient_id)
        notification = Notification(
            user_id=patient.user_id,
            title='New Prescription',
            message=f'Dr. {doctor.first_name} {doctor.last_name} has prescribed {data.get("medication")} for you.'
        )
        db.session.add(notification)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Prescription added successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/doctor/medical-records/<int:patient_id>')
def api_doctor_patient_medical_records(patient_id):
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    has_treated = MedicalRecord.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).first() is not None

    if not has_treated:
        return jsonify({'error': 'Access denied'}), 403

    records = MedicalRecord.query.filter_by(patient_id=patient_id).order_by(
        MedicalRecord.record_date.desc()
    ).all()

    records_data = []
    for record in records:
        doctor = Doctor.query.get(record.doctor_id)
        records_data.append({
            'id': record.id,
            'date': record.record_date.strftime('%Y-%m-%d'),
            'diagnosis': record.diagnosis,
            'treatment': record.treatment,
            'prescriptions': record.prescriptions,
            'notes': record.notes,
            'doctor_name': f'Dr. {record.doctor.first_name} {record.doctor.last_name}'
        })

    return jsonify(records_data)


@app.route('/doctor/dashboard')
def doctor_dashboard():
    print(f"Doctor dashboard access - session: {dict(session)}")

    if 'user_id' not in session:
        print("No user_id in session, redirecting to login")
        return redirect(url_for('login'))

    if session.get('user_type') != 'doctor':
        print(f"Wrong user type: {session.get('user_type')}, redirecting to login")
        return redirect(url_for('login'))

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        print("Doctor not found in database, redirecting to login")
        return redirect(url_for('login'))

    print(f"Doctor found: {doctor.first_name} {doctor.last_name}")

    today = datetime.now().date()

    appointments_today = Appointment.query.filter_by(
        doctor_id=doctor.id,
        appointment_date=today,
        status='scheduled'
    ).all()

    appointments_today_count = len(appointments_today)
    appointment_patients = Appointment.query.filter_by(doctor_id=doctor.id).all()
    medical_records = MedicalRecord.query.filter_by(doctor_id=doctor.id).all()
    patient_ids = set([record.patient_id for record in medical_records])
    patient_ids.update([app.patient_id for app in appointment_patients])
    total_patients = len(patient_ids) if patient_ids else 0
    total_appointments = Appointment.query.filter_by(doctor_id=doctor.id).count()

    yesterday = today - timedelta(days=1)
    yesterday_appointments_count = Appointment.query.filter_by(
        doctor_id=doctor.id,
        appointment_date=yesterday
    ).count()

    week_start = today - timedelta(days=today.weekday())
    new_patients_this_week = 0

    pending_prescriptions_count = 0

    unread_notifications_count = Notification.query.filter_by(
        user_id=session['user_id'],
        is_read=False
    ).count()

    weekly_appointments_data = []
    for i in range(7):
        day = today - timedelta(days=i)
        count = Appointment.query.filter_by(
            doctor_id=doctor.id,
            appointment_date=day
        ).count()
        weekly_appointments_data.append({
            'day': day.strftime('%a'),
            'count': count
        })
    weekly_appointments_data.reverse()

    recent_appointments = Appointment.query.filter_by(
        doctor_id=doctor.id
    ).order_by(Appointment.created_at.desc()).limit(5).all()

    recent_patients = []
    for app in recent_appointments:
        patient = Patient.query.get(app.patient_id)
        recent_patients.append({
            'id': patient.id,
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'gender': patient.gender or 'male',
            'last_visit': app.appointment_date.strftime('%Y-%m-%d')
        })

    recent_notifications = Notification.query.filter_by(
        user_id=session['user_id']
    ).order_by(Notification.created_at.desc()).limit(5).all()

    formatted_notifications = []
    for notification in recent_notifications:
        formatted_notifications.append({
            'title': notification.title,
            'message': notification.message,
            'time_ago': format_timesince(notification.created_at),
            'icon': get_notification_icon(notification.title)
        })

    appointment_patients = set([app.patient_id for app in Appointment.query.filter_by(doctor_id=doctor.id).all()])
    patient_ids = patient_ids.union(appointment_patients)

    all_patients = Patient.query.filter(Patient.id.in_(patient_ids)).all() if patient_ids else []

    medical_records_with_expiry = []
    medical_records = MedicalRecord.query.filter_by(doctor_id=doctor.id).order_by(
        MedicalRecord.record_date.desc()).limit(5).all()

    for record in medical_records:
        expiry_date = record.record_date + timedelta(days=30)
        medical_records_with_expiry.append({
            'record': record,
            'expiry_date': expiry_date.strftime('%Y-%m-%d')
        })

        upcoming_appointments = Appointment.query.filter_by(
            doctor_id=doctor.id,
            status='scheduled'
        ).filter(Appointment.appointment_date >= datetime.now().date()).order_by(
            Appointment.appointment_date.asc()
        ).limit(10).all()
        for appointment in upcoming_appointments:
            appointment.patient = Patient.query.get(appointment.patient_id)
        weekly_data = []
        for i in range(7):
            day = today - timedelta(days=6 - i)
            count = Appointment.query.filter_by(
                doctor_id=doctor.id,
                appointment_date=day
            ).count()
            max_appointments = 8
            percentage = (count / max_appointments) * 100 if max_appointments > 0 else 0
            weekly_data.append({
                'day': day.strftime('%a'),
                'count': count,
                'percentage': percentage
            })

    return render_template('e1.html',
                           doctor=doctor,
                           all_patients=all_patients,
                           appointments_today=appointments_today,
                           appointments_today_count=appointments_today_count,
                           total_patients=total_patients,
                           total_appointments=total_appointments,
                           yesterday_appointments_count=yesterday_appointments_count,
                           new_patients_this_week=new_patients_this_week,
                           pending_prescriptions_count=pending_prescriptions_count,
                           unread_notifications_count=unread_notifications_count,
                           weekly_appointments_data=weekly_appointments_data,
                           recent_patients=recent_patients,
                           recent_notifications=formatted_notifications,
                           unread_messages_count=0,
                           urgent_messages_count=0,
                           medical_records_with_expiry=medical_records_with_expiry,
                           today=today,
                           timedelta=timedelta)

@app.route('/api/doctor/my-patients')
def api_doctor_my_patients():
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    medical_records = MedicalRecord.query.filter_by(doctor_id=doctor.id).all()
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()

    patient_ids = set()
    for record in medical_records:
        patient_ids.add(record.patient_id)
    for appointment in appointments:
        patient_ids.add(appointment.patient_id)

    patients = Patient.query.filter(Patient.id.in_(patient_ids)).all() if patient_ids else []

    patients_data = []
    for patient in patients:
        patients_data.append({
            'id': patient.id,
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'full_name': f'{patient.first_name} {patient.last_name}'
        })

    return jsonify(patients_data)

def format_timesince(dt):
    now = datetime.utcnow()
    diff = now - dt

    if diff.days > 0:
        return f"{diff.days} days ago"
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        return f"{hours} hours ago"
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        return f"{minutes} minutes ago"
    else:
        return "Just now"

def get_notification_icon(title):
    icon_map = {
        'appointment': 'calendar-check',
        'prescription': 'prescription-bottle-alt',
        'message': 'envelope',
        'patient': 'user-plus',
        'lab': 'file-medical'
    }

    for key, icon in icon_map.items():
        if key in title.lower():
            return icon

    return 'bell'



@app.route('/api/doctor/associate-patient', methods=['POST'])
def api_doctor_associate_patient():
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    data = request.get_json()
    patient_id = data.get('patient_id')

    if not patient_id:
        return jsonify({'error': 'Patient ID is required'}), 400
    patient = Patient.query.get(patient_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    existing_record = MedicalRecord.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).first()

    if existing_record:
        return jsonify({'error': 'Patient is already associated with this doctor'}), 400

    try:

        medical_record = MedicalRecord(
            patient_id=patient_id,
            doctor_id=doctor.id,
            diagnosis='Initial consultation',
            treatment='',
            prescriptions='',
            notes=f'Patient associated by Dr. {doctor.first_name} {doctor.last_name} on {datetime.now().strftime("%Y-%m-%d")}'
        )
        db.session.add(medical_record)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Patient associated successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/patient/appointments')
def api_patient_appointments():
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    appointments = Appointment.query.filter_by(patient_id=patient.id).order_by(
        Appointment.appointment_date.desc(), Appointment.appointment_time.desc()).all()

    appointments_data = []
    for app in appointments:
        doctor = Doctor.query.get(app.doctor_id)
        appointments_data.append({
            'id': app.id,
            'doctor_name': f'Dr. {doctor.first_name} {doctor.last_name}',
            'specialization': doctor.specialization,
            'date': app.appointment_date.strftime('%Y-%m-%d'),
            'time': app.appointment_time.strftime('%H:%M'),
            'status': app.status,
            'reason': app.reason,
            'notes': app.notes
        })

    return jsonify(appointments_data)


@app.route('/api/patient/prescriptions')
def api_patient_prescriptions():
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    prescriptions = MedicalRecord.query.filter(
        MedicalRecord.patient_id == patient.id,
        MedicalRecord.prescriptions.isnot(None)
    ).order_by(MedicalRecord.record_date.desc()).all()

    prescriptions_data = []
    for record in prescriptions:
        doctor = Doctor.query.get(record.doctor_id)
        prescriptions_data.append({
            'id': record.id,
            'doctor_name': f'Dr. {doctor.first_name} {doctor.last_name}',
            'date': record.record_date.strftime('%Y-%m-%d'),
            'prescriptions': record.prescriptions,
            'diagnosis': record.diagnosis
        })

    return jsonify(prescriptions_data)


@app.route('/patient/dashboard')
def patient_dashboard():
    print(f"Patient dashboard access - session: {dict(session)}")

    if 'user_id' not in session:
        print("No user_id in session, redirecting to login")
        return redirect(url_for('login'))

    if session.get('user_type') != 'patient':
        print(f"Wrong user type: {session.get('user_type')}, redirecting to login")
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        print("User not found in database, redirecting to login")
        return redirect(url_for('login'))

    patient = Patient.query.filter_by(user_id=user.id).first()
    if not patient:
        print("Patient not found in database, redirecting to login")
        return redirect(url_for('login'))

    print(f"Patient found: {patient.first_name} {patient.last_name}")

    upcoming_appointments = Appointment.query.filter_by(
        patient_id=patient.id,
        status='scheduled'
    ).filter(Appointment.appointment_date >= datetime.now().date()).all()

    for appointment in upcoming_appointments:
        appointment.doctor = Doctor.query.get(appointment.doctor_id)

    doctors = Doctor.query.all()
    medical_records = MedicalRecord.query.filter_by(patient_id=patient.id).order_by(
        MedicalRecord.record_date.desc()
    ).all()
    for record in medical_records:
        record.doctor = Doctor.query.get(record.doctor_id)
    notifications = Notification.query.filter_by(user_id=patient.user_id, is_read=False).all()
    unread_notifications_count = len(notifications)
    thirty_days_ago = datetime.now().date() - timedelta(days=30)
    active_prescriptions_count = MedicalRecord.query.filter(
        MedicalRecord.patient_id == patient.id,
        MedicalRecord.prescriptions.isnot(None),
        MedicalRecord.record_date >= thirty_days_ago
    ).count()
    active_prescriptions = []
    prescriptions_records = MedicalRecord.query.filter(
        MedicalRecord.patient_id == patient.id,
        MedicalRecord.prescriptions.isnot(None),
        MedicalRecord.record_date >= thirty_days_ago
    ).order_by(MedicalRecord.record_date.desc()).all()

    for record in prescriptions_records:
        prescription_parts = record.prescriptions.split(' - ')
        medication = prescription_parts[0] if len(prescription_parts) > 0 else 'Unknown'
        dosage = prescription_parts[1] if len(prescription_parts) > 1 else 'Not specified'
        expiry_date = record.record_date + timedelta(days=30)

        active_prescriptions.append({
            'medication': medication,
            'dosage': dosage,
            'expiry_date': expiry_date,
            'record': record
        })
    recent_medical_records = MedicalRecord.query.filter_by(patient_id=patient.id).order_by(
        MedicalRecord.record_date.desc()
    ).limit(5).all()
    for record in recent_medical_records:
        record.doctor = Doctor.query.get(record.doctor_id)
    recent_notifications = Notification.query.filter_by(user_id=patient.user_id).order_by(
        Notification.created_at.desc()
    ).limit(5).all()
    urgent_notifications_count = Notification.query.filter_by(
        user_id=patient.user_id,
        is_read=False
    ).filter(Notification.title.ilike('%urgent%')).count()

    return render_template('e2.html',
                           patient=patient,
                           user=user,
                           upcoming_appointments=upcoming_appointments,
                           doctors=doctors,
                           active_prescriptions=active_prescriptions,
                           medical_records=medical_records,
                           recent_medical_records=recent_medical_records,
                           recent_notifications=recent_notifications,
                           active_prescriptions_count=active_prescriptions_count,
                           unread_notifications_count=unread_notifications_count,
                           urgent_notifications_count=urgent_notifications_count,
                           today=datetime.now().date(),
                           Doctor=Doctor)

@app.route('/api/doctor/patients-search')
def api_doctor_patients_search():
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    search_term = request.args.get('search', '')
    medical_record_patients = MedicalRecord.query.filter_by(doctor_id=doctor.id).with_entities(
        MedicalRecord.patient_id).all()
    appointment_patients = Appointment.query.filter_by(doctor_id=doctor.id).with_entities(Appointment.patient_id).all()

    patient_ids = set([record.patient_id for record in medical_record_patients])
    patient_ids.update([app.patient_id for app in appointment_patients])

    if not patient_ids:
        return jsonify([])

    query = Patient.query.filter(Patient.id.in_(patient_ids))

    if search_term:
        query = query.filter(or_(
            Patient.first_name.ilike(f'%{search_term}%'),
            Patient.last_name.ilike(f'%{search_term}%'),
            Patient.phone.ilike(f'%{search_term}%')
        ))

    patients = query.all()

    patients_data = []
    for patient in patients:
        last_appointment = Appointment.query.filter_by(
            patient_id=patient.id,
            doctor_id=doctor.id
        ).order_by(Appointment.appointment_date.desc()).first()

        patients_data.append({
            'id': patient.id,
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'email': patient.user.email,
            'phone': patient.phone,
            'last_visit': last_appointment.appointment_date.strftime('%Y-%m-%d') if last_appointment else 'Never',
            'blood_type': patient.blood_type or 'Not specified'
        })

    return jsonify(patients_data)


@app.route('/api/doctor/appointments')
def api_doctor_appointments():
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    appointments = Appointment.query.filter_by(doctor_id=doctor.id).order_by(
        Appointment.appointment_date.desc(), Appointment.appointment_time.desc()).all()

    appointments_data = []
    for appointment in appointments:
        patient = Patient.query.get(appointment.patient_id)
        appointments_data.append({
            'id': appointment.id,
            'patient_name': f'{patient.first_name} {patient.last_name}',
            'date': appointment.appointment_date.strftime('%Y-%m-%d'),
            'time': appointment.appointment_time.strftime('%H:%M'),
            'reason': appointment.reason,
            'status': appointment.status,
            'notes': appointment.notes
        })

    return jsonify(appointments_data)
@app.route('/api/doctor/patient/<int:patient_id>', methods=['DELETE'])
def api_doctor_delete_patient(patient_id):
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    has_treated = MedicalRecord.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).first() is not None

    if not has_treated:
        return jsonify({'error': 'Patient is not associated with this doctor'}), 403

    try:
        MedicalRecord.query.filter_by(
            doctor_id=doctor.id,
            patient_id=patient_id
        ).delete()
        Appointment.query.filter_by(
            doctor_id=doctor.id,
            patient_id=patient_id
        ).delete()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Patient removed successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/doctor/patient/<int:patient_id>', methods=['PUT'])
def api_doctor_update_patient(patient_id):
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    has_treated = MedicalRecord.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).first() is not None

    if not has_treated:
        return jsonify({'error': 'Patient is not associated with this doctor'}), 403

    patient = Patient.query.get_or_404(patient_id)
    data = request.get_json()

    try:
        if 'first_name' in data:
            patient.first_name = data['first_name']
        if 'last_name' in data:
            patient.last_name = data['last_name']
        if 'phone' in data:
            patient.phone = data['phone']
        if 'address' in data:
            patient.address = data['address']
        if 'blood_type' in data:
            patient.blood_type = data['blood_type']
        if 'allergies' in data:
            patient.allergies = data['allergies']
        if 'chronic_diseases' in data:
            patient.chronic_diseases = data['chronic_diseases']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Patient updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/patient/update-profile', methods=['POST'])
def api_patient_update_profile():
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    try:
        data = request.get_json()

        if 'first_name' in data:
            patient.first_name = data['first_name']
        if 'last_name' in data:
            patient.last_name = data['last_name']
        if 'phone' in data:
            patient.phone = data['phone']
        if 'address' in data:
            patient.address = data['address']
        if 'blood_type' in data:
            patient.blood_type = data['blood_type']
        if 'allergies' in data:
            patient.allergies = data['allergies']
        if 'chronic_diseases' in data:
            patient.chronic_diseases = data['chronic_diseases']

        db.session.commit()

        return jsonify({'success': True, 'message': 'Профіль успішно оновлено'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500




@app.route('/api/patient/update-medical-info', methods=['POST'])
def api_patient_update_medical_info():
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    try:
        data = request.get_json()

        if 'blood_type' in data:
            patient.blood_type = data['blood_type']
        if 'allergies' in data:
            patient.allergies = data['allergies']
        if 'chronic_diseases' in data:
            patient.chronic_diseases = data['chronic_diseases']

        db.session.commit()

        return jsonify({'success': True, 'message': 'Медична інформація успішно оновлена'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/doctors')
def api_doctors():
    specialization = request.args.get('specialization')
    if specialization:
        doctors = Doctor.query.filter_by(specialization=specialization, is_active=True).all()
    else:
        doctors = Doctor.query.filter_by(is_active=True).all()

    doctors_data = []
    for doctor in doctors:
        doctors_data.append({
            'id': doctor.id,
            'name': f'Др. {doctor.first_name} {doctor.last_name}',
            'specialization': doctor.specialization,
            'bio': doctor.bio
        })

    return jsonify(doctors_data)


@app.route('/api/doctor/<int:doctor_id>/availability')
def api_doctor_availability(doctor_id):
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'Date parameter is required'}), 400

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except:
        return jsonify({'error': 'Invalid date format'}), 400

    doctor = Doctor.query.get_or_404(doctor_id)

    day_of_week = date.weekday()
    working_hours = WorkingHours.query.filter_by(doctor_id=doctor_id, day_of_week=day_of_week).first()

    if not working_hours:
        return jsonify({'available_slots': []})

    appointments = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == date,
        Appointment.status == 'scheduled'
    ).all()

    available_slots = []
    current_time = datetime.combine(date, working_hours.start_time)
    end_time = datetime.combine(date, working_hours.end_time)

    while current_time + timedelta(minutes=30) <= end_time:
        slot_end = current_time + timedelta(minutes=30)

        slot_available = True
        for app in appointments:
            app_start = datetime.combine(date, app.appointment_time)
            app_end = app_start + timedelta(minutes=app.duration or 30)

            if not (slot_end <= app_start or current_time >= app_end):
                slot_available = False
                break

        if slot_available:
            available_slots.append(current_time.time().strftime('%H:%M'))

        current_time += timedelta(minutes=30)

    return jsonify({'available_slots': available_slots})


@app.route('/api/appointments', methods=['POST'])
def api_create_appointment():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json()
    doctor_id = data.get('doctor_id')
    appointment_date = data.get('date')
    appointment_time = data.get('time')
    reason = data.get('reason', '')

    try:
        appointment_date = datetime.strptime(appointment_date, '%Y-%m-%d').date()
        appointment_time = datetime.strptime(appointment_time, '%H:%M').time()
    except:
        return jsonify({'error': 'Invalid date or time format'}), 400

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    existing_appointment = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == appointment_date,
        Appointment.appointment_time == appointment_time,
        Appointment.status == 'scheduled'
    ).first()

    if existing_appointment:
        return jsonify({'error': 'Time slot is already taken'}), 400
    appointment = Appointment(
        patient_id=patient.id,
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        appointment_time=appointment_time,
        reason=reason,
        status='scheduled'
    )

    db.session.add(appointment)
    db.session.commit()

    doctor = Doctor.query.get(doctor_id)
    notification = Notification(
        user_id=doctor.user_id,
        title='Новий запис на прийом',
        message=f'Пацієнт {patient.first_name} {patient.last_name} записався на {appointment_date} о {appointment_time}'
    )
    db.session.add(notification)
    db.session.commit()

    return jsonify({'success': True, 'appointment_id': appointment.id})


@app.route('/api/medical-records/<int:patient_id>')
def api_medical_records(patient_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    if session.get('user_type') == 'doctor':
        doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
        if not doctor:
            return jsonify({'error': 'Doctor not found'}), 404

        has_access = MedicalRecord.query.filter_by(doctor_id=doctor.id, patient_id=patient_id).first() is not None
        if not has_access:
            return jsonify({'error': 'Access denied'}), 403

    records = MedicalRecord.query.filter_by(patient_id=patient_id).order_by(MedicalRecord.record_date.desc()).all()

    records_data = []
    for record in records:
        doctor = Doctor.query.get(record.doctor_id)
        records_data.append({
            'id': record.id,
            'date': record.record_date.strftime('%Y-%m-%d'),
            'doctor': f'Др. {doctor.first_name} {doctor.last_name}',
            'diagnosis': record.diagnosis,
            'treatment': record.treatment,
            'prescriptions': record.prescriptions,
            'notes': record.notes
        })

    return jsonify(records_data)


@app.route('/api/notifications')
def api_notifications():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    notifications = Notification.query.filter_by(user_id=session['user_id'], is_read=False).order_by(
        Notification.created_at.desc()).all()

    notifications_data = []
    for notification in notifications:
        notifications_data.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'created_at': notification.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_read': notification.is_read
        })

    return jsonify(notifications_data)

@app.route('/api/doctor/patient/<int:patient_id>/add-prescription', methods=['POST'])
def api_doctor_add_patient_prescription(patient_id):
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    has_treated = MedicalRecord.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).first() is not None

    if not has_treated:
        return jsonify({'error': 'Patient is not associated with this doctor'}), 403

    data = request.get_json()

    try:
        medical_record = MedicalRecord(
            patient_id=patient_id,
            doctor_id=doctor.id,
            diagnosis=data.get('diagnosis', ''),
            treatment=data.get('treatment', ''),
            prescriptions=f"{data.get('medication')} - {data.get('dosage')} - {data.get('duration')}",
            notes=data.get('instructions', ''),
            record_date=datetime.utcnow()
        )

        db.session.add(medical_record)
        patient = Patient.query.get(patient_id)
        notification = Notification(
            user_id=patient.user_id,
            title='New Prescription Added',
            message=f'Dr. {doctor.first_name} {doctor.last_name} has added a new prescription for you.',
            is_read=False
        )
        db.session.add(notification)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Prescription added successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/doctor/patient/<int:patient_id>/medical-records', methods=['POST'])
def api_doctor_add_medical_record(patient_id):
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    has_treated = MedicalRecord.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).first() is not None

    if not has_treated:
        return jsonify({'error': 'Patient is not associated with this doctor'}), 403

    data = request.get_json()

    try:
        medical_record = MedicalRecord(
            patient_id=patient_id,
            doctor_id=doctor.id,
            diagnosis=data.get('diagnosis', ''),
            treatment=data.get('treatment', ''),
            prescriptions=data.get('prescriptions', ''),
            notes=data.get('notes', ''),
            record_date=datetime.utcnow()
        )

        db.session.add(medical_record)
        patient = Patient.query.get(patient_id)
        notification = Notification(
            user_id=patient.user_id,
            title='Medical Record Updated',
            message=f'Dr. {doctor.first_name} {doctor.last_name} has updated your medical records.',
            is_read=False
        )
        db.session.add(notification)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Medical record added successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/doctor/patient/<int:patient_id>/send-notification', methods=['POST'])
def api_doctor_send_notification(patient_id):
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404
    has_treated = MedicalRecord.query.filter_by(
        doctor_id=doctor.id,
        patient_id=patient_id
    ).first() is not None

    if not has_treated:
        return jsonify({'error': 'Patient is not associated with this doctor'}), 403

    data = request.get_json()

    try:
        patient = Patient.query.get(patient_id)
        notification = Notification(
            user_id=patient.user_id,
            title=data.get('title', 'Notification from Doctor'),
            message=data.get('message', ''),
            is_read=False
        )

        db.session.add(notification)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Notification sent successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/patient/medical-records')
def api_patient_medical_records():
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    records = MedicalRecord.query.filter_by(patient_id=patient.id).order_by(
        MedicalRecord.record_date.desc()
    ).all()

    records_data = []
    for record in records:
        doctor = Doctor.query.get(record.doctor_id)
        records_data.append({
            'id': record.id,
            'date': record.record_date.strftime('%Y-%m-%d'),
            'doctor_name': f'Dr. {doctor.first_name} {doctor.last_name}',
            'diagnosis': record.diagnosis,
            'treatment': record.treatment,
            'prescriptions': record.prescriptions,
            'notes': record.notes
        })

    return jsonify(records_data)


@app.route('/api/patient/notifications')
def api_patient_notifications():
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    notifications = Notification.query.filter_by(
        user_id=session['user_id']
    ).order_by(Notification.created_at.desc()).all()

    notifications_data = []
    for notification in notifications:
        notifications_data.append({
            'id': notification.id,
            'title': notification.title,
            'message': notification.message,
            'is_read': notification.is_read,
            'created_at': notification.created_at.strftime('%Y-%m-%d %H:%M')
        })

    return jsonify(notifications_data)


@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
def api_mark_notification_read(notification_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != session['user_id']:
        return jsonify({'error': 'Access denied'}), 403

    notification.is_read = True
    db.session.commit()

    return jsonify({'success': True})
@app.route('/api/patient/prescription/<int:record_id>/pdf')
def download_prescription_pdf(record_id):
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    record = db.session.get(MedicalRecord, record_id)
    if not record or record.patient_id != patient.id:
        return jsonify({'error': 'Access denied'}), 403

    try:
        font_name = register_ukrainian_font()
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont(font_name, 12)

        y_position = 750
        line_height = 14

        def safe_draw_text(text, x=50, y=None, font_size=12, bold=False):
            nonlocal y_position
            if y is None:
                y = y_position
            if text is None:
                text = ""
            text = str(text)
            if bold:
                try:
                    bold_font = font_name + "-Bold"
                    p.setFont(bold_font, font_size)
                except:
                    p.setFont(font_name, font_size)
                    p.setFillColorRGB(0, 0, 0)
            else:
                p.setFont(font_name, font_size)
                p.setFillColorRGB(0, 0, 0)

            try:
                p.drawString(x, y, text)
            except UnicodeEncodeError:
                ukrainian_chars = {
                    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Ґ': 'G', 'Д': 'D',
                    'Е': 'E', 'Є': 'Ye', 'Ж': 'Zh', 'З': 'Z', 'И': 'Y',
                    'І': 'I', 'Ї': 'Yi', 'Й': 'Y', 'К': 'K', 'Л': 'L',
                    'М': 'M', 'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R',
                    'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'Kh',
                    'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch', 'Ь': '',
                    'Ю': 'Yu', 'Я': 'Ya',
                    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'ґ': 'g', 'д': 'd',
                    'е': 'e', 'є': 'ye', 'ж': 'zh', 'з': 'z', 'и': 'y',
                    'і': 'i', 'ї': 'yi', 'й': 'y', 'к': 'k', 'л': 'l',
                    'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
                    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh',
                    'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ь': '',
                    'ю': 'yu', 'я': 'ya'
                }
                safe_text = ''.join(ukrainian_chars.get(char, char) for char in text)
                p.drawString(x, y, safe_text)
            except Exception as e:
                p.drawString(x, y, "")

            if y == y_position:
                y_position -= line_height

            return y_position

        def draw_multiline_text(text, x=50, max_width=80):
            nonlocal y_position

            if not text:
                return
            words = text.split()
            lines = []
            current_line = []

            for word in words:
                test_line = ' '.join(current_line + [word])
                if len(test_line) <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]

            if current_line:
                lines.append(' '.join(current_line))

            for line in lines:
                safe_draw_text(line, x)
                y_position -= line_height
        safe_draw_text("МЕДИЧНА КЛІНІКА 'MEDICONNECT'", 50, 750, 14, True)
        safe_draw_text("ОФІЦІЙНИЙ РЕЦЕПТ", 50, 735, 12, True)
        y_position -= 20
        safe_draw_text(f"Номер рецепту: PR-{record_id:06d}", bold=True)
        safe_draw_text(f"Дата випису: {record.record_date.strftime('%d.%m.%Y %H:%M')}")
        safe_draw_text(f"Дійсний до: {(record.record_date + timedelta(days=30)).strftime('%d.%m.%Y')}")
        y_position -= 10
        safe_draw_text("ІНФОРМАЦІЯ ПРО ПАЦІЄНТА", bold=True)
        safe_draw_text(f"ПІБ: {patient.first_name} {patient.last_name}")
        safe_draw_text(f"Дата народження: {patient.birthdate.strftime('%d.%m.%Y')}")
        safe_draw_text(f"Телефон: {patient.phone or 'Не вказано'}")
        safe_draw_text(f"Група крові: {patient.blood_type or 'Не вказано'}")
        y_position -= 10
        doctor = db.session.get(Doctor, record.doctor_id)
        safe_draw_text("ІНФОРМАЦІЯ ПРО ЛІКАРЯ", bold=True)
        safe_draw_text(f"ПІБ: Др. {doctor.first_name} {doctor.last_name}")
        safe_draw_text(f"Спеціалізація: {doctor.specialization}")
        safe_draw_text(f"Ліцензія: {doctor.license_number}")
        safe_draw_text(f"Телефон: {doctor.phone}")
        y_position -= 10
        if record.diagnosis and record.diagnosis.strip():
            safe_draw_text("ДІАГНОЗ", bold=True)
            draw_multiline_text(record.diagnosis)
            y_position -= 5

        if record.treatment and record.treatment.strip():
            safe_draw_text("ЛІКУВАННЯ", bold=True)
            draw_multiline_text(record.treatment)
            y_position -= 5

        if record.prescriptions and record.prescriptions.strip():
            safe_draw_text("ПРИЗНАЧЕННЯ", bold=True)
            draw_multiline_text(record.prescriptions)
            y_position -= 5

        if record.notes and record.notes.strip():
            safe_draw_text("ДОДАТКОВІ ПРИМІТКИ", bold=True)
            draw_multiline_text(record.notes)
            y_position -= 5
        safe_draw_text("ВАЖЛИВІ ПРИМІТКИ", bold=True)
        y_position -= 5

        important_notes = [
            "Цей рецепт дійсний протягом 30 днів з дати випису",
            "Ліки приймати строго за призначенням лікаря",
            "При виникненні побічних ефектів негайно звернутися до лікаря",
            "Зберігати в недоступному для дітей місці",
            "Не використовувати після закінчення терміну придатності"
        ]

        for note in important_notes:
            safe_draw_text(f"• {note}")
            y_position -= line_height

        y_position -= 10

        safe_draw_text("_________________________", 50, y_position)
        safe_draw_text("Підпис пацієнта", 70, y_position - 15, 8)

        safe_draw_text("_________________________", 300, y_position)
        safe_draw_text("Підпис лікаря", 320, y_position - 15, 8)

        safe_draw_text(f"Документ створено: {datetime.now().strftime('%d.%m.%Y %H:%M')}", 50, 50, 8)

        p.showPage()
        p.save()
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'рецепт_{patient.last_name}_{record.record_date.strftime("%Y%m%d")}.pdf',
            mimetype='application/pdf'
        )

    except Exception as e:
        return jsonify({'error': f'Помилка генерації PDF: {str(e)}'}), 500

@app.route('/api/patient/prescription/<int:record_id>/pdf-simple')
def download_prescription_pdf_simple(record_id):
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    record = db.session.get(MedicalRecord, record_id)
    if not record or record.patient_id != patient.id:
        return jsonify({'error': 'Access denied'}), 403

    try:
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica", 10)

        y = 750
        line_height = 14

        def draw_ascii_text(text, y_pos=None):
            nonlocal y
            if y_pos is None:
                y_pos = y
            if text is None:
                text = ""
            ukrainian_to_latin = {
                'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Ґ': 'G', 'Д': 'D',
                'Е': 'E', 'Є': 'Ye', 'Ж': 'Zh', 'З': 'Z', 'И': 'Y',
                'І': 'I', 'Ї': 'Yi', 'Й': 'Y', 'К': 'K', 'Л': 'L',
                'М': 'M', 'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R',
                'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'Kh',
                'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
                'Ю': 'Yu', 'Я': 'Ya',
                'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'ґ': 'g', 'д': 'd',
                'е': 'e', 'є': 'ye', 'ж': 'zh', 'з': 'z', 'и': 'y',
                'і': 'i', 'ї': 'yi', 'й': 'y', 'к': 'k', 'л': 'l',
                'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
                'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh',
                'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
                'ю': 'yu', 'я': 'ya'
            }

            ascii_text = ''.join(ukrainian_to_latin.get(char, char) for char in str(text))
            p.drawString(50, y_pos, ascii_text[:80])

            if y_pos == y:
                y -= line_height
            return y
        draw_ascii_text("MEDYCHNA KLINIKA 'MEDICONNECT'")
        draw_ascii_text("OFITSIIYNYI RETSEPT")
        y -= 20
        draw_ascii_text(f"Nomier retseptu: PR-{record_id:06d}")
        draw_ascii_text(f"Data vypysu: {record.record_date.strftime('%d.%m.%Y %H:%M')}")
        draw_ascii_text(f"Diisnyi do: {(record.record_date + timedelta(days=30)).strftime('%d.%m.%Y')}")
        y -= 10
        draw_ascii_text("INFORMATSIIA PRO PATSIiENTA")
        draw_ascii_text(f"PIB: {patient.first_name} {patient.last_name}")
        draw_ascii_text(f"Data narodzhennia: {patient.birthdate.strftime('%d.%m.%Y')}")
        draw_ascii_text(f"Telefon: {patient.phone or 'Ne vkazano'}")
        draw_ascii_text(f"Grupa krovi: {patient.blood_type or 'Ne vkazano'}")
        y -= 10
        doctor = db.session.get(Doctor, record.doctor_id)
        draw_ascii_text("INFORMATSIIA PRO LIKARIA")
        draw_ascii_text(f"PIB: Dr. {doctor.first_name} {doctor.last_name}")
        draw_ascii_text(f"Spetsializatsiia: {doctor.specialization}")
        draw_ascii_text(f"Litsenziia: {doctor.license_number}")
        draw_ascii_text(f"Telefon: {doctor.phone}")
        y -= 10
        if record.diagnosis:
            draw_ascii_text("DIAHNOZ")
            words = record.diagnosis.split()
            lines = []
            current_line = []
            for word in words:
                if len(' '.join(current_line + [word])) <= 80:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
            if current_line:
                lines.append(' '.join(current_line))

            for line in lines:
                draw_ascii_text(line)
            y -= 5

        if record.prescriptions:
            draw_ascii_text("PRYZNACHENNIA")
            words = record.prescriptions.split()
            lines = []
            current_line = []
            for word in words:
                if len(' '.join(current_line + [word])) <= 80:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
            if current_line:
                lines.append(' '.join(current_line))

            for line in lines:
                draw_ascii_text(line)

        p.showPage()
        p.save()
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'prescription_{patient.last_name}.pdf',
            mimetype='application/pdf'
        )

    except Exception as e:
        return jsonify({'error': f'PDF generation failed: {str(e)}'}), 500

@app.route('/api/patient/medical-record/<int:record_id>/pdf')
def download_medical_record_pdf(record_id):
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    record = db.session.get(MedicalRecord, record_id)
    if not record or record.patient_id != patient.id:
        return jsonify({'error': 'Access denied'}), 403

    try:
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica", 10)

        y_position = 750
        line_height = 14

        def ukrainian_to_ascii(text):
            if not text:
                return ""

            translit_map = {
                'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'H', 'Ґ': 'G', 'Д': 'D',
                'Е': 'E', 'Є': 'Ye', 'Ж': 'Zh', 'З': 'Z', 'И': 'Y',
                'І': 'I', 'Ї': 'Yi', 'Й': 'Y', 'К': 'K', 'Л': 'L',
                'М': 'M', 'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R',
                'С': 'S', 'Т': 'T', 'У': 'U', 'Ф': 'F', 'Х': 'Kh',
                'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Shch',
                'Ю': 'Yu', 'Я': 'Ya',
                'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd',
                'е': 'e', 'є': 'ye', 'ж': 'zh', 'з': 'z', 'и': 'y',
                'і': 'i', 'ї': 'yi', 'й': 'y', 'к': 'k', 'л': 'l',
                'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
                'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh',
                'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
                'ю': 'yu', 'я': 'ya',
                'ʼ': "'", '`': "'", '´': "'", 'ь': '', 'ъ': ''
            }
            result = []
            for char in str(text):
                if char in translit_map:
                    result.append(translit_map[char])
                else:
                    result.append(char)

            return ''.join(result)

        def wrap_text(text, max_length):
            if not text:
                return []

            words = text.split()
            lines = []
            current_line = []

            for word in words:
                if len(' '.join(current_line + [word])) <= max_length:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]

            if current_line:
                lines.append(' '.join(current_line))

            return lines

        def draw_text(text, x=50, y=None, bold=False, font_size=10):
            nonlocal y_position
            if y is None:
                y = y_position
            safe_text = ukrainian_to_ascii(text)

            if bold:
                p.setFont("Helvetica-Bold", font_size)
            else:
                p.setFont("Helvetica", font_size)

            p.drawString(x, y, safe_text)

            if y == y_position:
                y_position -= line_height

            return y_position

        def draw_multiline(text, x=50):
            nonlocal y_position
            if not text:
                return y_position

            lines = wrap_text(text, 80)
            for line in lines:
                draw_text(line, x)
                y_position -= 2

            return y_position

        draw_text("MEDICAL RECORD - MEDICONNECT CLINIC", 50, 750, True, 14)
        draw_text("Official Medical Documentation", 50, 735, False, 12)
        y_position -= 20

        draw_text("RECORD INFORMATION", bold=True)
        draw_text(f"Record ID: MR-{record_id:06d}")
        draw_text(f"Date of Visit: {record.record_date.strftime('%d.%m.%Y at %H:%M')}")
        draw_text(f"Valid Until: {(record.record_date + timedelta(days=365)).strftime('%d.%m.%Y')}")
        y_position -= 10

        draw_text("PATIENT INFORMATION", bold=True)
        draw_text(f"Full Name: {patient.first_name} {patient.last_name}")
        draw_text(f"Date of Birth: {patient.birthdate.strftime('%d.%m.%Y')}")
        draw_text(f"Phone: {patient.phone or 'Not provided'}")
        draw_text(f"Blood Type: {patient.blood_type or 'Not specified'}")
        y_position -= 10

        doctor = db.session.get(Doctor, record.doctor_id)
        draw_text("DOCTOR INFORMATION", bold=True)
        draw_text(f"Name: Dr. {doctor.first_name} {doctor.last_name}")
        draw_text(f"Specialization: {doctor.specialization}")
        draw_text(f"License: {doctor.license_number}")
        draw_text(f"Contact: {doctor.phone}")
        y_position -= 10

        if record.diagnosis and record.diagnosis.strip():
            draw_text("DIAGNOSIS", bold=True)
            y_position = draw_multiline(record.diagnosis)
            y_position -= 5

        if record.treatment and record.treatment.strip():
            draw_text("TREATMENT PLAN", bold=True)
            y_position = draw_multiline(record.treatment)
            y_position -= 5

        if record.prescriptions and record.prescriptions.strip():
            draw_text("PRESCRIPTIONS", bold=True)
            y_position = draw_multiline(record.prescriptions)
            y_position -= 5

        if record.notes and record.notes.strip():
            draw_text("MEDICAL NOTES", bold=True)
            y_position = draw_multiline(record.notes)
            y_position -= 5

        y_position = 100
        draw_text("MEDICONNECT MEDICAL CLINIC", 50, y_position, True)
        draw_text("Official Medical Documentation", 50, y_position - 15)
        draw_text("This document is generated electronically and is legally valid", 50, y_position - 30, font_size=8)
        draw_text(f"Generated on: {datetime.now().strftime('%d.%m.%Y at %H:%M')}", 50, y_position - 45, font_size=8)

        p.showPage()
        p.save()
        buffer.seek(0)

        filename = f'medical_record_{patient.last_name}_{record.record_date.strftime("%Y%m%d")}.pdf'
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

    except Exception as e:
        return jsonify({'error': f'PDF generation failed: {str(e)}'}), 500

@app.route('/api/patient/notifications/mark-all-read', methods=['POST'])
def mark_all_notifications_read():
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        Notification.query.filter_by(user_id=session['user_id'], is_read=False).update({'is_read': True})
        db.session.commit()
        return jsonify({'success': True, 'message': 'Всі сповіщення позначено як прочитані'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/patient/appointments/<int:appointment_id>/cancel', methods=['POST'])
def cancel_patient_appointment(appointment_id):
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.patient_id != patient.id:
        return jsonify({'error': 'Access denied'}), 403

    try:
        appointment.status = 'cancelled'

        doctor = Doctor.query.get(appointment.doctor_id)
        notification = Notification(
            user_id=doctor.user_id,
            title='Запис скасовано',
            message=f'Пацієнт {patient.first_name} {patient.last_name} скасував запис на {appointment.appointment_date}'
        )
        db.session.add(notification)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Запис успішно скасовано'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/patient/doctors')
def api_patient_doctors():
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    medical_record_doctors = db.session.query(Doctor).join(MedicalRecord).filter(
        MedicalRecord.patient_id == patient.id
    ).distinct().all()

    appointment_doctors = db.session.query(Doctor).join(Appointment).filter(
        Appointment.patient_id == patient.id
    ).distinct().all()

    all_doctors = list(set(medical_record_doctors + appointment_doctors))

    doctors_data = []
    for doctor in all_doctors:
        last_appointment = Appointment.query.filter_by(
            patient_id=patient.id,
            doctor_id=doctor.id
        ).order_by(Appointment.appointment_date.desc()).first()

        total_appointments = Appointment.query.filter_by(
            patient_id=patient.id,
            doctor_id=doctor.id
        ).count()

        doctors_data.append({
            'id': doctor.id,
            'name': f'Др. {doctor.first_name} {doctor.last_name}',
            'specialization': doctor.specialization,
            'phone': doctor.phone,
            'bio': doctor.bio or 'Інформація відсутня',
            'last_visit': last_appointment.appointment_date.strftime(
                '%d.%m.%Y') if last_appointment else 'Ще не було візитів',
            'total_visits': total_appointments,
            'rating': 4.5,
            'reviews': 12
        })

    return jsonify(doctors_data)

@app.route('/api/patient/avatar', methods=['POST'])
def update_patient_avatar():
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'message': 'Аватар успішно оновлено'})

@app.route('/api/patient/appointments/<int:appointment_id>')
def get_appointment_details(appointment_id):
    if 'user_id' not in session or session.get('user_type') != 'patient':
        return jsonify({'error': 'Not authenticated'}), 401

    patient = Patient.query.filter_by(user_id=session['user_id']).first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    appointment = Appointment.query.get_or_404(appointment_id)
    if appointment.patient_id != patient.id:
        return jsonify({'error': 'Access denied'}), 403

    doctor = Doctor.query.get(appointment.doctor_id)

    appointment_data = {
        'id': appointment.id,
        'doctor_name': f'Др. {doctor.first_name} {doctor.last_name}',
        'specialization': doctor.specialization,
        'date': appointment.appointment_date.strftime('%d.%m.%Y'),
        'time': appointment.appointment_time.strftime('%H:%M'),
        'status': appointment.status,
        'reason': appointment.reason or 'Не вказано',
        'notes': appointment.notes or 'Примітки відсутні',
        'duration': appointment.duration or 30,
        'created_at': appointment.created_at.strftime('%d.%m.%Y %H:%M')
    }

    return jsonify(appointment_data)


def register_ukrainian_font():
    font_paths = [
        'arial.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
        '/Library/Fonts/Arial.ttf',
        'DejaVuSans.ttf',
        'times.ttf'
    ]

    for font_path in font_paths:
        try:
            pdfmetrics.registerFont(TTFont('UkrainianFont', font_path))
            return 'UkrainianFont'
        except:
            continue

    try:
        return 'Helvetica'
    except:
        return 'Helvetica'
def wrap_text(text, max_length):
    if not text:
        return []

    words = text.split()
    lines = []
    current_line = []

    for word in words:
        if len(' '.join(current_line + [word])) <= max_length:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]

    if current_line:
        lines.append(' '.join(current_line))

    return lines


@app.route('/api/doctor/avatar', methods=['POST'])
def upload_doctor_avatar():
    if 'user_id' not in session or session.get('user_type') != 'doctor':
        return jsonify({'error': 'Not authenticated'}), 401

    doctor = Doctor.query.filter_by(user_id=session['user_id']).first()
    if not doctor:
        return jsonify({'error': 'Doctor not found'}), 404

    if 'avatar' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(f"doctor_{doctor.id}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        file.save(filepath)

        doctor.avatar = filename
        db.session.commit()

        return jsonify({'success': True, 'avatar_url': f'/static/uploads/{filename}'})

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except FileNotFoundError:
        return send_from_directory('static', 'default-avatar.png')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()