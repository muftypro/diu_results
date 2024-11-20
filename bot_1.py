import telebot
import requests
import json
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# Replace 'YOUR_API_TOKEN' with the API token you received from the BotFather
API_TOKEN = '7682591511:AAFV8gLcyvT8Y1WJYZzH0BAQpqxZsegaekw'

bot = telebot.TeleBot(API_TOKEN)

# Base URL for API
BASE_URL = 'http://software.diu.edu.bd:8006'

# Temporary storage for user input
user_data = {}

def send_long_message(chat_id, text):
    max_length = 4000  # Telegram limit is ~4096
    while text:
        if len(text) > max_length:
            split_point = text[:max_length].rfind('\n')
            if split_point == -1:  # No newline found
                split_point = max_length
            bot.send_message(chat_id, text[:split_point])
            text = text[split_point:]
        else:
            bot.send_message(chat_id, text)
            break

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    results_button = KeyboardButton('Results')
    markup.add(results_button)
    bot.send_message(
        message.chat.id, 
        'Welcome to Mufty Bot! Press "Results" to fetch student data.', 
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text == 'Results')
def ask_student_id(message):
    bot.send_message(
        message.chat.id, 
        "Please enter your Student ID:",
        reply_markup=ForceReply(selective=True)
    )
    user_data[message.chat.id] = {}

@bot.message_handler(func=lambda message: message.reply_to_message and "Student ID" in message.reply_to_message.text)
def ask_defense(message):
    student_id = message.text.strip()
    user_data[message.chat.id]['student_id'] = student_id

    markup = InlineKeyboardMarkup()
    yes_button = InlineKeyboardButton("Yes", callback_data="defense_yes")
    no_button = InlineKeyboardButton("No", callback_data="defense_no")
    markup.add(yes_button, no_button)

    bot.send_message(
        message.chat.id, 
        "Do you want to include the defense result?", 
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('defense_'))
def handle_defense_response(call):
    chat_id = call.message.chat.id
    defense_included = call.data == "defense_yes"
    user_data[chat_id]['defense_included'] = defense_included

    if defense_included:
        bot.send_message(
            chat_id, 
            "Please enter the CGPA for the defense (e.g., 3.75):",
            reply_markup=ForceReply(selective=True)
        )
    else:
        fetch_results(chat_id)

@bot.message_handler(func=lambda message: message.reply_to_message and "CGPA for the defense" in message.reply_to_message.text)
def handle_defense_cgpa(message):
    chat_id = message.chat.id
    try:
        defense_cgpa = float(message.text.strip())
        user_data[chat_id]['defense_cgpa'] = defense_cgpa
    except ValueError:
        bot.send_message(chat_id, "Invalid CGPA. Please try again.")
        return

    fetch_results(chat_id)

def fetch_results(chat_id):
    student_id = user_data.get(chat_id, {}).get('student_id')
    defense_included = user_data.get(chat_id, {}).get('defense_included', False)
    defense_cgpa = user_data.get(chat_id, {}).get('defense_cgpa', 0)

    if not student_id:
        bot.send_message(chat_id, "Student ID not found. Please start over.")
        return

    try:
        # Fetch student information
        student_info_response = requests.get(f"{BASE_URL}/result/studentInfo", params={'studentId': student_id})
        student_info_response.raise_for_status()
        student_info = student_info_response.json()

        # Fetch semester list
        semester_list_response = requests.get(f"{BASE_URL}/result/semesterList")
        semester_list_response.raise_for_status()
        semesters = semester_list_response.json()

        # Add student information to the results message
        results_message = (
            f"Student Information:\n"
            f"Name: {student_info['studentName']}\n"
            f"ID: {student_info['studentId']}\n"
            f"Program: {student_info['programName']} ({student_info['progShortName']})\n"
            f"Department: {student_info['departmentName']} ({student_info['deptShortName']})\n"
            f"Faculty: {student_info['facultyName']} ({student_info['facShortName']})\n"
            f"Batch: {student_info['batchId']} (Batch No: {student_info['batchNo']})\n"
            f"Campus: {student_info['campusName']} (Shift: {student_info['shift']})\n"
            f"Current Semester: {student_info['semesterName']}\n"
            + "_"*50 + "\n"
        )

        total_credits = 0
        weighted_cgpa_sum = 0

        for semester in semesters:
            semester_id = semester['semesterId']
            semester_name = semester['semesterName']
            semester_year = semester['semesterYear']

            # Fetch results for the semester
            result_response = requests.get(f"{BASE_URL}/result", params={'studentId': student_id, 'semesterId': semester_id, 'grecaptcha': ''})
            if result_response.status_code != 200:
                continue

            results = result_response.json()
            if not results:
                continue

            results_message += f"Semester: {semester_name} {semester_year}\n"
            for result in results:
                course_title = result['courseTitle']
                course_code = result['customCourseId']
                grade_letter = result['gradeLetter']
                credits = float(result['totalCredit'])
                cgpa = float(result['pointEquivalent'])

                results_message += (
                    f"Course: {course_title} ({course_code})\n"
                    f"Grade: {grade_letter}, Credits: {credits}, CGPA: {cgpa}\n"
                )

                weighted_cgpa_sum += cgpa * credits
                total_credits += credits

            results_message += "-"*40 + "\n"

        # Include defense result if applicable
        if defense_included:
            defense_credits = 6.0
            weighted_cgpa_sum += defense_cgpa * defense_credits
            total_credits += defense_credits
            results_message += f"Defense added: CGPA {defense_cgpa}, Credits {defense_credits}\n"

        # Calculate total CGPA
        if total_credits > 0:
            total_cgpa = weighted_cgpa_sum / total_credits
            results_message += f"\nTotal CGPA: {total_cgpa:.2f}\n"
        else:
            results_message += "\nNo credits earned. CGPA cannot be calculated.\n"

        send_long_message(chat_id, results_message)
    except Exception as e:
        bot.send_message(chat_id, f"An error occurred: {e}")

bot.polling()
