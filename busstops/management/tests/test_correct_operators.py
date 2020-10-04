from django.test import TestCase
from mock import patch
from ...models import Region, Operator, Service
from ..commands import correct_operators


class CorrectOperatorsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.command = correct_operators.Command()

        cls.east = Region.objects.create(id='E', name='East')
        cls.west = Region.objects.create(id='W', name='West')
        cls.north = Region.objects.create(id='N', name='North')

        cls.goodwins = Operator.objects.create(
            region=cls.east,
            pk='GDWN',
            name='Go Goodwins'
        )
        cls.tellings = Operator.objects.create(
            region=cls.east,
            pk='TGML',
            name='Tellings Golden Miller'
        )

        cls.west_midlands_service = Service.objects.create(
            service_code='1',
            region=cls.west,
            date='2016-05-05'
        )
        cls.west_midlands_service.operator.set([cls.goodwins])

    def test_handle(self):
        self.assertEqual(self.goodwins.region_id, 'E')
        self.assertEqual(self.tellings.region_id, 'E')

        with patch('builtins.print') as mock_print:
            self.command.handle()
        mock_print.assert_called_with('moved Go Goodwins to West')

        self.assertEqual(Operator.objects.get(id='GDWN').region_id, 'W')
        self.assertEqual(Operator.objects.get(id='TGML').region_id, 'E')

    def test_maybe(self):
        self.assertEqual(self.tellings.region_id, 'E')
        self.west.services = 10
        self.north.services = 6

        self.assertEqual(
            "consider moving Tellings Golden Miller from East to [('W', 10), ('N', 6)]",
            self.command.maybe_move_operator(self.tellings, [self.west, self.north])
        )
