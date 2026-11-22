from allauth.account.forms import LoginForm
from django import forms

class CustomLoginForm(LoginForm):
    login = forms.CharField(
        label="Phone or Email",
        widget=forms.TextInput(attrs={
            'placeholder': 'Phone Number or Email',
            'autofocus': 'autofocus',
            'autocomplete': 'username',
        })
    )