"""Formularios de los mantenedores que cierran el alcance de la Actividad 1."""

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from laserena.rut import normalizar_rut
from servicios.models import TELEFONO_ACTIVIDAD, ItemMedicion, Meta, Periodo, SubtipoAtencion, TipoAtencion

from .models import Cargo, Delegacion, Funcionario, Hito, Territorio, Vecino


def _control(widget):
	widget.attrs.setdefault("class", "form-select" if isinstance(widget, (forms.Select, forms.SelectMultiple)) else "form-control")
	return widget


class DelegacionForm(forms.ModelForm):
	territorio = forms.ChoiceField(label="Territorio")

	class Meta:
		model = Delegacion
		fields = ["nombre", "slug", "territorio", "enfoque", "direccion", "telefono", "correo", "responsable", "activa"]
		widgets = {"enfoque": forms.Textarea(attrs={"rows": 3})}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		opciones = [(territorio.nombre, territorio.nombre) for territorio in Territorio.objects.filter(activo=True)]
		actual = (self.instance.territorio or "") if self.instance.pk else ""
		if actual and actual not in dict(opciones):
			opciones.insert(0, (actual, actual))
		self.fields["territorio"].choices = opciones
		self.fields["slug"].required = False
		self.fields["slug"].help_text = "Vacío: se arma a partir del nombre."
		for nombre, campo in self.fields.items():
			if nombre != "activa":
				_control(campo.widget)

	def clean_slug(self):
		slug = (self.cleaned_data.get("slug") or "").strip() or slugify(self.data.get("nombre", ""))
		if not slug:
			raise ValidationError("No se pudo armar el identificador. Escribe un nombre.")
		repetidos = Delegacion.objects.filter(slug=slug)
		if self.instance.pk:
			repetidos = repetidos.exclude(pk=self.instance.pk)
		if repetidos.exists():
			raise ValidationError("Ya existe una delegación con ese identificador.")
		return slug

	def clean_nombre(self):
		nombre = " ".join(self.cleaned_data["nombre"].split())
		repetidos = Delegacion.objects.filter(nombre__iexact=nombre)
		if self.instance.pk:
			repetidos = repetidos.exclude(pk=self.instance.pk)
		if repetidos.exists():
			raise ValidationError("Ya existe una delegación con ese nombre.")
		return nombre


class TerritorioForm(forms.ModelForm):
	class Meta:
		model = Territorio
		fields = ["codigo", "nombre", "descripcion", "activo"]
		widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["codigo"].help_text = "Código corto y estable, por ejemplo CENTRO o PAMPA."
		for nombre, campo in self.fields.items():
			if nombre != "activo":
				_control(campo.widget)

	def clean_codigo(self):
		codigo = " ".join(self.cleaned_data["codigo"].upper().split())
		repetidos = Territorio.objects.filter(codigo__iexact=codigo)
		if self.instance.pk:
			repetidos = repetidos.exclude(pk=self.instance.pk)
		if repetidos.exists():
			raise ValidationError("Ya existe un territorio con ese código.")
		return codigo

	def clean_nombre(self):
		nombre = " ".join(self.cleaned_data["nombre"].split())
		repetidos = Territorio.objects.filter(nombre__iexact=nombre)
		if self.instance.pk:
			repetidos = repetidos.exclude(pk=self.instance.pk)
		if repetidos.exists():
			raise ValidationError("Ya existe un territorio con ese nombre.")
		return nombre


class VecinoForm(forms.ModelForm):
	class Meta:
		model = Vecino
		fields = ["delegacion", "nombre", "rut", "telefono", "correo", "direccion", "activo"]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["delegacion"].queryset = Delegacion.objects.filter(activa=True)
		self.fields["rut"].required = False
		self.fields["telefono"].required = False
		self.fields["correo"].required = False
		self.fields["direccion"].required = False
		for nombre, campo in self.fields.items():
			if nombre != "activo":
				_control(campo.widget)

	def clean_rut(self):
		rut = (self.cleaned_data.get("rut") or "").strip()
		if not rut:
			return ""
		return normalizar_rut(rut)

	def clean_telefono(self):
		telefono = (self.cleaned_data.get("telefono") or "").strip()
		if telefono and not TELEFONO_ACTIVIDAD.match(telefono):
			raise ValidationError("El teléfono debe contener entre 8 y 15 dígitos.")
		return telefono

	def clean(self):
		limpio = super().clean()
		rut = limpio.get("rut")
		delegacion = limpio.get("delegacion")
		if rut and delegacion:
			repetidos = Vecino.objects.filter(delegacion=delegacion, rut=rut)
			if self.instance.pk:
				repetidos = repetidos.exclude(pk=self.instance.pk)
			if repetidos.exists():
				self.add_error("rut", "Ese RUT ya está registrado en la delegación.")
		return limpio


class HitoForm(forms.ModelForm):
	class Meta:
		model = Hito
		fields = ["nombre", "descripcion", "fecha", "delegacion", "responsable", "estado", "activo"]
		widgets = {
			"descripcion": forms.Textarea(attrs={"rows": 3}),
			"fecha": forms.DateInput(attrs={"type": "date"}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["fecha"].input_formats = ["%Y-%m-%d"]
		self.fields["delegacion"].queryset = Delegacion.objects.filter(activa=True)
		self.fields["responsable"].queryset = Funcionario.objects.filter(activo=True).select_related("delegacion", "cargo")
		self.fields["responsable"].label_from_instance = lambda funcionario: f"{funcionario.nombre_completo} · {funcionario.delegacion}"
		self.fields["descripcion"].required = False
		for nombre, campo in self.fields.items():
			if nombre != "activo":
				_control(campo.widget)

	def clean(self):
		limpio = super().clean()
		responsable = limpio.get("responsable")
		delegacion = limpio.get("delegacion")
		if responsable and delegacion and responsable.delegacion_id != delegacion.pk:
			self.add_error("responsable", "El responsable debe pertenecer a la delegación del hito.")
		return limpio


class PeriodoForm(forms.ModelForm):
	class Meta:
		model = Periodo
		fields = ["nombre", "fecha_inicio", "fecha_termino", "estado"]
		widgets = {
			"fecha_inicio": forms.DateInput(attrs={"type": "date"}),
			"fecha_termino": forms.DateInput(attrs={"type": "date"}),
		}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		for campo in ("fecha_inicio", "fecha_termino"):
			self.fields[campo].input_formats = ["%Y-%m-%d"]
			_control(self.fields[campo].widget)
		_control(self.fields["nombre"].widget)
		_control(self.fields["estado"].widget)


class MetaFuncionarioForm(forms.Form):
	"""Cantidad y ponderador propios de un funcionario, distintos de la meta del cargo."""

	funcionario = forms.ModelChoiceField(label="Funcionario", queryset=Funcionario.objects.none())
	item = forms.ModelChoiceField(label="Ítem", queryset=ItemMedicion.objects.none())
	objetivo = forms.DecimalField(label="Cantidad exigida", min_value=0.01, max_digits=10, decimal_places=2)
	ponderador = forms.DecimalField(label="Ponderador (%)", min_value=0, max_digits=5, decimal_places=2)

	def __init__(self, *args, periodo=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.periodo = periodo
		self.fields["funcionario"].queryset = Funcionario.objects.filter(activo=True).select_related("cargo", "delegacion").order_by("nombre_completo")
		self.fields["funcionario"].label_from_instance = lambda funcionario: f"{funcionario.nombre_completo} · {funcionario.cargo} · {funcionario.delegacion}"
		self.fields["item"].queryset = ItemMedicion.objects.filter(activo=True)
		for campo in self.fields.values():
			_control(campo.widget)

	def clean(self):
		limpio = super().clean()
		funcionario = limpio.get("funcionario")
		item = limpio.get("item")
		if funcionario and funcionario.cargo.nombre.casefold() == "delegado":
			self.add_error("funcionario", "El cargo Delegado no contabiliza actividades ni solicitudes. No se le fija una meta de puntaje.")
		if self.periodo and funcionario and item:
			existe = Meta.objects.filter(periodo=self.periodo, funcionario=funcionario, item=item)
			limpio["meta_existente"] = existe.first()
		return limpio

	def save(self):
		datos = self.cleaned_data
		meta = datos.get("meta_existente") or Meta(periodo=self.periodo, funcionario=datos["funcionario"], item=datos["item"])
		meta.objetivo = datos["objetivo"]
		meta.ponderador = datos["ponderador"]
		meta.full_clean()
		meta.save()
		return meta


class TipoAtencionForm(forms.ModelForm):
	class Meta:
		model = TipoAtencion
		fields = ["codigo", "nombre", "activo"]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["codigo"].help_text = "Identificador estable, por ejemplo informes-sociales."
		for nombre, campo in self.fields.items():
			if nombre != "activo":
				_control(campo.widget)

	def clean_codigo(self):
		return slugify(self.cleaned_data["codigo"])

	def clean_nombre(self):
		nombre = " ".join(self.cleaned_data["nombre"].split())
		repetidos = TipoAtencion.objects.filter(nombre__iexact=nombre)
		if self.instance.pk:
			repetidos = repetidos.exclude(pk=self.instance.pk)
		if repetidos.exists():
			raise ValidationError("Ya existe un tipo con ese nombre.")
		return nombre


class SubtipoAtencionForm(forms.ModelForm):
	class Meta:
		model = SubtipoAtencion
		fields = ["tipo", "codigo", "nombre", "forma", "activo"]

	def __init__(self, *args, tipo=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.fields["tipo"].queryset = TipoAtencion.objects.filter(activo=True)
		self.fields["forma"].required = False
		self.fields["forma"].help_text = "Opcional. Por ejemplo Dinero, Material o Aporte."
		if tipo is not None:
			self.fields["tipo"].initial = tipo
			self.fields["tipo"].disabled = True
			self.tipo_fijo = tipo
		else:
			self.tipo_fijo = None
		for nombre, campo in self.fields.items():
			if nombre != "activo":
				_control(campo.widget)

	def clean_codigo(self):
		return slugify(self.cleaned_data["codigo"]).replace("-", "_") or slugify(self.cleaned_data["codigo"])

	def clean(self):
		limpio = super().clean()
		if self.tipo_fijo is not None:
			limpio["tipo"] = self.tipo_fijo
		tipo = limpio.get("tipo")
		codigo = limpio.get("codigo")
		if tipo and codigo:
			repetidos = SubtipoAtencion.objects.filter(tipo=tipo, codigo=codigo)
			if self.instance.pk:
				repetidos = repetidos.exclude(pk=self.instance.pk)
			if repetidos.exists():
				self.add_error("codigo", "Ese subtipo ya existe en el tipo elegido.")
		return limpio

	def save(self, commit=True):
		subtipo = super().save(commit=False)
		if self.tipo_fijo is not None:
			subtipo.tipo = self.tipo_fijo
		if commit:
			subtipo.save()
		return subtipo
