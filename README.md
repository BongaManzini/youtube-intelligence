# 📺 YouTube Intelligence & Both-Sides Sentiment Dashboard

An interactive Web Application (Flask & Streamlit) that scans YouTube creator channels, fetches video metrics (Views, Likes, Comments), calculates **Likes-to-Comments Ratios**, extracts comment threads, and classifies audience feedback into **Positive** and **Negative** comments.

---

## 🚀 How to Run

### Option 1: Flask Web App (Recommended)
Run the Flask server:
```bash
.venv/bin/python app.py
```
Open **`http://127.0.0.1:5000`** in your browser.

---

### Option 2: Streamlit Dashboard
Run the Streamlit app:
```bash
.venv/bin/streamlit run streamlit_app.py
```
Open **`http://localhost:8501`** in your browser.

---

## 🔑 Google API Keys
- **YouTube Data API v3**: Enables live video statistics, likes, view counts, and public comment threads.
- **Google Gemini API** (Optional): Enables AI-powered executive synthesis of praise vs. criticism. Get a free key at [aistudio.google.com](https://aistudio.google.com/).
