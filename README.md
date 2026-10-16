<div align="center">

# 📖 Anuvad.ai (अनुवाद)
### *Next-Gen AI Book Translation & Interactive Split-Screen Reader*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.x%20%2F%206.x-092E20?style=for-the-badge&logo=django&logoColor=white)](https://djangoproject.com)
[![Groq](https://img.shields.io/badge/Groq-LPU%20Inference-F05A28?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com)
[![PDF.js](https://img.shields.io/badge/PDF.js-Client%20Rendering-FF0000?style=for-the-badge&logo=adobe&logoColor=white)](https://mozilla.github.io/pdf.js/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

<p align="center">
  <b>Read text-based English or Hindi PDFs side-by-side with context-aware AI translations in Hindi, conversational Hinglish, or English — while keeping the original document visible.</b>
</p>

</div>

---

## 🌟 Why Anuvad.ai?

For millions of bilingual readers, diving into English or classical literature comes with constant linguistic friction. Traditional translation tools strip away formatting, destroy typography, and translate line-by-line out of context.

**Anuvad.ai** provides an intelligent, split-screen reading experience:
- **Left Pane:** Pixel-perfect original PDF rendered in real-time via `PDF.js`.
- **Right Pane:** Natural, context-rich translation with instant switching between **Pure Hindi (हिंदी)**, **Conversational Hinglish**, and **English**.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 📑 **Split-View Reader** | Keeps the original PDF visible alongside a readable translated text pane. Complex scanned/image-only PDFs may require OCR and are not guaranteed to preserve layout. |
| ⚡ **Contextual AI Engine** | Powered by high-throughput **Groq LPU (Llama 3 / Qwen)** for authentic Indian literary cadence and idiom preservation. |
| 🛡️ **Race-Condition & Skip Defense** | Built with `AbortController` and monotonic request IDs — rapidly flipping through pages never causes stale or overlapping translations. |
| 🏎️ **Translation Caching** | Revisited pages reuse a database cache when the source text is unchanged, reducing repeat provider calls. |
| 🗣️ **Text-to-Speech (TTS)** | Listen to Hindi or English translations hands-free with the integrated web TTS player. |
| 🤖 **Ask The Book (AI Tutor)** | In-reader AI assistant that directly answers queries about the active page's storyline, characters, and themes. |
| 📖 **Vocabulary API** | Authenticated users can save, list, update, and delete translated vocabulary items with context. |
| 🧘 **Zen Focus Mode** | Built-in Pomodoro timer with ambient background audio (Rain, Focus, Forest) for distraction-free reading sessions. |
| 🔐 **Admin & User Management** | Complete Django admin dashboard for managing books, users, translation caches, and error logs. |

---

## 🏗️ Architecture & Data Flow

```mermaid
sequenceDiagram
    autonumber
    actor Reader as 👤 User
    participant Browser as 🖥️ Reader Frontend (PDF.js)
    participant Cache as 💾 Local Memory & DB Cache
    participant Django as ⚙️ Django API Server
    participant Groq as 🚀 Groq LPU (AI Engine)

    Reader->>Browser: Opens Book / Navigates to Page
    Browser->>Browser: Aborts previous in-flight requests (AbortController)
    Browser->>Browser: Renders PDF Page Canvas
    Browser->>Cache: Check Client Memory Cache
    
    alt Client Cache Hit
        Cache-->>Browser: Instant Render (<1ms)
    else Cache Miss
        Browser->>Django: POST /api/translate-page/ (page_num, extracted_text, lang)
        Django->>Cache: Query SQLite/PostgreSQL TranslationCache
        alt DB Cache Hit
            Cache-->>Django: Return cached translation
        else DB Cache Miss
            Django->>Groq: Generate Contextual Literary Translation
            Groq-->>Django: Return Hindi / Hinglish Text
            Django->>Cache: Save into TranslationCache
        end
        Django-->>Browser: Return JSON response with page verification
        Browser->>Browser: Guard check: Does response match current page?
        Browser-->>Reader: Display translated page & save to client cache
    end
```

---

## 🛠️ Technology Stack

- **Backend Framework:** Django 5.x / 6.x (Python 3.11+)
- **AI / LLM Acceleration:** Groq API (High-speed LPU inference with `allam-2-7b` / `qwen` fallbacks)
- **Frontend & Rendering:** Vanilla JavaScript (ES6+), PDF.js, Modern Brutalist Glassmorphism CSS
- **Audio & TTS Engine:** Web Speech API & Google Text-to-Speech integration
- **Database:** SQLite (default for development) / PostgreSQL (production-ready)
- **Authentication:** Django Auth & Django-Allauth (Google OAuth support)

---

## 🚀 Quickstart Guide

### 1. Clone the Repository
```bash
git clone https://github.com/aryamaddy/book-translation.git
cd book-translation
```

### 2. Set Up Virtual Environment
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the project root:
```env
# Required for AI Translation
GROQ_API_KEY=gsk_your_groq_api_key_here

# Django Settings (Set DEBUG explicitly for local development)
DEBUG=True
SECRET_KEY=your_secret_key_here
ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

# Database (Optional for local development; required on Vercel)
# DATABASE_URL=postgresql://user:password@localhost:5432/bookdb
```

`DEBUG` defaults to `False`. The local SQLite database and `media/` upload
directory are available when `DEBUG=True` is set explicitly. When `DEBUG=False`,
set `SECRET_KEY`; the application will fail at startup rather than use a
development key.

### 5. Apply Database Migrations
```bash
python manage.py migrate
```

### 6. Create an Admin User (Optional)
```bash
python manage.py createsuperuser
```

### 7. Run the Application
```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your web browser.

### Vercel deployment

Vercel's function filesystem is ephemeral, so this project does not fall back
to SQLite or `/tmp` for deployed data. If `VERCEL` is enabled, startup fails
with a clear error unless both a persistent database and complete S3-compatible
object-storage configuration are present.

Set these Vercel environment variables (Neon Object Storage uses these AWS
standard names):

```env
VERCEL=1
DEBUG=False
SECRET_KEY=replace_with_a_long_random_value
ALLOWED_HOSTS=.vercel.app,your-domain.example
CSRF_TRUSTED_ORIGINS=https://*.vercel.app,https://your-domain.example
DATABASE_URL=postgresql://user:password@host/database

AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_ENDPOINT_URL_S3=https://...
AWS_REGION=us-east-2
AWS_STORAGE_BUCKET_NAME=media
```

Provision the `media` bucket (see `neon.ts`) before deploying. The required
storage variables keep uploaded PDFs out of the ephemeral Vercel filesystem.
For a proxy with different HTTPS behavior, `SECURE_SSL_REDIRECT`,
`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
`SECURE_PROXY_SSL_HEADER_ENABLED`, `SECURE_HSTS_SECONDS`, and the other
`SECURE_*` settings can be overridden with environment variables.

---

## 📡 API Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/translate-page/` | Translates page text to Hindi, Hinglish, or English with caching |
| `POST` | `/api/tts/` | Authenticated users can generate audio for translated text |
| `POST` | `/api/ask-book/` | Context-aware AI tutor chat for the current page |
| `POST` | `/api/bookmark/` | Saves or toggles bookmark for the active page |
| `POST` | `/api/progress/` | Updates user reading percentage and resume state |
| `GET/POST/DELETE` | `/api/vocabulary/` | Lists, saves, updates, or deletes the current user's vocabulary |
| `GET` | `/admin/` | Superuser administration portal for books, users, and logs |

---

## 🧪 Running the Test Suite

Run the end-to-end automated verification suite:
```bash
python test_e2e.py
```
This tests user creation, authentication, PDF upload, reader rendering, Hindi and Hinglish AI translation, and conversational book queries.

---

## 🛡️ License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">
  <b>Developed & Maintained with ❤️ by <a href="https://github.com/aryamaddy">aryamaddy</a></b>
</div>
