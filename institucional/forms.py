from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import transaction

from .cuentas import conceder_permisos_parametros
from .models import Cargo, Delegacion, Funcionario

User = get_user_model()


class CuentaForm(forms.Form):
    username = forms.CharField(
        label="Usuario",
        max_length=150,
        validators=[UnicodeUsernameValidator()],
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
    nombre = forms.CharField(
        label="Nombre",
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
    apellido = forms.CharField(
        label="Apellido",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
    identificador = forms.CharField(
        label="Identificador",
        max_length=30,
        help_text="Código interno único, por ejemplo F-104.",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    correo = forms.EmailField(
        label="Correo",
        required=False,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
    )
    delegacion = forms.ModelChoiceField(
        label="Delegación",
        queryset=Delegacion.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    cargo = forms.ModelChoiceField(
        label="Cargo",
        queryset=Cargo.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    rol = forms.ChoiceField(
        label="Rol",
        choices=Funcionario.ROLES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    clave = forms.CharField(
        label="Contraseña",
        help_text="Mínimo 10 caracteres. No puede ser solo números, una clave común ni parecerse al usuario.",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )
    clave_confirmacion = forms.CharField(
        label="Repite la contraseña",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["delegacion"].queryset = Delegacion.objects.filter(activa=True)
        self.fields["cargo"].queryset = Cargo.objects.filter(activo=True)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise ValidationError("Ya existe una cuenta con ese usuario.")
        return username

    def clean_identificador(self):
        identificador = self.cleaned_data["identificador"].strip()
        if Funcionario.objects.filter(identificador=identificador).exists():
            raise ValidationError("Ya existe un funcionario con ese identificador.")
        return identificador

    def clean(self):
        limpio = super().clean()
        clave = limpio.get("clave")
        confirmacion = limpio.get("clave_confirmacion")
        if clave and confirmacion and clave != confirmacion:
            self.add_error("clave_confirmacion", "Las contraseñas no coinciden.")
        if clave and not self.errors.get("clave"):
            candidato = User(
                username=limpio.get("username", ""),
                first_name=limpio.get("nombre", ""),
                last_name=limpio.get("apellido", ""),
                email=limpio.get("correo") or "",
            )
            try:
                validate_password(clave, candidato)
            except ValidationError as error:
                self.add_error("clave", error)
        return limpio

    def save(self):
        datos = self.cleaned_data
        with transaction.atomic():
            usuario = User.objects.create_user(
                username=datos["username"],
                email=datos.get("correo") or "",
                password=datos["clave"],
                first_name=datos["nombre"],
                last_name=datos.get("apellido") or "",
            )
            usuario.is_staff = True
            usuario.is_superuser = False
            usuario.save(update_fields=["is_staff", "is_superuser"])
            if datos["rol"] == "administrador":
                conceder_permisos_parametros(usuario)
            nombre = " ".join(parte for parte in (datos["nombre"], datos.get("apellido")) if parte).strip()
            Funcionario.objects.create(
                usuario=usuario,
                identificador=datos["identificador"],
                nombre_completo=nombre,
                correo=datos.get("correo") or "",
                delegacion=datos["delegacion"],
                cargo=datos["cargo"],
                rol=datos["rol"],
            )
        return usuario
