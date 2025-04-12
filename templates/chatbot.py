import google.generativeai as genai
import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from datetime import datetime

# Initialize Flask app with proper CORS
app = Flask(__name__)
CORS(app, resources={
    r"/chatbot": {
        "origins": ["http://localhost:*", "http://127.0.0.1:*"],
        "methods": ["POST"],
        "allow_headers": ["Content-Type"]
    }
})

# Load API key with better error handling
try:
    with open("static\Keys.txt", "r") as file:
        api_key = file.read().strip()
    if not api_key:
        raise ValueError("API key is empty")
except Exception as e:
    print(f"Error loading API key: {e}")
    api_key = None

# Only configure if API key is available
if api_key:
    genai.configure(api_key=api_key)

# Generation Configuration
generation_config = {
    "temperature": 0.7,
    "max_output_tokens": 1024,
    "top_p": 1,
    "top_k": 40
}

# System instruction for India-specific context
system_instruction = (
    "You are an expert assistant specialized in addressing queries relevant to users in India. "
    "When structuring prompts or answering questions, always consider the Indian context — including local laws, "
    "culture, government policies, and regional practices. Your responses should be tailored for Indian users and "
    "should be clear, accurate, and respectful of regional diversity. Only respond within this context."
)

# Initialize Gemini model (only if API key is available)
model = None
if api_key:
    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro-latest",
        generation_config=generation_config,
        system_instruction=system_instruction
    )

# Database functions with error handling
def initialize_db():
    try:
        conn = sqlite3.connect('chatbot.db')
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_query TEXT,
                gemini_response TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database initialization error: {e}")

def save_conversation(user_id, user_query, gemini_response):
    try:
        conn = sqlite3.connect('chatbot.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO conversations (user_id, user_query, gemini_response)
            VALUES (?, ?, ?)
        ''', (user_id, user_query, gemini_response))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving conversation: {e}")

def get_user_conversation_history(user_id, limit=3):
    try:
        conn = sqlite3.connect('chatbot.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_query, gemini_response FROM conversations
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        rows = cursor.fetchall()
        conn.close()
        return rows[::-1]  # Return in chronological order
    except Exception as e:
        print(f"Error fetching conversation history: {e}")
        return []

def build_personalized_prompt(user_id, current_query):
    history = get_user_conversation_history(user_id)
    context = ""

    for i, (q, a) in enumerate(history):
        context += f"Previous Question {i+1}: {q}\nPrevious Answer {i+1}: {a}\n"

    return (
        f"{context}"
        f"Current Question: {current_query}\n"
        f"Based on the previous conversation, provide a relevant and personalized answer."
    )

def get_gemini_response(user_id, user_query):
    if not model:
        return "Error: API not properly configured. Please check backend setup."
    
    try:
        personalized_prompt = build_personalized_prompt(user_id, user_query)
        response = model.generate_content(personalized_prompt)
        final_response = response.text.strip()
        save_conversation(user_id, user_query, final_response)
        return final_response
    except Exception as e:
        print(f"Error generating Gemini response: {e}")
        return f"I encountered an error processing your request. Please try again later."

@app.route('/chatbot', methods=["GET", "POST"])
def ask():
    if request.method == "GET":
        return jsonify({
            "status": "Server is running",
            "usage": "Send POST request with {'user_id': string, 'user_query': string}",
            "example": {
                "user_id": "test123",
                "user_query": "What are Indian tax laws for freelancers?"
            }
        })
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data received"}), 400

        query = data.get("user_query")
        if not query:
            return jsonify({"error": "Missing user_query"}), 400

        user_id = data.get("user_id", "default_user")
        answer = get_gemini_response(user_id, query)
        
        return jsonify({
            "response": answer,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Endpoint Error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    initialize_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)