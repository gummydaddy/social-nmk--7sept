# nmk_chain/views.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from .forms import SendMoneyForm, BuyForm
from .models import Block
from only_card.models import AuthUser, CustomGroup, CustomGroupAdmin, RegistrationForm
from .utils import send_money, get_balance, get_blockchain, sync_blockchain
from django.utils import timezone



@login_required
def transaction(request):
    if request.method == 'POST':
        form = SendMoneyForm(request.POST)
        if form.is_valid():
            sender = request.user.username
            recipient = form.cleaned_data['username']
            amount = form.cleaned_data['amount']
            try:
                send_money(sender, recipient, amount)
                messages.success(request, "Money Sent!")
            except Exception as e:
                messages.error(request, str(e))
            return redirect('transaction')
    else:
        form = SendMoneyForm()
    balance = get_balance(request.user.username)
    return render(request, 'transaction.html', {'form': form, 'balance': balance})

@login_required
def buy(request):
    if request.method == 'POST':
        form = BuyForm(request.POST)
        if form.is_valid():
            try:
                send_money("BANK", request.user.username, form.cleaned_data['amount'])
                messages.success(request, "Purchase Successful!")
            except Exception as e:
                messages.error(request, str(e))
            return redirect('dashboard')
    else:
        form = BuyForm()
    balance = get_balance(request.user.username)
    return render(request, 'buy.html', {'form': form, 'balance': balance})

@login_required
def dashboard(request):
    balance = get_balance(request.user.username)
    blockchain = get_blockchain()
    current_time = timezone.now()
    return render(request, 'dashboard.html', {'balance': balance, 'blockchain': blockchain.chain, 'ct': current_time})

def index(request):
    return render(request, 'index.html')

