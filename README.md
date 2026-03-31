# AI-assistant
🤖 Silver Agent v2.0
The Ultimate AI-Powered Email Assistant for Low-End Hardware
Silver Agent v2.0 aik advanced AI assistant hai jo baghair kisi heavy GPU ke aapke Gmail ko automate karta hai. Ye khaas tor par un developers aur users ke liye banaya gaya hai jo optimized performance chahte hain.

🚀 Key Features
🚫 No-GPU Optimization: Heavy graphics card ki zaroorat nahi, ye low-end CPUs par smoothly chalta hai.

📧 Gmail Automation: Aapke inbox ko monitor karta hai aur professional replies draft karta hai.

🧠 Knowledge Integration: Saara data aur interactions automatic aapke Obsidian (Personal Knowledge Base) mein sync karta hai.

📂 Structured Database: Har email aur action ka record SQLite database mein save hota hai.

⚡ Agentic Workflow: Ye sirf aik script nahi, balki aik autonomous agent hai jo samajhta hai ke kab aur kaise reply dena hai.

🛠️ Tech Stack
Language: Python 🐍

AI Engine: (Ollama / Local LLM / Groq - Jo bhi aap use kar rahe hain)

Database: SQLite 🗄️

Note-Taking: Obsidian (Markdown sync) 📝

API: Gmail API ✉️

📥 Installation
Pehle repository ko clone karen:

Bash
git clone https://github.com/Abdullahzahoor755/AI-assistant.git
cd AI-assistant
Zaroori libraries install karen:

Bash
pip install -r requirements.txt
⚙️ Setup & Configuration
Gmail API: Google Cloud Console se credentials.json download kar ke project folder mein rakhen.

Environment Variables: Aik .env file banayen aur us mein ye details add karen:

GMAIL_USER=your-email@gmail.com

OBSIDIAN_PATH=/path/to/your/vault

DATABASE_NAME=silver_agent.db

Run the Agent:

Bash
python main.py
📈 Architecture Workflow
Monitor: Agent har 5 minute baad Gmail check karta hai.

Analyze: AI context samajhta hai aur dekhta hai ke reply zaroori hai ya nahi.

Draft: Professional reply generate kar ke draft folder mein rakhta hai ya bhej deta hai.

Log: SQLite mein entry karta hai aur Obsidian mein naya note create kar deta hai.

🛡️ License
Distributed under the MIT License. See LICENSE for more information.

👤 Author
Abdullah Zahoor

GitHub: @Abdullahzahoor755

Field: Agentic AI & Robotic Engineering Student

Bhai, kuch zaroori tips:
requirements.txt: Is file mein saari libraries (jaise google-api-python-client, sqlite3, etc.) zaroor likh dena.

Screenshots: Agar ho sake to terminal ya Obsidian ka aik screenshot README mein add kar dena, log bohot impress hote hain.

Usage: Agar koi khas command hai agent chalane ki, to wo installation section mein change kar lena.

Kaisa laga ye format? Agar kuch aur add karwana hai to batayen!
