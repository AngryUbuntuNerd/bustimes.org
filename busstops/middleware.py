from django.shortcuts import redirect
from multidb.pinning import pin_this_thread, unpin_this_thread
from .models import Service, StopPoint


def real_ip_middleware(get_response):
    def middleware(request):
        if 'HTTP_X_REAL_IP' in request.META:
            request.META['REMOTE_ADDR'] = request.META['HTTP_X_REAL_IP']
        return get_response(request)
    return middleware


def not_found_redirect_middleware(get_response):
    """
    Redirects from /services/17-N4-_-y08-1 to /services/17-N4-_-y08-2, for example,
    if the former doesn't exist (any more) and the latter does.
    """

    def middleware(request):
        response = get_response(request)

        if response.status_code == 404:
            suggestion = None

            if request.path.startswith('/services/'):
                service_code = request.path.split('/')[-1]
                service_code_parts = service_code.split('-')

                if len(service_code_parts) >= 4:
                    suggestion = Service.objects.filter(
                        service_code__icontains='_' + '-'.join(service_code_parts[:4]),
                        current=True
                    ).first()
                    if suggestion is None:
                        suggestion = Service.objects.filter(
                            slug__startswith='-'.join(service_code_parts[:-1]),
                            current=True
                        ).first()
                if suggestion is None:
                    suggestion = Service.objects.filter(
                        service_code__iexact=service_code,
                        current=True
                    ).first()

            elif request.path.startswith('/stops/'):
                suggestion = StopPoint.objects.only('atco_code').filter(naptan_code=request.path.split('/')[-1]).first()

            if suggestion is not None:
                return redirect(suggestion)

        return response

    return middleware


def pin_db_middleware(get_response):
    def middleware(request):
        if request.method == 'POST' or request.path.startswith('/admin/') or '/edit' in request.path:
            pin_this_thread()
        else:
            unpin_this_thread()
        return get_response(request)

    return middleware
