"""Serializers de la API del SGR.

Cada recurso tiene un serializer para el perfil Administrador (todos los campos) y otro para el perfil
Usuario (Supervisor y Administrativo), que omite los datos sensibles. Las contraseñas nunca se serializan.
"""

import copy

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.serializers import as_serializer_error
from rest_framework.settings import api_settings
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from institucional.forms import UsuarioForm
from institucional.models import Cargo, Delegacion, Funcionario, UnidadMunicipal
from laserena.permisos import GRUPOS_SGR, grupo_usuario
from oficina.models import Carta
from organizaciones.models import OrganizacionComunitaria
from servicios.models import TELEFONO_ACTIVIDAD, Actividad, Compromiso, ItemMedicion, Periodo, Servicio, TareaPreparatoria
from servicios.transacciones import actualizar_actividad, registrar_actividad

User = get_user_model()
MAXIMO_TAREAS = 10


def _error_drf(error):
    return serializers.ValidationError(as_serializer_error(error))


class ValidacionModeloMixin:
    """Aplica las reglas de `Model.clean()` (las mismas del formulario web) antes de guardar."""

    def valores_fijos(self):
        return self.context.get("valores_fijos", {})

    def validate(self, attrs):
        attrs = super().validate(attrs)
        instancia = copy.copy(self.instance) if self.instance is not None else self.Meta.model()
        for campo, valor in {**self.valores_fijos(), **attrs}.items():
            setattr(instancia, campo, valor)
        try:
            instancia.clean()
        except DjangoValidationError as error:
            raise _error_drf(error)
        return attrs


# --- Errores (solo documentación) ------------------------------------------------------


class DetalleErrorSerializer(serializers.Serializer):
    codigo = serializers.IntegerField(help_text="Código HTTP de la respuesta.")
    tipo = serializers.CharField(help_text="Tipo de error: solicitud_invalida, no_autenticado, sin_permiso, no_encontrado…")
    mensaje = serializers.CharField(help_text="Mensaje descriptivo para quien consume la API.")
    detalle = serializers.DictField(required=False, help_text="Errores por campo (solo en 400).")


class ErrorSerializer(serializers.Serializer):
    error = DetalleErrorSerializer()


class MensajeSerializer(serializers.Serializer):
    mensaje = serializers.CharField()
    id = serializers.IntegerField(required=False)


# --- JWT ----------------------------------------------------------------------------------


class TokenSGRSerializer(TokenObtainPairSerializer):
    """Agrega el perfil SGR al token. El payload es legible por cualquiera: no lleva datos personales."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["perfil"] = grupo_usuario(user)
        return token

    def validate(self, attrs):
        datos = super().validate(attrs)
        datos["perfil"] = grupo_usuario(self.user)
        return datos


class TokenRespuestaSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Token de acceso JWT (15 minutos). Se envía en la cabecera `Authorization: Bearer <access>`.")
    refresh = serializers.CharField(help_text="Token de renovación (8 horas). Solo sirve para pedir un token de acceso nuevo en /api/token/renovar/.")
    perfil = serializers.CharField(help_text="Perfil SGR de la cuenta: Administrador, Supervisor o Administrativo.")


class PerfilActualSerializer(serializers.Serializer):
    usuario = serializers.CharField()
    nombre = serializers.CharField()
    perfil = serializers.CharField()
    es_administrador = serializers.BooleanField()
    delegacion = serializers.CharField(allow_null=True)
    cargo = serializers.CharField(allow_null=True)
    ve_datos_sensibles = serializers.BooleanField()


# --- Mantenedor 1: usuarios -------------------------------------------------------------


class FuncionarioAdminSerializer(serializers.ModelSerializer):
    delegacion = serializers.StringRelatedField()
    cargo = serializers.StringRelatedField()

    class Meta:
        model = Funcionario
        fields = ["id", "identificador", "nombre_completo", "correo", "delegacion", "cargo", "codigo_area", "activo"]


class UsuarioAdminSerializer(serializers.ModelSerializer):
    """Perfil Administrador: todos los datos de la cuenta, salvo la contraseña (que nunca sale de la base)."""

    usuario = serializers.CharField(source="username", read_only=True)
    nombres = serializers.CharField(source="first_name", read_only=True)
    apellidos = serializers.CharField(source="last_name", read_only=True)
    correo = serializers.EmailField(source="email", read_only=True)
    perfil = serializers.SerializerMethodField(help_text="Grupo SGR de la cuenta.")
    activo = serializers.BooleanField(source="is_active", read_only=True)
    ultimo_acceso = serializers.DateTimeField(source="last_login", read_only=True, allow_null=True)
    fecha_creacion = serializers.DateTimeField(source="date_joined", read_only=True)
    funcionario = FuncionarioAdminSerializer(source="perfil_sgr", read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = ["id", "usuario", "nombres", "apellidos", "correo", "perfil", "activo", "ultimo_acceso", "fecha_creacion", "funcionario"]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_perfil(self, obj):
        return grupo_usuario(obj) if obj.is_active else obj.groups.filter(name__in=GRUPOS_SGR).values_list("name", flat=True).first()


class UsuarioPublicoSerializer(serializers.ModelSerializer):
    """Perfil Usuario: solo nombre, perfil, cargo y delegación. Sin usuario, correo ni datos de acceso."""

    nombre = serializers.SerializerMethodField()
    perfil = serializers.SerializerMethodField()
    delegacion = serializers.CharField(source="perfil_sgr.delegacion.nombre", default=None)
    cargo = serializers.CharField(source="perfil_sgr.cargo.nombre", default=None)

    class Meta:
        model = User
        fields = ["id", "nombre", "perfil", "cargo", "delegacion"]

    @extend_schema_field(serializers.CharField())
    def get_nombre(self, obj):
        perfil = getattr(obj, "perfil_sgr", None)
        return perfil.nombre_completo if perfil else obj.get_full_name() or obj.username

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_perfil(self, obj):
        return grupo_usuario(obj)


# Campo de la API (en español) → campo del formulario web y del modelo User de Django.
CAMPOS_FORMULARIO_USUARIO = {"usuario": "username", "nombres": "first_name", "apellidos": "last_name", "correo": "email", "activo": "is_active"}
CAMPOS_API_USUARIO = {**{v: k for k, v in CAMPOS_FORMULARIO_USUARIO.items()}, "grupo": "perfil"}


class UsuarioEntradaSerializer(serializers.Serializer):
    """Datos para crear o editar una cuenta. Usa las mismas validaciones del mantenedor web (UsuarioForm)."""

    usuario = serializers.CharField(max_length=150, help_text="Nombre de usuario para iniciar sesión.")
    nombres = serializers.CharField(max_length=150)
    apellidos = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    correo = serializers.EmailField(help_text="Se usa para recuperar la contraseña.")
    perfil = serializers.ChoiceField(choices=GRUPOS_SGR)
    activo = serializers.BooleanField(required=False, default=True)
    identificador = serializers.CharField(max_length=30, required=False, allow_blank=True, default="", help_text="Obligatorio para Supervisor y Administrativo.")
    delegacion = serializers.PrimaryKeyRelatedField(queryset=Delegacion.objects.filter(activa=True), required=False, allow_null=True, default=None)
    cargo = serializers.PrimaryKeyRelatedField(queryset=Cargo.objects.filter(activo=True), required=False, allow_null=True, default=None)
    codigo_area = serializers.CharField(max_length=10, required=False, allow_blank=True, default="")
    clave = serializers.CharField(
        write_only=True, required=False, allow_blank=True, default="", trim_whitespace=False, style={"input_type": "password"},
        help_text="Obligatoria al crear. Mínimo 10 caracteres; no puede ser común, solo números ni parecida al usuario.",
    )
    clave_confirmacion = serializers.CharField(write_only=True, required=False, allow_blank=True, default="", trim_whitespace=False, style={"input_type": "password"})

    def validate(self, attrs):
        grupo = Group.objects.filter(name=attrs["perfil"]).first()
        datos = {
            **{campo_formulario: attrs.get(campo) for campo, campo_formulario in CAMPOS_FORMULARIO_USUARIO.items()},
            **{campo: attrs.get(campo) for campo in ("identificador", "codigo_area", "clave", "clave_confirmacion")},
            "grupo": grupo.pk if grupo else None,
            "delegacion": attrs["delegacion"].pk if attrs.get("delegacion") else None,
            "cargo": attrs["cargo"].pk if attrs.get("cargo") else None,
        }
        formulario = UsuarioForm(data=datos, usuario=self.instance)
        formulario.solicitante = self.context["request"].user
        if not formulario.is_valid():
            errores = {CAMPOS_API_USUARIO.get(campo, campo): mensajes for campo, mensajes in formulario.errors.items()}
            if "__all__" in errores:
                errores[api_settings.NON_FIELD_ERRORS_KEY] = errores.pop("__all__")
            raise serializers.ValidationError(errores)
        self._formulario = formulario
        return attrs

    def create(self, validated_data):
        return self._formulario.save()

    def update(self, instance, validated_data):
        return self._formulario.save()


# --- Mantenedor 2: cartas de Oficina de Partes ---------------------------------------------


class CartaAdminSerializer(ValidacionModeloMixin, serializers.ModelSerializer):
    """Perfil Administrador: carta completa, incluido el contacto del remitente y quién la registró."""

    delegacion = serializers.PrimaryKeyRelatedField(queryset=Delegacion.objects.filter(activa=True))
    organizacion = serializers.PrimaryKeyRelatedField(queryset=OrganizacionComunitaria.objects.exclude(estado="inactiva"), required=False, allow_null=True)
    derivada_a = serializers.PrimaryKeyRelatedField(queryset=Funcionario.objects.filter(activo=True), required=False, allow_null=True, help_text="Funcionario de la misma delegación.")
    derivada_a_unidad = serializers.PrimaryKeyRelatedField(queryset=UnidadMunicipal.objects.filter(activa=True), required=False, allow_null=True)
    encargado_seguimiento = serializers.PrimaryKeyRelatedField(queryset=UnidadMunicipal.objects.filter(activa=True), required=False, allow_null=True)
    delegacion_nombre = serializers.CharField(source="delegacion.nombre", read_only=True)
    derivada_a_nombre = serializers.CharField(source="derivada_a.nombre_completo", read_only=True, default=None)
    estado_texto = serializers.CharField(source="get_estado_display", read_only=True)
    resolucion_texto = serializers.CharField(source="get_resolucion_display", read_only=True)
    vencida = serializers.BooleanField(read_only=True)
    registrada_por = serializers.CharField(source="registrada_por.username", read_only=True)

    class Meta:
        model = Carta
        fields = [
            "id", "folio", "numero_oficina_partes", "fecha_ingreso", "destinatario", "tipo", "remitente", "contacto_remitente",
            "asunto", "detalle", "fecha_actividad", "delegacion", "delegacion_nombre", "organizacion", "encargado_seguimiento",
            "pronunciamiento", "derivada_a", "derivada_a_nombre", "derivada_a_unidad", "estado", "estado_texto", "resolucion",
            "resolucion_texto", "plazo_respuesta", "respuesta", "fecha_respuesta", "vencida", "registrada_por", "creada_en", "actualizada_en",
        ]
        read_only_fields = ["folio", "creada_en", "actualizada_en"]
        extra_kwargs = {"contacto_remitente": {"help_text": "Dato sensible: teléfono o correo personal del remitente."}}


CAMPOS_SENSIBLES_CARTA = ("contacto_remitente", "registrada_por")


class CartaUsuarioSerializer(CartaAdminSerializer):
    """Perfil Usuario: sin el contacto personal del remitente ni la cuenta que la registró.

    El contacto se puede enviar al crear o editar (write_only), pero nunca vuelve en la respuesta.
    La delegación queda fija en la del funcionario.
    """

    delegacion = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta(CartaAdminSerializer.Meta):
        fields = [campo for campo in CartaAdminSerializer.Meta.fields if campo != "registrada_por"]
        extra_kwargs = {"contacto_remitente": {"write_only": True}}


class CartaSeguimientoSerializer(ValidacionModeloMixin, serializers.ModelSerializer):
    """El Administrativo solo actualiza el estado y la respuesta de las cartas derivadas a él."""

    estado = serializers.ChoiceField(choices=[c for c in Carta.ESTADOS if c[0] in ("derivada", "en_respuesta", "respondida")])

    class Meta:
        model = Carta
        fields = ["estado", "resolucion", "respuesta", "fecha_respuesta"]


# --- Transacción: registrar actividad --------------------------------------------------------


class TareaSerializer(serializers.ModelSerializer):
    tipo_texto = serializers.CharField(source="get_tipo_display", read_only=True, label="Tipo de gestión")

    class Meta:
        model = TareaPreparatoria
        fields = ["id", "tipo", "tipo_texto", "descripcion", "realizada", "realizada_en"]
        read_only_fields = ["realizada", "realizada_en"]
        extra_kwargs = {
            "tipo": {"label": "Tipo de gestión", "help_text": "Siempre «otra» (Otra gestión)."},
            "descripcion": {"label": "Gestión", "help_text": "Texto libre de la tarea. Ejemplo: Gestión de sillas."},
        }


class TareaEntradaSerializer(serializers.ModelSerializer):
    tipo = serializers.ChoiceField(
        choices=TareaPreparatoria.TIPOS,
        label="Tipo de gestión",
        help_text="Única opción: otra (Otra gestión). El nombre de la tarea va en descripcion.",
        error_messages={"invalid_choice": "La única opción es «Otra gestión». Escribe el nombre de la tarea en el texto."},
    )
    descripcion = serializers.CharField(
        max_length=280,
        label="Gestión",
        help_text="Texto libre de la gestión. Ejemplo: Gestión de sillas.",
        error_messages={
            "blank": "Escribe la gestión, por ejemplo «Gestión de sillas».",
            "required": "Escribe la gestión, por ejemplo «Gestión de sillas».",
        },
    )

    class Meta:
        model = TareaPreparatoria
        fields = ["tipo", "descripcion"]

    def validate_descripcion(self, valor):
        valor = (valor or "").strip()
        if not valor:
            raise serializers.ValidationError("Escribe la gestión, por ejemplo «Gestión de sillas».")
        return valor


class TareaMarcaSerializer(serializers.Serializer):
    realizada = serializers.BooleanField()


class RevisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=[("aprobar", "Aprobar"), ("rechazar", "Rechazar")])
    observacion = serializers.CharField(max_length=500, required=False, allow_blank=True, default="", help_text="Obligatoria al rechazar.")


class ActividadUsuarioSerializer(serializers.ModelSerializer):
    """Perfil Usuario: datos operacionales de la actividad, sin el contacto ni el teléfono de la persona atendida."""

    funcionario_nombre = serializers.CharField(source="funcionario.nombre_completo", read_only=True)
    delegacion = serializers.CharField(source="funcionario.delegacion.nombre", read_only=True)
    periodo_nombre = serializers.CharField(source="periodo.nombre", read_only=True)
    item_nombre = serializers.CharField(source="item.nombre", read_only=True)
    derivado_a_nombre = serializers.CharField(source="derivado_a.nombre", read_only=True, default=None)
    estado_texto = serializers.CharField(source="get_estado_display", read_only=True)
    tareas = TareaSerializer(many=True, read_only=True)
    tareas_completas = serializers.BooleanField(read_only=True)
    revisada_por = serializers.CharField(source="revisada_por.get_full_name", read_only=True, default=None)

    class Meta:
        model = Actividad
        fields = [
            "id", "codigo_verificador", "codigo_evidencia", "funcionario", "funcionario_nombre", "delegacion", "periodo", "periodo_nombre",
            "item", "item_nombre", "servicio", "compromiso", "fecha", "descripcion", "accion", "derivado_a", "derivado_a_nombre",
            "estado", "estado_texto", "tareas", "tareas_completas", "revisada_por", "revisada_en", "observacion_revision", "creada_en",
        ]
        read_only_fields = fields


class ActividadAdminSerializer(ActividadUsuarioSerializer):
    """Perfil Administrador: agrega el contacto y el teléfono personal de la persona atendida."""

    class Meta(ActividadUsuarioSerializer.Meta):
        _posicion = ActividadUsuarioSerializer.Meta.fields.index("accion") + 1
        fields = ActividadUsuarioSerializer.Meta.fields[:_posicion] + ["contacto", "telefono"] + ActividadUsuarioSerializer.Meta.fields[_posicion:]
        read_only_fields = fields


CAMPOS_SENSIBLES_ACTIVIDAD = ("contacto", "telefono")


class ActividadEdicionSerializer(serializers.ModelSerializer):
    """Campos que se pueden modificar mientras la actividad está pendiente y su semana sigue abierta."""

    periodo = serializers.PrimaryKeyRelatedField(queryset=Periodo.objects.filter(estado="abierto"))
    item = serializers.PrimaryKeyRelatedField(queryset=ItemMedicion.objects.filter(activo=True).exclude(tipo_medicion="tasa_tubo"))
    servicio = serializers.PrimaryKeyRelatedField(queryset=Servicio.objects.filter(activo=True), required=False, allow_null=True)
    compromiso = serializers.PrimaryKeyRelatedField(queryset=Compromiso.objects.filter(activo=True), required=False, allow_null=True, help_text="Ingreso al tubo de la misma delegación.")
    derivado_a = serializers.PrimaryKeyRelatedField(queryset=UnidadMunicipal.objects.filter(activa=True), required=False, allow_null=True)
    fecha = serializers.DateField(help_text="Día hábil de la semana en curso; no se aceptan fechas futuras.")

    class Meta:
        model = Actividad
        fields = ["fecha", "periodo", "item", "servicio", "compromiso", "descripcion", "accion", "contacto", "telefono", "derivado_a"]
        extra_kwargs = {
            "contacto": {"required": False, "help_text": "Dato sensible: solo lo ve el perfil Administrador."},
            "telefono": {"required": False, "help_text": "Dato sensible: 8 a 15 dígitos. Solo lo ve el perfil Administrador."},
        }

    def titular(self, attrs):
        return self.context.get("funcionario") or getattr(self.instance, "funcionario", None)

    def validate_telefono(self, valor):
        valor = (valor or "").strip()
        if valor and not TELEFONO_ACTIVIDAD.match(valor):
            raise serializers.ValidationError("Usa solo números, espacios o guiones, con un largo de 8 a 15 dígitos.")
        return valor

    def validate(self, attrs):
        titular = self.titular(attrs)
        item = attrs.get("item")
        if titular is not None and item is not None and titular.cargo.funciones.exists() and not titular.cargo.funciones.filter(pk=item.pk).exists():
            raise serializers.ValidationError({"item": f"El ítem no es una función del cargo {titular.cargo.nombre}."})
        compromiso = attrs.get("compromiso")
        if titular is not None and compromiso is not None and compromiso.delegacion_id != titular.delegacion_id:
            raise serializers.ValidationError({"compromiso": "El compromiso debe ser de la misma delegación del funcionario."})
        return attrs

    def update(self, instance, validated_data):
        for campo, valor in validated_data.items():
            setattr(instance, campo, valor)
        try:
            return actualizar_actividad(instance, self.context["request"].user)
        except DjangoValidationError as error:
            raise _error_drf(error)


class ActividadEntradaSerializer(ActividadEdicionSerializer):
    """Registrar actividad: actividad + tareas preparatorias + auditoría en una sola transacción atómica."""

    funcionario = serializers.PrimaryKeyRelatedField(
        queryset=Funcionario.objects.filter(activo=True), required=False, write_only=True,
        help_text="Solo el Administrador lo indica. Para el Administrativo se usa su propia ficha.",
    )
    tareas = TareaEntradaSerializer(many=True, help_text=f"Entre 1 y {MAXIMO_TAREAS} tareas. Cada una es «Otra gestión» más un texto libre, por ejemplo «Gestión de sillas».")

    class Meta(ActividadEdicionSerializer.Meta):
        fields = ActividadEdicionSerializer.Meta.fields + ["funcionario", "tareas"]

    def titular(self, attrs):
        return self.context.get("funcionario") or attrs.get("funcionario")

    def validate_tareas(self, tareas):
        if not tareas:
            raise serializers.ValidationError("Agrega al menos una tarea preparatoria.")
        if len(tareas) > MAXIMO_TAREAS:
            raise serializers.ValidationError(f"Máximo {MAXIMO_TAREAS} tareas por actividad.")
        return tareas

    def validate(self, attrs):
        if self.titular(attrs) is None:
            raise serializers.ValidationError({"funcionario": "Indica el funcionario que realizó la actividad."})
        return super().validate(attrs)

    def create(self, validated_data):
        tareas = [TareaPreparatoria(**tarea) for tarea in validated_data.pop("tareas")]
        funcionario = self.titular(validated_data)
        validated_data.pop("funcionario", None)
        try:
            return registrar_actividad(Actividad(**validated_data), tareas, funcionario, self.context["request"].user)
        except DjangoValidationError as error:
            raise _error_drf(error)
