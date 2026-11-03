import logging

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from laserena.permisos import GRUPO_ADMINISTRADOR, GRUPOS_SGR, grupo_usuario

from .cuentas import APPS_ADMINISTRADOR, MODELOS_AUTH_ADMINISTRADOR, asignar_grupo
from .models import Cargo, Delegacion, Funcionario

User = get_user_model()
registro = logging.getLogger(__name__)


class AccesoForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Usuario o contraseña incorrectos.",
        "inactive": "La cuenta está desactivada.",
        "sin_perfil": "La cuenta no tiene un perfil del SGR asignado. Contacta a coordinación.",
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if grupo_usuario(user) is None:
            raise ValidationError(self.error_messages["sin_perfil"], code="sin_perfil")


class RecuperarClaveForm(PasswordResetForm):
    """Envía el enlace solo a cuentas activas con ese correo; un fallo SMTP no rompe la página."""

    email = forms.EmailField(
        label="Correo registrado",
        max_length=254,
        widget=forms.EmailInput(attrs={"class": "form-control form-control-lg", "autocomplete": "email", "autofocus": True}),
    )

    def get_users(self, email):
        return (usuario for usuario in super().get_users(email) if usuario.is_active and grupo_usuario(usuario) is not None)

    def send_mail(self, *args, **kwargs):
        try:
            super().send_mail(*args, **kwargs)
        except Exception:
            # Misma respuesta al usuario para no revelar si el correo existe; el detalle queda en el log.
            registro.exception("No se pudo enviar el correo de recuperación de contraseña")


class NuevaClaveForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control form-control-lg"


def _control(widget):
    widget.attrs.setdefault("class", "form-select" if isinstance(widget, forms.Select) else "form-control")
    return widget


class UsuarioForm(forms.Form):
    """Crea o edita una cuenta: usuario de Django, grupo SGR y ficha de funcionario."""

    username = forms.CharField(label="Usuario", max_length=150, validators=[UnicodeUsernameValidator()])
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellido", max_length=150, required=False)
    email = forms.EmailField(label="Correo", help_text="Se usa para recuperar la contraseña.")
    grupo = forms.ModelChoiceField(label="Perfil (grupo)", queryset=Group.objects.none(), empty_label="Selecciona un perfil")
    is_active = forms.BooleanField(label="Cuenta activa", required=False, initial=True)
    identificador = forms.CharField(label="Identificador de funcionario", max_length=30, required=False, help_text="Código interno único, por ejemplo F-104.")
    delegacion = forms.ModelChoiceField(label="Delegación", queryset=Delegacion.objects.none(), required=False)
    cargo = forms.ModelChoiceField(label="Cargo", queryset=Cargo.objects.none(), required=False)
    clave = forms.CharField(label="Contraseña", required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    clave_confirmacion = forms.CharField(label="Repite la contraseña", required=False, strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        self.perfil = getattr(usuario, "perfil_sgr", None) if usuario else None
        if usuario is not None and "initial" not in kwargs:
            kwargs["initial"] = {
                "username": usuario.username,
                "first_name": usuario.first_name,
                "last_name": usuario.last_name,
                "email": usuario.email,
                "grupo": usuario.groups.filter(name__in=GRUPOS_SGR).first(),
                "is_active": usuario.is_active,
                "identificador": getattr(self.perfil, "identificador", ""),
                "delegacion": getattr(self.perfil, "delegacion", None),
                "cargo": getattr(self.perfil, "cargo", None),
            }
        super().__init__(*args, **kwargs)
        self.fields["grupo"].queryset = Group.objects.order_by("name")
        self.fields["delegacion"].queryset = Delegacion.objects.filter(activa=True)
        self.fields["cargo"].queryset = Cargo.objects.filter(activo=True)
        if usuario is None:
            self.fields["clave"].required = True
            self.fields["clave_confirmacion"].required = True
            self.fields["clave"].help_text = "Mínimo 10 caracteres. No puede ser solo números, una clave común ni parecerse al usuario."
        else:
            self.fields["clave"].help_text = "Déjala vacía para mantener la contraseña actual."
        for campo in self.fields.values():
            if not isinstance(campo.widget, forms.CheckboxInput):
                _control(campo.widget)
            campo.error_messages["required"] = "Este campo es obligatorio."

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        repetidos = User.objects.filter(username__iexact=username)
        if self.usuario is not None:
            repetidos = repetidos.exclude(pk=self.usuario.pk)
        if repetidos.exists():
            raise ValidationError("Ya existe una cuenta con ese usuario.")
        return username

    def clean_identificador(self):
        identificador = self.cleaned_data["identificador"].strip()
        if identificador:
            repetidos = Funcionario.objects.filter(identificador=identificador)
            if self.perfil is not None:
                repetidos = repetidos.exclude(pk=self.perfil.pk)
            if repetidos.exists():
                raise ValidationError("Ya existe un funcionario con ese identificador.")
        return identificador

    def clean(self):
        limpio = super().clean()
        grupo = limpio.get("grupo")
        if grupo is not None and grupo.name in GRUPOS_SGR and grupo.name != GRUPO_ADMINISTRADOR:
            for campo in ("identificador", "delegacion", "cargo"):
                if not limpio.get(campo):
                    self.add_error(campo, "Obligatorio para Supervisor y Administrativo: define su ámbito de delegación.")
        if self.usuario is not None and self.usuario == getattr(self, "solicitante", None):
            if not limpio.get("is_active") or (grupo is not None and grupo.name != GRUPO_ADMINISTRADOR):
                raise ValidationError("No puedes quitarte el perfil Administrador ni desactivar tu propia cuenta.")
        clave = limpio.get("clave")
        confirmacion = limpio.get("clave_confirmacion")
        if clave or confirmacion:
            if clave != confirmacion:
                self.add_error("clave_confirmacion", "Las contraseñas no coinciden.")
            elif not self.errors.get("clave"):
                candidato = self.usuario or User()
                candidato.username = limpio.get("username", "")
                candidato.first_name = limpio.get("first_name", "")
                candidato.last_name = limpio.get("last_name", "")
                candidato.email = limpio.get("email", "")
                try:
                    validate_password(clave, candidato)
                except ValidationError as error:
                    self.add_error("clave", error)
        return limpio

    @transaction.atomic
    def save(self):
        datos = self.cleaned_data
        usuario = self.usuario or User()
        usuario.username = datos["username"]
        usuario.first_name = datos["first_name"]
        usuario.last_name = datos.get("last_name") or ""
        usuario.email = datos["email"]
        usuario.is_active = datos.get("is_active", False)
        usuario.is_staff = False
        if datos.get("clave"):
            usuario.set_password(datos["clave"])
        usuario.save()
        grupo = datos["grupo"]
        if grupo.name in GRUPOS_SGR:
            asignar_grupo(usuario, grupo.name)
        else:
            usuario.groups.add(grupo)
        if datos.get("identificador") and datos.get("delegacion") and datos.get("cargo"):
            perfil = self.perfil or Funcionario(usuario=usuario)
            perfil.identificador = datos["identificador"]
            perfil.nombre_completo = " ".join(p for p in (datos["first_name"], datos.get("last_name")) if p).strip()
            perfil.correo = datos["email"]
            perfil.delegacion = datos["delegacion"]
            perfil.cargo = datos["cargo"]
            perfil.activo = usuario.is_active
            perfil.save()
        return usuario


class GrupoForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        label="Permisos",
        queryset=Permission.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Group
        fields = ["name", "permissions"]
        labels = {"name": "Nombre del grupo"}
        widgets = {"name": forms.TextInput(attrs={"class": "form-control"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].queryset = Permission.objects.filter(
            Q(content_type__app_label__in=APPS_ADMINISTRADOR)
            | Q(content_type__app_label="auth", content_type__model__in=MODELOS_AUTH_ADMINISTRADOR)
        ).select_related("content_type").order_by("content_type__app_label", "content_type__model", "codename")
        if self.instance.pk and self.instance.name in GRUPOS_SGR:
            self.fields["name"].disabled = True
            self.fields["name"].help_text = "Los tres perfiles base del SGR no cambian de nombre."

    def clean_name(self):
        nombre = " ".join(self.cleaned_data["name"].split())
        repetidos = Group.objects.filter(name__iexact=nombre)
        if self.instance.pk:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise ValidationError("Ya existe un grupo con ese nombre.")
        return nombre
