import os
import zipfile
import vcr
from freezegun import freeze_time
from mock import patch
from datetime import date
from django.test import TestCase, override_settings
from django.conf import settings
from django.core.management import call_command
from busstops.models import Region, AdminArea, StopPoint, Service, Operator
from ...models import Route
from ..commands import import_gtfs


FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')


@override_settings(DATA_DIR=FIXTURES_DIR, IE_COLLECTIONS=['mortons', 'seamusdoherty'])
@freeze_time('2019-08-30')
class GTFSTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Make a GTFS feed (a zip file containing some text files)."""

        cls.leinster = Region.objects.create(
            id='LE',
            name='Leinster'
        )
        cls.ulster = Region.objects.create(
            id='UL',
            name='Ulster'
        )
        cls.dublin = AdminArea.objects.create(
            id=822,
            atco_code=822,
            region_id='LE',
            name='Dublin'
        )
        cls.south_dublin = AdminArea.objects.create(
            id=823,
            atco_code=823,
            region_id='LE'
        )
        cls.donegal = AdminArea.objects.create(
            id=853,
            atco_code=853,
            region_id='UL'
        )

        # Create an existing operator (with a slightly different name) to test that it is re-used
        Operator.objects.create(id=132, name='Seumas Doherty', region=cls.leinster)

        for collection in settings.IE_COLLECTIONS:
            dir_path = os.path.join(FIXTURES_DIR, 'google_transit_' + collection)
            feed_path = dir_path + '.zip'
            with zipfile.ZipFile(feed_path, 'a') as open_zipfile:
                for item in os.listdir(dir_path):
                    open_zipfile.write(os.path.join(dir_path, item), item)

        with vcr.use_cassette(os.path.join(FIXTURES_DIR, 'google_transit_ie') + '.yaml'):
            with patch('builtins.print') as mocked_print:
                call_command('import_gtfs', '--force', '-v2')
        mocked_print.assert_called_with((0, {}))

        # import a second time - test that it's OK if stuff already exists
        with vcr.use_cassette(os.path.join(FIXTURES_DIR, 'google_transit_ie') + '.yaml'):
            with patch('builtins.print') as mocked_print:
                call_command('import_gtfs', '--force')
        mocked_print.assert_called_with((0, {}))

        for collection in settings.IE_COLLECTIONS:
            dir_path = os.path.join(FIXTURES_DIR, 'google_transit_' + collection)
            os.remove(dir_path + '.zip')

    def test_stops(self):
        stops = StopPoint.objects.all()
        self.assertEqual(len(stops), 75)
        stop = StopPoint.objects.get(atco_code='822000153')
        self.assertEqual(stop.common_name, 'Terenure Library')
        self.assertEqual(stop.admin_area_id, 822)

    def test_operator(self):
        self.assertEqual(Operator.objects.count(), 2)
        self.assertEqual(Operator.objects.filter(service__current=True).distinct().count(), 2)

    def test_small_timetable(self):
        with freeze_time('2017-06-07'):
            response = self.client.get('/services/165')
        timetable = response.context_data['timetable']
        self.assertEqual(str(timetable.groupings[0]), 'Outbound')
        self.assertEqual(str(timetable.groupings[1]), 'Inbound')
        # self.assertEqual(str(timetable.groupings[0]), 'Merrion - Citywest')
        # self.assertEqual(str(timetable.groupings[1]), 'Citywest - Ballsbridge')
        self.assertEqual(str(timetable.groupings[0].rows[0].times), '[07:45]')
        self.assertEqual(str(timetable.groupings[0].rows[4].times), '[07:52]')
        self.assertEqual(str(timetable.groupings[0].rows[6].times), '[08:01]')
        self.assertEqual(str(timetable.groupings[1].rows[0].times), '[17:20]')
        self.assertEqual(str(timetable.groupings[1].rows[6].times), '[17:45]')
        self.assertEqual(str(timetable.groupings[1].rows[-1].times), '[18:25]')
        self.assertEqual(len(timetable.groupings[0].rows), 18)
        self.assertEqual(len(timetable.groupings[1].rows), 14)

        self.assertContains(
            response,
            '<a href="https://www.transportforireland.ie/transitData/PT_Data.html">Transport for Ireland</a>'
        )

        for day in (date(2017, 6, 11), date(2017, 12, 25), date(2015, 12, 3), date(2020, 12, 3)):
            with freeze_time(day):
                with self.assertNumQueries(10):
                    response = self.client.get(f'/services/165?date={day}')
                timetable = response.context_data['timetable']
                self.assertEqual(day, timetable.date)
                self.assertEqual(timetable.groupings, [])

    def test_big_timetable(self):
        service = Service.objects.get(service_code='seamusdoherty-963-1')
        timetable = service.get_timetable(date(2017, 6, 7))
        self.assertEqual(str(timetable.groupings[0].rows[0].times), "['', 10:15, '', 14:15, 17:45]")
        self.assertEqual(str(timetable.groupings[0].rows[1].times), "['', 10:20, '', 14:20, 17:50]")
        self.assertEqual(str(timetable.groupings[0].rows[2].times), "['', 10:22, '', 14:22, 17:52]")

        self.assertTrue(service.geometry)

    def test_admin_area(self):
        res = self.client.get(self.dublin.get_absolute_url())
        self.assertContains(res, 'Bus services in Dublin', html=True)
        self.assertContains(res, '/services/165')

    def test_download_if_modified(self):
        path = 'poop.txt'
        url = 'https://bustimes.org/static/js/global.js'

        if os.path.exists(path):
            os.remove(path)

        cassette = os.path.join(FIXTURES_DIR, 'download_if_modified.yaml')

        with vcr.use_cassette(cassette, match_on=['uri', 'headers']):
            self.assertEqual(str(import_gtfs.download_if_changed(path, url)),
                             '(True, FakeDatetime(2020, 6, 2, 7, 35, 34, tzinfo=<UTC>))')

            with patch('os.path.getmtime', return_value=1593870909.0) as getmtime:
                self.assertEqual(str(import_gtfs.download_if_changed(path, url)),
                                 '(True, FakeDatetime(2020, 6, 2, 7, 35, 34, tzinfo=<UTC>))')
                getmtime.assert_called_with('poop.txt')

        self.assertTrue(os.path.exists(path))

        os.remove(path)

    def test_handle(self):
        Route.objects.all().delete()

        with patch('bustimes.management.commands.import_gtfs.download_if_changed', return_value=(False, None)):
            call_command('import_gtfs')
        self.assertFalse(Route.objects.all())

        with patch('bustimes.management.commands.import_gtfs.download_if_changed', return_value=(True, None)):
            with patch('builtins.print') as mocked_print:
                with self.assertRaises(FileNotFoundError):
                    call_command('import_gtfs')
        mocked_print.assert_called_with('mortons', None)
        self.assertFalse(Route.objects.all())
