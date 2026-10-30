from pathlib import Path
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ValidationError


class AlmacenPrivado(FileSystemStorage):
    def url(self, name):
        raise NotImplementedError('Los adjuntos solo se descargan mediante una vista autorizada.')


def almacen_privado():
    return AlmacenPrivado(location=getattr(settings, 'SOLICITUDES_PRIVATE_ROOT', settings.BASE_DIR / 'var' / 'solicitudes_privadas'))


def validar_adjunto(archivo):
    if not archivo:
        return
    if archivo.size > 5 * 1024 * 1024:
        raise ValidationError('El archivo no debe superar 5 MB.')
    cabecera = archivo.read(8)
    archivo.seek(0)
    extension = Path(archivo.name).suffix.lower()
    valido = ((extension == '.pdf' and cabecera.startswith(b'%PDF-')) or
              (extension == '.png' and cabecera == b'\x89PNG\r\n\x1a\n') or
              (extension in ('.jpg', '.jpeg') and cabecera.startswith(b'\xff\xd8\xff')))
    if not valido:
        raise ValidationError('Solo se permiten PDF, PNG o JPEG con contenido del formato indicado.')
