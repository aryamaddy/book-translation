import os
import io
import json
import django
from django.core.files.uploadedfile import SimpleUploadedFile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User
from reader.models import Book, UserProfile, TranslationCache, Bookmark, ReadingProgress

def make_test_pdf():
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 53 >>\nstream\nBT\n/F1 24 Tf\n100 700 Td\n(The Art of War by Sun Tzu) Tj\nET\nendstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000244 00000 n \n0000000348 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n428\n%%EOF"
    )

def run_tests():
    print("=== 1. Testing User Setup ===")
    user, _ = User.objects.get_or_create(username='demouser', email='demo@example.com')
    user.set_password('pass1234')
    user.save()

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.onboarded = True
    profile.preferred_language = 'hindi'
    profile.save()
    print("User & Profile ready.")

    client = Client()
    logged_in = client.login(username='demouser', password='pass1234')
    print("Login successful:", logged_in)

    print("\n=== 2. Testing Landing Page & Dashboard ===")
    res_dash = client.get('/dashboard/')
    print("Dashboard status:", res_dash.status_code)
    assert res_dash.status_code == 200

    print("\n=== 3. Testing PDF Upload ===")
    pdf_data = make_test_pdf()
    pdf_file = SimpleUploadedFile("art_of_war.pdf", pdf_data, content_type="application/pdf")
    res_upload = client.post('/dashboard/', {'title': 'The Art of War', 'pdf_file': pdf_file}, follow=True)
    print("Upload status:", res_upload.status_code)
    
    book = Book.objects.filter(title='The Art of War', user=user).first()
    print("Book created in DB:", bool(book), "ID:", book.id if book else None)
    assert book is not None

    print("\n=== 4. Testing Reader View ===")
    res_reader = client.get(f'/read/{book.id}/')
    print("Reader view status:", res_reader.status_code)
    assert res_reader.status_code == 200

    print("\n=== 5. Testing Translation (Hindi) ===")
    trans_payload_hi = {
        'book_id': book.id,
        'page_number': 1,
        'english_text': 'The art of war is of vital importance to the State.',
        'language': 'hindi',
        'force_refresh': True
    }
    res_trans_hi = client.post(
        '/api/translate-page/',
        data=json.dumps(trans_payload_hi),
        content_type='application/json'
    )
    print("Translate Hindi status:", res_trans_hi.status_code)
    hi_json = res_trans_hi.json()
    print("Hindi result:", ascii(hi_json.get('hindi_text')))
    assert 'hindi_text' in hi_json and len(hi_json['hindi_text']) > 0

    print("\n=== 6. Testing Translation (Hinglish) ===")
    trans_payload_hg = {
        'book_id': book.id,
        'page_number': 1,
        'english_text': 'The art of war is of vital importance to the State.',
        'language': 'hinglish',
        'force_refresh': True
    }
    res_trans_hg = client.post(
        '/api/translate-page/',
        data=json.dumps(trans_payload_hg),
        content_type='application/json'
    )
    print("Translate Hinglish status:", res_trans_hg.status_code)
    hg_json = res_trans_hg.json()
    print("Hinglish result:", ascii(hg_json.get('hindi_text')))
    assert 'hindi_text' in hg_json and len(hg_json['hindi_text']) > 0

    print("\n=== 7. Testing Bookmark & Progress APIs ===")
    res_bm = client.post(
        '/api/bookmark/',
        data=json.dumps({'book_id': book.id, 'page_number': 1, 'note': 'Important start'}),
        content_type='application/json'
    )
    print("Bookmark toggle status:", res_bm.status_code, res_bm.json())

    res_prog = client.post(
        '/api/progress/',
        data=json.dumps({'book_id': book.id, 'current_page': 1, 'total_pages': 5}),
        content_type='application/json'
    )
    print("Progress update status:", res_prog.status_code, res_prog.json())

    print("\n=== 8. Testing Ask Book API ===")
    res_ask = client.post(
        '/api/ask-book/',
        data=json.dumps({'question': 'What is this chapter about?', 'page_text': 'The art of war is vital to the State.'}),
        content_type='application/json'
    )
    print("Ask Book status:", res_ask.status_code, res_ask.json())

    print("\n ALL TESTS COMPLETED SUCCESSFULLY!")

if __name__ == '__main__':
    run_tests()
