# Anuvad.ai (अनुवाद)

> Read English and Hindi books in the language that feels natural to you.

Anuvad.ai is an AI-assisted PDF reading application for bilingual readers. It
keeps the original PDF visible in a split-screen reader and generates readable
Hindi, Hinglish, or English text page by page.

**Live app:** [anuvad-alpha.vercel.app](https://anuvad-alpha.vercel.app/)

## Why Anuvad.ai?

Long books are difficult to read when the language creates friction. Anuvad.ai
helps readers keep the original document in view while using contextual AI
translation for the active page.

The product is designed for:

- bilingual readers who prefer Hindi or Hinglish;
- students and self-learners reading English reference material;
- readers of literature who want to preserve the original text;
- anyone who wants to build vocabulary while reading.

## Features

- **Split-screen reader** — original PDF on one side and translated text on the other.
- **Hindi, Hinglish, and English modes** — switch translation style while reading.
- **Page-by-page translation** — translate only the page the reader opens.
- **Source-aware caching** — reuse a cached translation only when the source page text is unchanged.
- **AI reading tutor** — ask questions about the active page.
- **Text-to-speech** — listen to translated text after signing in.
- **Bookmarks and notes** — save important pages and reading notes.
- **Reading progress** — resume books from the last saved page.
- **Vocabulary API** — save, update, list, and delete vocabulary items with context.
- **Tags and library dashboard** — organize books and track reading activity.
- **Django admin** — manage books, users, translations, logs, and reading data.
- **Light/dark mode and responsive UI** — designed for desktop and smaller screens.

## Important limitations

Anuvad.ai is an alpha application. Please keep these limitations in mind:

- Uploading requires an account.
- Text-based PDFs work best.
- Scanned or image-only PDFs may require OCR and may not translate correctly.
- Complex tables, multi-column layouts, charts, and embedded text are not
  guaranteed to preserve their original structure in the translation pane.
- AI translations can contain mistakes. Verify important medical, legal,
  academic, or technical information against the original source.
- The active-page tutor is not a full-book research assistant yet.
- Uploaded text may be sent to configured third-party AI, translation, or TTS
  providers. Do not upload confidential material unless you understand the
  provider and retention policies.

## How it works

```mermaid
sequenceDiagram
    actor Reader
    participant Browser
    participant Django
    participant Database
    participant AI as AI provider

    Reader->>Browser: Open a book and select a page
    Browser->>Browser: Render the original PDF with PDF.js
    Browser->>Django: Send page text, page number, and language
    Django->>Database: Check the source-aware translation cache
    alt Cached translation exists
        Database-->>Django: Return cached translation
    else Cache miss
        Django->>AI: Generate Hindi, Hinglish, or English text
        AI-->>Django: Return translation
        Django->>Database: Store translation and source text
    end
    Django-->>Browser: Return translated page text
    Browser-->>Reader: Show the split-screen reading view
```

## Technology stack

- **Backend:** Django, Python
- **Frontend:** Django templates, vanilla JavaScript, CSS
- **PDF rendering:** PDF.js
- **Translation:** Groq with configured fallbacks
- **Speech:** gTTS and browser audio playback
- **Authentication:** Django Auth and optional django-allauth Google OAuth
- **Development database:** SQLite
- **Production database:** PostgreSQL-compatible database such as Neon
- **Production file storage:** S3-compatible object storage
- **Deployment:** Vercel Python runtime

## Project structure

```text
book-translation/
├── config/                  # Django project settings, URLs, WSGI/ASGI
├── reader/                  # Main application, models, views, APIs, tests
├── templates/reader/        # Landing page, dashboard, reader, auth UI
├── static/                  # Static asset directory
├── manage.py
├── requirements.txt
├── vercel.json
└── README.md
```

## Run locally

### 1. Clone the project

```bash
git clone https://github.com/aryamaddy/book-translation.git
cd book-translation
```

### 2. Create and activate a virtual environment

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows CMD:**

```bat
python -m venv .venv
.venv\Scripts\activate
```

**macOS/Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure local environment

Create a `.env` file in the project root. Never commit this file.

```env
# Explicitly enable local development mode
DEBUG=True
SECRET_KEY=replace-with-a-local-development-secret
ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

# Required for the primary AI translation path
GROQ_API_KEY=gsk_your_key_here
# Optional: override the default model
# GROQ_MODEL=your-model-id

# Optional local database override
# DATABASE_URL=postgresql://user:password@localhost:5432/anuvad

# Optional Google OAuth
# GOOGLE_CLIENT_ID=...
# GOOGLE_CLIENT_SECRET=...
```

`DEBUG` defaults to `False`. Local SQLite and the local `media/` directory are
available only when `DEBUG=True` is explicitly set. Production must provide a
real `SECRET_KEY`.

### 5. Prepare the database

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Start the development server

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Production deployment on Vercel

Vercel function storage is ephemeral. Do **not** use SQLite or `/tmp` for
production data. The application intentionally fails during startup when a
Vercel deployment is missing a persistent database or complete object-storage
configuration.

Set these Vercel environment variables:

```env
VERCEL=1
DEBUG=False
SECRET_KEY=replace-with-a-long-random-production-secret
ALLOWED_HOSTS=.vercel.app,your-domain.example
CSRF_TRUSTED_ORIGINS=https://*.vercel.app,https://your-domain.example

DATABASE_URL=postgresql://user:password@host/database

AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_ENDPOINT_URL_S3=https://...
AWS_REGION=...
AWS_STORAGE_BUCKET_NAME=media

GROQ_API_KEY=gsk_your_key_here
```

The storage variables are the standard names used by `django-storages` for an
S3-compatible provider. Provision the bucket before deploying and configure
its access policy deliberately. Private PDFs should be served through an
appropriate signed/private-storage strategy rather than exposed publicly.

Optional security settings include:

```env
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_PROXY_SSL_HEADER_ENABLED=True
```

## API overview

All reader APIs are authenticated unless noted otherwise. Requests that change
data require the normal Django CSRF protection when called from the browser.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/translate-page/` | Translate the active page into Hindi, Hinglish, or English |
| `POST` | `/api/tts/` | Generate audio for translated text |
| `POST` | `/api/ask-book/` | Ask a question about the active page |
| `POST` | `/api/progress/` | Save reading progress |
| `POST` | `/api/bookmark/` | Add, update, or remove a bookmark |
| `GET` | `/api/bookmarks/<book_id>/` | List bookmarks for a book |
| `POST` | `/api/note/` | Save a note on a bookmarked page |
| `POST` | `/api/tags/` | Create, delete, assign, or remove tags |
| `GET` | `/api/vocabulary/` | List the current user's vocabulary |
| `POST` | `/api/vocabulary/` | Save or update a vocabulary item |
| `DELETE` | `/api/vocabulary/` | Delete a vocabulary item owned by the user |

## Testing and checks

Run Django's system checks:

**macOS/Linux/Git Bash:**

```bash
DEBUG=True SECRET_KEY=test python manage.py check
```

**Windows PowerShell:**

```powershell
$env:DEBUG = "True"
$env:SECRET_KEY = "test"
python manage.py check
```

Run the application tests:

**macOS/Linux/Git Bash:**

```bash
DEBUG=True SECRET_KEY=test python manage.py test reader
```

**Windows PowerShell:**

```powershell
$env:DEBUG = "True"
$env:SECRET_KEY = "test"
python manage.py test reader
```

Run the existing end-to-end script when its browser and provider prerequisites
are available:

```bash
python test_e2e.py
```

Before deploying, also verify:

- production environment variables are configured;
- database migrations run successfully;
- object storage can upload and retrieve a PDF;
- Google OAuth is either configured or intentionally disabled;
- AI provider quotas and fallback behavior are understood;
- uploaded material complies with copyright and privacy requirements.

## Security notes

- Keep `.env`, API keys, OAuth secrets, and storage credentials out of Git.
- Use a strong, unique production `SECRET_KEY`.
- Use PostgreSQL and persistent object storage in production.
- Restrict PDF access to the owning user and review object-storage permissions.
- Treat uploaded PDF text as untrusted input.
- Add provider-specific privacy and retention information before public launch.
- Do not rely on AI output for medical, legal, financial, or safety-critical decisions.

## Roadmap

- OCR support for scanned PDFs
- Better table and multi-column layout handling
- Full-book search and retrieval-augmented Q&A
- Vocabulary UI with revision and flashcards
- Password reset and email verification
- Signed private PDF URLs
- Background translation jobs and progress tracking
- Translation quality evaluation and user feedback tools

## Contributing

1. Fork the repository.
2. Create a focused branch.
3. Make a small, tested change.
4. Run `manage.py check` and the relevant tests.
5. Open a pull request with the behavior change and verification details.

## License

This project is licensed under the [MIT License](LICENSE).

---

Built with ❤️ for readers who learn across languages.
