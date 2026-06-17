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
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from django.views.decorators.vary import vary_on_headers
from django.views.decorators.cache import cache_page, cache_control

from django.views.decorators.http import require_POST

from .websocket_notifications import (
    create_message_notification,
    send_notification_sync,
    get_notifications,
    get_unread_count,
    clear_unread_count
)

from .tasks import process_uploaded_file

AuthUser = get_user_model()
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
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def _base(request):
    return render(request,'_base.html')

'''
def get_online_users(request):
    online_users = []
    for user in AuthUser.objects.all():
        if LoggedInUser.objects.filter(user=user).exists():
            online_users.append(user.id)
    return JsonResponse({'online_users': online_users})

'''
'''
def get_online_users(request):
    online_threshold = now() - timedelta(minutes=5)

    online_users = list(
        LoggedInUser.objects.filter(
            last_activity__gte=online_threshold
        ).values_list('user_id', flat=True)
    )

    return JsonResponse({
        'online_users': online_users
    })
'''
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def get_online_users(request):
    online_threshold = now() - timedelta(minutes=5)

    online_users = [
        {
            "id": obj.user.id,
            "username": obj.user.username,
        }
        for obj in LoggedInUser.objects.select_related('user').filter(
            last_activity__gte=online_threshold
        )
    ]

    return JsonResponse({
        "online_users": online_users
    })
#----------------------------------------------------------------------------------------
#
#
#----------------------------------------------------------------------------------------


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def send_message_view(request):

    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "error": "POST request required."
        }, status=405)

    form = MessageForm(request.POST, request.FILES)

    if not form.is_valid():
        return JsonResponse({
            "success": False,
            "error": "Invalid form data.",
            "errors": form.errors
        }, status=400)

    recipient_username = form.cleaned_data["recipient"]
    content = form.cleaned_data["content"]
    uploaded_file = request.FILES.get("file")

    # ----------------------------
    # Get recipient
    # ----------------------------
    try:
        recipient = AuthUser.objects.get(username=recipient_username)
    except AuthUser.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Recipient user does not exist."
        }, status=404)

    # ----------------------------
    # Encryption keys
    # ----------------------------
    try:
        recipient_keys = UserEncryptionKeys.objects.get(user=recipient)
        sender_keys = UserEncryptionKeys.objects.get(user=request.user)
    except UserEncryptionKeys.DoesNotExist:
        create_user_encryption_keys(AuthUser, request.user, True)
        create_user_encryption_keys(AuthUser, recipient, True)

        recipient_keys = UserEncryptionKeys.objects.get(user=recipient)
        sender_keys = UserEncryptionKeys.objects.get(user=request.user)

    if not sender_keys.signing_private_key:
        logger.error(
            f"Sender signing private key missing for {request.user.username}"
        )
        return JsonResponse({
            "success": False,
            "error": "Sender signing private key missing."
        }, status=500)

    # ----------------------------
    # Encrypt + Sign
    # ----------------------------
    conversation_key = get_or_create_conversation_key(
        request.user,
        recipient
    )

    try:
        encrypted_content = encrypt_message(
            content,
            conversation_key.encode()
        )
        signature = sign_message(
            content,
            sender_keys.signing_private_key
        )
    except Exception as e:
        logger.error(f"Encryption/signing error: {str(e)}")
        return JsonResponse({
            "success": False,
            "error": "Encryption or signing failed."
        }, status=500)

    # ----------------------------
    # Save message
    # ----------------------------
    new_message = Message.objects.create(
        sender=request.user,
        recipient=recipient,
        content=encrypted_content,
        signature=signature,
        file=uploaded_file
    )

    # ----------------------------
    # API response ONLY
    # ----------------------------
    return JsonResponse({
        "success": True,
        "message": {
            "id": new_message.id,
            "sender": request.user.username,
            "recipient": recipient.username,
            "content": content,  # plaintext for UI display
            "timestamp": new_message.timestamp.isoformat(),
            "file_url": (
                new_message.file.url
                if new_message.file else None
            ),
        }
    }, status=201)

#----------------------------------------------------------------------------------------
#
#
#----------------------------------------------------------------------------------------





@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def message_list_view(request):
    latest_messages = Message.objects.filter(
        Q(sender=request.user) | Q(recipient=request.user)
    ).values('sender', 'recipient').annotate(
        latest_message=Max('timestamp')
    ).order_by('-latest_message')

    user_ids = set()
    for message in latest_messages:
        other_user_id = message['sender'] if message['sender'] != request.user.id else message['recipient']
        if other_user_id:
            user_ids.add(other_user_id)

    users_with_latest_message_time = []
    users_qs = AuthUser.objects.filter(id__in=list(user_ids))

    for user in users_qs:
        latest_time = None
        for m in latest_messages:
            if m['sender'] == user.id or m['recipient'] == user.id:
                latest_time = m['latest_message']
                break

        if latest_time:
            users_with_latest_message_time.append({'user': user, 'latest_message_time': latest_time})

    sorted_users_data = sorted(users_with_latest_message_time, key=lambda x: x['latest_message_time'], reverse=True)
    users = [data['user'] for data in sorted_users_data]

    return render(request, 'message_list.html', {'users': users})


#----------------------------------------------------------------------------------------
#
#
#----------------------------------------------------------------------------------------

# FIXED user_messages_view function for views.py
'''
@login_required
def user_messages_view(request, username):
    user = get_object_or_404(AuthUser, username=username)
    
    # Get messages for display - ORDER BY TIMESTAMP ASCENDING (oldest first)
    messages_qs = Message.objects.filter(
        (Q(sender=request.user) & Q(recipient=user)) |
        (Q(sender=user) & Q(recipient=request.user))
    ).order_by('timestamp')
 
    # ===== HANDLE POST REQUESTS =====
    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        logger.info(f"POST request from {request.user.username} to {username}")
        logger.info(f"Is AJAX: {is_ajax}")
        
        form = MessageForm(request.POST, request.FILES)
        
        if form.is_valid():
            content = form.cleaned_data.get('content', '').strip()
            uploaded_file = request.FILES.get('file', None)
 
            logger.info(f"Form valid - content: {bool(content)}, file: {bool(uploaded_file)}")
 
            if not content and not uploaded_file:
                return JsonResponse({
                    'success': False,
                    'error': 'Cannot send empty message.'
                }, status=400)
 
            try:
                # Get encryption keys
                try:
                    recipient_keys = UserEncryptionKeys.objects.get(user=user)
                    sender_keys = UserEncryptionKeys.objects.get(user=request.user)
                except UserEncryptionKeys.DoesNotExist:
                    logger.warning('Encryption keys not found, creating...')
                    create_user_encryption_keys(AuthUser, request.user, True)
                    create_user_encryption_keys(AuthUser, user, True)
                    sender_keys = UserEncryptionKeys.objects.get(user=request.user)
                    recipient_keys = UserEncryptionKeys.objects.get(user=user)
 
                if not sender_keys.signing_private_key:
                    logger.error('Sender signing private key missing')
                    return JsonResponse({
                        'success': False,
                        'error': 'Signing key missing.'
                    }, status=500)
 
                conversation_key = get_or_create_conversation_key(request.user, user)
 
                # Encrypt and sign message
                encrypted_content = None
                signature = None
                if content:
                    encrypted_content = encrypt_message(content, conversation_key.encode())
                    signature = sign_message(content, sender_keys.signing_private_key)
                    logger.info('Message encrypted and signed')
 
                # Create message in database
                new_message = Message.objects.create(
                    sender=request.user,
                    recipient=user,
                    content=encrypted_content,
                    signature=signature,
                    file=uploaded_file
                )
 
                logger.info(f"✅ Message created in database: id={new_message.id}")
 
                # ========================================
                # CREATE AND SEND NOTIFICATION (NEW CODE)
                # ========================================
                try:
                    # Prepare notification message preview
                    if content:
                        message_preview = content
                    elif uploaded_file:
                        message_preview = f"📎 {uploaded_file.name}"
                    else:
                        message_preview = "Sent a message"
                    
                    # Create notification
                    notification_data = create_message_notification(
                        sender_username=request.user.username,
                        sender_id=request.user.id,
                        recipient_user_id=user.id,
                        message_preview=message_preview,
                        message_id=new_message.id
                    )
                    
                    logger.info(f"🔔 Notification created: {notification_data}")
                    
                    # Broadcast notification via WebSocket
                    send_notification_sync(user.id, notification_data)
                    
                    logger.info(f"✅ Notification sent to user {user.username}")
                    
                except Exception as e:
                    # Don't fail the message send if notification fails
                    logger.warning(f"⚠️ Failed to send notification: {e}")
                # ========================================
 
                response_data = {
                    'success': True,
                    'message_id': new_message.id,
                    'sender': request.user.username,
                    'recipient': user.username,
                    'content': content,
                    'timestamp': new_message.timestamp.isoformat(),
                    'file_url': new_message.file.url if new_message.file else None
                }
                
                logger.info(f"Returning JSON response: message_id={new_message.id}")
                return JsonResponse(response_data)
 
            except Exception as e:
                logger.error(f'Error processing message: {str(e)}', exc_info=True)
                return JsonResponse({
                    'success': False,
                    'error': f'Server error: {str(e)}'
                }, status=500)
        else:
            logger.error(f'Form validation errors: {form.errors}')
            return JsonResponse({
                'success': False,
                'error': 'Invalid form data.',
                'errors': dict(form.errors)
            }, status=400)
 
    # ===== HANDLE GET REQUESTS =====
    form = MessageForm(initial={'recipient': user.username})
 
    try:
        user_keys = UserEncryptionKeys.objects.get(user=request.user)
    except UserEncryptionKeys.DoesNotExist:
        logger.error('Encryption keys not found for current user')
        return HttpResponse('Your encryption keys not found.', status=404)
 
    # Decrypt messages for display
    decrypted_messages = []
    for msg in messages_qs:
        conversation_key = get_or_create_conversation_key(
            request.user,
            msg.sender if msg.sender != request.user else msg.recipient
        )
        
        decrypted_content = None
        if msg.content:
            decrypted_content = decrypt_message(msg.content, conversation_key.encode())
            if decrypted_content is None:
                logger.warning(f'Failed to decrypt message {msg.id}')
                decrypted_content = "[Decryption Failed]"
 
        signature_valid = False
        if (decrypted_content and decrypted_content != "[Decryption Failed]" and 
            msg.signature and hasattr(msg.sender, 'encryption_keys')):
            if msg.sender.encryption_keys.signing_public_key:
                signature_valid = verify_message(
                    decrypted_content,
                    msg.signature,
                    msg.sender.encryption_keys.signing_public_key
                )
 
        decrypted_messages.append({
            'id': msg.id,

            'sender': msg.sender,
            'content': decrypted_content,
            'timestamp': msg.timestamp,
            'signature_valid': signature_valid,
            'file_url': msg.file.url if msg.file else None
        })
 
    return render(request, 'user_messages.html', {
        'messages': decrypted_messages,
        'form': form,
        'recipient': user
    })

'''

# Find the part where new_message is created and add notification sending



# nmk/service_auth/only_message/views.py
# UPDATED user_messages_view function with async file processing
@login_required
def user_messages_view(request, username):
    user = get_object_or_404(AuthUser, username=username)

    # Get messages for display - ORDER BY TIMESTAMP ASCENDING
    messages_qs = Message.objects.filter(
        (Q(sender=request.user) & Q(recipient=user)) |
        (Q(sender=user) & Q(recipient=request.user))
    ).order_by('timestamp')

    # =====================================================
    # HANDLE POST REQUESTS
    # =====================================================
    if request.method == 'POST':

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        logger.info(
            f"POST request from {request.user.username} to {username}"
        )

        logger.info(f"Is AJAX: {is_ajax}")

        form = MessageForm(request.POST, request.FILES)

        if form.is_valid():

            content = form.cleaned_data.get('content', '').strip()
            uploaded_file = request.FILES.get('file', None)

            logger.info(
                f"Form valid - "
                f"content: {bool(content)}, "
                f"file: {bool(uploaded_file)}"
            )

            # Prevent empty messages
            if not content and not uploaded_file:
                return JsonResponse({
                    'success': False,
                    'error': 'Cannot send empty message.'
                }, status=400)

            try:

                # =====================================================
                # GET ENCRYPTION KEYS
                # =====================================================
                try:
                    recipient_keys = UserEncryptionKeys.objects.get(
                        user=user
                    )

                    sender_keys = UserEncryptionKeys.objects.get(
                        user=request.user
                    )

                except UserEncryptionKeys.DoesNotExist:

                    logger.warning(
                        'Encryption keys not found, creating...'
                    )

                    create_user_encryption_keys(
                        AuthUser,
                        request.user,
                        True
                    )

                    create_user_encryption_keys(
                        AuthUser,
                        user,
                        True
                    )

                    sender_keys = UserEncryptionKeys.objects.get(
                        user=request.user
                    )

                    recipient_keys = UserEncryptionKeys.objects.get(
                        user=user
                    )

                # =====================================================
                # VALIDATE SIGNING KEY
                # =====================================================
                if not sender_keys.signing_private_key:

                    logger.error(
                        'Sender signing private key missing'
                    )

                    return JsonResponse({
                        'success': False,
                        'error': 'Signing key missing.'
                    }, status=500)

                # =====================================================
                # GET CONVERSATION KEY
                # =====================================================
                conversation_key = get_or_create_conversation_key(
                    request.user,
                    user
                )

                # =====================================================
                # ENCRYPT + SIGN MESSAGE
                # =====================================================
                encrypted_content = None
                signature = None

                if content:

                    encrypted_content = encrypt_message(
                        content,
                        conversation_key.encode()
                    )

                    signature = sign_message(
                        content,
                        sender_keys.signing_private_key
                    )

                    logger.info(
                        'Message encrypted and signed'
                    )

                # =====================================================
                # CREATE MESSAGE
                # =====================================================
                new_message = Message.objects.create(
                    sender=request.user,
                    recipient=user,
                    content=encrypted_content,
                    signature=signature,
                    file=uploaded_file
                )

                logger.info(
                    f"✅ Message created: {new_message.id}"
                )

                # =====================================================
                # START ASYNC FILE PROCESSING
                # =====================================================
                if uploaded_file:

                    try:
                        from .tasks import process_message_file

                        logger.info(
                            f"🚀 Starting Celery task "
                            f"for message {new_message.id}"
                        )

                        process_message_file.delay(
                            message_id=new_message.id,
                            sender_id=request.user.id,
                            recipient_id=user.id
                        )

                        logger.info(
                            f"✅ Celery task queued "
                            f"for message {new_message.id}"
                        )

                    except Exception as celery_error:

                        logger.error(
                            f"❌ Failed to queue Celery task: "
                            f"{str(celery_error)}",
                            exc_info=True
                        )

                # =====================================================
                # CREATE NOTIFICATION
                # =====================================================
                try:

                    if content:
                        message_preview = content[:100]

                    elif uploaded_file:
                        message_preview = (
                            f"📎 {uploaded_file.name}"
                        )

                    else:
                        message_preview = "Sent a message"

                    notification_data = (
                        create_message_notification(
                            sender_username=request.user.username,
                            sender_id=request.user.id,
                            recipient_user_id=user.id,
                            message_preview=message_preview,
                            message_id=new_message.id
                        )
                    )

                    logger.info(
                        f"🔔 Notification created "
                        f"for message {new_message.id}"
                    )

                    send_notification_sync(
                        user.id,
                        notification_data
                    )

                    logger.info(
                        f"✅ Notification sent to "
                        f"{user.username}"
                    )

                except Exception as notification_error:

                    logger.warning(
                        f"⚠️ Notification failed: "
                        f"{notification_error}"
                    )

                # =====================================================
                # PREPARE RESPONSE
                # =====================================================
                response_data = {
                    'success': True,
                    'message_id': new_message.id,
                    'sender': request.user.username,
                    'recipient': user.username,
                    'content': content,
                    'timestamp': (
                        new_message.timestamp.isoformat()
                    ),

                    'file_url': (
                        new_message.file.url
                        if new_message.file else None
                    ),

                    'has_file': bool(uploaded_file),

                    'processing': bool(uploaded_file)
                }

                logger.info(
                    f"Returning JSON response "
                    f"for message {new_message.id}"
                )

                return JsonResponse(response_data)

            except Exception as e:

                logger.error(
                    f'Error processing message: {str(e)}',
                    exc_info=True
                )

                return JsonResponse({
                    'success': False,
                    'error': f'Server error: {str(e)}'
                }, status=500)

        else:

            logger.error(
                f'Form validation errors: {form.errors}'
            )

            return JsonResponse({
                'success': False,
                'error': 'Invalid form data.',
                'errors': dict(form.errors)
            }, status=400)

    # =====================================================
    # HANDLE GET REQUESTS
    # =====================================================
    form = MessageForm(
        initial={'recipient': user.username}
    )

    try:
        user_keys = UserEncryptionKeys.objects.get(
            user=request.user
        )

    except UserEncryptionKeys.DoesNotExist:

        logger.error(
            'Encryption keys not found for current user'
        )

        return HttpResponse(
            'Your encryption keys not found.',
            status=404
        )

    # =====================================================
    # DECRYPT MESSAGES
    # =====================================================
    decrypted_messages = []

    for msg in messages_qs:

        conversation_key = get_or_create_conversation_key(
            request.user,
            msg.sender if msg.sender != request.user
            else msg.recipient
        )

        decrypted_content = None

        if msg.content:

            decrypted_content = decrypt_message(
                msg.content,
                conversation_key.encode()
            )

            if decrypted_content is None:

                logger.warning(
                    f'Failed to decrypt message {msg.id}'
                )

                decrypted_content = "[Decryption Failed]"

        signature_valid = False

        if (
            decrypted_content and
            decrypted_content != "[Decryption Failed]" and
            msg.signature and
            hasattr(msg.sender, 'encryption_keys')
        ):

            if msg.sender.encryption_keys.signing_public_key:

                signature_valid = verify_message(
                    decrypted_content,
                    msg.signature,
                    msg.sender.encryption_keys.signing_public_key
                )

        decrypted_messages.append({
            'id': msg.id,
            'sender': msg.sender,
            'content': decrypted_content,
            'timestamp': msg.timestamp,
            'signature_valid': signature_valid,
            'file_url': (
                msg.file.url if msg.file else None
            )
        })

    # =====================================================
    # RENDER TEMPLATE
    # =====================================================
    return render(request, 'user_messages.html', {
        'messages': decrypted_messages,
        'form': form,
        'recipient': user
    })

#----------------------------------------------------------------------------------------
#
#
#----------------------------------------------------------------------------------------




#----------------------------------------------------------------------------------------
#integration for push notification when messages are sent supporting the new view function
#
#----------------------------------------------------------------------------------------

# ========================================
# API VIEWS (Add to views.py) websocket based notification system no fcm in this part
# ========================================

@login_required
def get_notifications_api(request):
    """Get notifications for current user"""
    notifications = get_notifications(request.user.id)
    unread_count = get_unread_count(request.user.id)
    
    return JsonResponse({
        'success': True,
        'notifications': notifications,
        'unread_count': unread_count
    })
 
 
@login_required
def mark_notifications_read(request):
    """Mark all notifications as read"""
    clear_unread_count(request.user.id)
    
    return JsonResponse({
        'success': True,
        'message': 'Notifications marked as read'
    })

@login_required
@require_http_methods(["POST"])
def clear_notifications_api(request):
    """Clear all notifications"""
    cache_key = f'notifications:{request.user.id}'
    cache.delete(cache_key)
    clear_unread_count(request.user.id)
    
    return JsonResponse({
        'success': True,
        'message': 'Notifications cleared'
    })

# ========================================
# API VIEWS (Add to views.py) websocket based notification system no fcm in this part
# ========================================

#----------------------------------------------------------------------------------------
#integration for push notification when messages are sent supporting the new view function
#
#----------------------------------------------------------------------------------------



@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def search_user_message(request):
    query = request.GET.get('q')
    if query:
        users = AuthUser.objects.filter(username__icontains=query)
    else:
        users = AuthUser.objects.none()
    
    return render(request, 'search_user_message.html', {'users': users})


@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
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




#new update for message sending message deletion logic
#____________________________________________________

@login_required
@require_POST
def delete_messages_view(request, username):
    """
    Delete messages and related files.
    Also notify both users via WebSocket.
    """

    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({
            'success': False,
            'error': 'Invalid request'
        }, status=400)

    message_ids = request.POST.getlist('message_ids[]')

    if not message_ids:
        return JsonResponse({
            'success': False,
            'error': 'No messages selected.'
        })

    # Get recipient
    recipient = get_object_or_404(
        AuthUser,
        username=username
    )

    # Only allow sender to delete own messages
    messages = Message.objects.filter(
        id__in=message_ids,
        sender=request.user,
        recipient=recipient
    )

    if not messages.exists():
        return JsonResponse({
            'success': False,
            'error': 'Unauthorized or invalid messages.'
        })

    # ==========================================
    # DELETE MESSAGES INDIVIDUALLY
    # ==========================================
    deleted_ids = []

    for message in messages:

        deleted_ids.append(message.id)

        logger.info(
            f"Deleting message {message.id} "
            f"from {request.user.username}"
        )

        # This triggers signals.py
        message.delete()

    # ==========================================
    # WEBSOCKET BROADCAST
    # ==========================================
    try:

        channel_layer = get_channel_layer()

        sorted_ids = sorted([
            request.user.id,
            recipient.id
        ])

        room_group_name = (
            f'chat_{sorted_ids[0]}_{sorted_ids[1]}'
        )

        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'chat_message_delete',

                'message_ids': deleted_ids,

                'sender': request.user.username
            }
        )

        logger.info(
            f"Broadcast delete event "
            f"for messages {deleted_ids}"
        )

    except Exception as e:

        logger.error(
            f"WebSocket delete broadcast failed: {e}",
            exc_info=True
        )

    return JsonResponse({
        'success': True,
        'deleted_ids': deleted_ids
    })


#____________________________________________________
#new update for message sending message deletion logic


#@login_required
@cache_control(public=True, max_age=3600, s_maxage=7200, must_revalidate=True)
def stranger_chat_view(request):
    from django_countries import countries
    return render(request, 'only_message/stranger_chat.html', {
        'country_list': list(countries),
    })


