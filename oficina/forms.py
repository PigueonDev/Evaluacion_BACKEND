from django import forms

from django.utils import timezone

from institucional.models import Delegacion, Funcionario, UnidadMunicipal
from laserena.permisos import perfil_de_ambito
from laserena.rut import normalizar_rut
from organizaciones.models import OrganizacionComunitaria
from servicios.models import Periodo

from .models import Ausencia, BeneficioNino, Carta, Reconocimiento

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
			"fecha_ingreso", "numero_oficina_partes", "destinatario", "tipo", "remitente", "contacto_remitente", "asunto", "detalle",
			"fecha_actividad", "delegacion", "organizacion", "encargado_seguimiento", "pronunciamiento", "derivada_a", "derivada_a_unidad",
			"estado", "resolucion", "plazo_respuesta", "respuesta", "fecha_respuesta",
		]
		widgets = {
			"fecha_ingreso": forms.DateInput(), "plazo_respuesta": forms.DateInput(), "fecha_respuesta": forms.DateInput(), "fecha_actividad": forms.DateInput(),
			"detalle": forms.Textarea(attrs={"rows": 3}), "respuesta": forms.Textarea(attrs={"rows": 3}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		funcionarios = Funcionario.objects.filter(activo=True).select_related("delegacion")
		if self.perfil is not None:
			funcionarios = funcionarios.filter(delegacion=self.perfil.delegacion)
		self.fields["derivada_a"].queryset = funcionarios
		self.fields["derivada_a"].label_from_instance = lambda f: f"{f.nombre_completo} · {f.delegacion}"
		unidades = UnidadMunicipal.objects.filter(activa=True)
		for nombre in ("encargado_seguimiento", "derivada_a_unidad"):
			self.fields[nombre].queryset = unidades
		self.fields["numero_oficina_partes"].help_text = "Número que asigna la Oficina de Partes municipal. El folio OP-AAAA-NNNN del SGR se genera solo."
		self.fields["resolucion"].help_text = "Estado del tubo de cartas de la matriz. Al responder o archivar pasa a Finalizada si sigue En proceso."
		_opcionales_con_valor_actual(self, "destinatario", "pronunciamiento", "resolucion")

	def clean(self):
		return _completar_con_valor_actual(self, super().clean())


def _opcionales_con_valor_actual(form, *campos):
	"""Campos de la matriz que, si no vienen en el envío, conservan el valor de la carta (o su valor por defecto)."""
	form.campos_con_valor_actual = campos
	for nombre in campos:
		form.fields[nombre].required = False


def _completar_con_valor_actual(form, cleaned):
	for nombre in form.campos_con_valor_actual:
		if not cleaned.get(nombre):
			cleaned[nombre] = getattr(form.instance, nombre)
	return cleaned


class CartaSeguimientoForm(forms.ModelForm):
	"""El Administrativo solo actualiza el estado y la respuesta de las cartas derivadas a él."""

	class Meta:
		model = Carta
		fields = ["estado", "resolucion", "respuesta", "fecha_respuesta"]
		widgets = {"fecha_respuesta": forms.DateInput(), "respuesta": forms.Textarea(attrs={"rows": 4})}

	def __init__(self, *args, usuario=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["estado"].choices = [c for c in Carta.ESTADOS if c[0] in ("derivada", "en_respuesta", "respondida")]
		_estilar(self)
		_opcionales_con_valor_actual(self, "resolucion")

	def clean(self):
		return _completar_con_valor_actual(self, super().clean())


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


class ReconocimientoForm(forms.ModelForm):
	"""El delegado registra felicitaciones y reclamos escritos de su delegación."""

	class Meta:
		model = Reconocimiento
		fields = ["tipo", "funcionario", "periodo", "fecha", "usuario_nombre", "contacto", "ubicacion", "situacion", "medio", "respaldo"]
		widgets = {
			"fecha": forms.DateInput(),
			"situacion": forms.Textarea(attrs={"rows": 3}),
			"respaldo": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,image/png,image/jpeg,image/webp"}),
		}

	def __init__(self, *args, usuario=None, **kwargs):
		super().__init__(*args, **kwargs)
		perfil = perfil_de_ambito(usuario)
		funcionarios = Funcionario.objects.filter(activo=True).select_related("delegacion", "cargo")
		if perfil is not None:
			funcionarios = funcionarios.filter(delegacion=perfil.delegacion).exclude(pk=perfil.pk)
		self.fields["funcionario"].queryset = funcionarios
		self.fields["funcionario"].label_from_instance = lambda f: f"{f.nombre_completo} · {f.cargo} · {f.delegacion}"
		self.fields["periodo"].queryset = Periodo.objects.filter(estado="abierto")
		periodo = self.fields["periodo"].queryset.first()
		if not self.is_bound:
			self.initial.setdefault("fecha", timezone.localdate())
			if periodo:
				self.initial.setdefault("periodo", periodo.pk)
		self.fields["medio"].help_text = "La matriz solo acepta felicitaciones y reclamos por escrito."
		self.fields["situacion"].help_text = "Los reclamos deben referirse a la atención del funcionario."
		self.fields["respaldo"].required = False
		self.fields["respaldo"].help_text = "Obligatorio en una felicitación: es el respaldo formal del delegado. PDF, JPG, PNG o WebP."
		_estilar(self)
