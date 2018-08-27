import ciso8601
from django.contrib.gis.geos import Point
from django.db.utils import IntegrityError
from ..import_live_vehicles import ImportLiveVehiclesCommand
from ...models import Operator, Vehicle, VehicleLocation, Service


class Command(ImportLiveVehiclesCommand):
    operators = {}
    source_name = 'ZipTrip'
    url = 'https://ziptrip-vps.api.urbanthings.cloud/api/0.2/vehiclepositions?maxLat=60&maxLng=10&minLng=-50&minLat=40'

    def get_items(self):
        return super().get_items()['items']

    def get_vehicle_and_service(self, item):
        operator_id, vehicle = item['vehicleCode'].split('_', 1)

        if operator_id == 'BOWE':
            operator_id = 'HIPK'
            if item['routeName'] == '199':
                item['routeName'] = 'Skyline 199'
            if item['routeName'] == 'TP':
                item['routeName'] = 'Transpeak'
        elif operator_id == 'LAS':
            operator_id = ('GAHL', 'LGEN')
        elif operator_id == '767STEP':
            operator_id = 'SESX'
        elif operator_id == 'CB':
            operator_id = ('CBUS', 'CACB')
        elif operator_id == 'IOM':
            operator_id = 'IMHR'
            if item['routeName'] == 'IMR':
                item['routeName'] = 'Isle of Man Steam Railway'
            elif item['routeName'] == 'HT':
                item['routeName'] = 'Douglas Bay Horse Tram'
            elif item['routeName'] == 'MER':
                item['routeName'] = 'Manx Electric Railway'
            elif item['routeName'] == 'SMR':
                item['routeName'] = 'Snaefell Mountain Railway'
            else:
                operator_id = 'bus-vannin'

        if operator_id in self.operators:
            operator = self.operators[operator_id]
        elif type(operator_id) is str:
            try:
                operator = Operator.objects.get(id=operator_id)
            except Operator.DoesNotExist:
                operator = None
            self.operators[operator_id] = operator
        else:
            operator = None

        if vehicle.isdigit():
            fleet_number = vehicle
        else:
            fleet_number = None
        defaults = {
             'fleet_number': fleet_number
        }
        if operator:
            defaults['source'] = self.source
            try:
                vehicle, created = Vehicle.objects.get_or_create(defaults, operator=operator, code=vehicle)
            except IntegrityError:
                defaults['operator'] = operator
                vehicle, created = Vehicle.objects.get_or_create(defaults, source=self.source, code=vehicle)
        else:
            vehicle, created = Vehicle.objects.get_or_create(defaults, source=self.source, code=vehicle)

        service = None
        services = Service.objects.filter(line_name__iexact=item['routeName'], current=True)
        try:
            if operator:
                service = services.get(operator=operator)
            elif type(operator_id) is tuple:
                service = services.get(operator__in=operator_id)
                if not vehicle.operator:
                    vehicle.operator = service.operator.first()
                    vehicle.save()
            elif operator_id != 'Rtl':
                print(item)
        except (Service.MultipleObjectsReturned, Service.DoesNotExist) as e:
            print(e, operator_id, item['routeName'])

        return vehicle, created, service

    def create_vehicle_location(self, item, vehicle, service):
        bearing = item.get('bearing')
        while bearing and bearing < 0:
            bearing += 180
        position = item['position']
        return VehicleLocation(
            datetime=ciso8601.parse_datetime(item['reported']),
            latlong=Point(position['longitude'], position['latitude']),
            heading=bearing
        )
