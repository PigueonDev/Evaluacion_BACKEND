from django import forms

from institucional.models import Delegacion, Funcionario
from laserena.permisos import perfil_de_ambito
from laserena.rut import normalizar_rut
from organizaciones.models import OrganizacionComunitaria
from servicios.models import Periodo

from .models import Ausencia, BeneficioNino, Carta

FECHA = {"type": "date", "class": "form-control"}


def _estilar(form):
	for campo in form.fields.values():
		widget = campo.widget
		if isinstance(widget, forms.DateInput):
			widget.attrs.update(FECHA)
			widget.format = "%Y-%m-%d"
			campo.input_formats = ["%Y-%m-%d"]
		else:
			widget.attrs.setdefault("class", "form-select" if isinstance(widget, forms.Select) else "form-control")
		campo.label = campo.label[:1].upper() + campo.label[1:]


class _FormularioConAmbito(forms.ModelForm):
	"""Fija la delegación al ámbito del usuario: solo el Administrador elige delegación."""

	def __init__(self, *args, usuario=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.perfil = perfil_de_ambito(usuario)
		self.fields["delegacion"].queryset = Delegacion.objects.filter(activa=True)
		self.fields["organizacion"].queryset = OrganizacionComunitaria.objects.exclude(estado="inactiva")
		self.fields["organizacion"].required = False
		if self.perfil is not None:
			self.fields.pop("delegacion")
			self.instance.delegacion = self.perfil.delegacion
		_estilar(self)


class CartaForm(_FormularioConAmbito):
	class Meta:
		model = Carta
		fields = [
			"fecha_ingreso", "tipo", "remitente", "contacto_remitente", "asunto", "detalle", "delegacion",
			"organizacion", "derivada_a", "estado", "plazo_respuesta", "respuesta", "fecha_respuesta",
		]
		widgets = {
			"fecha_ingreso": forms.DateInput(), "plazo_respuesta": forms.DateInput(), "fecha_respuesta": forms.DateInput(),
			"detalle": forms.Textarea(attrs={"rows": 3}), "respuesta": forms.Textarea(attrs={"rows": 3}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		funcionarios = Funcionario.objects.filter(activo=True).select_related("delegacion")
		if self.perfil is not None:
			funcionarios = funcionarios.filter(delegacion=self.perfil.delegacion)
		self.fields["derivada_a"].queryset = funcionarios
		self.fields["derivada_a"].label_from_instance = lambda f: f"{f.nombre_completo} · {f.delegacion}"


class CartaSeguimientoForm(forms.ModelForm):
	"""El Administrativo solo actualiza el estado y la respuesta de las cartas derivadas a él."""

	class Meta:
		model = Carta
		fields = ["estado", "respuesta", "fecha_respuesta"]
		widgets = {"fecha_respuesta": forms.DateInput(), "respuesta": forms.Textarea(attrs={"rows": 4})}

	def __init__(self, *args, usuario=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["estado"].choices = [c for c in Carta.ESTADOS if c[0] in ("derivada", "en_respuesta", "respondida")]
		_estilar(self)


class BeneficioForm(_FormularioConAmbito):
	class Meta:
		model = BeneficioNino
		fields = [
			"rut_nino", "nombre_nino", "fecha_nacimiento", "sexo", "tipo", "descripcion",
			"apoderado", "telefono_apoderado", "delegacion", "organizacion", "estado", "fecha_entrega",
		]
		widgets = {"fecha_nacimiento": forms.DateInput(), "fecha_entrega": forms.DateInput()}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["rut_nino"].widget.attrs.update({"placeholder": "12.345.678-5", "autocomplete": "off"})
		self.fields["rut_nino"].help_text = "Se valida el dígito verificador. Un niño o niña recibe un solo beneficio en todo el municipio."

	def clean_rut_nino(self):
		rut = normalizar_rut(self.cleaned_data["rut_nino"])
		repetido = BeneficioNino.objects.filter(rut_nino=rut).exclude(pk=self.instance.pk).select_related("delegacion").first()
		if repetido:
			raise forms.ValidationError(f"Ese RUT ya tiene un beneficio registrado en la delegación {repetido.delegacion}.")
		return rut


class AusenciaForm(forms.ModelForm):
	class Meta:
		model = Ausencia
		fields = ["funcionario", "periodo", "fecha_inicio", "fecha_termino", "motivo", "observacion"]
		widgets = {"fecha_inicio": forms.DateInput(), "fecha_termino": forms.DateInput()}

	def __init__(self, *args, usuario=None, **kwargs):
		super().__init__(*args, **kwargs)
		perfil = perfil_de_ambito(usuario)
		funcionarios = Funcionario.objects.filter(activo=True).select_related("delegacion", "cargo")
		if perfil is not None:
			funcionarios = funcionarios.filter(delegacion=perfil.delegacion)
		self.fields["funcionario"].queryset = funcionarios
		self.fields["funcionario"].label_from_instance = lambda f: f"{f.nombre_completo} · {f.cargo} · {f.delegacion}"
		self.fields["periodo"].queryset = Periodo.objects.filter(estado="abierto")
		periodo = self.fields["periodo"].queryset.first()
		if periodo and not self.is_bound:
			self.initial.setdefault("periodo", periodo.pk)
		_estilar(self)
