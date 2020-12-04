from time import sleep
from datetime import timedelta
from pytz.exceptions import AmbiguousTimeError
from ciso8601 import parse_datetime
from requests import RequestException
from django.contrib.gis.geos import Point
from django.utils import timezone
from busstops.models import Service
from bustimes.models import get_calendars, Trip
from ...models import VehicleLocation, VehicleJourney
from ..import_live_vehicles import ImportLiveVehiclesCommand


class Command(ImportLiveVehiclesCommand):
    source_name = 'National coach code'
    operators = ['NATX', 'NXSH', 'NXAP', 'WAIR']
    url = 'https://coachtracker.nationalexpress.com/api/eta/routes/{}/{}'
    sleep = 1.5

    @staticmethod
    def get_datetime(item):
        try:
            return timezone.make_aware(parse_datetime(item['live']['timestamp']['dateTime']))
        except AmbiguousTimeError:
            return timezone.make_aware(parse_datetime(item['live']['timestamp']['dateTime']), is_dst=True)

    def get_items(self):
        now = self.source.datetime
        time_since_midnight = timedelta(hours=now.hour, minutes=now.minute, seconds=now.second,
                                        microseconds=now.microsecond)
        trips = Trip.objects.filter(calendar__in=get_calendars(now),
                                    start__lte=time_since_midnight + timedelta(minutes=5),
                                    end__gte=time_since_midnight - timedelta(minutes=30))
        services = Service.objects.filter(operator__in=self.operators, route__trip__in=trips).distinct()
        for service in services.values('line_name'):
            line_name = service['line_name'].replace('-x', 'X')
            for direction in 'OI':
                try:
                    res = self.session.get(self.url.format(line_name, direction), timeout=5)
                except RequestException as e:
                    print(e)
                    continue
                if not res.ok:
                    print(res.url, res)
                    continue
                if direction != res.json()['dir']:
                    print(res.url)
                for item in res.json()['services']:
                    if item['live']:
                        yield(item)
            self.save()
            sleep(self.sleep)

    def get_vehicle(self, item):
        return self.vehicles.get_or_create(source=self.source, operator_id=self.operators[0],
                                           code=item['live']['vehicle'])

    def get_journey(self, item, vehicle):
        journey = VehicleJourney()

        try:
            journey.datetime = timezone.make_aware(parse_datetime(item['startTime']['dateTime']))
        except AmbiguousTimeError:
            journey.datetime = timezone.make_aware(parse_datetime(item['startTime']['dateTime']), is_dst=True)

        latest_location = vehicle.latest_location
        if latest_location and journey.datetime == latest_location.journey.datetime:
            journey = latest_location.journey
        else:
            try:
                journey = VehicleJourney.objects.get(vehicle=vehicle, datetime=journey.datetime)
            except VehicleJourney.DoesNotExist:
                pass

        journey.route_name = item['route']
        if journey.route_name.endswith('X'):
            journey.route_name = f'{journey.route_name[:-1]}-x'

        journey.destination = item['arrival']
        journey.code = item['journeyId']

        latest_location = vehicle.latest_location
        if latest_location and journey.route_name == latest_location.journey.route_name:
            if latest_location.journey.service:
                journey.service = vehicle.latest_location.journey.service
                return journey

        try:
            journey.service = Service.objects.get(operator__in=self.operators, line_name=journey.route_name,
                                                  current=True)
        except (Service.DoesNotExist, Service.MultipleObjectsReturned) as e:
            print(journey.route_name, e)

        return journey

    def create_vehicle_location(self, item):
        heading = item['live']['bearing']
        return VehicleLocation(
            latlong=Point(item['live']['lon'], item['live']['lat']),
            heading=heading
        )
