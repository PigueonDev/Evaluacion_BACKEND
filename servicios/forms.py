from django import forms
from django.core.exceptions import ValidationError

from institucional.models import Delegacion, Funcionario, UnidadMunicipal

from .matriz import SECTORES_POR_DELEGACION
from .models import MAXIMO_GESTIONES_POR_CASO, MOTIVO_RECHAZO_MAX, SUBATENCIONES_POR_TIPO, SUBATENCIONES_SOCIALES, TELEFONO_ACTIVIDAD, TIPOS_ATENCION_SOCIAL, Actividad, Caso, Compromiso, Evidencia, Gestion, ItemMedicion, Periodo, Servicio, TareaPreparatoria

FECHA = {"type": "date", "class": "form-control"}


class ActividadForm(forms.ModelForm):
	funcionario = forms.ModelChoiceField(
		label="Funcionario",
		queryset=Funcionario.objects.none(),
		required=False,
		widget=forms.Select(attrs={"class": "form-select"}),
	)

	class Meta:
		model = Actividad
		fields = ["fecha", "periodo", "item", "servicio", "descripcion", "accion", "solicitante", "contacto", "telefono", "derivado_a", "compromiso"]
		labels = {
			"fecha": "Fecha",
			"periodo": "Período",
			"item": "Ítem de medición",
			"servicio": "Servicio",
			"descripcion": "Actividad o problema",
			"accion": "Acción realizada",
			"solicitante": "Solicitante",
			"contacto": "Contacto",
			"telefono": "Teléfono",
			"derivado_a": "Derivado a",
			"compromiso": "Ingreso al tubo",
		}
		help_texts = {
			"solicitante": "Nombre de quien solicita. Si eliges un ingreso al tubo y lo dejas vacío, se usa el solicitante de ese compromiso. Si escribes un nombre, debe ser el mismo.",
			"telefono": "Opcional. Solo números, espacios o guiones.",
			"derivado_a": "Opcional. Unidad municipal o institución a la que se derivó a la persona.",
			"compromiso": "Opcional. Asocia la actividad a un ingreso del tubo de trabajo de la misma delegación.",
			"servicio": "Opcional.",
		}
		widgets = {
			"fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
			"periodo": forms.Select(attrs={"class": "form-select"}),
			"item": forms.Select(attrs={"class": "form-select"}),
			"servicio": forms.Select(attrs={"class": "form-select"}),
			"descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
			"accion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
			"solicitante": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej.: Junta de vecinos Los Aromos"}),
			"contacto": forms.TextInput(attrs={"class": "form-control"}),
			"telefono": forms.TextInput(attrs={"class": "form-control", "inputmode": "tel"}),
			"derivado_a": forms.Select(attrs={"class": "form-select"}),
			"compromiso": forms.Select(attrs={"class": "form-select"}),
		}

	def __init__(self, *args, funcionario=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.funcionario_fijo = funcionario
		self.fields["fecha"].input_formats = ["%Y-%m-%d"]
		self.fields["periodo"].queryset = Periodo.objects.filter(estado="abierto").order_by("-fecha_inicio")
		# La tasa del tubo se calcula con los compromisos; no se registra como actividad.
		items = ItemMedicion.objects.filter(activo=True).exclude(tipo_medicion="tasa_tubo")
		titular = funcionario or (self.instance.funcionario if self.instance.pk else None)
		if titular is not None and titular.cargo.funciones.exists():
			items = items.filter(pk__in=titular.cargo.funciones.values("pk"))
		self.fields["item"].queryset = items
		self.fields["derivado_a"].queryset = UnidadMunicipal.objects.filter(activa=True)
		self.fields["derivado_a"].required = False
		self.fields["derivado_a"].empty_label = "Sin derivación"
		self.fields["servicio"].queryset = Servicio.objects.filter(activo=True)
		self.fields["servicio"].required = False
		self.fields["solicitante"].required = False
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


class TareaForm(forms.Form):
	descripcion = forms.CharField(
		label="Tarea",
		max_length=280,
		strip=False,
		widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej.: Gestión de sillas"}),
		error_messages={"required": "Escribe la tarea, por ejemplo «Gestión de sillas»."},
	)

	def clean_descripcion(self):
		texto = (self.cleaned_data.get("descripcion") or "").strip()
		if not texto:
			raise ValidationError("Escribe la tarea, por ejemplo «Gestión de sillas».")
		return texto


class TareaFormSetBase(forms.BaseFormSet):
	def clean(self):
		if any(self.errors):
			return
		if not any(form.has_changed() for form in self.forms):
			raise ValidationError("Agrega al menos una tarea preparatoria.")


TareaFormSet = forms.formset_factory(TareaForm, formset=TareaFormSetBase, extra=4)


class RevisionForm(forms.Form):
	decision = forms.ChoiceField(choices=[("aprobar", "Aprobar"), ("rechazar", "Rechazar")], widget=forms.HiddenInput)
	observacion = forms.CharField(
		label="Observación",
		required=False,
		max_length=500,
		widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
	)


class EvidenciaForm(forms.ModelForm):
	class Meta:
		model = Evidencia
		fields = ["tarea", "archivo"]
		labels = {
			"tarea": "Tarea que acredita",
			"archivo": "Captura de pantalla",
		}
		help_texts = {
			"tarea": "Elige la tarea ya realizada que esta captura demuestra.",
			"archivo": "Imagen PNG, JPG o WebP de hasta 5 MB.",
		}
		widgets = {
			"tarea": forms.Select(attrs={"class": "form-select"}),
			"archivo": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/png,image/jpeg,image/webp"}),
		}

	def __init__(self, *args, actividad=None, **kwargs):
		self.actividad = actividad
		super().__init__(*args, **kwargs)
		tareas = TareaPreparatoria.objects.none()
		if actividad is not None:
			tareas = actividad.tareas.filter(realizada=True).order_by("pk")
		self.fields["tarea"].queryset = tareas
		self.fields["tarea"].empty_label = "Elige la tarea"
		self.fields["tarea"].error_messages["required"] = "Elige la tarea que esta captura acredita."
		self.fields["archivo"].error_messages["required"] = "Adjunta la captura de pantalla."
		self.fields["archivo"].error_messages["invalid"] = "Adjunta una imagen PNG, JPG o WebP de hasta 5 MB."

	def clean(self):
		cleaned = super().clean()
		if self.actividad is not None:
			self.instance.actividad = self.actividad
		tarea = cleaned.get("tarea")
		if tarea is not None:
			self.instance.texto_tarea = tarea.descripcion
		return cleaned


class RevisionEvidenciaForm(forms.Form):
	decision = forms.ChoiceField(
		choices=[("aprobar", "Aprobar"), ("rechazar", "Rechazar")],
		error_messages={"required": "Elige si apruebas o rechazas la evidencia.", "invalid_choice": "Decisión no válida."},
	)
	motivo = forms.CharField(
		label="Motivo del rechazo",
		required=False,
		max_length=MOTIVO_RECHAZO_MAX,
		error_messages={"max_length": "El motivo del rechazo no puede superar los 280 caracteres."},
	)

	def clean(self):
		cleaned = super().clean()
		motivo = (cleaned.get("motivo") or "").strip()
		cleaned["motivo"] = motivo
		if cleaned.get("decision") == "rechazar" and not motivo:
			self.add_error("motivo", "Indica un motivo breve del rechazo.")
		return cleaned


class CasoForm(forms.ModelForm):
	class Meta:
		model = Caso
		fields = [
			"identificacion", "nombre", "solicitante", "rut", "telefono", "delegacion", "tipo_atencion", "sub_atencion", "fecha_ingreso",
			"requiere_visita", "fecha_programada_visita", "fecha_visita", "fecha_entrega_informe", "fecha_entrega_beneficio",
			"devoluciones_informe", "observacion",
		]
		labels = {
			"identificacion": "Identificación principal",
			"nombre": "Nombre de la persona usuaria",
			"solicitante": "Solicitante",
			"delegacion": "Delegación",
			"observacion": "Observación",
		}
		help_texts = {
			"identificacion": "Se registra una sola vez. Las gestiones se asocian a este caso y no repiten el identificador.",
			"solicitante": "Nombre de quien solicita. Si el caso se asocia a una actividad o a un ingreso al tubo, debe ser el mismo nombre.",
			"sub_atencion": "Debe corresponder al tipo de atención (hoja LISTA de la matriz).",
			"fecha_programada_visita": "Plazo de la matriz: hasta 10 días desde el ingreso.",
			"fecha_entrega_informe": "Plazo de la matriz: hasta 4 días desde la visita.",
			"fecha_entrega_beneficio": "Plazo de la matriz: hasta 4 días desde el informe y 20 desde el ingreso.",
			"devoluciones_informe": "Veces que el informe social fue devuelto para corrección.",
		}
		widgets = {
			"identificacion": forms.TextInput(attrs={"class": "form-control"}),
			"nombre": forms.TextInput(attrs={"class": "form-control"}),
			"solicitante": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej.: Junta de vecinos Los Aromos"}),
			"rut": forms.TextInput(attrs={"class": "form-control", "placeholder": "12.345.678-5"}),
			"telefono": forms.TextInput(attrs={"class": "form-control", "inputmode": "tel"}),
			"delegacion": forms.Select(attrs={"class": "form-select"}),
			"tipo_atencion": forms.Select(attrs={"class": "form-select"}),
			"sub_atencion": forms.Select(attrs={"class": "form-select"}),
			"fecha_ingreso": forms.DateInput(attrs=FECHA, format="%Y-%m-%d"),
			"requiere_visita": forms.CheckboxInput(attrs={"class": "form-check-input"}),
			"fecha_programada_visita": forms.DateInput(attrs=FECHA, format="%Y-%m-%d"),
			"fecha_visita": forms.DateInput(attrs=FECHA, format="%Y-%m-%d"),
			"fecha_entrega_informe": forms.DateInput(attrs=FECHA, format="%Y-%m-%d"),
			"fecha_entrega_beneficio": forms.DateInput(attrs=FECHA, format="%Y-%m-%d"),
			"devoluciones_informe": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 3}),
			"observacion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
		}

	def __init__(self, *args, delegacion=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["observacion"].required = False
		self.fields["solicitante"].required = True
		for nombre in ("fecha_ingreso", "fecha_programada_visita", "fecha_visita", "fecha_entrega_informe", "fecha_entrega_beneficio"):
			self.fields[nombre].input_formats = ["%Y-%m-%d"]
		self.fields["fecha_ingreso"].required = False
		etiquetas = dict(SUBATENCIONES_SOCIALES)
		self.fields["sub_atencion"].choices = [("", "Sin subatención")] + [
			(etiqueta_tipo, [(codigo, etiquetas[codigo]) for codigo in SUBATENCIONES_POR_TIPO[tipo]])
			for tipo, etiqueta_tipo in TIPOS_ATENCION_SOCIAL
		]
		if delegacion is not None:
			self.fields["delegacion"].queryset = Delegacion.objects.filter(pk=delegacion.pk, activa=True)
			self.fields["delegacion"].initial = delegacion
		else:
			self.fields["delegacion"].queryset = Delegacion.objects.filter(activa=True)
		for campo in self.fields.values():
			campo.error_messages["required"] = "Este campo es obligatorio."

	def clean_identificacion(self):
		return (self.cleaned_data.get("identificacion") or "").strip()

	def clean_fecha_ingreso(self):
		return self.cleaned_data.get("fecha_ingreso") or self.instance.fecha_ingreso


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
		fields = [
			"delegacion", "fecha_solicitud", "ambito", "origen", "solicitante", "territorio", "descripcion", "responsable",
			"area_apoyo", "fecha_comprometida", "observacion", "estado",
		]
		labels = {
			"delegacion": "Delegación",
			"fecha_solicitud": "Fecha de solicitud",
			"ambito": "Interno o externo",
			"responsable": "Responsable",
			"origen": "Origen",
			"solicitante": "Solicitante",
			"territorio": "Territorio o sector",
			"area_apoyo": "Área o persona de apoyo",
			"descripcion": "Descripción",
			"fecha_comprometida": "Fecha comprometida",
			"observacion": "Observación",
			"estado": "Estado",
		}
		widgets = {
			"delegacion": forms.Select(attrs={"class": "form-select"}),
			"fecha_solicitud": forms.DateInput(attrs=FECHA, format="%Y-%m-%d"),
			"ambito": forms.Select(attrs={"class": "form-select"}),
			"responsable": forms.Select(attrs={"class": "form-select"}),
			"area_apoyo": forms.Select(attrs={"class": "form-select"}),
			"origen": forms.TextInput(attrs={"class": "form-control"}),
			"solicitante": forms.TextInput(attrs={"class": "form-control"}),
			"territorio": forms.TextInput(attrs={"class": "form-control", "list": "sectores-delegacion"}),
			"descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
			"fecha_comprometida": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
			"observacion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
			"estado": forms.Select(attrs={"class": "form-select"}),
		}

	def __init__(self, *args, delegacion=None, edicion=False, **kwargs):
		super().__init__(*args, **kwargs)
		self.edicion = edicion
		self.fields["fecha_comprometida"].input_formats = ["%Y-%m-%d"]
		self.fields["fecha_solicitud"].input_formats = ["%Y-%m-%d"]
		self.fields["fecha_solicitud"].required = False
		self.fields["ambito"].required = False
		self.fields["observacion"].required = False
		self.fields["area_apoyo"].queryset = UnidadMunicipal.objects.filter(activa=True)
		self.fields["area_apoyo"].required = False
		self.fields["area_apoyo"].empty_label = "Sin apoyo de otra unidad"
		if delegacion is not None:
			self.sectores = SECTORES_POR_DELEGACION.get(delegacion.slug, [])
		else:
			self.sectores = sorted({sector for sectores in SECTORES_POR_DELEGACION.values() for sector in sectores})
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
		if not cleaned.get("ambito"):
			cleaned["ambito"] = self.instance.ambito
		solicitud, comprometida = cleaned.get("fecha_solicitud"), cleaned.get("fecha_comprometida")
		if not solicitud:
			solicitud = self.instance.fecha_solicitud
			if comprometida and solicitud and comprometida < solicitud:
				solicitud = comprometida
			cleaned["fecha_solicitud"] = solicitud
		elif comprometida and comprometida < solicitud:
			self.add_error("fecha_comprometida", "La fecha de compromiso no puede ser anterior a la solicitud.")
		if self.edicion and "estado" in cleaned and not self.instance.puede_transitar(cleaned["estado"]):
			self.add_error("estado", "Esa transición de estado no está permitida.")
		return cleaned
