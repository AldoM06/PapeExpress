from django import forms
from .models import FiguraFomy


class FiguraFomyForm(forms.ModelForm):
    class Meta:
        model  = FiguraFomy
        fields = [
            'nombre', 'descripcion', 'imagen_referencia',
            'etapa_actual', 'responsable',
            'cantidad_planificada', 'cantidad_disponible',
            'costo_estimado', 'precio_venta', 'tiene_fomy', 'notas',
            'archivo_studio3', 'archivo_instrucciones_pdf', 'archivo_instrucciones_word',
        ]
        widgets = {
            'nombre':      forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'etapa_actual': forms.Select(attrs={'class': 'form-select'}),
            'responsable':  forms.Select(attrs={'class': 'form-select'}),
            'cantidad_planificada': forms.NumberInput(attrs={'class': 'form-control'}),
            'cantidad_disponible':  forms.NumberInput(attrs={'class': 'form-control'}),
            'costo_estimado': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'precio_venta':   forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'archivo_studio3':            'Plantilla Studio3 (.studio3)',
            'archivo_instrucciones_pdf':  'Instrucciones PDF',
            'archivo_instrucciones_word': 'Instrucciones Word (.docx)',
            'imagen_referencia':          'Imagen de referencia',
        }
