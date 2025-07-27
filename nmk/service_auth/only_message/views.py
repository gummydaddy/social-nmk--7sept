# views.py
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User as AuthUser
from .forms import MessageForm
from .signals import create_user_encryption_keys
from .models import Message, UserEncryptionKeys, ConversationKey, LoggedInUser
from django.db.models import Q, Max
from .encryption_utils import encrypt_message, decrypt_message, sign_message, verify_message
from django.http import HttpResponse, JsonResponse
import logging
from cryptography.fernet import Fernet
from datetime import timedelta
from django.utils.timezone import now

from .encryption_utils import encrypt_message, decrypt_message, sign_message, verify_message, generate_key_pair, serialize_key
#from .utils import encrypt_message, sign_message, get_or_create_conversation_key, create_user_encryption_keys # Make sure these are correctly imported
from django.contrib.auth import get_user_model
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
from django.views.decorators.http import require_http_methods



logger = logging.getLogger(__name__)


def get_or_create_conversation_key(sender, recipient):
    conversation = ConversationKey.objects.filter(participants=sender).filter(participants=recipient).first()
    if conversation:
        return conversation.key

    key = Fernet.generate_key().decode()
    conversation = ConversationKey.objects.create(key=key)
    conversation.participants.set([sender, recipient])
    return key


# @login_required
# def user_list(request):
#     users = AuthUser.objects.all()
#     online_threshold = now() - timedelta(minutes=5)
#     online_users = []
#     user_ids = {}
#     for user in users:
#         user.is_online = hasattr(user, 'loggedinuser') and user.loggedinuser.last_activity > online_threshold
#         if user.is_online:
#             online_users.append(user.id)
#         user_ids[user.username] = user.id
    
#     if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
#         return JsonResponse({'online_users': online_users, 'user_ids': user_ids})
    
#     return render(request, 'user_list.html', {'users': users})

@login_required
def _base(request):
    return render(request,'_base.html')


def get_online_users(request):
    online_users = []
    for user in AuthUser.objects.all():
        if LoggedInUser.objects.filter(user=user).exists():
            online_users.append(user.id)
    return JsonResponse({'online_users': online_users})


@login_required
def send_message_view(request):
    if request.method == 'POST':
        form = MessageForm(request.POST, request.FILES) # Add request.FILES for file uploads
        if form.is_valid():
            recipient_username = form.cleaned_data['recipient']
            content = form.cleaned_data['content']
            uploaded_file = request.FILES.get('file') # Get the uploaded file

            try:
                recipient = AuthUser.objects.get(username=recipient_username)
            except AuthUser.DoesNotExist:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Recipient user does not exist.'})
                messages.error(request, 'Recipient user does not exist.')
                return redirect('only_message:send_message_view')

            try:
                recipient_keys = UserEncryptionKeys.objects.get(user=recipient)
                sender_keys = UserEncryptionKeys.objects.get(user=request.user)
            except UserEncryptionKeys.DoesNotExist:
                create_user_encryption_keys(AuthUser, request.user, True) # Pass sender as AuthUser
                create_user_encryption_keys(AuthUser, recipient, True)
                recipient_keys = UserEncryptionKeys.objects.get(user=recipient)
                sender_keys = UserEncryptionKeys.objects.get(user=request.user)

            if not sender_keys.signing_private_key:
                logger.error(f'Sender signing private key is missing for user {request.user.username}.')
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Sender signing private key is missing.'})
                messages.error(request, 'An error occurred while sending the message. Please try again.')
                return redirect('only_message:send_message_view')

            conversation_key = get_or_create_conversation_key(request.user, recipient)

            try:
                encrypted_content = encrypt_message(content, conversation_key.encode())
                signature = sign_message(content, sender_keys.signing_private_key)
            except Exception as e:
                logger.error(f'Error during message encryption or signing: {str(e)}')
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Error during message encryption or signing.'})
                messages.error(request, 'An error occurred while sending the message. Please try again.')
                return redirect('only_message:send_message_view')

            new_message = Message.objects.create(
                sender=request.user,
                recipient=recipient,
                content=encrypted_content,
                signature=signature,
                file=uploaded_file # Save the file here
            )

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                # For AJAX requests, return JSON
                return JsonResponse({
                    'success': True,
                    'message_id': new_message.id,
                    'sender': request.user.username,
                    'recipient': recipient.username,
                    'content': content, # Send original content for display if client decrypts, or decrypted_content
                    'timestamp': new_message.timestamp.isoformat(),
                    'file_url': new_message.file.url if new_message.file else None
                })
            else:
                # For regular form submissions, redirect
                messages.success(request, 'Message sent successfully.')
                return redirect('only_message:message_list_view')
        else:
            # Form is not valid
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Invalid form data.', 'errors': form.errors})
            messages.error(request, 'There was an error sending your message. Please try again.')
            return render(request, 'send_message.html', {'form': form}) # Render with form errors
    else:
        initial_data = {}
        recipient_username = request.GET.get('recipient')
        if recipient_username:
            initial_data['recipient'] = recipient_username
        form = MessageForm(initial=initial_data)
    return render(request, 'send_message.html', {'form': form})

"""
@login_required
def message_list_view(request):
    # Get the latest message timestamp for each user
    latest_messages = Message.objects.filter(
        Q(sender=request.user) | Q(recipient=request.user)
    ).values('sender', 'recipient').annotate(
        latest_message=Max('timestamp')
    ).order_by('-latest_message')

    user_ids = set()
    for message in latest_messages:
        user_ids.add(message['sender'] if message['sender'] != request.user.id else message['recipient'])

    # Get the users and their latest message timestamp
    users = AuthUser.objects.filter(id__in=user_ids)
    users = sorted(users, key=lambda u: next(
        (m['latest_message'] for m in latest_messages if m['sender'] == u.id or m['recipient'] == u.id),
        None
    ), reverse=True)

    return render(request, 'message_list.html', {'users': users})

"""

@login_required
def message_list_view(request):
    # Get the latest message timestamp for each user
    latest_messages = Message.objects.filter(
        Q(sender=request.user) | Q(recipient=request.user)
    ).values('sender', 'recipient').annotate(
        latest_message=Max('timestamp')
    ).order_by('-latest_message')

    user_ids = set()
    for message in latest_messages:
        # Determine the other user in the conversation
        other_user_id = message['sender'] if message['sender'] != request.user.id else message['recipient']
        if other_user_id: # Ensure other_user_id is not None (can happen if sender/recipient is deleted)
            user_ids.add(other_user_id)

    # Get the users and their latest message timestamp
    users_with_latest_message_time = []
    users_qs = AuthUser.objects.filter(id__in=list(user_ids)) # Convert set to list for __in lookup

    for user in users_qs:
        # Find the latest message timestamp for this specific user
        latest_time = None
        for m in latest_messages:
            if m['sender'] == user.id or m['recipient'] == user.id:
                latest_time = m['latest_message']
                break # Found the latest for this user

        if latest_time:
            users_with_latest_message_time.append({'user': user, 'latest_message_time': latest_time})

    # Sort users by their latest message timestamp in reverse order
    sorted_users_data = sorted(users_with_latest_message_time, key=lambda x: x['latest_message_time'], reverse=True)
    users = [data['user'] for data in sorted_users_data]

    return render(request, 'message_list.html', {'users': users})


#sending message update that included sending files 
@login_required
def user_messages_view(request, username):
    user = get_object_or_404(AuthUser, username=username)
    messages = Message.objects.filter(
        (Q(sender=request.user) & Q(recipient=user)) |
        (Q(sender=user) & Q(recipient=request.user))
    ).order_by('-timestamp')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        message_data = [{
            'id': msg.id,
            'content': msg.content,
            'sender': msg.sender.username,
            'timestamp': msg.timestamp.isoformat(),
            'file_url': msg.file.url if msg.file else None  # Include file URL if file exists
        } for msg in messages]
        return JsonResponse({'messages': message_data})

    if request.method == 'POST':
        form = MessageForm(request.POST, request.FILES)  # Handle file uploads
        if form.is_valid():
            content = form.cleaned_data['content']
            uploaded_file = request.FILES.get('file', None)  # Get uploaded file if present

            try:
                recipient_keys = UserEncryptionKeys.objects.get(user=user)
                sender_keys = UserEncryptionKeys.objects.get(user=request.user)
            except UserEncryptionKeys.DoesNotExist:
                logger.error('User encryption keys not found.')
                return HttpResponse('User encryption keys not found.', status=404)

            if not sender_keys.signing_private_key:
                logger.error(f'Sender signing private key is missing for user {request.user.username}.')
                return HttpResponse('Sender signing private key is missing.', status=500)

            conversation_key = get_or_create_conversation_key(request.user, user)

            try:
                encrypted_content = encrypt_message(content, conversation_key.encode())
                signature = sign_message(content, sender_keys.signing_private_key)
            except Exception as e:
                logger.error(f'Error during message encryption or signing: {e}')
                return HttpResponse('Error during message encryption or signing.', status=500)

            # File is saved as-is, not encrypted.
            Message.objects.create(
                sender=request.user,
                recipient=user,
                content=encrypted_content,
                signature=signature,
                file=uploaded_file  # Save the uploaded file directly
            )

            return redirect('only_message:user_messages_view', username=user.username)
    else:
        form = MessageForm(initial={'recipient': user.username})

    try:
        user_keys = UserEncryptionKeys.objects.get(user=request.user)
    except UserEncryptionKeys.DoesNotExist:
        logger.error('Your encryption keys not found.')
        return HttpResponse('Your encryption keys not found.', status=404)

    decrypted_messages = []
    for msg in messages:
        conversation_key = get_or_create_conversation_key(request.user, msg.sender if msg.sender != request.user else msg.recipient)
        decrypted_content = decrypt_message(msg.content, conversation_key.encode())
        if decrypted_content is None:
            logger.warning(f'Failed to decrypt message {msg.id}.')
            continue

        # Ensure the sender has encryption_keys associated, especially for signature verification
        if not hasattr(msg.sender, 'encryption_keys') or not msg.sender.encryption_keys.signing_public_key:
            logger.error(f"Sender {msg.sender.username} does not have signing_public_key for message {msg.id}.")
            signature_valid = False # Cannot verify without public key
        else:
            signature_valid = verify_message(
                decrypted_content,
                msg.signature,
                msg.sender.encryption_keys.signing_public_key
            )

        decrypted_messages.append({
            'sender': msg.sender,
            'content': decrypted_content,
            'timestamp': msg.timestamp,
            'signature_valid': signature_valid,
            'file_url': msg.file.url if msg.file else None  # Include file URL for decrypted messages
        })

    return render(request, 'user_messages.html', {'messages': decrypted_messages, 'form': form, 'recipient': user})


"""
#old message sending function 
@login_required
def user_messages_view(request, username):
    user = get_object_or_404(AuthUser, username=username)
    messages_qs = Message.objects.filter(
        (Q(sender=request.user) & Q(recipient=user)) |
        (Q(sender=user) & Q(recipient=request.user))
    ).order_by('timestamp') # Order by timestamp ASC for chat flow

    # Handle AJAX POST request for sending messages/files
    if request.method == 'POST':
        form = MessageForm(request.POST, request.FILES) # Handle file uploads
        if form.is_valid():
            content = form.cleaned_data['content']
            uploaded_file = request.FILES.get('file', None)

            # Ensure either content or file exists
            if not content and not uploaded_file:
                return JsonResponse({'success': False, 'error': 'Cannot send empty message or without a file.'}, status=400)


            # --- Encryption/Signature Logic (as per your original code) ---
            try:
                recipient_keys = UserEncryptionKeys.objects.get(user=user)
                sender_keys = UserEncryptionKeys.objects.get(user=request.user)
            except UserEncryptionKeys.DoesNotExist:
                logger.error(f'User encryption keys not found for {request.user.username} or {user.username}. Attempting to create.')
                # This logic is a bit risky if not properly designed for concurrency
                # Best to ensure keys exist at user registration.
                try:
                    create_user_encryption_keys(AuthUser, request.user, True)
                    create_user_encryption_keys(AuthUser, user, True)
                    sender_keys = UserEncryptionKeys.objects.get(user=request.user)
                    recipient_keys = UserEncryptionKeys.objects.get(user=user)
                except Exception as e:
                    logger.error(f'Failed to create encryption keys: {e}')
                    return JsonResponse({'success': False, 'error': 'User encryption keys could not be generated.'}, status=500)


            if not sender_keys.signing_private_key:
                logger.error(f'Sender signing private key is missing for user {request.user.username}.')
                return JsonResponse({'success': False, 'error': 'Sender signing private key is missing.'}, status=500)

            conversation_key = get_or_create_conversation_key(request.user, user)

            encrypted_content = None
            signature = None
            if content: # Only encrypt/sign if there's actual text content
                try:
                    encrypted_content = encrypt_message(content, conversation_key.encode())
                    signature = sign_message(content, sender_keys.signing_private_key)
                except Exception as e:
                    logger.error(f'Error during message encryption or signing: {e}')
                    return JsonResponse({'success': False, 'error': 'Error during message encryption or signing.'}, status=500)

            # --- Create Message Object ---
            new_message = Message.objects.create(
                sender=request.user,
                recipient=user,
                content=encrypted_content, # Can be None if only file is sent
                signature=signature,       # Can be None if only file is sent
                file=uploaded_file         # Stored as-is
            )

            # --- Send Message via WebSocket (to both sender and recipient) ---
            channel_layer = get_channel_layer()
            group_name = f'chat_{request.user.id}_{user.id}' # Adjust group naming as per your consumer logic
            group_name_reverse = f'chat_{user.id}_{request.user.id}'

            # Prepare data to send over WebSocket
            # Note: We send the original content for display purposes,
            # as the client-side JS expects it for display.
            # In a true end-to-end encrypted scenario, the client would decrypt.
            websocket_message_data = {
                'type': 'chat_message', # Corresponds to a method in your consumer
                'message': content, # Original content
                'sender': request.user.username,
                'recipient': user.username,
                'timestamp': new_message.timestamp.isoformat(),
                'file_url': new_message.file.url if new_message.file else None,
                # 'signature_valid': True # You might want to pass this if you verify on server before sending
            }

            # Send to sender's group (if they are also connected to this chat)
            async_to_sync(channel_layer.group_send)(
                group_name,
                websocket_message_data
            )
            # Send to recipient's group (ensures recipient sees it)
            async_to_sync(channel_layer.group_send)(
                group_name_reverse,
                websocket_message_data
            )

            # --- Return JSON Response for AJAX success ---
            return JsonResponse({'success': True, 'message_id': new_message.id})
        else:
            # Form is not valid, return errors as JSON
            return JsonResponse({'success': False, 'error': 'Invalid form data.', 'errors': form.errors}, status=400)

    # --- Initial GET request for displaying chat history ---
    try:
        user_keys = UserEncryptionKeys.objects.get(user=request.user)
    except UserEncryptionKeys.DoesNotExist:
        logger.error('Your encryption keys not found.')
        messages.error(request, 'Your encryption keys not found.') # Use Django messages for initial load errors
        return render(request, 'user_messages.html', {'messages': [], 'form': MessageForm(), 'recipient': user})

    decrypted_messages = []
    for msg in messages_qs:
        conversation_key = get_or_create_conversation_key(request.user, msg.sender if msg.sender != request.user else msg.recipient)
        decrypted_content = None
        if msg.content: # Only attempt decryption if content exists
            decrypted_content = decrypt_message(msg.content, conversation_key.encode())
            if decrypted_content is None:
                logger.warning(f'Failed to decrypt message {msg.id}. Content will be empty.')
                decrypted_content = "[Message Decryption Failed]" # Placeholder

        signature_valid = False
        if decrypted_content and msg.signature and hasattr(msg.sender, 'encryption_keys') and msg.sender.encryption_keys.signing_public_key:
            signature_valid = verify_message(
                decrypted_content,
                msg.signature,
                msg.sender.encryption_keys.signing_public_key
            )
        elif not msg.content: # If no content, signature validity is irrelevant for text
            signature_valid = True # Or handle as a different status

        decrypted_messages.append({
            'sender': msg.sender,
            'content': decrypted_content,
            'timestamp': msg.timestamp,
            'signature_valid': signature_valid,
            'file_url': msg.file.url if msg.file else None
        })

    form = MessageForm(initial={'recipient': user.username}) # Pre-populate recipient for the form
    return render(request, 'user_messages.html', {'messages': decrypted_messages, 'form': form, 'recipient': user})
"""


def search_user_message(request):
    query = request.GET.get('q')
    if query:
        users = AuthUser.objects.filter(username__icontains=query)
    else:
        users = AuthUser.objects.none()
    
    return render(request, 'search_user_message.html', {'users': users})


@login_required
def get_messages_api(request, username):
    user = get_object_or_404(AuthUser, username=username)
    messages = Message.objects.filter(
        (Q(sender=request.user) & Q(recipient=user)) | (Q(sender=user) & Q(recipient=request.user))
    ).order_by('timestamp')

    decrypted_messages = []
    for msg in messages:
        conversation_key = get_or_create_conversation_key(request.user, msg.sender if msg.sender != request.user else msg.recipient)
        decrypted_content = decrypt_message(msg.content, conversation_key.encode())
        if decrypted_content is not None:
            decrypted_messages.append({
                'id': msg.id,
                'content': decrypted_content,
                'sender': msg.sender.username,
                'timestamp': msg.timestamp.strftime('%H:%M')
            })

    return JsonResponse({'messages': decrypted_messages})







#new update for message sending



