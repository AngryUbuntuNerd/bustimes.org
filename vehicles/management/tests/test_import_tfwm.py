import os
from freezegun import freeze_time
from vcr import use_cassette
from mock import patch
from django.test import TestCase, override_settings
from busstops.models import Region, Operator, DataSource
from ...models import Vehicle
from ..commands import import_tfwm


class TfWMImportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = DataSource.objects.create(datetime='2018-08-06T22:41:15+01:00', name='WM')
        Region.objects.create(id='WM')

        Operator.objects.bulk_create([
            Operator(id='FSMR', region_id='WM', name='First Worcestershire'),
            Operator(id='MDCL', region_id='WM', name='Midland Classic'),
            Operator(id='SLBS', region_id='WM', name='Select Bus Services'),
        ])

    @use_cassette(os.path.join('data', 'vcr', 'import_tfwm.yaml'), decode_compressed_response=True)
    @freeze_time('2018-08-21 00:00:09')
    def test_handle(self):
        command = import_tfwm.Command()

        command.source = self.source

        with override_settings(TFWM={}):
            items = command.get_items()

        with self.assertNumQueries(11):  # X12
            with patch('builtins.print') as mocked_print:
                command.handle_item(items[0], self.source.datetime)
        mocked_print.assert_called()

        with self.assertNumQueries(11):
            with patch('builtins.print') as mocked_print:
                command.handle_item(items[217], self.source.datetime)
        mocked_print.assert_called()

        with self.assertNumQueries(2):
            with patch('builtins.print') as mocked_print:
                command.handle_item(items[217], self.source.datetime)
        mocked_print.assert_called()

        with self.assertNumQueries(12):
            with patch('builtins.print') as mocked_print:
                command.handle_item(items[216], self.source.datetime)
        mocked_print.assert_called()

        self.assertEqual(3, Vehicle.objects.all().count())
