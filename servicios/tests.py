from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from institucional.models import Cargo, Delegacion, Funcionario

from .models import Actividad, ItemMedicion, Meta, Periodo


class ReglasSgrTest(TestCase):
	def setUp(self):
		usuario = get_user_model().objects.create_user(username="funcionario-demo", password="demo")
		delegacion = Delegacion.objects.create(
			nombre="Delegación de prueba",
			slug="delegacion-prueba",
			territorio="Territorio ficticio",
			enfoque="Demostración académica",
		)
		cargo = Cargo.objects.create(nombre="Cargo de prueba")
		self.funcionario = Funcionario.objects.create(
			usuario=usuario,
			identificador="F-001",
			nombre_completo="Funcionario de prueba",
			delegacion=delegacion,
			cargo=cargo,
		)
		self.item = ItemMedicion.objects.create(codigo="TEST-001", nombre="Ítem de prueba")
		self.periodo = Periodo.objects.create(
			nombre="Período de prueba",
			fecha_inicio=date(2026, 1, 1),
			fecha_termino=date(2026, 12, 31),
		)

	def test_periodo_rechaza_termino_anterior(self):
		self.periodo.fecha_termino = date(2025, 12, 31)
		with self.assertRaises(ValidationError):
			self.periodo.full_clean()

	def test_meta_requiere_objetivo_positivo(self):
		meta = Meta(periodo=self.periodo, item=self.item, funcionario=self.funcionario, objetivo=0, ponderador=100)
		with self.assertRaises(ValidationError):
			meta.full_clean()

	def test_solo_actividad_validada_aporta_al_avance(self):
		meta = Meta(periodo=self.periodo, item=self.item, funcionario=self.funcionario, objetivo=2, ponderador=100)
		Actividad.objects.create(
			funcionario=self.funcionario,
			periodo=self.periodo,
			item=self.item,
			descripcion="Actividad pendiente",
			accion="Acción de prueba",
			estado="pendiente",
		)
		Actividad.objects.create(
			funcionario=self.funcionario,
			periodo=self.periodo,
			item=self.item,
			descripcion="Actividad validada",
			accion="Acción de prueba",
			estado="validada",
		)
		self.assertEqual(meta.avance_aprobado, 1)
		self.assertEqual(meta.cumplimiento, 50)
