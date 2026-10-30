import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from .models import Book, Vocabulary


class AuthCsrfTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def test_landing_sets_fresh_csrf_cookie_and_disables_caching(self):
        response = self.client.get(reverse('landing_page'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', response.cookies)
        cache_control = response.headers.get('Cache-Control', '')
        self.assertIn('no-store', cache_control)
        self.assertIn('private', cache_control)

    def test_registration_accepts_token_from_current_cookie(self):
        self.client.get(reverse('landing_page'))
        token = self.client.cookies['csrftoken'].value

        response = self.client.post(reverse('register_user'), data={
            'csrfmiddlewaretoken': token,
            'username': 'csrf-reader',
            'email': 'csrf-reader@example.com',
            'password': 'safe-password-123',
            'confirm_password': 'safe-password-123',
            'next': reverse('dashboard'),
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='csrf-reader').exists())

    def test_stale_token_uses_safe_failure_page(self):
        self.client.get(reverse('landing_page'))
        stale_token = self.client.cookies['csrftoken'].value
        self.client.cookies['csrftoken'] = 'a' * 32

        response = self.client.post(reverse('register_user'), data={
            'csrfmiddlewaretoken': stale_token,
            'username': 'stale-reader',
            'email': 'stale-reader@example.com',
            'password': 'safe-password-123',
            'confirm_password': 'safe-password-123',
        })

        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            'Your security token expired. Please submit the form again.',
            status_code=403,
        )
        self.assertNotContains(response, 'CSRF verification failed', status_code=403)


class ReaderApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='reader-one',
            email='reader@example.com',
            password='safe-password-123',
        )
        self.other_user = User.objects.create_user(
            username='reader-two',
            email='other@example.com',
            password='safe-password-123',
        )
        self.book = Book.objects.create(
            user=self.user,
            title='A Test Book',
            pdf_file=SimpleUploadedFile('book.pdf', b'%PDF-1.4 test', content_type='application/pdf'),
        )

    def test_tts_requires_authentication(self):
        response = self.client.post(
            reverse('text_to_speech'),
            data=json.dumps({'text': 'hello', 'language': 'english'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

    def test_progress_rejects_invalid_page_values(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('api_update_progress'),
            data=json.dumps({'book_id': self.book.id, 'current_page': 4, 'total_pages': 3}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_progress_cannot_access_another_users_book(self):
        self.client.force_login(self.other_user)
        response = self.client.post(
            reverse('api_update_progress'),
            data=json.dumps({'book_id': self.book.id, 'current_page': 1, 'total_pages': 3}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)

    def test_vocabulary_crud_is_scoped_to_current_user(self):
        self.client.force_login(self.user)
        create_response = self.client.post(
            reverse('api_vocabulary'),
            data=json.dumps({
                'english_word': 'context',
                'hindi_translation': 'संदर्भ',
                'context_sentence': 'Use the word in context.',
            }),
            content_type='application/json',
        )
        self.assertEqual(create_response.status_code, 200)
        vocabulary_id = create_response.json()['id']

        list_response = self.client.get(reverse('api_vocabulary'))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()['vocabulary']), 1)

        self.client.force_login(self.other_user)
        delete_response = self.client.delete(
            reverse('api_vocabulary'),
            data=json.dumps({'id': vocabulary_id}),
            content_type='application/json',
        )
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(Vocabulary.objects.filter(id=vocabulary_id, user=self.user).exists())
