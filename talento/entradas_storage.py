from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class AlmacenEntradasPrivado(FileSystemStorage):
    """Archivos fuera de las URL públicas, con permisos locales privados."""

    def __init__(self):
        super().__init__(file_permissions_mode=0o600, directory_permissions_mode=0o700)

    def url(self, name):
        raise ValueError("Use la descarga autenticada de la entrada.")
