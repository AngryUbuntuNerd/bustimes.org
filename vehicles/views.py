import redis
import json
import xml.etree.cElementTree as ET
import datetime
from django.db.models import Exists, OuterRef, Prefetch, Subquery
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.core.paginator import Paginator
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.gis.db.models import Extent
from django.contrib.postgres.aggregates import StringAgg
from django.http import HttpResponse, JsonResponse, Http404, HttpResponseBadRequest
from django.views.generic.detail import DetailView
from django.urls import reverse
from django.utils import timezone
# from django.utils.safestring import mark_safe
from busstops.utils import get_bounding_box
from busstops.models import Operator, Service
from bustimes.utils import format_timedelta
from .models import Vehicle, VehicleLocation, VehicleJourney, VehicleEdit, VehicleEditFeature, VehicleRevision
from .forms import EditVehiclesForm, EditVehicleForm
from .utils import get_vehicle_edit, do_revision, do_revisions
from .tasks import handle_siri_vm, handle_siri_sx


class Vehicles():
    def __init__(self, operator):
        self.operator = operator

    def __str__(self):
        return 'Vehicles'

    def get_absolute_url(self):
        return reverse('operator_vehicles', args=(self.operator.slug,))


def vehicles(request):
    return render(request, 'vehicles.html', {
        'operators': Operator.objects.filter(vehicle__withdrawn=False).distinct()
    })


def map(request):
    return render(request, 'map.html')


def operator_vehicles(request, slug=None, parent=None):
    operators = Operator.objects.select_related('region')
    if slug:
        try:
            operator = operators.get(slug=slug.lower())
        except Operator.DoesNotExist:
            operator = get_object_or_404(operators, operatorcode__code=slug, operatorcode__source__name='slug')
        vehicles = operator.vehicle_set.filter(withdrawn=False)
    elif parent:
        operators = list(operators.filter(parent=parent))
        vehicles = Vehicle.objects.filter(operator__in=operators, withdrawn=False).select_related('operator')
        if not operators:
            raise Http404
        operator = operators[0]

    vehicles = vehicles.order_by('fleet_number', 'fleet_code', 'reg', 'code')
    if not parent:
        latest_journeys = Subquery(VehicleJourney.objects.filter(
            vehicle=OuterRef('pk')
        ).order_by('-datetime').values('pk')[:1])
        latest_journeys = vehicles.filter(latest_location=None).annotate(latest_journey=latest_journeys)
        latest_journeys = VehicleJourney.objects.filter(id__in=latest_journeys.values('latest_journey'))
        prefetch = Prefetch('vehiclejourney_set',
                            queryset=latest_journeys.select_related('service'), to_attr='latest_journeys')
        vehicles = vehicles.prefetch_related(prefetch, 'features')
        pending_edits = VehicleEdit.objects.filter(approved=None, vehicle=OuterRef('id')).only('id')
        vehicles = vehicles.annotate(pending_edits=Exists(pending_edits))
        vehicles = vehicles.select_related('latest_location__journey__service')

    vehicles = vehicles.select_related('livery', 'vehicle_type')

    submitted = False
    revisions = False
    breadcrumb = [operator.region, operator]

    form = request.path.endswith('/edit')

    if form:
        if not request.user.is_authenticated:
            return redirect(f'/accounts/login/?next={request.path}')
        if request.user.trusted is False:
            raise PermissionDenied

        breadcrumb.append(Vehicles(operator))
        initial = {
            'operator': operator,
            'other_colour': '#ffffff',
        }
        if request.method == 'POST':
            form = EditVehiclesForm(request.POST, initial=initial, operator=operator, user=request.user)
            if not form.has_really_changed():
                form.add_error(None, 'You haven\'t changed anything')
            elif form.is_valid():
                data = {key: form.cleaned_data[key] for key in form.changed_data}
                vehicle_ids = request.POST.getlist('vehicle')
                now = timezone.now()

                revisions, changed_fields = do_revisions(vehicle_ids, data, request.user)
                if revisions and changed_fields:
                    Vehicle.objects.bulk_update((revision.vehicle for revision in revisions), changed_fields)
                    for revision in revisions:
                        revision.datetime = now
                    VehicleRevision.objects.bulk_create(revisions)
                    revisions = len(revisions)

                if data:
                    # this will fetch the vehicles list
                    # - slightly important that it occurs before any change of operator
                    ticked_vehicles = [v for v in vehicles if str(v.id) in vehicle_ids]
                    edits = [get_vehicle_edit(vehicle, data, now, request) for vehicle in ticked_vehicles]
                    edits = VehicleEdit.objects.bulk_create(edit for edit in edits if edit)
                    submitted = len(edits)
                    if 'features' in data:
                        for edit in edits:
                            edit.features.set(data['features'])
                form = EditVehiclesForm(initial=initial, operator=operator, user=request.user)
        else:
            form = EditVehiclesForm(initial=initial, operator=operator, user=request.user)

    if operator.name == 'National Express':
        vehicles = sorted(vehicles, key=lambda v: v.notes)

    if not vehicles:
        raise Http404

    paginator = Paginator(vehicles, 1000)
    page = request.GET.get('page')
    vehicles = paginator.get_page(page)

    features_column = not parent and any(vehicle.features.all() for vehicle in vehicles)

    columns = set(key for vehicle in vehicles if vehicle.data for key in vehicle.data)
    for vehicle in vehicles:
        vehicle.column_values = [vehicle.data and vehicle.data_get(key) or '' for key in columns]

    if not parent:
        today = timezone.localdate()
        for vehicle in vehicles:
            if vehicle.latest_location:
                journey = vehicle.latest_location.journey
                when = vehicle.latest_location.datetime
            elif vehicle.latest_journeys:
                journey = vehicle.latest_journeys[0]
                when = journey.datetime
            else:
                continue
            if journey.service:
                service = journey.service.get_line_name_and_brand()
            else:
                service = journey.route_name
            vehicle.last_seen = {
                'service': service,
                'when': when,
                'today': timezone.localdate(when) == today,
            }

    context = {
        'breadcrumb': breadcrumb,
        'parent': parent,
        'operators': parent and operators,
        'object': operator,
        'map': any(vehicle.latest_location_id for vehicle in vehicles),
        'vehicles': vehicles,
        'paginator': paginator,
        'code_column': any(vehicle.fleet_number_mismatch() for vehicle in vehicles),
        'branding_column': any(vehicle.branding and vehicle.branding != 'None' for vehicle in vehicles),
        'name_column': any(vehicle.name for vehicle in vehicles),
        'notes_column': any(vehicle.notes and vehicle.notes != 'Spare ticket machine' for vehicle in vehicles),
        'features_column': features_column,
        'columns': columns,
        'edits': submitted,
        'revisions': revisions,
        'revision': revisions and revision,
        'form': form,
    }

    if not parent and not form:
        context['map'] = any(vehicle.latest_location_id for vehicle in vehicles)

    return render(request, 'operator_vehicles.html', context)


def operator_map(request, slug):
    operator = get_object_or_404(Operator.objects.select_related('region'), slug=slug)

    services = operator.service_set.filter(current=True)
    extent = services.aggregate(Extent('geometry'))['geometry__extent']
    if not extent:
        extent = operator.vehicle_set.aggregate(Extent('latest_location__latlong'))['latest_location__latlong__extent']
    if not extent:
        raise Http404

    return render(request, 'operator_map.html', {
        'object': operator,
        'operator': operator,
        'breadcrumb': [operator.region, operator],
        'operator_id': operator.id,
        'extent': extent
    })


def get_locations(request):
    now = timezone.now()
    fifteen_minutes_ago = now - datetime.timedelta(minutes=15)
    locations = VehicleLocation.objects.filter(latest_vehicle__isnull=False, datetime__gte=fifteen_minutes_ago,
                                               current=True)

    try:
        bounding_box = get_bounding_box(request)
        locations = locations.filter(latlong__bboverlaps=bounding_box)
    except KeyError:
        pass

    if 'service' in request.GET:
        locations = locations.filter(journey__service=request.GET['service'])

    return locations


def vehicles_json(request):
    try:
        locations = get_locations(request).order_by()
    except ValueError:
        return HttpResponseBadRequest()
    locations = locations.select_related('journey__vehicle__livery', 'journey__vehicle__vehicle_type')

    if 'service' in request.GET:
        extended = False
        locations = locations.prefetch_related('journey__vehicle__features')
    else:
        extended = True
        locations = locations.select_related('journey__service', 'journey__vehicle__operator')
        locations = locations.defer('journey__service__geometry', 'journey__service__search_vector')

    return JsonResponse({
        'type': 'FeatureCollection',
        'features': [location.get_json(extended=extended) for location in locations]
    })


def get_dates(journeys, vehicle=None, service=None):
    if vehicle:
        key = f'vehicle:{vehicle.id}:dates'
    else:
        key = f'service:{service.id}:dates'

    dates = cache.get(key)

    if not dates:
        dates = list(journeys.values_list('datetime__date', flat=True).distinct().order_by('datetime__date'))
        if dates:
            now = timezone.localtime()
            if dates[-1] == now.date():
                time_until_midnight = datetime.timedelta(days=1)
                time_until_midnight -= datetime.timedelta(hours=now.hour, minutes=now.minute, seconds=now.second)
                time_until_midnight = time_until_midnight.total_seconds()
                if time_until_midnight > 0:
                    cache.set(key, dates, time_until_midnight)

    return dates


def service_vehicles_history(request, slug):
    service = get_object_or_404(Service, slug=slug)
    journeys = service.vehiclejourney_set
    date = request.GET.get('date')
    if date:
        try:
            date = datetime.date.fromisoformat(date)
        except ValueError:
            date = None
    dates = get_dates(journeys, service=service)
    if not dates:
        raise Http404()
    if not date:
        date = dates[-1]
    # calls = Call.objects.filter(journey=OuterRef('pk'))
    # journeys = journeys.annotate(calls=Exists(calls))
    journeys = journeys.filter(datetime__date=date).select_related('vehicle').order_by('datetime')
    try:
        r = redis.from_url(settings.REDIS_URL)
        pipe = r.pipeline()
        for journey in journeys:
            pipe.exists(f'journey{journey.id}')
        locations = pipe.execute()
        previous = None
        for i, journey in enumerate(journeys):
            journey.locations = locations[i]
            if journey.locations:
                if previous:
                    previous.next = journey
                    journey.previous = previous
                previous = journey
    except redis.exceptions.ConnectionError:
        pass

    operator = service.operator.select_related('region').first()
    return render(request, 'vehicles/vehicle_detail.html', {
        'breadcrumb': [operator, service],
        'date': date,
        'dates': dates,
        'object': service,
        'journeys': journeys,
    })


class VehicleDetailView(DetailView):
    model = Vehicle
    queryset = model.objects.select_related('operator', 'operator__region',
                                            'vehicle_type', 'livery').prefetch_related('features')
    slug_field = 'reg__iexact'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        journeys = self.object.vehiclejourney_set
        context['pending_edits'] = self.object.vehicleedit_set.filter(approved=None).exists()
        dates = get_dates(journeys, vehicle=self.object)
        if self.object.operator:
            context['breadcrumb'] = [self.object.operator, Vehicles(self.object.operator)]

            context['previous'] = self.object.get_previous()
            context['next'] = self.object.get_next()

        if dates:
            context['dates'] = dates
            date = self.request.GET.get('date')
            if date:
                try:
                    date = datetime.date.fromisoformat(date)
                except ValueError:
                    date = None
            if not date:
                date = context['dates'][-1]
            context['date'] = date

            journeys = journeys.filter(datetime__date=date).order_by('datetime')
            # calls = Call.objects.filter(journey=OuterRef('pk'))
            # locations = VehicleLocation.objects.filter(journey=OuterRef('pk'))
            journeys = journeys.select_related('service')

            try:
                r = redis.from_url(settings.REDIS_URL)
                pipe = r.pipeline()
                for journey in journeys:
                    pipe.exists(f'journey{journey.id}')
                locations = pipe.execute()
                previous = None
                for i, journey in enumerate(journeys):
                    journey.locations = locations[i]
                    if journey.locations:
                        if previous:
                            previous.next = journey
                            journey.previous = previous
                        previous = journey
            except redis.exceptions.ConnectionError:
                pass

            context['journeys'] = journeys

        return context


@login_required
def edit_vehicle(request, vehicle_id):
    if request.user.trusted is False:
        raise PermissionDenied
    vehicle = get_object_or_404(Vehicle.objects.select_related('vehicle_type', 'livery', 'operator'), id=vehicle_id)
    if not vehicle.editable():
        raise Http404
    submitted = False
    revision = None
    initial = {
        'operator': vehicle.operator,
        'reg': vehicle.reg,
        'vehicle_type': vehicle.vehicle_type,
        'features': vehicle.features.all(),
        'colours': str(vehicle.livery_id or vehicle.colours),
        'other_colour': '#ffffff',
        'branding': vehicle.branding,
        'name': vehicle.name,
        'previous_reg': vehicle.data and vehicle.data.get('Previous reg') or None,
        'depot': vehicle.data and vehicle.data.get('Depot') or None,
        'notes': vehicle.notes,
        'withdrawn': vehicle.withdrawn
    }
    if vehicle.fleet_code:
        initial['fleet_number'] = vehicle.fleet_code
    elif vehicle.fleet_number is not None:
        initial['fleet_number'] = str(vehicle.fleet_number)

    if request.method == 'POST':
        form = EditVehicleForm(request.POST,
                               initial=initial, operator=vehicle.operator, vehicle=vehicle, user=request.user)
        if not form.has_really_changed():
            form.add_error(None, 'You haven\'t changed anything')
        elif form.is_valid():
            data = {key: form.cleaned_data[key] for key in form.changed_data}
            now = timezone.now()
            revision = do_revision(vehicle, data, request.user)
            if revision:
                revision.datetime = now
                revision.save()

            form = None

            if data:
                edit = get_vehicle_edit(vehicle, data, now, request)
                edit.save()
                if 'features' in data:
                    for feature in vehicle.features.all():
                        if feature not in data['features']:
                            VehicleEditFeature.objects.create(
                                edit=edit,
                                feature=feature,
                                add=False
                            )
                    for feature in data['features']:
                        edit.features.add(feature)
                submitted = True
    else:
        form = EditVehicleForm(initial=initial, operator=vehicle.operator, vehicle=vehicle, user=request.user)

    if vehicle.operator:
        breadcrumb = [vehicle.operator, Vehicles(vehicle.operator), vehicle]
    else:
        breadcrumb = [vehicle]

    response = render(request, 'edit_vehicle.html', {
        'breadcrumb': breadcrumb,
        'form': form,
        'object': vehicle,
        'vehicle': vehicle,
        'previous': vehicle.get_previous(),
        'next': vehicle.get_next(),
        'submitted': submitted,
        'revision': revision,
        'pending_edits': form and vehicle.vehicleedit_set.filter(approved=None).exists()
    })

    return response


def vehicle_history(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    revisions = vehicle.vehiclerevision_set.select_related(
        'vehicle', 'from_livery', 'to_livery', 'from_type', 'to_type', 'user'
    ).order_by('-id')
    return render(request, 'vehicle_history.html', {
        'breadcrumb': [vehicle.operator, vehicle.operator and Vehicles(vehicle.operator), vehicle],
        'vehicle': vehicle,
        'revisions': revisions
    })


def vehicles_history(request):
    revisions = VehicleRevision.objects.all().select_related(
        'vehicle', 'from_livery', 'to_livery', 'from_type', 'to_type', 'user'
    )
    revisions = revisions.order_by('-id')
    paginator = Paginator(revisions, 100)
    page = request.GET.get('page')
    return render(request, 'vehicle_history.html', {
        'revisions': paginator.get_page(page)
    })


def journey_json(request, pk):
    data = {}

    journey = get_object_or_404(VehicleJourney, pk=pk)

    if journey.trip_id:
        try:
            data['stops'] = [{
                'name': stop_time.stop.get_qualified_name() if stop_time.stop else stop_time.stop_code,
                'aimed_arrival_time': format_timedelta(stop_time.arrival) if stop_time.arrival else None,
                'aimed_departure_time': format_timedelta(stop_time.departure) if stop_time.departure else None,
            } for stop_time in journey.trip.stoptime_set.select_related('stop__locality')]
        except ObjectDoesNotExist:
            pass

    try:
        r = redis.from_url(settings.REDIS_URL)
        locations = r.lrange(f'journey{pk}', 0, -1)
        if locations:
            locations = (json.loads(location) for location in locations)
            data['locations'] = [{
                'coordinates': location[1],
                'delta': location[3],
                'direction': location[2],
                'datetime': location[0]
            } for location in locations]
    except redis.exceptions.ConnectionError:
        pass

    return JsonResponse(data)


def location_detail(request, location_id):
    locations = VehicleLocation.objects.select_related('journey__vehicle__vehicle_type', 'journey__service')
    locations = locations.annotate(features=StringAgg('journey__vehicle__features__name', ', '))
    locations = locations.defer('journey__service__geometry', 'journey__service__search_vector')
    location = get_object_or_404(locations, id=location_id)
    return render(request, 'location_detail.html', {
        'location': location
    })


def journey_debug(request, pk):
    journey = get_object_or_404(VehicleJourney, id=pk)
    return JsonResponse(journey.data or {})


def siri(request):
    body = request.body.decode()
    if not body:
        return HttpResponse()
    if 'HeartbeatNotification' in body:
        for _, element in ET.iterparse(request):
            if element.tag == '{http://www.siri.org.uk/siri}ProducerRef':
                cache.set(f'Heartbeat:{element.text}', True, 300)  # 5 minutes
                break
    elif 'VehicleLocation' in body:
        handle_siri_vm.delay(body)
    else:
        assert 'SituationElement' in body
        handle_siri_sx.delay(body)
    return HttpResponse(f"""<?xml version="1.0" ?>
<Siri xmlns="http://www.siri.org.uk/siri" version="1.3">
  <DataReceivedAcknowledgement>
    <ResponseTimestamp>{timezone.now().isoformat()}</ResponseTimestamp>
    <Status>true</Status>
  </DataReceivedAcknowledgement>
</Siri>""", content_type='text/xml')
