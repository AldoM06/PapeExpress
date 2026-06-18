from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Usuario


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Usuario o correo'}),
        label='Usuario'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña'}),
        label='Contraseña'
    )


class RegistroClienteForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(required=True, widget=forms.TextInput(attrs={'class': 'form-control'}), label='Nombre')
    last_name = forms.CharField(required=True, widget=forms.TextInput(attrs={'class': 'form-control'}), label='Apellido')
    empresa = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label='Empresa')
    telefono = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}), label='Teléfono')

    class Meta:
        model = Usuario
        fields = ('username', 'first_name', 'last_name', 'email', 'empresa', 'telefono', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.rol = 'cliente'
        if commit:
            user.save()
        return user
