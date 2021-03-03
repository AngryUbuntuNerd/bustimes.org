from datetime import datetime
from ciso8601 import parse_datetime
from django.utils import timezone
from django.contrib.gis.geos import Point
from busstops.models import Service, DataSource
from ...models import VehicleLocation, VehicleJourney
from ..import_live_vehicles import ImportLiveVehiclesCommand


def get_datetime(string):
    if string:
        try:
            when = parse_datetime(string)
        except ValueError:
            when = datetime.strptime(string, '%d/%m/%Y %H:%M:%S')
        try:
            return timezone.make_aware(when)
        except ValueError:
            return when


class Command(ImportLiveVehiclesCommand):
    @staticmethod
    def add_arguments(parser):
        parser.add_argument('source_name', type=str)

    def handle(self, source_name, **options):
        self.source_name = source_name
        super().handle(**options)

    def do_source(self):
        try:
            super().do_source()
        except DataSource.MultipleObjectsReturned:
            self.source = DataSource.objects.get(name=self.source_name, url__contains='/nearby?')
            self.url = self.source.url

    @staticmethod
    def get_datetime(item):
        return get_datetime(item['RecordedAtTime'])

    def get_vehicle(self, item):
        code = item['VehicleRef']
        if code.isdigit():
            fleet_number = code
        else:
            fleet_number = None

        if self.source.settings and 'OperatorRef' in self.source.settings:
            item['OperatorRef'] = self.source.settings['OperatorRef']

        defaults = {'fleet_number': fleet_number, 'source': self.source, 'operator_id': item['OperatorRef']}

        if item['OperatorRef'] == 'SESX':
            operators = ['SESX', 'NIBS', 'GECL']
        else:
            operators = [item['OperatorRef']]

        try:
            return self.vehicles.get_or_create(defaults, code=code, operator__in=operators)
        except self.vehicles.model.MultipleObjectsReturned:
            return self.vehicles.filter(code=code, operator__in=operators).first(), False

    @classmethod
    def get_service(cls, item):
        line_name = item['PublishedLineName']
        if not line_name:
            return
        services = Service.objects.filter(current=True, line_name=line_name)
        if item['OperatorRef'] == 'SESX':
            services = services.filter(operator__in=['SESX', 'GECL'])
        else:
            services = services.filter(operator=item['OperatorRef'])
        try:
            return services.get()
        except Service.DoesNotExist as e:
            if line_name[-1].isalpha():
                item['PublishedLineName'] = line_name[:-1]
            elif line_name[0].isalpha():
                item['PublishedLineName'] = line_name[1:]
            else:
                print(e, item['OperatorRef'], line_name)
                return
            return cls.get_service(item)
        except Service.MultipleObjectsReturned:
            try:
                return services.filter(stops__locality__stoppoint=item['DestinationRef']).distinct().get()
            except (Service.DoesNotExist, Service.MultipleObjectsReturned) as e:
                print(e, item['OperatorRef'], item['PublishedLineName'], item['DestinationRef'])

    def get_journey(self, item, vehicle):
        code = item['JourneyCode']
        datetime = get_datetime(item['DepartureTime'])

        latest_journey = vehicle.latest_journey
        if latest_journey and latest_journey.code == code and latest_journey.datetime == datetime:
            journey = latest_journey
        else:
            try:
                journey = VehicleJourney.objects.select_related('service').get(vehicle=vehicle, datetime=datetime)
            except VehicleJourney.DoesNotExist:
                journey = VehicleJourney(datetime=datetime, data=item)

        journey.code = code
        journey.route_name = item['PublishedLineName']

        if not journey.service_id:
            journey.service = self.get_service(item)

        journey.destination = item['DestinationStopLocality']

        return journey

    def create_vehicle_location(self, item):
        bearing = item['Bearing']
        if bearing == '-1':
            bearing = None
        return VehicleLocation(
            latlong=Point(float(item['Longitude']), float(item['Latitude'])),
            heading=bearing
        )
