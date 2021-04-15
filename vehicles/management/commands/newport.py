from ciso8601 import parse_datetime
from django.contrib.gis.geos import Point
from busstops.models import Service
from ...models import VehicleLocation, VehicleJourney
from ..import_live_vehicles import ImportLiveVehiclesCommand


class Command(ImportLiveVehiclesCommand):
    source_name = 'newport'

    def get_items(self):
        response = self.session.get(self.source.url, **self.source.settings)
        return response.json().get('items')

    @staticmethod
    def get_datetime(item):
        return parse_datetime(item['reported'])

    def get_vehicle(self, item):
        code = item['vehicleRef']
        defaults = {
            'fleet_code': code
        }
        if code.isdigit():
            defaults['fleet_number'] = code

        try:
            return self.vehicles.get_or_create(defaults, code=code, operator_id='NWPT')
        except self.vehicles.model.MultipleObjectsReturned:
            return self.vehicles.filter(code=code, operator='NWPT').first(), False

    @classmethod
    def get_service(cls, item):
        line_name = item['routeName']
        if not line_name:
            return
        services = Service.objects.filter(current=True, line_name=line_name, operator='NWPT')
        try:
            return services.get()
        except (Service.MultipleObjectsReturned, Service.DoesNotExist) as e:
            print(e)

    def get_journey(self, item, vehicle):
        datetime = parse_datetime(item['scheduledTripStartTime'])

        latest_journey = vehicle.latest_journey
        if latest_journey and latest_journey.datetime == datetime:
            return latest_journey
        else:
            try:
                return vehicle.vehiclejourney_set.get(datetime=datetime)
            except VehicleJourney.DoesNotExist:
                journey = VehicleJourney(datetime=datetime, data=item)

        journey.route_name = item['routeName']

        if not journey.service_id:
            journey.service = self.get_service(item)

        journey.destination = item.get('destination', '')

        journey.code = f'{datetime.hour:02}{datetime.minute:02}'
        journey.trip = journey.get_trip()
        if journey.trip and journey.trip.destination and journey.trip.destination.locality:
            journey.destination = str(journey.trip.destination.locality)

        return journey

    def create_vehicle_location(self, item):
        position = item['position']
        bearing = position.get('bearing')
        if bearing == '-1':
            bearing = None
        return VehicleLocation(
            latlong=Point(float(position['longitude']), float(position['latitude'])),
            heading=bearing
        )