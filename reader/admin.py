from django.contrib import admin
from .models import (
    Book, TranslationCache, Vocabulary, UserProfile,
    ErrorLog, ReadingProgress, Bookmark, BookTag, BookTagAssignment
)

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'user', 'uploaded_at', 'cover_color')
    list_filter = ('uploaded_at', 'user')
    search_fields = ('title', 'user__username')
    ordering = ('-uploaded_at',)

@admin.register(TranslationCache)
class TranslationCacheAdmin(admin.ModelAdmin):
    list_display = ('id', 'book', 'page_number', 'language', 'summary_text')
    list_filter = ('language', 'book')
    search_fields = ('book__title', 'english_text', 'hindi_text')
    ordering = ('book', 'page_number')

@admin.register(Vocabulary)
class VocabularyAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'english_word', 'hindi_translation', 'saved_at')
    list_filter = ('saved_at', 'user')
    search_fields = ('english_word', 'hindi_translation', 'user__username')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'preferred_language', 'onboarded')
    list_filter = ('preferred_language', 'onboarded')
    search_fields = ('user__username', 'user__email')

@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'action', 'user_info', 'error_message')
    list_filter = ('action', 'timestamp')
    search_fields = ('action', 'error_message', 'user_info')
    ordering = ('-timestamp',)

@admin.register(ReadingProgress)
class ReadingProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'book', 'current_page', 'total_pages', 'percent', 'last_read_at')
    list_filter = ('last_read_at', 'user')
    search_fields = ('user__username', 'book__title')

@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ('user', 'book', 'page_number', 'note', 'created_at')
    list_filter = ('created_at', 'user')
    search_fields = ('user__username', 'book__title', 'note')

@admin.register(BookTag)
class BookTagAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'color', 'user')
    search_fields = ('name', 'user__username')

@admin.register(BookTagAssignment)
class BookTagAssignmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'book', 'tag')
    search_fields = ('book__title', 'tag__name')
