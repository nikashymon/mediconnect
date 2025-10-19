import sqlite3
import telebot
from telebot import types
import datetime
import random
from datetime import datetime, timedelta
import requests
import json
import time
import threading
from flask import Flask
import logging
import os
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.lib import colors
import io
import pytz
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bot = telebot.TeleBot('8303636514:AAFbdfLKzi0f1tCH6nZ591_nSW5ygJJTnuQ')
WEBSITE_URL = "http://127.0.0.1:5000"
user_states = {}

def get_db_connection():
    return sqlite3.connect('DataBase.db', check_same_thread=False)

def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telegram_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                user_email TEXT,
                patient_id INTEGER,
                is_verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notification_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                appointment_reminders BOOLEAN DEFAULT TRUE,
                prescription_alerts BOOLEAN DEFAULT TRUE,
                general_notifications BOOLEAN DEFAULT TRUE,
                medication_reminders BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (telegram_id) REFERENCES telegram_users (telegram_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS medication_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                medication_name TEXT,
                dosage TEXT,
                frequency TEXT,
                times_per_day INTEGER,
                specific_times TEXT,
                start_date DATE,
                end_date DATE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS appointment_reminders_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER,
                appointment_id INTEGER,
                reminder_type TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        logging.info("Database tables initialized successfully")
    except Exception as e:
        logging.error(f"Error initializing database: {e}")
    finally:
        conn.close()

init_database()

def get_user_state(telegram_id):
    return user_states.get(telegram_id, {})

def set_user_state(telegram_id, state, data=None):
    if telegram_id not in user_states:
        user_states[telegram_id] = {}
    user_states[telegram_id]['state'] = state
    if data:
        user_states[telegram_id]['data'] = data

def clear_user_state(telegram_id):
    if telegram_id in user_states:
        del user_states[telegram_id]

def get_patient_by_email(email):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT p.id, p.first_name, p.last_name, u.email 
            FROM patient p 
            JOIN user u ON p.user_id = u.id 
            WHERE u.email = ?
        ''', (email,))
        result = cursor.fetchone()
        return result
    except Exception as e:
        logging.error(f"Error getting patient by email: {e}")
        return None
    finally:
        conn.close()

def verify_patient_email(email, telegram_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        patient = get_patient_by_email(email)
        if patient:
            patient_id, first_name, last_name, patient_email = patient
            cursor.execute('''
                INSERT OR REPLACE INTO telegram_users 
                (telegram_id, user_email, patient_id, is_verified) 
                VALUES (?, ?, ?, TRUE)
            ''', (telegram_id, patient_email, patient_id))
            cursor.execute('''
                INSERT OR IGNORE INTO notification_settings 
                (telegram_id, appointment_reminders, prescription_alerts, general_notifications, medication_reminders) 
                VALUES (?, TRUE, TRUE, TRUE, TRUE)
            ''', (telegram_id,))

            conn.commit()
            logging.info(f"Patient {patient_email} verified successfully for Telegram ID {telegram_id}")
            return True, patient
        return False, None
    except Exception as e:
        logging.error(f"Error verifying email: {e}")
        conn.rollback()
        return False, None
    finally:
        conn.close()


def get_patient_appointments(patient_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT a.id, a.appointment_date, a.appointment_time, 
                   d.first_name, d.last_name, d.specialization
            FROM appointment a
            JOIN doctor d ON a.doctor_id = d.id
            WHERE a.patient_id = ? AND a.status = 'scheduled'
            AND a.appointment_date >= date('now')
            ORDER BY a.appointment_date, a.appointment_time
        ''', (patient_id,))
        result = cursor.fetchall()
        return result
    except Exception as e:
        logging.error(f"Error getting patient appointments: {e}")
        return []
    finally:
        conn.close()


def get_recent_prescriptions(patient_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT mr.id, mr.record_date, mr.prescriptions, 
                   d.first_name, d.last_name, d.specialization
            FROM medical_record mr
            JOIN doctor d ON mr.doctor_id = d.id
            WHERE mr.patient_id = ? AND mr.prescriptions IS NOT NULL
            ORDER BY mr.record_date DESC
            LIMIT 10
        ''', (patient_id,))
        result = cursor.fetchall()
        return result
    except Exception as e:
        logging.error(f"Error getting patient prescriptions: {e}")
        return []
    finally:
        conn.close()


def get_prescription_details(prescription_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT mr.id, mr.record_date, mr.prescriptions, 
                   d.first_name, d.last_name, d.specialization,
                   p.first_name, p.last_name, p.date_of_birth
            FROM medical_record mr
            JOIN doctor d ON mr.doctor_id = d.id
            JOIN patient p ON mr.patient_id = p.id
            WHERE mr.id = ?
        ''', (prescription_id,))
        result = cursor.fetchone()
        return result
    except Exception as e:
        logging.error(f"Error getting prescription details: {e}")
        return None
    finally:
        conn.close()


def get_telegram_user(telegram_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT tu.*, p.first_name, p.last_name 
            FROM telegram_users tu
            LEFT JOIN patient p ON tu.patient_id = p.id
            WHERE tu.telegram_id = ?
        ''', (telegram_id,))
        result = cursor.fetchone()
        return result
    except Exception as e:
        logging.error(f"Error getting telegram user: {e}")
        return None
    finally:
        conn.close()


def get_medication_schedule(patient_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT * FROM medication_schedule 
            WHERE patient_id = ? AND is_active = TRUE
            ORDER BY created_at DESC
        ''', (patient_id,))
        result = cursor.fetchall()
        return result
    except Exception as e:
        logging.error(f"Error getting medication schedule: {e}")
        return []
    finally:
        conn.close()


def add_medication_schedule(patient_id, medication_name, dosage, frequency, times_per_day, specific_times, start_date,
                            end_date):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO medication_schedule 
            (patient_id, medication_name, dosage, frequency, times_per_day, specific_times, start_date, end_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (patient_id, medication_name, dosage, frequency, times_per_day, specific_times, start_date, end_date))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error adding medication schedule: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def generate_prescription_pdf(prescription_data):
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            alignment=1,
            textColor=colors.darkblue
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            spaceAfter=12,
            textColor=colors.darkblue
        )

        normal_style = styles['Normal']
        story = []
        story.append(Paragraph("МЕДИЧНИЙ РЕЦЕПТ", title_style))
        story.append(Spacer(1, 20))
        story.append(Paragraph("ІНФОРМАЦІЯ ПРО ПАЦІЄНТА", heading_style))
        patient_info = [
            f"ПІБ: {prescription_data[6]} {prescription_data[7]}",
            f"Дата народження: {prescription_data[8]}",
            f"Дата призначення: {prescription_data[1]}"
        ]
        for info in patient_info:
            story.append(Paragraph(info, normal_style))
        story.append(Spacer(1, 15))
        story.append(Paragraph("ЛІКАР", heading_style))
        doctor_info = [
            f"ПІБ: Др. {prescription_data[3]} {prescription_data[4]}",
            f"Спеціалізація: {prescription_data[5]}"
        ]
        for info in doctor_info:
            story.append(Paragraph(info, normal_style))
        story.append(Spacer(1, 15))
        story.append(Paragraph("ПРИЗНАЧЕННЯ", heading_style))
        prescription_text = prescription_data[2] or "Інформація відсутня"
        story.append(Paragraph(prescription_text, normal_style))
        story.append(Spacer(1, 20))
        footer_text = f"Згенеровано: {datetime.now().strftime('%d.%m.%Y о %H:%M')}"
        story.append(Paragraph(footer_text, normal_style))
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()
        return pdf
    except Exception as e:
        logging.error(f"Error generating PDF: {e}")
        return None


def send_medication_reminders():
    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            current_time = datetime.now()
            current_time_str = current_time.strftime('%H:%M')
            cursor.execute('''
                SELECT ms.*, tu.telegram_id, p.first_name, p.last_name
                FROM medication_schedule ms
                JOIN patient p ON ms.patient_id = p.id
                JOIN telegram_users tu ON p.id = tu.patient_id
                JOIN notification_settings ns ON tu.telegram_id = ns.telegram_id
                WHERE ms.is_active = TRUE 
                AND ns.medication_reminders = TRUE
                AND tu.is_verified = TRUE
                AND ms.start_date <= date('now') 
                AND (ms.end_date IS NULL OR ms.end_date >= date('now'))
            ''')
            medications = cursor.fetchall()
            for med in medications:
                if len(med) >= 14:
                    med_id, patient_id, med_name, dosage, frequency, times_per_day, specific_times, start_date, end_date, is_active, created_at, telegram_id, first_name, last_name = med
                    if specific_times:
                        times_list = [t.strip() for t in specific_times.split(',')]
                        for med_time in times_list:
                            if current_time_str == med_time:
                                send_medication_alert(telegram_id, first_name, last_name, med_name, dosage, med_time)
                    else:
                        default_times = {
                            1: ["08:00"],
                            2: ["08:00", "20:00"],
                            3: ["08:00", "14:00", "20:00"],
                            4: ["08:00", "12:00", "16:00", "20:00"]
                        }
                        if times_per_day in default_times:
                            for default_time in default_times[times_per_day]:
                                if current_time_str == default_time:
                                    send_medication_alert(telegram_id, first_name, last_name, med_name, dosage,
                                                          default_time)
            conn.close()
            time.sleep(60)
        except Exception as e:
            logging.error(f"Error in medication reminder loop: {e}")
            time.sleep(300)


def send_medication_alert(telegram_id, first_name, last_name, medication_name, dosage, med_time):
    try:
        message = f"""
💊 **Час прийому ліків**

👤 Пацієнт: {first_name} {last_name}
💊 Ліки: {medication_name}
📏 Дозування: {dosage}
⏰ Час: {med_time}

Будь ласка, прийміть ліки відповідно до призначення лікаря.

Будьте здорові! ❤️
        """

        bot.send_message(telegram_id, message, parse_mode='Markdown')
        logging.info(f"Sent medication reminder to {telegram_id}")

    except Exception as e:
        logging.error(f"Failed to send medication reminder to {telegram_id}: {e}")


def send_appointment_reminders():
    while True:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.id, a.patient_id, a.appointment_date, a.appointment_time,
                       d.first_name, d.last_name, d.specialization,
                       p.first_name, p.last_name, tu.telegram_id
                FROM appointment a
                JOIN doctor d ON a.doctor_id = d.id
                JOIN patient p ON a.patient_id = p.id
                JOIN telegram_users tu ON p.id = tu.patient_id
                JOIN notification_settings ns ON tu.telegram_id = ns.telegram_id
                WHERE a.status = 'scheduled'
                AND ns.appointment_reminders = TRUE
                AND tu.is_verified = TRUE
            ''')
            appointments = cursor.fetchall()
            for appointment in appointments:
                app_id, patient_id, app_date, app_time, doc_first, doc_last, specialization, pat_first, pat_last, telegram_id = appointment
                if '.' in app_time:
                    app_time = app_time.split('.')[0]
                try:
                    app_datetime = datetime.strptime(f"{app_date} {app_time}", "%Y-%m-%d %H:%M")
                    now = datetime.now()
                    time_diff = (app_datetime - now).total_seconds() / 3600
                    cursor.execute('''
                        SELECT reminder_type FROM appointment_reminders_log 
                        WHERE appointment_id = ? AND patient_id = ?
                        AND date(sent_at) = date('now')
                    ''', (app_id, patient_id))
                    sent_reminders = [row[0] for row in cursor.fetchall()]
                    if 24 <= time_diff < 25 and '24h' not in sent_reminders:
                        send_single_appointment_reminder(telegram_id, pat_first, pat_last, doc_first, doc_last,
                                                         specialization, app_date, app_time, "24 години")
                        log_appointment_reminder(conn, patient_id, app_id, '24h')
                    elif 1 <= time_diff < 2 and '1h' not in sent_reminders:
                        send_single_appointment_reminder(telegram_id, pat_first, pat_last, doc_first, doc_last,
                                                         specialization, app_date, app_time, "1 година")
                        log_appointment_reminder(conn, patient_id, app_id, '1h')
                except ValueError as e:
                    logging.error(f"Error parsing time: {e}")
                    continue
            time.sleep(300)
        except Exception as e:
            logging.error(f"Error in appointment reminder loop: {e}")
            time.sleep(300)
        finally:
            if conn:
                conn.close()
def send_single_appointment_reminder(telegram_id, pat_first, pat_last, doc_first, doc_last, specialization, app_date,
                                     app_time, reminder_time):
    try:
        reminder_message = f"""
🔔 **Нагадування про прийом ({reminder_time})**

👤 Пацієнт: {pat_first} {pat_last}
👨‍⚕️ Лікар: Др. {doc_first} {doc_last}
🎯 Спеціалізація: {specialization}
📅 Дата: {app_date}
⏰ Час: {app_time}

Не забудьте про ваш запис! 🏥
        """

        bot.send_message(telegram_id, reminder_message, parse_mode='Markdown')
        logging.info(f"Sent appointment reminder to {telegram_id}")

    except Exception as e:
        logging.error(f"Failed to send appointment reminder to {telegram_id}: {e}")


def log_appointment_reminder(conn, patient_id, appointment_id, reminder_type):
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO appointment_reminders_log (patient_id, appointment_id, reminder_type)
            VALUES (?, ?, ?)
        ''', (patient_id, appointment_id, reminder_type))
        conn.commit()
    except Exception as e:
        logging.error(f"Error logging appointment reminder: {e}")


def send_prescription_alerts():
    while True:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT mr.id, mr.patient_id, mr.record_date, mr.prescriptions,
                       d.first_name, d.last_name, p.first_name, p.last_name,
                       tu.telegram_id
                FROM medical_record mr
                JOIN doctor d ON mr.doctor_id = d.id
                JOIN patient p ON mr.patient_id = p.id
                JOIN telegram_users tu ON p.id = tu.patient_id
                JOIN notification_settings ns ON tu.telegram_id = ns.telegram_id
                WHERE mr.prescriptions IS NOT NULL
                AND mr.record_date >= datetime('now', '-1 hour')
                AND ns.prescription_alerts = TRUE
                AND tu.is_verified = TRUE
            ''')
            prescriptions = cursor.fetchall()
            for prescription in prescriptions:
                mr_id, patient_id, record_date, prescriptions_text, doc_first, doc_last, pat_first, pat_last, telegram_id = prescription

                alert_message = f"""
💊 **Нове призначення ліків**

👤 Пацієнт: {pat_first} {pat_last}
👨‍⚕️ Лікар: Др. {doc_first} {doc_last}
📅 Дата призначення: {record_date}
💊 Призначення: {prescriptions_text}

Будьте здорові! ❤️
                """

                try:
                    bot.send_message(telegram_id, alert_message, parse_mode='Markdown')
                    logging.info(f"Sent prescription alert to {telegram_id}")
                except Exception as e:
                    logging.error(f"Failed to send prescription alert to {telegram_id}: {e}")

            time.sleep(1800)

        except Exception as e:
            logging.error(f"Error in prescription alert loop: {e}")
            time.sleep(300)
        finally:
            if conn:
                conn.close()


def start_notification_threads():
    appointment_thread = threading.Thread(target=send_appointment_reminders, daemon=True)
    prescription_thread = threading.Thread(target=send_prescription_alerts, daemon=True)
    medication_thread = threading.Thread(target=send_medication_reminders, daemon=True)
    appointment_thread.start()
    prescription_thread.start()
    medication_thread.start()
    logging.info("All notification threads started successfully")
@bot.message_handler(commands=['start'])
def send_welcome(message):
    telegram_id = message.chat.id
    user = get_telegram_user(telegram_id)

    if user and user[4]:
        welcome_message = f"""
👋 Вітаємо, {user[6]} {user[7]}!

🏥 **Mediconnect Telegram Bot**

Оберіть опцію з меню нижче:
        """
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add('📅 Мої записи', '💊 Мої призначення')
        markup.add('⏰ Мої ліки', '📥 Завантажити рецепт')
        markup.add('⚙️ Налаштування', 'ℹ️ Допомога')
        bot.send_message(telegram_id, welcome_message, reply_markup=markup, parse_mode='Markdown')
    else:
        welcome_message = """
👋 Вітаємо в Mediconnect!

🏥 **Telegram Bot для пацієнтів**

Для початку роботи необхідно підтвердити ваш обліковий запис.

📧 Будь ласка, введіть ваш email, який ви використовували при реєстрації на сайті:
        """
        set_user_state(telegram_id, 'awaiting_email')
        bot.send_message(telegram_id, welcome_message, parse_mode='Markdown')
@bot.message_handler(func=lambda message: get_user_state(message.chat.id).get('state') == 'awaiting_email')
def handle_email_input(message):
    telegram_id = message.chat.id
    email = message.text.strip()
    if '@' not in email or '.' not in email:
        bot.send_message(telegram_id, "❌ Будь ласка, введіть коректний email адрес:")
        return
    bot.send_message(telegram_id, "🔍 Перевіряємо ваш email...")
    success, patient = verify_patient_email(email, telegram_id)
    if success:
        clear_user_state(telegram_id)
        success_message = f"""
✅ **Вітаємо! Обліковий запис підтверджено!**

👤 Пацієнт: {patient[1]} {patient[2]}
📧 Email: {patient[3]}

Тепер ви будете отримувати сповіщення про:
• 📅 Записи на прийом
• 💊 Призначення ліків
• ⏰ Нагадування про прийом ліків
• 🔔 Важливі повідомлення

Оберіть опцію з меню:
        """

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add('📅 Мої записи', '💊 Мої призначення')
        markup.add('⏰ Мої ліки', '📥 Завантажити рецепт')
        markup.add('⚙️ Налаштування', 'ℹ️ Допомога')

        bot.send_message(telegram_id, success_message, reply_markup=markup, parse_mode='Markdown')
    else:
        bot.send_message(telegram_id, """
❌ **Не вдалося знайти обліковий запис**

Перевірте, чи правильно ви ввели email, який використовували при реєстрації на сайті.

📧 Будь ласка, спробуйте ще раз або зверніться до адміністратора:
        """)

@bot.message_handler(func=lambda message: message.text == '📅 Мої записи')
def show_appointments(message):
    telegram_id = message.chat.id
    user = get_telegram_user(telegram_id)

    if not user or not user[4]:
        bot.send_message(telegram_id, "❌ Будь ласка, спочатку підтвердіть ваш обліковий запис командою /start")
        return

    appointments = get_patient_appointments(user[3])

    if not appointments:
        bot.send_message(telegram_id, "📭 У вас немає майбутніх записів на прийом.")
        return

    appointments_text = "📅 **Ваші майбутні записи:**\n\n"

    for i, appointment in enumerate(appointments, 1):
        app_id, app_date, app_time, doc_first, doc_last, specialization = appointment
        appointments_text += f"{i}. **Др. {doc_first} {doc_last}**\n"
        appointments_text += f"   🎯 {specialization}\n"
        appointments_text += f"   📅 {app_date} ⏰ {app_time}\n\n"

    bot.send_message(telegram_id, appointments_text, parse_mode='Markdown')


@bot.message_handler(func=lambda message: message.text == '💊 Мої призначення')
def show_prescriptions(message):
    telegram_id = message.chat.id
    user = get_telegram_user(telegram_id)

    if not user or not user[4]:
        bot.send_message(telegram_id, "❌ Будь ласка, спочатку підтвердіть ваш обліковий запис командою /start")
        return

    prescriptions = get_recent_prescriptions(user[3])

    if not prescriptions:
        bot.send_message(telegram_id, "💊 У вас немає активних призначень ліків.")
        return

    for i, prescription in enumerate(prescriptions, 1):
        mr_id, record_date, prescription_text, doc_first, doc_last, specialization = prescription

        prescription_msg = f"""
**Рецепт #{i}**

👨‍⚕️ **Лікар:** Др. {doc_first} {doc_last}
🎯 **Спеціалізація:** {specialization}
📅 **Дата призначення:** {record_date}
💊 **Призначення:** {prescription_text[:100]}...
        """

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📥 Завантажити PDF", callback_data=f"download_pdf_{mr_id}"))

        bot.send_message(telegram_id, prescription_msg, parse_mode='Markdown', reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == '⏰ Мої ліки')
def show_medication_schedule(message):
    telegram_id = message.chat.id
    user = get_telegram_user(telegram_id)

    if not user or not user[4]:
        bot.send_message(telegram_id, "❌ Будь ласка, спочатку підтвердіть ваш обліковий запис командою /start")
        return

    medications = get_medication_schedule(user[3])

    if not medications:
        bot.send_message(telegram_id, "⏰ У вас немає активного графіку прийому ліків.")

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ Додати графік прийому ліків", callback_data="add_medication"))
        bot.send_message(telegram_id, "Бажаєте додати графік прийому ліків для нагадувань?", reply_markup=markup)
        return

    medications_text = "⏰ **Ваш графік прийому ліків:**\n\n"

    for i, med in enumerate(medications, 1):
        if len(med) >= 11:
            med_id, patient_id, med_name, dosage, frequency, times_per_day, specific_times, start_date, end_date, is_active, created_at = med

            medications_text += f"{i}. **{med_name}**\n"
            medications_text += f"   📏 Дозування: {dosage}\n"
            medications_text += f"   ⏱️ Частота: {frequency}\n"

            if specific_times:
                medications_text += f"   ⏰ Час прийому: {specific_times}\n"
            else:
                medications_text += f"   🔢 Разів на день: {times_per_day}\n"

            medications_text += f"   📅 Початок: {start_date}\n"
            if end_date:
                medications_text += f"   📅 Завершення: {end_date}\n"

            medications_text += f"   {'✅ Активно' if is_active else '❌ Неактивно'}\n\n"

    bot.send_message(telegram_id, medications_text, parse_mode='Markdown')


@bot.message_handler(func=lambda message: message.text == '📥 Завантажити рецепт')
def download_prescription_menu(message):
    telegram_id = message.chat.id
    user = get_telegram_user(telegram_id)

    if not user or not user[4]:
        bot.send_message(telegram_id, "❌ Будь ласка, спочатку підтвердіть ваш обліковий запис командою /start")
        return

    prescriptions = get_recent_prescriptions(user[3])

    if not prescriptions:
        bot.send_message(telegram_id, "💊 У вас немає призначень для завантаження.")
        return

    markup = types.InlineKeyboardMarkup()

    for i, prescription in enumerate(prescriptions[:5], 1):
        mr_id, record_date, prescription_text, doc_first, doc_last, specialization = prescription
        button_text = f"{i}. {record_date} - Др. {doc_first} {doc_last}"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"download_pdf_{mr_id}"))

    bot.send_message(telegram_id, "📥 Оберіть призначення для завантаження у форматі PDF:", reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == '⚙️ Налаштування')
def show_settings(message):
    telegram_id = message.chat.id
    user = get_telegram_user(telegram_id)

    if not user or not user[4]:
        bot.send_message(telegram_id, "❌ Будь ласка, спочатку підтвердіть ваш обліковий запис командою /start")
        return

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            SELECT appointment_reminders, prescription_alerts, general_notifications, medication_reminders
            FROM notification_settings WHERE telegram_id = ?
        ''', (telegram_id,))
        settings = cursor.fetchone()

        if settings:
            app_reminders, presc_alerts, gen_notif, med_reminders = settings

            settings_text = f"""
⚙️ **Налаштування сповіщень**

👤 Пацієнт: {user[6]} {user[7]}
📧 Email: {user[2]}

🔔 **Типи сповіщень:**
{'✅' if app_reminders else '❌'} Нагадування про записи
{'✅' if presc_alerts else '❌'} Сповіщення про призначення
{'✅' if med_reminders else '❌'} Нагадування про ліки
{'✅' if gen_notif else '❌'} Загальні сповіщення

Використовуйте кнопки нижче для зміни налаштувань:
            """

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton(
                    f"{'🔕' if app_reminders else '🔔'} Записи",
                    callback_data=f"toggle_appointments_{not app_reminders}"
                ),
                types.InlineKeyboardButton(
                    f"{'🔕' if presc_alerts else '🔔'} Призначення",
                    callback_data=f"toggle_prescriptions_{not presc_alerts}"
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    f"{'🔕' if med_reminders else '🔔'} Ліки",
                    callback_data=f"toggle_medications_{not med_reminders}"
                ),
                types.InlineKeyboardButton(
                    f"{'🔕' if gen_notif else '🔔'} Загальні",
                    callback_data=f"toggle_general_{not gen_notif}"
                )
            )

            bot.send_message(telegram_id, settings_text, parse_mode='Markdown', reply_markup=markup)

    except Exception as e:
        logging.error(f"Error getting settings: {e}")
        bot.send_message(telegram_id, "❌ Помилка при завантаженні налаштувань.")
    finally:
        conn.close()


@bot.message_handler(func=lambda message: message.text == 'ℹ️ Допомога')
def show_help(message):
    help_text = """
ℹ️ **Довідка по боту**

🏥 **Mediconnect Telegram Bot**

**Доступні функції:**

📅 **Мої записи** - Перегляд майбутніх записів на прийом
💊 **Мої призначення** - Останні призначення ліків
⏰ **Мої ліки** - Графік прийому ліків та нагадування
📥 **Завантажити рецепт** - Завантажити призначення у PDF
⚙️ **Налаштування** - Керування сповіщеннями
ℹ️ **Допомога** - Ця довідка

**Автоматичні сповіщення:**
• Нагадування про записи (за 24 години та 1 годину)
• Сповіщення про нові призначення
• Нагадування про прийом ліків
• Важливі загальні сповіщення

**Команди:**
/start - Початок роботи
/help - Довідка

📞 **Підтримка:** Звертайтеся до адміністратора клініки за додатковою допомогою.
    """

    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')


@bot.callback_query_handler(func=lambda call: call.data.startswith('download_pdf_'))
def handle_pdf_download(call):
    telegram_id = call.message.chat.id
    data = call.data

    try:
        prescription_id = int(data.split('_')[2])
        bot.answer_callback_query(call.id, "📄 Генеруємо PDF...")
        download_prescription_pdf(telegram_id, prescription_id)

    except Exception as e:
        logging.error(f"Error handling PDF download callback: {e}")
        bot.answer_callback_query(call.id, "❌ Помилка при завантаженні")
        bot.send_message(telegram_id, "❌ Сталася помилка при завантаженні PDF. Спробуйте пізніше.")


def download_prescription_pdf(telegram_id, prescription_id):
    try:
        logging.info(f"Downloading PDF for prescription {prescription_id}")

        prescription_data = get_prescription_details(prescription_id)

        if not prescription_data:
            bot.send_message(telegram_id, "❌ Не вдалося знайти інформацію про призначення.")
            return
        pdf_data = generate_prescription_pdf(prescription_data)

        if pdf_data:
            pdf_file = io.BytesIO(pdf_data)
            pdf_file.name = f"рецепт_{prescription_id}.pdf"
            bot.send_document(
                telegram_id,
                pdf_file,
                caption="💊 Ваше медичне призначення"
            )
            logging.info(f"PDF sent successfully to {telegram_id}")
        else:
            bot.send_message(telegram_id, "❌ Помилка при генерації PDF файлу.")

    except Exception as e:
        logging.error(f"Error downloading PDF: {e}")
        bot.send_message(telegram_id, "❌ Помилка при завантаженні PDF файлу.")


@bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_'))
def handle_toggle_callback(call):
    telegram_id = call.message.chat.id
    data = call.data

    try:
        setting_type = data.split('_')[1]
        new_value = data.split('_')[2] == 'True'

        conn = get_db_connection()
        cursor = conn.cursor()

        setting_map = {
            'appointments': 'appointment_reminders',
            'prescriptions': 'prescription_alerts',
            'medications': 'medication_reminders',
            'general': 'general_notifications'
        }

        if setting_type in setting_map:
            column = setting_map[setting_type]
            cursor.execute(f'''
                UPDATE notification_settings 
                SET {column} = ? 
                WHERE telegram_id = ?
            ''', (new_value, telegram_id))
            conn.commit()

            status = "увімкнено" if new_value else "вимкнено"
            bot.answer_callback_query(call.id, f"✅ Налаштування {status}!")
            show_settings(call.message)

    except Exception as e:
        logging.error(f"Error toggling setting: {e}")
        bot.answer_callback_query(call.id, "❌ Помилка при зміні налаштувань.")
    finally:
        conn.close()


@bot.callback_query_handler(func=lambda call: call.data == 'add_medication')
def handle_add_medication(call):
    telegram_id = call.message.chat.id
    start_medication_setup(telegram_id)
    bot.answer_callback_query(call.id)


def start_medication_setup(telegram_id):
    set_user_state(telegram_id, 'awaiting_medication_name')
    bot.send_message(telegram_id, "💊 **Додавання графіку прийому ліків**\n\nВведіть назву ліків:")


@bot.message_handler(
    func=lambda message: get_user_state(message.chat.id).get('state', '').startswith('awaiting_medication'))
def handle_medication_setup(message):
    telegram_id = message.chat.id
    current_state = get_user_state(telegram_id).get('state')
    user_data = get_user_state(telegram_id).get('data', {})

    if current_state == 'awaiting_medication_name':
        user_data['medication_name'] = message.text
        set_user_state(telegram_id, 'awaiting_medication_dosage', user_data)
        bot.send_message(telegram_id, "📏 Введіть дозування (наприклад: 1 таблетка, 10мл тощо):")

    elif current_state == 'awaiting_medication_dosage':
        user_data['dosage'] = message.text
        set_user_state(telegram_id, 'awaiting_medication_frequency', user_data)

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add('Щодня', 'Через день', 'Щотижня', 'За потребою')
        bot.send_message(telegram_id, "⏱️ Оберіть частоту прийому:", reply_markup=markup)

    elif current_state == 'awaiting_medication_frequency':
        user_data['frequency'] = message.text
        set_user_state(telegram_id, 'awaiting_medication_times', user_data)
        bot.send_message(telegram_id, "🔢 Скільки разів на день потрібно приймати ліки? (Введіть число):")

    elif current_state == 'awaiting_medication_times':
        try:
            times_per_day = int(message.text)
            user_data['times_per_day'] = times_per_day
            set_user_state(telegram_id, 'awaiting_medication_start', user_data)
            bot.send_message(telegram_id, "📅 Введіть дату початку прийому (РРРР-ММ-ДД):")
        except ValueError:
            bot.send_message(telegram_id, "❌ Будь ласка, введіть коректне число:")

    elif current_state == 'awaiting_medication_start':
        user_data['start_date'] = message.text
        set_user_state(telegram_id, 'awaiting_medication_end', user_data)
        bot.send_message(telegram_id,
                         "📅 Введіть дату завершення прийому (РРРР-ММ-ДД) або 'немає' для постійного прийому:")

    elif current_state == 'awaiting_medication_end':
        end_date = None if message.text.lower() == 'немає' else message.text
        user_data['end_date'] = end_date

        user = get_telegram_user(telegram_id)
        if user:
            success = add_medication_schedule(
                user[3],
                user_data['medication_name'],
                user_data['dosage'],
                user_data['frequency'],
                user_data['times_per_day'],
                "",
                user_data['start_date'],
                user_data['end_date']
            )

            if success:
                bot.send_message(telegram_id, "✅ Графік прийому ліків успішно додано!",
                                 reply_markup=types.ReplyKeyboardRemove())
            else:
                bot.send_message(telegram_id, "❌ Помилка при додаванні графіку.")

        clear_user_state(telegram_id)


@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    telegram_id = message.chat.id
    user = get_telegram_user(telegram_id)

    if user and user[4]:
        bot.send_message(telegram_id, "❓ Не розпізнано команду. Використовуйте меню або /help для довідки.")
    else:
        bot.send_message(telegram_id, "❓ Будь ласка, спочатку підтвердіть ваш обліковий запис. Введіть /start")

if __name__ == '__main__':
    try:
        logging.info("Starting Mediconnect Telegram Bot...")
        start_notification_threads()
        logging.info("Bot is running. Press Ctrl+C to stop.")
        bot.polling(none_stop=True, interval=1, timeout=60)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Error starting bot: {e}")