"""PostgreSQL synthetic tests. Independent PD_TEST_DB_* variables only."""
import os
from .settings_test import *

_prueba_nombre = os.environ.get("PD_TEST_DB_NAME", "dahiedhi_pruebas")
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": _prueba_nombre,
    "USER": os.environ.get("PD_TEST_DB_USER", "postgres"),
    "PASSWORD": os.environ.get("PD_TEST_DB_PASSWORD", ""),
    "HOST": os.environ.get("PD_TEST_DB_HOST", "127.0.0.1"),
    "PORT": os.environ.get("PD_TEST_DB_PORT", "5432"),
    "TEST": {"NAME": "test_" + _prueba_nombre},
}}
