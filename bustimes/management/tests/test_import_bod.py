import zipfile
import datetime
from ciso8601 import parse_datetime
from tempfile import TemporaryDirectory
from pathlib import Path
from vcr import use_cassette
from unittest.mock import patch
import time_machine
from django.test import TestCase, override_settings
from django.core.management import call_command
from busstops.models import Region, Operator, DataSource, OperatorCode, Service, ServiceCode
from vehicles.models import VehicleJourney
from ...models import Route, BankHoliday, CalendarBankHoliday, VehicleType, Block, Garage


FIXTURES_DIR = Path(__file__).resolve().parent / 'fixtures'


class MockZipFile:
    def __init__(self):
        pass


class ImportBusOpenDataTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        ea = Region.objects.create(pk='EA', name='East Anglia')
        lynx = Operator.objects.create(id='LYNX', region=ea, name='Lynx')
        scpb = Operator.objects.create(id='SCCM', region=ea, name='Stagecoach East', parent='Stagecoach')
        schu = Operator.objects.create(id='SCHU', region=ea, name='Huntingdon', parent='Stagecoach')
        source = DataSource.objects.create(name='National Operator Codes')
        OperatorCode.objects.bulk_create([
            OperatorCode(operator=lynx, source=source, code='LYNX'),
            OperatorCode(operator=scpb, source=source, code='SCPB'),
            OperatorCode(operator=schu, source=source, code='SCHU')
        ])

    @use_cassette(str(FIXTURES_DIR / 'bod_lynx.yaml'))
    @time_machine.travel(datetime.datetime(2020, 5, 1))
    @override_settings(BOD_OPERATORS=[
        ('LYNX', 'EA', {
            'CO': 'LYNX',
        }, False),
    ])
    def test_import_bod(self):
        with TemporaryDirectory() as directory:
            with override_settings(DATA_DIR=Path(directory)):
                call_command('import_bod', '0123456789abc19abc190123456789abc19abc19')

                with self.assertNumQueries(5):
                    call_command('import_bod', '0123456789abc19abc190123456789abc19abc19')

                route = Route.objects.get()

                response = self.client.get(route.get_absolute_url())
                self.assertEqual(200, response.status_code)

        self.assertEqual(route.source.name, 'Lynx_Clenchwarton_54_20200330')
        self.assertEqual(route.source.url, 'https://data.bus-data.dft.gov.uk/category/dataset/35/download/')
        self.assertEqual(route.source.sha1, 'a5eaa3ef8ddefd702833d52d0148adfa0a504e9a')

        self.assertEqual(route.code, 'Lynx_Clenchwarton_54_20200330')

        with self.assertNumQueries(3):
            response = self.client.get(f'/services/{route.service_id}.json')
        self.assertTrue(response.json()['geometry'])

        self.assertFalse(route.service.public_use)

        # a TicketMachineServiceCode should have been created
        service_code = ServiceCode.objects.get()
        self.assertEqual(service_code.code, '1')
        self.assertEqual(service_code.scheme, 'SIRI')

        response = self.client.get(f'/services/{route.service_id}/timetable')

        self.assertContains(response, """
            <tr>
                <th class="stop-name" scope="row">
                    <a href="/stops/2900W0321">Walpole St Peter Lion Store</a>
                </th>
                <td>12:19</td>
            </tr>""", html=True)

        self.assertContains(
            response,
            'Timetable data from '
            '<a href="https://data.bus-data.dft.gov.uk/category/dataset/35/">Lynx/Bus Open Data Service</a>, '
            '1 April 2020.'
        )

        # test views:

        trip = route.trip_set.first()

        response = self.client.get(f'/trips/{trip.id}.json')
        self.assertEqual(27, len(response.json()['times']))

        response = self.client.get(trip.get_absolute_url())

        self.assertContains(response, """<tr class="minor">
                <td class="stop-name">
                        <a href="/stops/2900C1814">Clenchwarton Post Box</a>
                </td>
            <td>
                09:33
            </td>
        </tr>""", html=True)

        expected_json = {
            'times': [
                {
                    'service': {'line_name': '54', 'operators': [{'id': 'LYNX', 'name': 'Lynx', 'parent': ''}]},
                    'trip_id': trip.id,
                    'destination': {
                        'atco_code': '2900K132', 'name': 'Kings Lynn Transport Interchange'
                    },
                    'aimed_arrival_time': None, 'aimed_departure_time': '2020-05-01T09:15:00+01:00'
                }
            ]
        }

        with self.assertNumQueries(6):
            response = self.client.get('/stops/2900W0321/times.json')
        self.assertEqual(response.json(), expected_json)

        with self.assertNumQueries(6):
            response = self.client.get('/stops/2900W0321/times.json?when=2020-05-01T09:15:00%2b01:00')
        self.assertEqual(response.json(), expected_json)

        with self.assertNumQueries(6):
            response = self.client.get('/stops/2900W0321/times.json?when=2020-05-01T09:15:00')
        self.assertEqual(response.json(), expected_json)

        with self.assertNumQueries(6):
            response = self.client.get('/stops/2900W0321/times.json?limit=10')
        self.assertEqual(1, len(response.json()['times']))

        with self.assertNumQueries(1):
            response = self.client.get('/stops/2900W0321/times.json?limit=nine')
        self.assertEqual(400, response.status_code)

        with self.assertNumQueries(1):
            response = self.client.get('/stops/2900W0321/times.json?when=yesterday')
        self.assertEqual(400, response.status_code)

        # test get_trip
        journey = VehicleJourney(
            datetime=datetime.datetime(2020, 11, 2, 15, 7, 6),
            service=Service.objects.get(),
            code='1'
        )
        trip = journey.get_trip()
        self.assertEqual(trip.ticket_machine_code, '1')

        journey.code = '0915'
        trip = journey.get_trip()
        self.assertEqual(trip.ticket_machine_code, '1')

        trip = journey.get_trip(destination_ref='290J34')
        self.assertIsNone(trip)

        trip = journey.get_trip(destination_ref='2900K132')
        self.assertEqual(trip.ticket_machine_code, '1')

        journey.code = '0916'
        trip = journey.get_trip()
        self.assertIsNone(trip)

        trip = journey.get_trip(destination_ref='2900K132')
        self.assertIsNone(trip)

        # test trip copy:
        trip = route.trip_set.first()
        trip.copy(datetime.timedelta(hours=1))

    def test_ticketer(self):
        with TemporaryDirectory() as directory:
            with override_settings(DATA_DIR=Path(directory)):
                with use_cassette(str(FIXTURES_DIR / 'bod_ticketer.yaml')):
                    with override_settings(
                        TICKETER_OPERATORS=[('EA', ['Completely_Coach_Travel', 'CPLT'], 'Completely Coach Travel')]
                    ):
                        with self.assertLogs('bustimes.management.commands.import_transxchange', 'WARNING') as cm:
                            call_command('import_bod', 'ticketer')

                    with override_settings(
                        TICKETER_OPERATORS=[('EA', ['Completely_Coach_Travel', 'CPLT'])]
                    ):
                        with self.assertNumQueries(1):
                            call_command('import_bod', 'ticketer')  # not modified

                        with self.assertNumQueries(0):
                            call_command('import_bod', 'ticketer', 'POOP')  # no matching setting

                source = DataSource.objects.get(name='Completely Coach Travel')
                service = source.service_set.first()
                route = service.route_set.first()

                response = self.client.get(route.get_absolute_url())
                self.assertEqual(response.status_code, 200)

        response = self.client.get(service.get_absolute_url())
        self.assertContains(
            response,
            "Timetable data from "
            "https://opendata.ticketer.com/uk/Completely_Coach_Travel/routes_and_timetables/current.zip, "
            "24 September 2021"
        )

        self.assertEqual(
            cm.output,
            ["WARNING:bustimes.management.commands.import_transxchange:{'NationalOperatorCode': 'CPLT', "
             "'OperatorShortName': 'Completely Coach Travel', 'LicenceNumber': 'PF2024545'}"]
        )

    @override_settings(STAGECOACH_OPERATORS=[('EA', 'sccm', 'Stagecoach East', ['SCHU', 'SCPB'])])
    @time_machine.travel(datetime.datetime(2020, 6, 10))
    def test_import_stagecoach(self):

        with TemporaryDirectory() as directory:
            with override_settings(DATA_DIR=Path(directory)):
                archive_name = 'stagecoach-sccm-route-schedule-data-transxchange.zip'
                path = Path(directory) / archive_name

                with zipfile.ZipFile(path, 'a') as open_zipfile:
                    for filename in (
                        '904_FE_PF_904_20210102.xml',
                        '904_VI_PF_904_20200830.xml',
                    ):
                        open_zipfile.write(FIXTURES_DIR / filename, filename)

                with patch(
                    'bustimes.management.commands.import_bod.download_if_changed',
                    return_value=(True, parse_datetime('2020-06-10T12:00:00+01:00')),
                ) as download_if_changed:
                    with self.assertNumQueries(140):
                        call_command('import_bod', 'stagecoach')
                    download_if_changed.assert_called_with(
                        path, 'https://opendata.stagecoachbus.com/' + archive_name
                    )

                    with self.assertNumQueries(1):
                        call_command('import_bod', 'stagecoach')

                    with self.assertNumQueries(0):
                        call_command('import_bod', 'stagecoach', 'scox')

                    with self.assertNumQueries(81):
                        call_command('import_bod', 'stagecoach', 'sccm')

                source = DataSource.objects.get(name='Stagecoach East')
                response = self.client.get(f'/sources/{source.id}/routes/')

                self.assertEqual(response.content.decode(), '904_FE_PF_904_20210102.xml\n904_VI_PF_904_20200830.xml')

                route = Route.objects.first()
                response = self.client.get(route.get_absolute_url())
                self.assertEqual(200, response.status_code)
                self.assertEqual('', response.filename)

        self.assertEqual(BankHoliday.objects.count(), 13)
        self.assertEqual(CalendarBankHoliday.objects.count(), 130)
        self.assertEqual(VehicleType.objects.count(), 3)
        self.assertEqual(Garage.objects.count(), 4)
        self.assertEqual(Block.objects.count(), 12)

        with self.assertNumQueries(4):
            response = self.client.get(f'/services/{route.service_id}.json')
        self.assertTrue(response.json()['geometry'])

        self.assertEqual(1, Service.objects.count())
        self.assertEqual(2, Route.objects.count())

        with self.assertNumQueries(14):
            response = self.client.get('/services/904-huntingdon-peterborough')
        self.assertContains(response, '<option selected value="2020-08-31">Monday 31 August 2020</option>')
        self.assertContains(response, '<a href="/operators/huntingdon">Huntingdon</a>')
