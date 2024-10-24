# nmk_chain/forms.py

from django import forms

class SendMoneyForm(forms.Form):
    username = forms.CharField(max_length=25)
    amount = forms.DecimalField(max_digits=10, decimal_places=2)

class BuyForm(forms.Form):
    amount = forms.DecimalField(max_digits=10, decimal_places=2)
