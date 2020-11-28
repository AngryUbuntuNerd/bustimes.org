import os
from datetime import date
from ciso8601 import parse_datetime
from tempfile import TemporaryDirectory
from vcr import use_cassette
from mock import patch
from freezegun import freeze_time
from django.test import TestCase, override_settings
from django.core.management import call_command
from busstops.models import Region, Operator, DataSource, OperatorCode, Service, ServiceCode
from ...models import Route


FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


class ImportBusOpenDataTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        ea = Region.objects.create(pk='EA', name='East Anglia')
        ne = Region.objects.create(pk='NE', name='North East')
        lynx = Operator.objects.create(id='LYNX', region=ea, name='Lynx')
        sund = Operator.objects.create(id='SCSU', region=ne, name='Sunderland')
        source = DataSource.objects.create(name='National Operator Codes')
        OperatorCode.objects.create(operator=lynx, source=source, code='LYNX')
        OperatorCode.objects.create(operator=sund, source=source, code='SCSU')

    @use_cassette(os.path.join(FIXTURES_DIR, 'bod_lynx.yaml'))
    @freeze_time('2020-05-01')
    @override_settings(BOD_OPERATORS=[
        ('LYNX', 'EA', {
            'CO': 'LYNX',
        }, False),
    ])
    def test_import_bod(self):
        with TemporaryDirectory() as directory:
            with override_settings(DATA_DIR=directory):
                with patch('builtins.print') as mocked_print:
                    call_command('import_bod', '')
                mocked_print.assert_called_with({'GoodFriday', 'NewYearsDay', 'EasterMonday', 'BoxingDay', 'MayDay',
                                                 'BoxingDayHoliday', 'ChristmasDay', 'ChristmasDayHoliday',
                                                 'NewYearsDayHoliday', 'LateSummerBankHolidayNotScotland',
                                                 'SpringBank'})

                call_command('import_bod', '')

        route = Route.objects.get()
        self.assertEqual(route.code, 'Lynx_Clenchwarton_54_20200330')

        # a TicketMachineServiceCode should have been created
        service_code = ServiceCode.objects.get()
        self.assertEqual(service_code.code, '1')
        self.assertEqual(service_code.scheme, ' SIRI')

        response = self.client.get('/services/54-kings-lynn-the-walpoles-via-clenchwarton')

        self.assertContains(response, """
            <tr>
                <th>
                    <a href="/stops/2900W0321">Walpole St Peter Lion Store</a>
                </th>
                <td>12:19</td>
            </tr>""", html=True)

        self.assertContains(response, """<p class="credit">Timetable data from <a href="https://data.bus-data.dft.gov.uk/category/dataset/35/">Lynx/\
Bus Open Data Service</a>, 1 April 2020</p>""")

    @override_settings(STAGECOACH_OPERATORS=[('NE', 'scne', 'Stagecoach North East', {
        'SCNE': 'SCNE',
        'SCSS': 'SCSS',
        'SCSU': 'SCSU',
        'SCTE': 'SCTE',
        'SCHA': 'SCHA'
    })], DATA_DIR=FIXTURES_DIR)
    @freeze_time('2020-06-10')
    def test_import_stagecoach(self):

        archive_name = 'stagecoach-scne-route-schedule-data-transxchange.zip'
        path = os.path.join(FIXTURES_DIR, archive_name)

        with patch(
            'bustimes.management.commands.import_bod.download_if_changed',
            return_value=(True, parse_datetime('2020-06-10T12:00:00+01:00'))
        ) as download_if_changed:
            with patch('bustimes.management.commands.import_transxchange.BANK_HOLIDAYS', {
                'AllBankHolidays': date(2020, 8, 31),
            }):
                with self.assertNumQueries(216):
                    with patch('builtins.print') as mocked_print:
                        call_command('import_bod', 'stagecoach')
                download_if_changed.assert_called_with(path, 'https://opendata.stagecoachbus.com/' + archive_name)
                mocked_print.assert_called_with({'ChristmasDay', 'NewYearsDay', 'BoxingDay'})

                with self.assertNumQueries(1):
                    call_command('import_bod', 'stagecoach')

                DataSource.objects.update(datetime=None)
                with self.assertNumQueries(212):
                    with patch('builtins.print') as mocked_print:
                        call_command('import_bod', 'stagecoach')
                mocked_print.assert_called_with({'ChristmasDay', 'NewYearsDay', 'BoxingDay'})

        self.assertEqual(3, Service.objects.count())
        self.assertEqual(6, Route.objects.count())

        Route.objects.filter(code__endswith='/E1_SIS_PB_E1E2_20200614.xml#8980').delete()

        with self.assertNumQueries(16):
            response = self.client.get('/services/e2-sunderland-south-shields')
        self.assertContains(response, '<option selected value="2020-06-10">Wednesday 10 June 2020</option>')
        self.assertContains(response, '<a href="/operators/sunderland">Sunderland</a>')

        route = Route.objects.first()
        response = self.client.get(route.get_absolute_url())
        self.assertEqual(200, response.status_code)
        self.assertEqual('', response.filename)
