# your_app/tests/test_fields.py

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from notion.models import Notion, Comment, Hashtag, Notification
from django.contrib.auth.models import User as AuthUser

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


class PostNotionViewTest(TestCase):
    def setUp(self):
        # Create a user for testing
        self.user = AuthUser.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')

    
    def test_post_notion(self):
        # Define notion content and tags
        content = "This is a test notion with #hashtag and @testuser"
        
        # Send a POST request to post a notion
        response = self.client.post(reverse('notion:post_notion'), {'content': content})
        
        # Check that the response redirects to notion_home
        self.assertRedirects(response, reverse('notion:notion_home'))
        
        # Check that the notion was created
        self.assertEqual(Notion.objects.count(), 1)
        
        # Retrieve the notion
        notion = Notion.objects.first()
        
        # Check notion content
        self.assertEqual(notion.content, content)
        
        # Check deletion date
        expected_deletion_date = timezone.now() + timedelta(days=1)
        self.assertTrue((notion.deletion_date - expected_deletion_date).total_seconds() < 60)  # Allow for slight timing discrepancies
        
        # Check hashtags
        self.assertEqual(notion.hashtags.count(), 1)
        self.assertTrue(Hashtag.objects.filter(name='hashtag').exists())
        
        # Check tagged users
        self.assertEqual(notion.tagged_users.count(), 1)
        self.assertTrue(notion.tagged_users.filter(username='testuser').exists())
        
        # Check notification for tagged user
        self.assertEqual(Notification.objects.count(), 1)
        notification = Notification.objects.first()
        self.assertEqual(notification.user, self.user)
        self.assertIn('You were tagged in a notion', notification.content)
        
        # Simulate time passing and check deletion
        with timezone.override(timezone.now() + timedelta(days=2)):
            # Ensure the notion gets deleted
            Notion.objects.filter(deletion_date__lt=timezone.now()).delete()
            self.assertEqual(Notion.objects.count(), 0)