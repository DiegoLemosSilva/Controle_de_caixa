"""Views públicas para a instalação do aplicativo."""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET


@require_GET
def service_worker(request):
    """Sirva o Service Worker na raiz para permitir escopo sobre a aplicação."""
    path = finders.find('pwa/service-worker.js')
    if not path:
        raise Http404
    response = FileResponse(
        Path(path).open('rb'), content_type='application/javascript; charset=utf-8'
    )
    response['Cache-Control'] = 'no-cache'
    return response
