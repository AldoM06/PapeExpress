from django import forms
from .models import MensajeContacto


class ContactoForm(forms.ModelForm):
    class Meta:
        model = MensajeContacto
        fields = ('nombre', 'email', 'telefono', 'asunto', 'mensaje')
        widgets = {
            'nombre':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tu nombre completo'}),
            'email':    forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@ejemplo.com'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '(55) 1234-5678'}),
            'asunto':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Asunto del mensaje'}),
            'mensaje':  forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Escribe tu mensaje aquí...'}),
        }
        labels = {
            'nombre': 'Nombre completo',
            'email': 'Correo electrónico',
            'telefono': 'Teléfono (opcional)',
            'asunto': 'Asunto',
            'mensaje': 'Mensaje',
        }
