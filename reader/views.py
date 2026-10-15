import os
import json
import requests as http_requests
from dotenv import load_dotenv
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from deep_translator import GoogleTranslator
from django.conf import settings
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from .models import Book, TranslationCache, Vocabulary, UserProfile, ErrorLog, ReadingProgress, Bookmark, BookTag, BookTagAssignment
from .forms import BookForm, UserProfileForm, RegisterForm, PageTranslationForm, AskBookForm, TTSForm
from django_ratelimit.decorators import ratelimit
from .hinglish_engine import translate_to_natural_hinglish
from gtts import gTTS
from io import BytesIO

load_dotenv()


def _safe_next_url(request):
    """Return a local redirect target, never an attacker-controlled URL."""
    candidate = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return reverse('dashboard')

# g4f for free AI Fallback
try:
    from g4f.client import Client as G4FClient
except ImportError:
    G4FClient = None

# ── Groq Config (for premium Hinglish) ──
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
GROQ_AVAILABLE = bool(GROQ_API_KEY)

if GROQ_AVAILABLE:
    from groq import Groq


def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    # Use landing.html instead of upload.html
    return render(request, 'reader/landing.html')

@login_required(login_url='/')
def dashboard(request):
    if not hasattr(request.user, 'profile') or not request.user.profile.onboarded:
        return redirect('onboarding')

    error = None
    if request.method == 'POST':
        try:
            ErrorLog.objects.create(action="Dashboard POST", error_message="Received POST request", user_info=request.user.username)
            if not request.user.is_authenticated:
                return redirect('landing_page')
                
            form = BookForm(request.POST, request.FILES)
            if form.is_valid():
                title = form.cleaned_data.get('title')
                existing_book = Book.objects.filter(title__iexact=title, user=request.user).first()
                if existing_book:
                    ErrorLog.objects.create(action="Dashboard Upload Duplicate", error_message="Redirecting to existing book", user_info=request.user.username)
                    return redirect('reader_view', book_id=existing_book.id)
                else:
                    import random
                    new_book = form.save(commit=False)
                    new_book.user = request.user
                    new_book.cover_color = random.randint(0, 7)
                    new_book.save()
                    ErrorLog.objects.create(action="Dashboard Upload Success", error_message=f"Book {new_book.id} saved", user_info=request.user.username)
                    return redirect('reader_view', book_id=new_book.id)
            else:
                error_msgs = []
                for field, errors in form.errors.items():
                    for err in errors:
                        error_msgs.append(f"{field}: {err}")
                error = "Upload failed: " + " | ".join(error_msgs)
                ErrorLog.objects.create(action="Dashboard Form Invalid", error_message=error, user_info=request.user.username)
        except Exception as e:
            import traceback
            ErrorLog.objects.create(action="Dashboard Exception", error_message=traceback.format_exc(), user_info=request.user.username)
            error = "An unexpected error occurred during upload. Our team has been notified."
    else:
        form = BookForm()
        
    books = Book.objects.filter(user=request.user).annotate(pages_translated=Count('translations')).order_by('-uploaded_at')
    
    total_books = books.count()
    total_pages_translated = TranslationCache.objects.filter(book__user=request.user).count()
    
    # Reading progress for recent book
    recent_progress = ReadingProgress.objects.filter(user=request.user).order_by('-last_read_at').first()
    recent_book = recent_progress.book if recent_progress else (books.first() if total_books > 0 else None)
    recent_progress_percent = recent_progress.percent if recent_progress else 0
    
    # Translation DNA calculation
    all_translations = TranslationCache.objects.filter(book__user=request.user)
    total_pages_translated = all_translations.count()
    hindi_count = all_translations.filter(language='hindi').count()
    hinglish_count = all_translations.filter(language='hinglish').count()
    
    hindi_percent = int((hindi_count / total_pages_translated * 100)) if total_pages_translated > 0 else 50
    hinglish_percent = 100 - hindi_percent if total_pages_translated > 0 else 50
    
    # Fetch the latest summary
    latest_translation = TranslationCache.objects.filter(book__user=request.user).exclude(summary_text='').order_by('-id').first()
    latest_summary = latest_translation.summary_text if latest_translation and latest_translation.summary_text else None
    latest_summary_book = latest_translation.book.title if latest_translation else None

    # Reading history (last 10 sessions)
    reading_history = ReadingProgress.objects.filter(user=request.user).select_related('book').order_by('-last_read_at')[:10]
    
    # User tags
    user_tags = BookTag.objects.filter(user=request.user)
    
    # Total bookmarks
    total_bookmarks = Bookmark.objects.filter(user=request.user).count()
    
    # Reading streak (consecutive days)
    from django.utils import timezone
    import datetime
    today = timezone.now().date()
    streak = 0
    check_date = today
    while ReadingProgress.objects.filter(user=request.user, last_read_at__date=check_date).exists():
        streak += 1
        check_date -= datetime.timedelta(days=1)

    context = {
        'form': form,
        'books': books,
        'error': error,
        'total_books': total_books,
        'total_pages_translated': total_pages_translated,
        'recent_book': recent_book,
        'recent_progress_percent': recent_progress_percent,
        'hindi_percent': hindi_percent,
        'hinglish_percent': hinglish_percent,
        'latest_summary': latest_summary,
        'latest_summary_book': latest_summary_book,
        'reading_history': reading_history,
        'user_tags': user_tags,
        'total_bookmarks': total_bookmarks,
        'reading_streak': streak,
    }
    
    return render(request, 'reader/dashboard.html', context)


@login_required(login_url='/')
def onboarding(request):
    # If they are already onboarded, send them to dashboard
    if hasattr(request.user, 'profile') and request.user.profile.onboarded:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserProfileForm(request.POST)
        if form.is_valid():
            # Update user details
            request.user.first_name = form.cleaned_data['first_name']
            request.user.last_name = form.cleaned_data['last_name']
            request.user.save()

            # Create or update profile
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            profile.preferred_language = form.cleaned_data['preferred_language']
            profile.bio = form.cleaned_data['bio']
            profile.onboarded = True
            profile.save()

            return redirect('dashboard')
    else:
        # Pre-fill if Google gave us their name
        form = UserProfileForm(initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        })

    return render(request, 'reader/onboarding.html', {'form': form})

@login_required(login_url='/')
def profile_view(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST)
        if form.is_valid():
            request.user.first_name = form.cleaned_data['first_name']
            request.user.last_name = form.cleaned_data['last_name']
            request.user.save()
            
            profile.preferred_language = form.cleaned_data['preferred_language']
            profile.bio = form.cleaned_data['bio']
            profile.save()
            return redirect('profile_view')
    else:
        form = UserProfileForm(initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'preferred_language': profile.preferred_language,
            'bio': profile.bio,
        })
        
    stats = {
        'total_books': request.user.books.count(),
        'total_pages_translated': TranslationCache.objects.filter(book__user=request.user).count(),
        'vocab_saved': request.user.vocabulary.count()
    }
    
    return render(request, 'reader/profile.html', {'form': form, 'profile': profile, 'stats': stats})


@login_required(login_url='/')
def delete_book(request, book_id):
    if request.method == 'POST':
        try:
            book = get_object_or_404(Book, id=book_id, user=request.user)
            book.pdf_file.delete(save=False) # delete physical file
            book.delete() # delete db entry
            ErrorLog.objects.create(action="Delete Book Success", error_message=f"Deleted book {book_id}", user_info=request.user.username)
        except Exception as e:
            import traceback
            ErrorLog.objects.create(action="Delete Book Error", error_message=str(e) + "\n" + traceback.format_exc(), user_info=request.user.username)
    return redirect('dashboard')

@ratelimit(key='ip', rate=os.environ.get('RATE_LIMIT_AUTH_IP', '5/m'), block=False)
@ratelimit(key='post:username', rate=os.environ.get('RATE_LIMIT_AUTH_ACCOUNT', '10/h'), block=False)
def register_user(request):
    if getattr(request, 'limited', False) and not settings.DEBUG:
        return render(request, 'reader/landing.html', {'auth_error': 'Too many registration attempts. Please try again later.', 'auth_action': 'register'}, status=429)

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password']
            )
            UserProfile.objects.get_or_create(user=user)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect(_safe_next_url(request))
        else:
            errors = " | ".join([f"{e[0]}" for e in form.errors.values()])
            return render(request, 'reader/landing.html', {'auth_error': errors, 'auth_action': 'register'})
    return redirect('landing_page')

@ratelimit(key='ip', rate=os.environ.get('RATE_LIMIT_AUTH_IP', '5/m'), block=False)
@ratelimit(key='post:username', rate=os.environ.get('RATE_LIMIT_AUTH_ACCOUNT', '10/h'), block=False)
def login_user(request):
    if getattr(request, 'limited', False) and not settings.DEBUG:
        return render(request, 'reader/landing.html', {'auth_error': 'Too many login attempts. Please try again later.', 'auth_action': 'login'}, status=429)

    if request.method == 'POST':
        data = request.POST
        login_input = (data.get('username') or '').strip()
        password = data.get('password', '')

        # Support login by username or email
        user = authenticate(request, username=login_input, password=password)
        if user is None and '@' in login_input:
            matched_user = User.objects.filter(email__iexact=login_input).first()
            if matched_user:
                user = authenticate(request, username=matched_user.username, password=password)

        if user is not None:
            UserProfile.objects.get_or_create(user=user)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect(_safe_next_url(request))
        else:
            return render(request, 'reader/landing.html', {'auth_error': 'Invalid username/email or password', 'auth_action': 'login'})
    return redirect('landing_page')

def logout_user(request):
    logout(request)
    return redirect('landing_page')


@login_required(login_url='/')
def reader_view(request, book_id):
    book = get_object_or_404(Book, id=book_id, user=request.user)
    bookmarks = []
    progress = None
    if request.user.is_authenticated:
        bookmarks = list(Bookmark.objects.filter(user=request.user, book=book).values_list('page_number', flat=True))
        progress = ReadingProgress.objects.filter(user=request.user, book=book).first()
    return render(request, 'reader/reader.html', {
        'book': book,
        'bookmarks_json': json.dumps(bookmarks),
        'current_page': progress.current_page if progress else 1,
    })

import re

def _clean_hindi_ocr(text):
    """Fix common Hindi PDF/OCR extraction errors and remove watermarks/ad noise."""
    if not text:
        return ""

    # Remove common PDF watermarks and ads
    watermark_patterns = [
        r'(?:https?://|www\.)[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?',
        r'[a-zA-Z0-9-]+\.(?:com|org|net|in|co\.in|edu|gov)\b(?:/[^\s]*)?',
        r'hindustanbooks\.com',
        r't\.me/[a-zA-Z0-9_]+',
        r'telegram',
        r'scanned\s*(?:by|with)\s*(?:camscanner|adobe\s*scan|wps)',
        r'pdfdrive(?:\.com)?',
        r'downloaded\s*from',
        r'@\w+',
    ]
    for pat in watermark_patterns:
        text = re.sub(pat, '', text, flags=re.IGNORECASE)

    # Devanagari matra characters (dependent vowel signs)
    matras = 'ा ि ी ु ू ृ ॄ ॅ ॆ े ै ॉ ॊ ो ौ ् ं ँ ः'
    matra_chars = matras.replace(' ', '')
    
    # 1. Remove spaces BEFORE any matra (most critical fix)
    text = re.sub(r'(\S) ([' + matra_chars + r'])', r'\1\2', text)
    text = re.sub(r'(\S) ([' + matra_chars + r'])', r'\1\2', text)
    
    # 2. Fix ॅ (Candra E)
    text = re.sub(r'ॅ([ँं])', r'\1', text)
    text = re.sub(r'ॅू', r'ूँ', text)
    text = re.sub(r'ॅ(?=[क-ह])', r'ँ', text)
    text = re.sub(r'ॅ(?=\s|$|[,।\.])', r'ँ', text)
    
    # 3. Fix broken halant combinations
    text = re.sub(r'(्) +', r'\1', text)
    
    # 4. Fix double matras
    for m in matra_chars:
        text = text.replace(m + m, m)
    
    # 5. Clean up multiple spaces
    text = re.sub(r'  +', ' ', text)
    
    # 6. Fix common character substitution errors from PDF encoding
    common_fixes = {
        'लेककन': 'लेकिन',
        'नजसे': 'जिसे', 
        'कदखा': 'दिखा',
        'नहश': 'नहीं',
        'धननया': 'धनिया',
        'भकत': 'भक्त',
        'कक ': 'कि ',
        'ककसी': 'किसी',
        'ककसान': 'किसान',
        'चाकहए': 'चाहिए',
        'लड़ककय': 'लड़कीय',
        'ककया': 'किया',
        'ककस': 'किस',
        'नसकोड': 'सिकोड़',
        'चचता': 'चिंता',
        'मानलक': 'मालिक',
        'पजा': 'पूजा',
        'कववानहत': 'विवाहित',
        'कतर - ब्योंत': 'कतर-ब्योंत',
        'मुकश्कल': 'मुश्किल',
        'कवषय': 'विषय',
        'नजंदा': 'ज़िंदा',
        'लड़ककयाँ': 'लड़कियाँ',
        'नबला': 'मिला',
        'नबलें': 'मिलें',
        'नचरस्थायी': 'चिरस्थायी',
        'रोदटयाँ': 'रोटियाँ',
        'पररक्स्र्स्थनत': 'परिस्थिति',
        'कवद्रोह': 'विद्रोह',
        'झुर्ररयों': 'झुर्रियों',
        'झुर्ररयाँ': 'झुर्रियाँ',
        'स्त्र ी': 'स्त्री',
        'हु ए': 'हुए',
        'ददन': 'दिन',
        'ककधर': 'किधर',
        'कुसल': 'कुशल',
        'परसाद': 'प्रसाद',
        'असनान': 'अस्नान',
    }
    for wrong, right in common_fixes.items():
        text = text.replace(wrong, right)
    
    return text.strip()


def _translate_conversational_hindi(text):
    """Translate English to conversational Hindi or fix broken Hindi PDF text using LLM."""
    text = _clean_hindi_ocr(text)
    if not text.strip():
        return ""

    is_english = len(re.findall(r'[a-zA-Z]', text)) > len(re.findall(r'[\u0900-\u097F]', text))

    if is_english:
        system_prompt = (
            "You are a master Hindi literary translator and scholar. "
            "Translate the following English passage into eloquent, natural, and grammatically flawless Hindi written strictly in Devanagari script (हिंदी). "
            "Keep the flow, emotional nuance, and depth of the original text. "
            "Do NOT output Hinglish or Latin script. Do NOT add any notes, explanations, or quotes. Output ONLY the clean translated Hindi text."
        )
    else:
        system_prompt = (
            "You are a master Hindi literary editor, proofreader, and scholar. "
            "The user provides text extracted from a Hindi PDF that suffers from font encoding and OCR corruptions "
            "(e.g., broken halants, detached matras, incorrect character substitutions). "
            "Completely reconstruct and polish the text into 100% flawless, authentic, and grammatically correct literary Hindi in Devanagari script (हिंदी). "
            "Maintain original literary cadence and dialogue formatting. "
            "Output ONLY the clean Hindi text without any explanations, notes, or markdown fences."
        )
    
    if GROQ_AVAILABLE:
        client = Groq(api_key=GROQ_API_KEY)
        candidate_models = [GROQ_MODEL, "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        for m in candidate_models:
            if not m:
                continue
            try:
                completion = client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text}
                    ],
                    temperature=0.2
                )
                result = completion.choices[0].message.content.strip()
                if result.startswith('```') and result.endswith('```'):
                    lines = result.split('\n')
                    result = '\n'.join(lines[1:-1]).strip()
                if result:
                    return result
            except Exception as e:
                print(f"Groq {m} Hindi translation attempt failed: {e}")

    # Fallback to free AI if available
    if G4FClient:
        try:
            g4f_client = G4FClient()
            completion = g4f_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ]
            )
            result = completion.choices[0].message.content.strip()
            if result and len(result) > 10:
                return result
        except Exception as e:
            print("g4f Hindi translation failed:", e)

    # Ultimate fallback: Google Translator
    try:
        return _translate_chunks_hindi(text)
    except Exception:
        return text


def _translate_chunks_hindi(text):
    """Translate English text to Hindi (Devanagari) using Google or MyMemory fallback."""
    try:
        translator = GoogleTranslator(source='auto', target='hi')
        chunks = [text[i:i + 4500] for i in range(0, len(text), 4500)]
        result = ""
        for chunk in chunks:
            translated = translator.translate(chunk)
            if translated:
                result += translated + " "
        if result.strip():
            return result.strip()
    except Exception as e:
        print("GoogleTranslator failed, trying MyMemory fallback:", e)

    try:
        from deep_translator import MyMemoryTranslator
        translator = MyMemoryTranslator(source='en-US', target='hi-IN')
        chunks = [text[i:i + 500] for i in range(0, len(text), 500)]
        result = ""
        for chunk in chunks:
            translated = translator.translate(chunk)
            if translated:
                result += translated + " "
        if result.strip():
            return result.strip()
    except Exception as e:
        print("MyMemory fallback failed:", e)

    return text


def _translate_chunks_english(text):
    """Translate text to English using Groq or deep-translator."""
    text = _clean_hindi_ocr(text)
    if not text.strip():
        return ""

    is_english = len(re.findall(r'[a-zA-Z]', text)) > len(re.findall(r'[\u0900-\u097F]', text))
    if is_english and len(re.findall(r'[\u0900-\u097F]', text)) == 0:
        return text

    prompt = (
        "You are an expert literary translator specializing in Indian literature. "
        "The user will provide text extracted from a Hindi PDF which may contain font/OCR errors. "
        "Reconstruct the intended meaning and translate into eloquent, fluent, natural English suitable for published literature. "
        "Do NOT add any notes, explanations, or quotes. Output ONLY the English text."
    )
    
    if GROQ_AVAILABLE:
        client = Groq(api_key=GROQ_API_KEY)
        candidate_models = [GROQ_MODEL, "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        for m in candidate_models:
            if not m:
                continue
            try:
                completion = client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": text}
                    ],
                    temperature=0.2
                )
                result = completion.choices[0].message.content.strip()
                if result.startswith('```') and result.endswith('```'):
                    lines = result.split('\n')
                    result = '\n'.join(lines[1:-1]).strip()
                if result:
                    return result
            except Exception as e:
                print(f"Groq {m} English translation failed: {e}")
            
    # Try free AI first if available
    if G4FClient:
        try:
            g4f_client = G4FClient()
            completion = g4f_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt + "\n\nText:\n" + text}]
            )
            result = completion.choices[0].message.content.strip()
            if result and len(result) > 10:
                return result
        except Exception as e:
            print("g4f English translation failed:", e)

    # Fallback to Google Translate
    translator = GoogleTranslator(source='auto', target='en')
    chunks = [text[i:i + 4500] for i in range(0, len(text), 4500)]
    result = ""
    for chunk in chunks:
        translated = translator.translate(chunk)
        if translated:
            result += translated + " "
    return result.strip()


def _translate_to_hinglish(english_text):
    """
    Translate text to natural, accurate conversational Hinglish (romanized Hindi)
    using Groq with specialized bilingual contextual understanding, or high-fidelity fallback.
    """
    cleaned_text = _clean_hindi_ocr(english_text)
    if not cleaned_text.strip():
        return ""

    is_english = len(re.findall(r'[a-zA-Z]', cleaned_text)) > len(re.findall(r'[\u0900-\u097F]', cleaned_text))

    if is_english:
        prompt = (
            "You are an expert bilingual Indian literary translator. "
            "Translate the following English passage into natural, fluent, engaging conversational HINGLISH "
            "(Hindi written in Roman/Latin script, the way modern educated Indians talk, read, and explain ideas). "
            "\nCRITICAL RULES:\n"
            "1. Use natural Roman Hindi words for grammar, verbs, connectors, and sentence flow (e.g. 'karta hai', 'zaroori hai', 'lekin', 'kyunki', 'samajhna padega', 'hamesha', 'isliye').\n"
            "2. Keep important technical, business, military, and conceptual nouns in English as educated Indians naturally do (e.g. 'art of war', 'strategy', 'state', 'vital importance', 'life and death', 'decision', 'discipline').\n"
            "3. STRICTLY output in Roman/Latin script. Do NOT output Devanagari script. Do NOT output pure English.\n"
            "4. Output ONLY the clean Hinglish translation without any quotes, preambles, or markdown formatting."
        )
    else:
        prompt = (
            "You are an expert Indian literary editor and translator. "
            "The user will provide text extracted from a Hindi book that may contain font encoding or OCR corruptions. "
            "Fix character substitutions, broken words, and translate/transliterate it into natural, fluent, and highly accurate HINGLISH "
            "(conversational Hindi written in English/Latin script). "
            "\nCRITICAL RULES:\n"
            "1. Fix character names and terms accurately into standard Romanized Hindi (e.g. 'Dhaniya', 'bailon', 'maalik', 'sikod kar', 'katar-byont').\n"
            "2. Keep the natural Indian storytelling tone, emotions, and dialogue style.\n"
            "3. Use standard Romanized Hindi spellings (e.g. 'nahi', 'apni', 'chinta', 'kaha', 'main', 'kyun').\n"
            "4. STRICTLY output in Roman/Latin script. Do NOT output Devanagari script.\n"
            "5. Output ONLY the clean Hinglish text, without any quotes, notes, or preamble."
        )

    if GROQ_AVAILABLE:
        client = Groq(api_key=GROQ_API_KEY)
        candidate_models = [GROQ_MODEL, "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        for m in candidate_models:
            if not m:
                continue
            try:
                completion = client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": cleaned_text}
                    ],
                    temperature=0.2
                )
                result = completion.choices[0].message.content.strip()
                if result and len(result) > 10:
                    if result.startswith('```') and result.endswith('```'):
                        lines = result.split('\n')
                        result = '\n'.join(lines[1:-1]).strip()
                    if result.startswith('"') and result.endswith('"'):
                        result = result[1:-1]
                    return result
            except Exception as e:
                print(f"Groq {m} Hinglish attempt failed: {e}")

    # Try free AI if available
    if G4FClient:
        try:
            g4f_client = G4FClient()
            completion = g4f_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt + "\n\nText:\n" + cleaned_text}]
            )
            result = completion.choices[0].message.content.strip()
            if result and len(result) > 10:
                if result.startswith('"') and result.endswith('"'):
                    result = result[1:-1]
                return result
        except Exception as e:
            print("g4f Hinglish failed:", e)

    # Fallback: English -> Hindi -> Romanized Google Translate
    hindi_text = _translate_conversational_hindi(cleaned_text)
    if not hindi_text:
        return cleaned_text

    url = "https://translate.googleapis.com/translate_a/single"
    chunk_size = 4000
    hindi_chunks = [hindi_text[i:i + chunk_size] for i in range(0, len(hindi_text), chunk_size)]
    romanized_parts = []

    for chunk in hindi_chunks:
        try:
            params = {
                'client': 'gtx',
                'sl': 'hi',
                'tl': 'en',
                'dt': 'rm'
            }
            response = http_requests.post(url, params=params, data={'q': chunk}, timeout=15)
            data = response.json()

            if data and data[0]:
                for segment in data[0]:
                    if segment and len(segment) > 3 and segment[3]:
                        romanized_parts.append(segment[3])
                    elif segment and segment[0]:
                        romanized_parts.append(segment[0])
            else:
                romanized_parts.append(chunk)
        except Exception:
            romanized_parts.append(chunk)

    return " ".join(romanized_parts).strip()


@ratelimit(key='user', rate=os.environ.get('RATE_LIMIT_USER', '60/m'), block=False)
@login_required(login_url='/')
def translate_page(request):
    if getattr(request, 'limited', False) and not settings.DEBUG:
        return JsonResponse({'error': 'Too many requests. Please wait a moment.'}, status=429)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            form = PageTranslationForm(data)
            
            if not form.is_valid():
                return JsonResponse({'error': 'Invalid request data', 'details': form.errors}, status=400)
                
            book_id = form.cleaned_data.get('book_id')
            page_number = form.cleaned_data.get('page_number')
            english_text = form.cleaned_data.get('english_text', '').strip()
            language = form.cleaned_data.get('language') or 'hindi'
            force_refresh = form.cleaned_data.get('force_refresh', False)

            if language not in ('hindi', 'hinglish', 'english'):
                language = 'hindi'

            if book_id is None or page_number is None:
                return JsonResponse({'error': 'Missing required fields'}, status=400)
                
            if not english_text:
                return JsonResponse({'page_number': page_number, 'hindi_text': '', 'language': language})

            book = get_object_or_404(Book, id=book_id, user=request.user)

            # ── Check cache ──
            if not force_refresh:
                cache_entry = TranslationCache.objects.filter(
                    book=book, page_number=page_number, language=language
                ).first()
                if cache_entry and cache_entry.hindi_text:
                    cached_val = cache_entry.hindi_text.strip()
                    is_bad_cache = False
                    if language == 'hinglish' and ('(mausam aur samay)' in cached_val or '(zameen aur terrain' in cached_val or '(desh/rajya)' in cached_val):
                        is_bad_cache = True
                    if not is_bad_cache:
                        return JsonResponse({
                            'page_number': page_number,
                            'hindi_text': cached_val,
                            'summary_text': cache_entry.summary_text or '',
                            'language': language
                        })

            # ── Translate ──
            if language == 'hindi':
                # Use conversational Hindi by default for 'hindi' mode
                translated_text = _translate_conversational_hindi(english_text)
            elif language == 'hinglish':
                translated_text = _translate_to_hinglish(english_text)
            elif language == 'english':
                translated_text = _translate_chunks_english(english_text)
            else:
                return JsonResponse({'error': 'Unsupported language'}, status=400)

            # ── Save to cache ──
            if force_refresh:
                TranslationCache.objects.filter(book=book, page_number=page_number, language=language).delete()
                
            TranslationCache.objects.get_or_create(
                book=book,
                page_number=page_number,
                language=language,
                defaults={
                    'english_text': english_text,
                    'hindi_text': translated_text,
                    'summary_text': ""
                }
            )

            return JsonResponse({
                'page_number': page_number,
                'hindi_text': translated_text, 
                'summary_text': "",
                'language': language
            })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@ratelimit(key='ip', rate=os.environ.get('RATE_LIMIT_PUBLIC', '30/m'), block=False)
def text_to_speech(request):
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'Rate limit exceeded. Try again later.'}, status=429)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            form = TTSForm(data)
            
            if not form.is_valid():
                return JsonResponse({'error': 'Invalid request data', 'details': form.errors}, status=400)
                
            text = form.cleaned_data.get('text', '')
            lang = form.cleaned_data.get('language') or 'hindi'

            # gTTS language code
            gtts_lang = 'hi' if lang in ['hindi', 'hinglish'] else 'en'
            
            # Using gTTS to generate natural Google voice
            tts = gTTS(text=text, lang=gtts_lang, slow=False)
            fp = BytesIO()
            tts.write_to_fp(fp)
            fp.seek(0)
            
            return HttpResponse(fp.read(), content_type="audio/mpeg")
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required(login_url='/')
@ratelimit(key='user', rate=os.environ.get('RATE_LIMIT_USER', '60/m'), block=False)
def ask_book(request):
    if getattr(request, 'limited', False):
        return JsonResponse({'error': 'Too many questions asked. Please wait a moment.'}, status=429)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            form = AskBookForm(data)
            
            if not form.is_valid():
                return JsonResponse({'error': 'Invalid request data', 'details': form.errors}, status=400)
                
            question = form.cleaned_data.get('question', '').strip()
            page_text = form.cleaned_data.get('page_text', '').strip()
                
            prompt = f"You are a helpful and intelligent reading tutor. The user is reading a book (which might be in Hindi, English, or Hinglish) and is asking a question about the current page.\n\nCurrent Page Text:\n{page_text}\n\nUser Question: {question}\n\nCRITICAL INSTRUCTIONS:\n1. Answer the question concisely and clearly based on the page text.\n2. ALWAYS reply in the exact language the user used in their question! If they ask in 'Hinglish' (e.g., 'hinglish me batao', 'kya ho raha hai'), you MUST reply in Hinglish! If they ask in Hindi, reply in Hindi.\n3. Do NOT say 'the text is in English'. Just explain what is happening."
            
            GROQ_API_KEY = os.getenv('GROQ_API_KEY')
            if not GROQ_API_KEY:
                return JsonResponse({'answer': 'AI Book Chat requires a GROQ_API_KEY configured in your .env file. Add your Groq API key to start chatting.'})
            
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            
            completion = client.chat.completions.create(
                model=os.getenv("GROQ_MODEL", GROQ_MODEL),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7
            )
            
            answer = completion.choices[0].message.content
            return JsonResponse({'answer': answer})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


# ══════════════════════════════════════════════════
# NEW FEATURE APIS
# ══════════════════════════════════════════════════

@login_required(login_url='/')
def api_update_progress(request):
    """Update reading progress for a book."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            book_id = data.get('book_id')
            current_page = data.get('current_page', 1)
            total_pages = data.get('total_pages', 0)
            book = get_object_or_404(Book, id=book_id, user=request.user)
            progress, created = ReadingProgress.objects.update_or_create(
                user=request.user,
                book=book,
                defaults={'current_page': current_page, 'total_pages': total_pages}
            )
            return JsonResponse({'status': 'ok', 'percent': progress.percent})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@login_required(login_url='/')
def api_toggle_bookmark(request):
    """Toggle bookmark on a page. Optionally save a note."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            book_id = data.get('book_id')
            page_number = data.get('page_number')
            note = data.get('note', '')
            book = get_object_or_404(Book, id=book_id, user=request.user)
            existing = Bookmark.objects.filter(user=request.user, book=book, page_number=page_number).first()
            if existing:
                if note and note != existing.note:
                    existing.note = note
                    existing.save()
                    return JsonResponse({'status': 'updated', 'bookmarked': True})
                existing.delete()
                return JsonResponse({'status': 'removed', 'bookmarked': False})
            else:
                Bookmark.objects.create(user=request.user, book=book, page_number=page_number, note=note)
                return JsonResponse({'status': 'added', 'bookmarked': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@login_required(login_url='/')
def api_get_bookmarks(request, book_id):
    """Get all bookmarks for a book."""
    book = get_object_or_404(Book, id=book_id, user=request.user)
    bookmarks = Bookmark.objects.filter(user=request.user, book=book).values('page_number', 'note', 'created_at')
    return JsonResponse({'bookmarks': list(bookmarks)})


@login_required(login_url='/')
def api_save_note(request):
    """Save a quick note on a bookmark."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            book_id = data.get('book_id')
            page_number = data.get('page_number')
            note = data.get('note', '')
            book = get_object_or_404(Book, id=book_id, user=request.user)
            bookmark, created = Bookmark.objects.update_or_create(
                user=request.user, book=book, page_number=page_number,
                defaults={'note': note}
            )
            return JsonResponse({'status': 'saved'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@login_required(login_url='/')
def api_manage_tags(request):
    """Create/delete tags and assign/remove them from books."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action')  # 'create', 'delete', 'assign', 'unassign'
            
            if action == 'create':
                name = data.get('name', '').strip()
                color = data.get('color', '#8b5cf6')
                if not name:
                    return JsonResponse({'error': 'Tag name required'}, status=400)
                tag, created = BookTag.objects.get_or_create(
                    name=name, user=request.user, defaults={'color': color}
                )
                return JsonResponse({'status': 'created' if created else 'exists', 'tag_id': tag.id, 'name': tag.name, 'color': tag.color})
            
            elif action == 'delete':
                tag_id = data.get('tag_id')
                BookTag.objects.filter(id=tag_id, user=request.user).delete()
                return JsonResponse({'status': 'deleted'})
            
            elif action == 'assign':
                book_id = data.get('book_id')
                tag_id = data.get('tag_id')
                book = get_object_or_404(Book, id=book_id, user=request.user)
                tag = get_object_or_404(BookTag, id=tag_id, user=request.user)
                BookTagAssignment.objects.get_or_create(book=book, tag=tag)
                return JsonResponse({'status': 'assigned'})
            
            elif action == 'unassign':
                book_id = data.get('book_id')
                tag_id = data.get('tag_id')
                book = get_object_or_404(Book, id=book_id, user=request.user)
                tag = get_object_or_404(BookTag, id=tag_id, user=request.user)
                BookTagAssignment.objects.filter(book=book, tag=tag).delete()
                return JsonResponse({'status': 'unassigned'})
            
            return JsonResponse({'error': 'Unknown action'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=405)


def safe_google_login(request):
    """
    Safely handles Google OAuth login. If GOOGLE_CLIENT_ID is not configured,
    avoids redirecting to Google's broken 'Error 400: invalid_request (Missing client_id)'
    page, and returns a clean, friendly message directing the user to use
    Username & Password registration/login.
    """
    google_client_id = os.environ.get('GOOGLE_CLIENT_ID', '').strip()
    if not google_client_id:
        return render(request, 'reader/landing.html', {
            'auth_error': 'Google Sign-In is not configured yet (Missing GOOGLE_CLIENT_ID). Please register or log in using Username & Password below.',
            'auth_action': 'login'
        })
    from allauth.socialaccount.providers.google.views import oauth2_login
    return oauth2_login(request)

