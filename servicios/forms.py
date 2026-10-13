from django import forms
from django.core.exceptions import ValidationError

from institucional.models import Delegacion, Funcionario

from .models import MAXIMO_GESTIONES_POR_CASO, TELEFONO_ACTIVIDAD, Actividad, Caso, Compromiso, Gestion, ItemMedicion, Periodo, Servicio


class ActividadForm(forms.ModelForm):
	funcionario = forms.ModelChoiceField(
		label="Funcionario",
		queryset=Funcionario.objects.none(),
		required=False,
		widget=forms.Select(attrs={"class": "form-select"}),
	)

	class Meta:
		model = Actividad
		fields = ["fecha", "periodo", "item", "servicio", "descripcion", "accion", "contacto", "telefono", "compromiso"]
		labels = {
			"fecha": "Fecha",
			"periodo": "Período",
			"item": "Ítem de medición",
			"servicio": "Servicio",
			"descripcion": "Actividad o problema",
			"accion": "Acción realizada",
			"contacto": "Contacto",
			"telefono": "Teléfono",
			"compromiso": "Vínculo con la agenda",
		}
		help_texts = {
			"telefono": "Opcional. Solo números, espacios o guiones.",
			"compromiso": "Opcional. Asocia la actividad a un compromiso ya publicado en la misma delegación.",
			"servicio": "Opcional.",
		}
		widgets = {
			"fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
			"periodo": forms.Select(attrs={"class": "form-select"}),
			"item": forms.Select(attrs={"class": "form-select"}),
			"servicio": forms.Select(attrs={"class": "form-select"}),
			"descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
			"accion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
			"contacto": forms.TextInput(attrs={"class": "form-control"}),
			"telefono": forms.TextInput(attrs={"class": "form-control", "inputmode": "tel"}),
			"compromiso": forms.Select(attrs={"class": "form-select"}),
		}

	def __init__(self, *args, funcionario=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.funcionario_fijo = funcionario
		self.fields["fecha"].input_formats = ["%Y-%m-%d"]
		self.fields["periodo"].queryset = Periodo.objects.filter(estado="abierto").order_by("-fecha_inicio")
		self.fields["item"].queryset = ItemMedicion.objects.filter(activo=True)
		self.fields["servicio"].queryset = Servicio.objects.filter(activo=True)
		self.fields["servicio"].required = False
		self.fields["contacto"].required = False
		self.fields["telefono"].required = False
		self.fields["compromiso"].required = False
		compromisos = Compromiso.objects.filter(activo=True).select_related("delegacion")
		if funcionario is not None:
			compromisos = compromisos.filter(delegacion=funcionario.delegacion)
			self.fields.pop("funcionario")
		elif self.instance.pk:
			self.fields.pop("funcionario")
		else:
			self.fields["funcionario"].queryset = Funcionario.objects.filter(activo=True).select_related("delegacion")
			self.fields["funcionario"].required = True
		self.fields["compromiso"].queryset = compromisos
		for campo in self.fields.values():
			campo.error_messages["required"] = "Este campo es obligatorio."

	def clean_telefono(self):
		telefono = (self.cleaned_data.get("telefono") or "").strip()
		if telefono and not TELEFONO_ACTIVIDAD.match(telefono):
			raise ValidationError("Usa solo números, espacios o guiones, con un largo de 8 a 15 dígitos.")
		return telefono

	def clean(self):
		cleaned = super().clean()
		funcionario = self.funcionario_fijo or cleaned.get("funcionario") or getattr(self.instance, "funcionario", None)
		compromiso = cleaned.get("compromiso")
		if compromiso and funcionario and compromiso.delegacion_id != funcionario.delegacion_id:
			self.add_error("compromiso", "El compromiso debe ser de la misma delegación del funcionario.")
		return cleaned


class CasoForm(forms.ModelForm):
	class Meta:
		model = Caso
		fields = ["identificacion", "nombre", "delegacion", "observacion"]
		labels = {
			"identificacion": "Identificación principal",
			"nombre": "Nombre de la persona usuaria",
			"delegacion": "Delegación",
			"observacion": "Observación",
		}
		help_texts = {
			"identificacion": "Se registra una sola vez. Las gestiones se asocian a este caso y no repiten el identificador.",
		}
		widgets = {
			"identificacion": forms.TextInput(attrs={"class": "form-control"}),
			"nombre": forms.TextInput(attrs={"class": "form-control"}),
			"delegacion": forms.Select(attrs={"class": "form-select"}),
			"observacion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
		}

	def __init__(self, *args, delegacion=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["observacion"].required = False
		if delegacion is not None:
			self.fields["delegacion"].queryset = Delegacion.objects.filter(pk=delegacion.pk, activa=True)
			self.fields["delegacion"].initial = delegacion
		else:
			self.fields["delegacion"].queryset = Delegacion.objects.filter(activa=True)
		for campo in self.fields.values():
			campo.error_messages["required"] = "Este campo es obligatorio."

	def clean_identificacion(self):
		return (self.cleaned_data.get("identificacion") or "").strip()


class GestionForm(forms.ModelForm):
	class Meta:
		model = Gestion
		fields = ["numero", "fecha", "descripcion", "actividad"]
		labels = {
			"numero": "Número de gestión",
			"fecha": "Fecha",
			"descripcion": "Descripción de la atención",
			"actividad": "Actividad asociada",
		}
		help_texts = {
			"actividad": "Opcional. Una actividad solo puede contarse en una gestión.",
		}
		widgets = {
			"numero": forms.Select(attrs={"class": "form-select"}),
			"fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
			"descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
			"actividad": forms.Select(attrs={"class": "form-select"}),
		}

	def __init__(self, *args, caso=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.caso = caso or self.instance.caso
		self.fields["fecha"].input_formats = ["%Y-%m-%d"]
		self.fields["actividad"].required = False
		ocupados = Gestion.objects.filter(caso=self.caso)
		if self.instance.pk:
			ocupados = ocupados.exclude(pk=self.instance.pk)
		numeros_libres = [n for n in range(1, MAXIMO_GESTIONES_POR_CASO + 1) if not ocupados.filter(numero=n).exists()]
		if self.instance.pk and self.instance.numero not in numeros_libres:
			numeros_libres.append(self.instance.numero)
			numeros_libres.sort()
		self.fields["numero"].widget = forms.Select(
			attrs={"class": "form-select"},
			choices=[(n, f"Gestión {n}") for n in numeros_libres],
		)
		actividades = Actividad.objects.filter(funcionario__delegacion=self.caso.delegacion).exclude(estado="anulada")
		usadas = Gestion.objects.exclude(actividad__isnull=True)
		if self.instance.pk:
			usadas = usadas.exclude(pk=self.instance.pk)
		self.fields["actividad"].queryset = actividades.exclude(pk__in=usadas.values("actividad_id"))
		self.numeros_libres = numeros_libres
		for campo in self.fields.values():
			campo.error_messages["required"] = "Este campo es obligatorio."

	def clean_numero(self):
		numero = self.cleaned_data.get("numero")
		if numero not in self.numeros_libres:
			raise ValidationError("Ese número de gestión no está disponible.")
		return numero

	def clean(self):
		cleaned = super().clean()
		if not self.caso or self.errors:
			return cleaned
		temporal = Gestion(
			pk=self.instance.pk,
			caso=self.caso,
			numero=cleaned.get("numero") or 0,
			fecha=cleaned.get("fecha"),
			descripcion=cleaned.get("descripcion") or "",
			actividad=cleaned.get("actividad"),
		)
		try:
			temporal.clean()
		except ValidationError as error:
			self._update_errors(error)
		return cleaned

	def save(self, commit=True):
		gestion = super().save(commit=False)
		gestion.caso = self.caso
		if commit:
			gestion.save()
		return gestion


class CompromisoForm(forms.ModelForm):
	observacion_cambio = forms.CharField(
		label="Observación del cambio de estado",
		required=False,
		widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
	)

	class Meta:
		model = Compromiso
		fields = ["delegacion", "responsable", "origen", "solicitante", "territorio", "descripcion", "fecha_comprometida", "observacion", "estado"]
		labels = {
			"delegacion": "Delegación",
			"responsable": "Responsable",
			"origen": "Origen",
			"solicitante": "Solicitante",
			"territorio": "Territorio",
			"descripcion": "Descripción",
			"fecha_comprometida": "Fecha comprometida",
			"observacion": "Observación",
			"estado": "Estado",
		}
		widgets = {
			"delegacion": forms.Select(attrs={"class": "form-select"}),
			"responsable": forms.Select(attrs={"class": "form-select"}),
			"origen": forms.TextInput(attrs={"class": "form-control"}),
			"solicitante": forms.TextInput(attrs={"class": "form-control"}),
			"territorio": forms.TextInput(attrs={"class": "form-control"}),
			"descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
			"fecha_comprometida": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
			"observacion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
			"estado": forms.Select(attrs={"class": "form-select"}),
		}

	def __init__(self, *args, delegacion=None, edicion=False, **kwargs):
		super().__init__(*args, **kwargs)
		self.edicion = edicion
		self.fields["fecha_comprometida"].input_formats = ["%Y-%m-%d"]
		self.fields["observacion"].required = False
		if delegacion is not None:
			self.fields["delegacion"].queryset = Delegacion.objects.filter(pk=delegacion.pk, activa=True)
			self.fields["delegacion"].initial = delegacion.pk
			self.fields["responsable"].queryset = Funcionario.objects.filter(activo=True, delegacion=delegacion)
		else:
			self.fields["delegacion"].queryset = Delegacion.objects.filter(activa=True)
			self.fields["responsable"].queryset = Funcionario.objects.filter(activo=True).select_related("delegacion")
		if not edicion:
			self.fields.pop("estado")
			self.fields.pop("observacion_cambio")
		else:
			permitidos = {self.instance.estado, *self.instance.transiciones_disponibles()}
			self.fields["estado"].choices = [opcion for opcion in Compromiso.ESTADOS if opcion[0] in permitidos]
		for campo in self.fields.values():
			campo.error_messages["required"] = "Este campo es obligatorio."

	def clean(self):
		cleaned = super().clean()
		delegacion = cleaned.get("delegacion")
		responsable = cleaned.get("responsable")
		if delegacion and responsable and responsable.delegacion_id != delegacion.pk:
			self.add_error("responsable", "El responsable debe pertenecer a la delegación del compromiso.")
		if self.edicion and "estado" in cleaned and not self.instance.puede_transitar(cleaned["estado"]):
			self.add_error("estado", "Esa transición de estado no está permitida.")
		return cleaned
