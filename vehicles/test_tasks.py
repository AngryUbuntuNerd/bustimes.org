from django.test import TestCase
from busstops.models import Service, SIRISource, Region, Operator
from .models import Vehicle
from . import tasks


class VehiclesTasksTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.siri_source = SIRISource.objects.create(name='HP')

        ea = Region.objects.create(id='EA', name='East Anglia')

        cls.badgerline = Operator.objects.create(region=ea, name='Badgerine', id='BADG', slug='badgerline',
                                                 parent='First')
        cls.pmt = Operator.objects.create(region=ea, name='Potteries Motor Traction', id='PMT', slug='pmt')

        cls.service = Service.objects.create(service_code='49', date='2018-12-25',
                                             description='Spixworth - Hunworth - Happisburgh')
        cls.service_2 = Service.objects.create(service_code='5', date='2018-12-25',
                                               description='Wolterton - Lakes Est')
        cls.service.operator.add(cls.badgerline)
        cls.service_2.operator.add(cls.pmt)

        Vehicle.objects.create(operator=cls.badgerline, code='POOP-11111')

    def test_create_service_code(self):
        tasks.create_service_code('Kingfisher', self.service.id, 'Sutton SIRI')

        code = self.service.servicecode_set.get()
        self.assertEqual('Sutton SIRI', code.scheme)
        self.assertEqual('Kingfisher', code.code)

    def test_create_journey_code(self):
        tasks.create_journey_code('Brazen Bottom', self.service.id, '601', self.siri_source.id)

        code = self.service.journeycode_set.get(siri_source=self.siri_source)
        self.assertEqual('Brazen Bottom', code.destination)
        self.assertEqual('601', code.code)

    def test_log_vehicle_journey(self):
        with self.assertNumQueries(1):
            tasks.log_vehicle_journey(None, {
                'OperatorRef': 'FMR',
                'VehicleRef': 'FMR-66692',
                'LineRef': '49',
                'OriginAimedDepartureTime': '2019-02-09T12:10:00Z',
                'FramedVehicleJourneyRef': {
                    'DatedVehicleJourneyRef': '311_4560_220',
                },
            }, None, 'EVESHAM Bus Station', 'Worcestershire', 'http://example.com')
        self.assertFalse(Vehicle.objects.filter(code='66692').exists())

        with self.assertNumQueries(14):
            tasks.log_vehicle_journey(self.service.id, {
                'OperatorRef': 'FMR',
                'VehicleRef': 'FMR-66692',
                'LineRef': '49',
                'OriginAimedDepartureTime': '2019-02-09T12:10:00Z',
                'FramedVehicleJourneyRef': {
                    'DatedVehicleJourneyRef': '311_4560_220',
                },
            }, None, 'EVESHAM Bus Station', 'Worcestershire', 'http://example.com')

        with self.assertNumQueries(4):
            tasks.log_vehicle_journey(self.service.id, {
                'OperatorRef': 'FMR',
                'VehicleRef': 'FMR-66692',
                'LineRef': '49',
                'OriginAimedDepartureTime': '2019-02-09T12:10:00Z',
                'FramedVehicleJourneyRef': {
                    'DatedVehicleJourneyRef': '311_4560_220',
                },
            }, None, 'EVESHAM Bus Station', 'Worcestershire', 'http://example.com')

        vehicle = Vehicle.objects.get(code='66692')
        self.assertEqual(vehicle.code, '66692')
        self.assertEqual(vehicle.operator, self.badgerline)

    def test_log_vehicle_journey_2(self):
        with self.assertNumQueries(11):
            tasks.log_vehicle_journey(self.service.id, {
                'OperatorRef': 'FMR',
                'VehicleRef': 'FMR-11111',
                'LineRef': '49',
                'OriginAimedDepartureTime': '2019-02-09T12:10:00Z',
                'FramedVehicleJourneyRef': {
                    'DatedVehicleJourneyRef': '311_4560_220',
                },
            }, None, 'EVESHAM Bus Station', 'Worcestershire', 'http://example.com')
        vehicle = Vehicle.objects.get(code='POOP-11111')
        self.assertEqual(1, vehicle.vehiclejourney_set.count())
