from django import forms

from .models import OrganizacionComunitaria


class OrganizacionForm(forms.ModelForm):
	class Meta:
		model = OrganizacionComunitaria
		fields = [
			"nombre", "tipo", "territorio", "domicilio", "socios_activos",
			"fecha_constitucion", "numero_registro_pj", "fecha_inscripcion", "registro_directiva",
		]
		widgets = {
			"nombre": forms.TextInput(attrs={"class": "form-control"}),
			"tipo": forms.Select(attrs={"class": "form-select"}),
			"territorio": forms.Select(attrs={"class": "form-select"}),
			"domicilio": forms.TextInput(attrs={"class": "form-control"}),
			"socios_activos": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
			"fecha_constitucion": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
			"numero_registro_pj": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
			"fecha_inscripcion": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
			"registro_directiva": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		for nombre in ("fecha_constitucion", "fecha_inscripcion"):
			self.fields[nombre].input_formats = ["%Y-%m-%d"]
		for campo in self.fields.values():
			campo.label = campo.label[:1].upper() + campo.label[1:]

	def clean_nombre(self):
		nombre = " ".join(self.cleaned_data["nombre"].split()).upper()
		repetidas = OrganizacionComunitaria.objects.filter(nombre__iexact=nombre)
		if self.instance.pk:
			repetidas = repetidas.exclude(pk=self.instance.pk)
		if repetidas.exists():
			raise forms.ValidationError("Ya existe una organización con ese nombre.")
		return nombre
