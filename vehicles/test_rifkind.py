import vcr
from freezegun import freeze_time
from django.test import TestCase, override_settings
from busstops.models import Region, Service, StopPoint, DataSource, Operator
from bustimes.models import Route, Calendar, Trip, StopTime


class RifkindTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        source = DataSource.objects.create(name='Rifkind', url='https://rifkind.co.uk/api.php apikey')

        destination = StopPoint.objects.create(common_name="Inspector Resnick's house", active=True)
        region = Region.objects.create(id='EM', name='EM')
        operator = Operator.objects.create(id='TBTN', region=region, name='Trent Burton')
        service = Service.objects.create(service_code='skylink', line_name='rainbow one', date='2019-06-08')
        service.operator.add(operator)
        route = Route.objects.create(service=service, source=source)
        calendar = Calendar.objects.create(start_date='2019-11-17', mon=False, tue=False, wed=False, thu=False,
                                           fri=False, sat=False, sun=True)
        trip = Trip.objects.create(route=route, start='12:25', end='12:35', calendar=calendar, destination=destination)
        StopTime.objects.create(stop_code='1000DCMP4529', arrival='12:30', departure='12:30', sequence=0, trip=trip)

    @override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
    def test_vehicles_json(self):
        with vcr.use_cassette('data/vcr/rifkind.yaml'):

            with freeze_time('2019-11-17'):
                with self.assertNumQueries(4):
                    self.client.get('/vehicles.json?service=skylink')

            with freeze_time('2019-11-17 12:20+00:00'):
                with self.assertNumQueries(37):
                    self.client.get('/vehicles.json?service=skylink')
                with self.assertNumQueries(1):
                    res = self.client.get('/vehicles.json?service=skylink')

        json = res.json()
        self.assertEqual(len(json['features']), 2)