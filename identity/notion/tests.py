# your_app/tests/test_fields.py

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from notion.models import Notion, Comment, Hashtag, Notification
from django.contrib.auth.models import User as AuthUser
from unittest.mock import patch  # <-- Add this import


AuthUser = get_user_model()


class CompressedTextFieldTests(TestCase):
    def setUp(self):
        self.user = AuthUser.objects.create(username='testuser', password='testpassword')

    def test_compressed_field(self):
        # Create a notion
        notion = Notion.objects.create(user=self.user, content='This is a test notion.')
        self.assertEqual(notion.content, 'This is a test notion.')
        self.assertTrue(notion.content.startswith('This is a test notion.'))

        # Fetch the notion from the database
        notion_from_db = Notion.objects.get(id=notion.id)
        self.assertEqual(notion_from_db.content, 'This is a test notion.')

        # Create a comment
        comment = Comment.objects.create(user=self.user, notion=notion, content='This is a test comment.')
        self.assertEqual(comment.content, 'This is a test comment.')
        self.assertTrue(comment.content.startswith('This is a test comment.'))

        # Fetch the comment from the database
        comment_from_db = Comment.objects.get(id=comment.id)
        self.assertEqual(comment_from_db.content, 'This is a test comment.')

    def test_uncompressed_field(self):
        # Create a notion with uncompressed content
        notion = Notion.objects.create(user=self.user, content='Uncompressed test notion.')
        notion.content = 'Uncompressed test notion.'
        notion.save()
        self.assertEqual(notion.content, 'Uncompressed test notion.')

        # Fetch the notion from the database
        notion_from_db = Notion.objects.get(id=notion.id)
        self.assertEqual(notion_from_db.content, 'Uncompressed test notion.')

        # Create a comment with uncompressed content
        comment = Comment.objects.create(user=self.user, notion=notion, content='Uncompressed test comment.')
        comment.content = 'Uncompressed test comment.'
        comment.save()
        self.assertEqual(comment.content, 'Uncompressed test comment.')

        # Fetch the comment from the database
        comment_from_db = Comment.objects.get(id=comment.id)
        self.assertEqual(comment_from_db.content, 'Uncompressed test comment.')


# your_app/tests.py
class PostNotionViewTest(TestCase):
    def setUp(self):
        # Create a user for testing
        self.user = AuthUser.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')

    @patch('notion.views.make_usernames_clickable')
    def test_post_notion(self, mock_make_usernames_clickable):
        # Define the content with hashtags and tagged usernames
        content = "This is a test notion with #hashtag and @testuser"

        # Mock the make_usernames_clickable function to return the content as is
        mock_make_usernames_clickable.return_value = content

        # Send a POST request to post a notion
        response = self.client.post(reverse('notion:post_notion'), {'content': content})

        # Check the response status code (expecting 302 if successful)
        self.assertEqual(response.status_code, 302)

        # Retrieve the created notion
        notion = Notion.objects.first()

        # Check if the notion was created
        self.assertIsNotNone(notion, "The Notion object should have been created but wasn't.")

        # Check that the response redirects to notion_home with the notion_id
        self.assertRedirects(response, reverse('notion:notion_home', kwargs={'notion_id': notion.id}))