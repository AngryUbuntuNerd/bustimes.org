import asyncio
import websockets
import json
import pid
from asgiref.sync import sync_to_async
from uuid import uuid4
from datetime import datetime
from ciso8601 import parse_datetime
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.contrib.gis.db.models import Extent
from django.utils import timezone
from busstops.models import Service, DataSource
from ...models import Vehicle, VehicleJourney, VehicleLocation


class Command(BaseCommand):
    operators = {}
    vehicles = Vehicle.objects.select_related('latest_location__journey__service', 'livery')

    @staticmethod
    def add_arguments(parser):
        parser.add_argument('operator')

    def handle_item(self, item, operator):
        vehicle_id = item['status']['vehicle_id']
        parts = vehicle_id.split('-')

        vehicle = parts[6]

        try:
            vehicle = self.vehicles.get(operator__parent='First', code=vehicle)
            created = False
        except (Vehicle.MultipleObjectsReturned, Vehicle.DoesNotExist):
            defaults = {
                'source': self.source
            }
            if vehicle.isdigit():
                defaults['fleet_number'] = defaults['fleet_code'] = vehicle
            vehicle, created = self.vehicles.get_or_create(defaults, operator_id=operator, code=vehicle)

        recorded_at_time = parse_datetime(item['status']['recorded_at_time'])
        if not created and vehicle.latest_location and recorded_at_time <= vehicle.latest_location.datetime:
            return

        # origin aimed departure time
        departure_time = item['stops'][0]['date'] + ' ' + item['stops'][0]['time']
        departure_time = timezone.make_aware(datetime.strptime(departure_time, '%Y-%m-%d %H:%M'))

        journey = VehicleJourney.objects.filter(vehicle=vehicle, datetime=departure_time).first()

        if not journey:
            try:
                service = Service.objects.get(current=True, operator=item['operator'],
                                              line_name__iexact=item['line_name'])
            except (Service.DoesNotExist, Service.MultipleObjectsReturned) as e:
                print(e, operator, item['line_name'])
                service = None
            if service and not service.tracking:
                service.tracking = True
                service.save(update_fields=['tracking'])
            journey = VehicleJourney.objects.create(
                route_name=item['line_name'],
                direction=item['dir'],
                datetime=departure_time,
                source=self.source,
                destination=item['stops'][-1]['locality'].split(', ', 1)[0],
                vehicle=vehicle,
                service=service
            )

        heading = item['status']['bearing']
        if heading == -1:
            heading = None

        location = VehicleLocation(
            datetime=recorded_at_time,
            latlong=Point(*item['status']['location']['coordinates']),
            journey=journey,
            current=True,
            heading=heading
        )

        if not created and vehicle.latest_location_id:
            location.id = vehicle.latest_location_id

        location.save()
        location.redis_append()
        location.channel_send(vehicle)

        if not vehicle.latest_location_id:
            vehicle.latest_location = location
            vehicle.save(update_fields=['latest_location'])

    @sync_to_async
    def handle_data(self, data, operator):
        for item in data['params']['resource']['member']:
            self.handle_item(item, operator)

    @staticmethod
    def get_extent(operator):
        services = Service.objects.filter(operator=operator, current=True)
        return services.aggregate(Extent('geometry'))['geometry__extent']

    async def sock_it(self, operator, extent):
        min_lon, min_lat, max_lon, max_lat = extent
        message = json.dumps({
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "configuration",
            "params": {
                # "operator": operator,
                # "service": "X1",
                "min_lon": min_lon,
                "max_lon": max_lon,
                "min_lat": min_lat,
                "max_lat": max_lat
            }
        })

        async with websockets.connect(self.source.url) as websocket:
            print(message)
            await websocket.send(message)

            response = await websocket.recv()
            ok = True
            print(response)

            while ok:
                response = await websocket.recv()

                data = json.loads(response)
                try:
                    await self.handle_data(data, operator)
                    count = len(data['params']['resource']['member'])
                    if count >= 50:
                        print(operator, count)
                        ok = False
                except (KeyError, ValueError) as e:
                    print(e)

        width = max_lon - max_lon
        height = max_lat - min_lat
        if width < height:
            extent_1 = [
                min_lon,
                min_lat,
                max_lon,
                (min_lat + max_lat) / 2
            ]
            extent_2 = [
                min_lon,
                (min_lat + max_lat) / 2,
                max_lon,
                max_lat
            ]
        else:
            extent_1 = [
                min_lon,
                min_lat,
                (min_lon + max_lon) / 2,
                max_lat
            ]
            extent_2 = [
                (min_lon + max_lon) / 2,
                min_lat,
                max_lon,
                max_lat
            ]

        futures = [self.sock_it(operator, extent_1), self.sock_it(operator, extent_2)]
        await asyncio.wait(futures, return_when=asyncio.FIRST_EXCEPTION)

    def handle(self, operator, *args, **options):
        try:
            with pid.PidFile(f'First{operator}'):
                self.source = DataSource.objects.get(name='First')

                extent = self.get_extent(operator)
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.sock_it(operator, extent))
                loop.close()
        except pid.PidFileError:
            return
