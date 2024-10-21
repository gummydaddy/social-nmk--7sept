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
    initial_data = {}
    recipient_username = request.GET.get('recipient')
    if recipient_username:
        initial_data['recipient'] = recipient_username

    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            recipient_username = form.cleaned_data['recipient']
            content = form.cleaned_data['content']
            try:
                recipient = AuthUser.objects.get(username=recipient_username)
            except AuthUser.DoesNotExist:
                messages.error(request, 'Recipient user does not exist.')
                return redirect('only_message:send_message_view')

            try:
                recipient_keys = UserEncryptionKeys.objects.get(user=recipient)
                sender_keys = UserEncryptionKeys.objects.get(user=request.user)
            except UserEncryptionKeys.DoesNotExist:
                # If keys don't exist, create them
                create_user_encryption_keys(sender=AuthUser, instance=request.user, created=True)
                create_user_encryption_keys(sender=AuthUser, instance=recipient, created=True)
                recipient_keys = UserEncryptionKeys.objects.get(user=recipient)
                sender_keys = UserEncryptionKeys.objects.get(user=request.user)

            if not sender_keys.signing_private_key:
                logger.error(f'Sender signing private key is missing for user {request.user.username}.')
                messages.error(request, 'An error occurred while sending the message. Please try again.')
                return redirect('only_message:send_message_view')

            conversation_key = get_or_create_conversation_key(request.user, recipient)
            
            try:
                encrypted_content = encrypt_message(content, conversation_key.encode())
                signature = sign_message(content, sender_keys.signing_private_key)
            except Exception as e:
                logger.error(f'Error during message encryption or signing: {str(e)}')
                messages.error(request, 'An error occurred while sending the message. Please try again.')
                return redirect('only_message:send_message_view')

            Message.objects.create(
                sender=request.user, 
                recipient=recipient, 
                content=encrypted_content,
                signature=signature
            )

            messages.success(request, 'Message sent successfully.')
            return redirect('only_message:message_list_view')
        else:
            messages.error(request, 'There was an error sending your message. Please try again.')
    else:
        form = MessageForm(initial=initial_data)
    return render(request, 'send_message.html', {'form': form})


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


# @login_required
# def user_messages_view(request, username):
#     user = get_object_or_404(AuthUser, username=username)
#    # Return the newest message at the bottom of the message list
#     messages = Message.objects.filter(
#         (Q(sender=request.user) & Q(recipient=user)) | (Q(sender=user) & Q(recipient=request.user))
#     ).order_by('-timestamp')  # Order by timestamp in descending order


    
#     if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
#         message_data = [{
#             'id': msg.id,
#             'content': msg.content,  # Ensure this is decrypted if necessary
#             'sender': msg.sender.username,
#             'timestamp': msg.timestamp.isoformat()
#         } for msg in messages]
#         return JsonResponse({'messages': message_data})

#     if request.method == 'POST':
#         form = MessageForm(request.POST)
#         if form.is_valid():
#             content = form.cleaned_data['content']
#             try:
#                 recipient_keys = UserEncryptionKeys.objects.get(user=user)
#                 sender_keys = UserEncryptionKeys.objects.get(user=request.user)
#             except UserEncryptionKeys.DoesNotExist:
#                 logger.error('User encryption keys not found.')
#                 return HttpResponse('User encryption keys not found.', status=404)

#             if not sender_keys.signing_private_key:
#                 logger.error(f'Sender signing private key is missing for user {request.user.username}.')
#                 return HttpResponse('Sender signing private key is missing.', status=500)

#             conversation_key = get_or_create_conversation_key(request.user, user)

#             try:
#                 encrypted_content = encrypt_message(content, conversation_key.encode())
#                 signature = sign_message(content, sender_keys.signing_private_key)
#             except Exception as e:
#                 logger.error(f'Error during message encryption or signing: {e}')
#                 return HttpResponse('Error during message encryption or signing.', status=500)

#             Message.objects.create(
#                 sender=request.user, 
#                 recipient=user, 
#                 content=encrypted_content,
#                 signature=signature
#             )

#             return redirect('only_message:user_messages_view', username=user.username)
#     else:
#         form = MessageForm(initial={'recipient': user.username})

#     try:
#         user_keys = UserEncryptionKeys.objects.get(user=request.user)
#     except UserEncryptionKeys.DoesNotExist:
#         logger.error('Your encryption keys not found.')
#         return HttpResponse('Your encryption keys not found.', status=404)

#     decrypted_messages = []
#     for msg in messages:
#         conversation_key = get_or_create_conversation_key(request.user, msg.sender if msg.sender != request.user else msg.recipient)
#         decrypted_content = decrypt_message(
#             msg.content,
#             conversation_key.encode()
#         )
#         if decrypted_content is None:
#             logger.warning(f'Failed to decrypt message {msg.id}.')
#             continue

#         signature_valid = verify_message(
#             decrypted_content,
#             msg.signature,
#             msg.sender.encryption_keys.signing_public_key
#         )
#         decrypted_messages.append({
#             'sender': msg.sender,
#             'content': decrypted_content,
#             'timestamp': msg.timestamp,
#             'signature_valid': signature_valid,
#         })

#     return render(request, 'user_messages.html', {'messages': decrypted_messages, 'form': form, 'recipient': user})


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
                encrypted_file = None
                if uploaded_file:
                    # Optional: Encrypt the file content here
                    encrypted_file = uploaded_file  # Save file as-is or encrypt it
            except Exception as e:
                logger.error(f'Error during message encryption or signing: {e}')
                return HttpResponse('Error during message encryption or signing.', status=500)

            Message.objects.create(
                sender=request.user, 
                recipient=user, 
                content=encrypted_content,
                signature=signature,
                file=encrypted_file  # Save the uploaded file
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