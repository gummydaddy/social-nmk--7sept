from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from .models import Media, Hashtag, UserHashtagPreference
from .storage import CompressedMediaStorage
from PIL import Image
import tempfile
import os
import json


AuthUser = get_user_model()

# class MediaUploadTest(TestCase):
#     def setUp(self):
#         self.user = AuthUser.objects.create_user(username='testuser', password='12345')
#         self.client.login(username='testuser', password='12345')

#     def test_image_upload_and_compression(self):
#         # Create a simple image
#         image = Image.new('RGB', (100, 100), color='red')
#         tmp_file = tempfile.NamedTemporaryFile(suffix='.jpg')
#         image.save(tmp_file.name)

#         # Upload the image
#         with open(tmp_file.name, 'rb') as img:
#             response = self.client.post('/upload_media/', {'file': img, 'description': 'Test Image', 'media_type': 'image'})

#         # Verify upload and compression
#         self.assertEqual(response.status_code, 302)  # Redirects after successful upload
#         media = Media.objects.get(description='Test Image')
#         self.assertTrue(media.file.url.endswith('.jpg'))

#     def test_video_upload_and_compression(self):
#         # Create a dummy video file
#         tmp_file = tempfile.NamedTemporaryFile(suffix='.mp4')
#         tmp_file.write(os.urandom(1024))  # Writing random bytes to simulate a video file
#         tmp_file.seek(0)

#         # Upload the video
#         with open(tmp_file.name, 'rb') as vid:
#             response = self.client.post('/upload_media/', {'file': vid, 'description': 'Test Video', 'media_type': 'video'})

#         # Verify upload and compression
#         self.assertEqual(response.status_code, 302)  # Redirects after successful upload
#         media = Media.objects.get(description='Test Video')
#         self.assertTrue(media.file.url.endswith('.mp4'))




class MediaInteractionTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')

        # Create hashtags
        self.hashtag1 = Hashtag.objects.create(name='hashtag1')
        self.hashtag2 = Hashtag.objects.create(name='hashtag2')

        # Create media
        self.media = Media.objects.create(
            user=self.user,
            media_type='image',
            file='media/test_image.jpg',
            description='#hashtag1 #hashtag2',
            is_paid=False
        )
        self.media.hashtags.add(self.hashtag1, self.hashtag2)

        self.like_url = reverse('like_media', args=[self.media.id])
        self.not_interested_url = reverse('not_interested', args=[self.media.id])
        self.explore_url = reverse('explore')
        self.feedback_url = reverse('feedback', args=[self.media.id, 'positive'])

    def test_like_media(self):
        response = self.client.post(self.like_url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.media.likes.filter(id=self.user.id).exists())

        # Check if the hashtag is added to the liked hashtags list
        user_pref = UserHashtagPreference.objects.get(user=self.user)
        self.assertIn('hashtag1', user_pref.liked_hashtags)
        self.assertIn('hashtag2', user_pref.liked_hashtags)

    def test_not_interested(self):
        response = self.client.post(self.not_interested_url)
        self.assertEqual(response.status_code, 302)

        # Check if the hashtag is added to the not interested hashtags list
        user_pref = UserHashtagPreference.objects.get(user=self.user)
        self.assertIn('hashtag1', user_pref.not_interested_hashtags)
        self.assertIn('hashtag2', user_pref.not_interested_hashtags)

    def test_explore_view(self):
        response = self.client.get(self.explore_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'explore.html')

        # Check if media is present in the response
        media_list = response.context['page_obj']
        self.assertIn(self.media, media_list.object_list)

    def test_feedback(self):
        response = self.client.post(self.feedback_url)
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'status': 'success', 'message': 'Feedback recorded'})

        # Check if the hashtag is added to the liked hashtags list
        user_pref = UserHashtagPreference.objects.get(user=self.user)
        self.assertIn('hashtag1', user_pref.liked_hashtags)
        self.assertIn('hashtag2', user_pref.liked_hashtags)

if __name__ == "__main__":
    TestCase.main()