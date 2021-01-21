import xml.etree.cElementTree as ET
from io import StringIO
from ciso8601 import parse_datetime
from celery import shared_task
from busstops.models import DataSource, ServiceCode, Operator
from django.db.models import Q
from disruptions.management.commands.import_siri_sx import handle_item as siri_sx
from .management.commands import import_sirivm, import_bod_avl
from .models import JourneyCode, Vehicle, VehicleJourney


@shared_task
def bod_avl(items):
    command = import_bod_avl.Command().do_source()
    for item in items:
        command.handle_item(item)
    command.save()


@shared_task
def handle_siri_vm(request_body):
    command = import_sirivm.Command()
    command.source = DataSource.objects.get(name='TransMach')
    iterator = ET.iterparse(StringIO(request_body))
    for _, element in iterator:
        if element.tag[:5] != '{http':
            element.tag = '{http://www.siri.org.uk/siri}' + element.tag
        if element.tag[-15:] == 'VehicleActivity':
            command.handle_item(element)
            element.clear()
    command.save()


@shared_task
def handle_siri_sx(request_body):
    source = DataSource.objects.get(name='Transport for the North')
    iterator = ET.iterparse(StringIO(request_body))
    situation_ids = []
    for _, element in iterator:
        if element.tag[:29] == '{http://www.siri.org.uk/siri}':
            element.tag = element.tag[29:]
            if element.tag == 'SubscriptionRef':
                subscription_ref = element.text
            if element.tag == 'PtSituationElement':
                situation_ids.append(siri_sx(element, source))
                element.clear()

    if subscription_ref != source.settings.get('subscription_ref'):
        source.settings['subscription_ref'] = subscription_ref
        source.save(update_fields=['settings'])
        source.situation_set.filter(current=True).exclude(id__in=situation_ids).update(current=False)


@shared_task
def create_service_code(line_ref, service_id, scheme):
    ServiceCode.objects.update_or_create({'code': line_ref}, service_id=service_id, scheme=scheme)


@shared_task
def create_journey_code(destination, service_id, journey_ref, source_id):
    JourneyCode.objects.update_or_create({
        'destination': destination
    }, service_id=service_id, code=journey_ref, siri_source_id=source_id)


@shared_task
def log_vehicle_journey(service, data, time, destination, source_name, url):
    operator_ref = data.get('OperatorRef')
    if operator_ref and operator_ref == 'MCG':
        return

    if not time:
        time = data.get('OriginAimedDepartureTime')
    if not time:
        return

    vehicle = data['VehicleRef']

    if operator_ref and vehicle.startswith(f'{operator_ref}-'):
        vehicle = vehicle[len(operator_ref) + 1:]
    elif operator_ref == 'FAB' and vehicle.startswith('111-'):  # Aberdeen
        vehicle = vehicle[4:]

    if not vehicle or vehicle == '-':
        return

    if 'FramedVehicleJourneyRef' in data and 'DatedVehicleJourneyRef' in data['FramedVehicleJourneyRef']:
        journey_ref = data['FramedVehicleJourneyRef']['DatedVehicleJourneyRef']
    else:
        journey_ref = None

    operator = None
    if operator_ref:
        try:
            operator = Operator.objects.get(id=operator_ref)
        except Operator.DoesNotExist:
            if not service:
                return

    if not operator:
        try:
            operator = Operator.objects.get(service=service)
        except (Operator.DoesNotExist, Operator.MultipleObjectsReturned):
            return

    if operator.parent == 'Stagecoach' or operator.id in {'EYMS', 'MCGL'}:
        return

    data_source, _ = DataSource.objects.get_or_create({'url': url}, name=source_name)

    defaults = {
        'source': data_source,
        'operator': operator,
        'code': vehicle
    }

    vehicles = Vehicle.objects
    if operator.parent:
        vehicles = Vehicle.objects.filter(operator__parent=operator.parent)
    else:
        vehicles = operator.vehicle_set

    vehicles = vehicles.select_related('latest_location')

    if vehicle.isdigit():
        defaults['fleet_number'] = vehicle
        vehicles = vehicles.filter(Q(code=vehicle)
                                   | Q(code__endswith=f'-{vehicle}') | Q(code__startswith=f'{vehicle}_-_'))
    else:
        vehicles = vehicles.filter(code=vehicle)

    vehicle, created = vehicles.get_or_create(defaults)

    if journey_ref and journey_ref.startswith('Unknown'):
        journey_ref = ''

    time = parse_datetime(time)

    if vehicle.latest_location and (time - vehicle.latest_location.datetime).total_seconds() < 7200:
        # vehicle tracked 2 hours ago (or more recently)
        return

    destination = destination or ''
    route_name = data.get('LineName') or data.get('LineRef')
    if VehicleJourney.objects.filter(vehicle=vehicle, datetime=time).exists():
        return

    if journey_ref:
        try:
            existing_journey = VehicleJourney.objects.get(vehicle=vehicle, route_name=route_name, code=journey_ref,
                                                          datetime__date=time.date())
            if existing_journey.datetime != time:
                existing_journey.datetime = time
                existing_journey.save(update_fields=['datetime'])
        except VehicleJourney.DoesNotExist:
            VehicleJourney.objects.create(vehicle=vehicle, service_id=service, route_name=route_name, data=data,
                                          code=journey_ref, datetime=time, source=data_source, destination=destination)
        except VehicleJourney.MultipleObjectsReturned:
            return
    else:
        VehicleJourney.objects.create(vehicle=vehicle, service_id=service, route_name=route_name,
                                      datetime=time, source=data_source, destination=destination)
