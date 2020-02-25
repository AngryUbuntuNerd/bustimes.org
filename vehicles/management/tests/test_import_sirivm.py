import os
import xml.etree.cElementTree as ET
from mock import patch
from vcr import use_cassette
from django.test import TestCase
from busstops.models import Region, DataSource
from bustimes.models import Operator, Service, OperatorCode
from ...models import VehicleLocation, JourneyCode
from ..commands import import_sirivm


class SiriVMImportTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        Region.objects.create(id='EA')
        cls.operator = Operator.objects.create(id='FESX', region_id='EA')
        cls.service = Service.objects.create(service_code='73', line_name='73', date='2010-01-01', tracking=True)
        cls.service.operator.set(['FESX'])
        cls.command = import_sirivm.Command()
        cls.command.source = DataSource.objects.create(name='Essex SIRI', datetime='2018-08-06T22:41:15+01:00')
        OperatorCode.objects.create(operator=cls.operator, source=cls.command.source, code='FE')
        JourneyCode.objects.create(service=cls.service, code='14', destination='Hundred Acre Wood')

    @use_cassette(os.path.join('data', 'vcr', 'import_sirivm.yaml'), decode_compressed_response=True)
    def test_handle(self):
        items = self.command.get_items()
        item = next(items)

        vehicle, vehicle_created = self.command.get_vehicle(item)
        journey = self.command.get_journey(item, vehicle)

        self.assertEqual('14', journey.code)
        self.assertEqual('Hundred Acre Wood', journey.destination)
        self.assertEqual('69532', str(vehicle))
        self.assertTrue(vehicle_created)
        self.assertEqual(self.service, journey.service)
        self.assertEqual(self.operator, vehicle.operator)

        location = self.command.create_vehicle_location(item)
        self.assertIsNone(location.heading)

        self.assertEqual('2018-08-06 21:44:32+01:00', str(self.command.get_datetime(item)))

        locations = VehicleLocation.objects.filter(journey__source=self.command.source)

        with self.assertNumQueries(8):
            self.command.handle_item(item, None)
        self.assertIsNone(locations.get().heading)

        # if datetime is the same, shouldn't create new vehicle location
        with self.assertNumQueries(1):
            self.command.handle_item(item, None)
        self.assertEqual(1, locations.count())

        # different datetime - should create new vehicle location
        item.find('siri:RecordedAtTime', import_sirivm.NS).text = '2018-08-06T21:45:32+01:00'
        with self.assertNumQueries(2):
            self.command.handle_item(item, None)

        # another different datetime - but speed == 0
        item.find('siri:RecordedAtTime', import_sirivm.NS).text = '2018-08-06T21:46:32+01:00'
        with self.assertNumQueries(2):
            self.command.handle_item(item, None)

        self.assertEqual(1, locations.count())
        last_location = locations.last()
        self.assertIsNone(last_location.heading)
        self.assertEqual(last_location.early, -8)

        # test an item with an invalid delay ('-PT2M.492S')
        item = next(items)
        location = self.command.create_vehicle_location(item)
        self.assertIsNone(location.early)

    def test_devonshire(self):
        item = ET.fromstring("""
            <VehicleActivity xmlns="http://www.siri.org.uk/siri">
                <RecordedAtTime>2018-12-27T16:26:42Z</RecordedAtTime>
                <ItemIdentifier>f3d015d8-8cd4-4146-9b45-42bb2a4dd0b6</ItemIdentifier>
                <ValidUntilTime>2018-12-27T16:26:42Z</ValidUntilTime>
                <VehicleMonitoringRef>DTCO-106</VehicleMonitoringRef>
                <MonitoredVehicleJourney>
                    <LineRef>184</LineRef>
                    <DirectionRef>none</DirectionRef>
                    <FramedVehicleJourneyRef>
                        <DataFrameRef>2018-12-27</DataFrameRef>
                        <DatedVehicleJourneyRef>1607</DatedVehicleJourneyRef>
                    </FramedVehicleJourneyRef>
                    <JourneyPatternRef>624836</JourneyPatternRef>
                    <VehicleMode>bus</VehicleMode>
                    <PublishedLineName>184</PublishedLineName>
                    <DirectionName>none</DirectionName>
                    <OperatorRef>DTCO</OperatorRef>
                    <OriginRef>1100DEC11150</OriginRef>
                    <OriginName>Railway Station</OriginName>
                    <Via>
                        <PlaceName>Bishopsteignton</PlaceName>
                    </Via>
                    <Via>
                        <PlaceName>Kingsteignton</PlaceName>
                    </Via>
                    <Via>
                        <PlaceName>Newton Abbot</PlaceName>
                    </Via>
                    <DestinationRef>1100DEM55095</DestinationRef>
                    <DestinationName>Rail Station</DestinationName>
                    <OriginAimedDepartureTime>2018-12-27T16:07:00Z</OriginAimedDepartureTime>
                    <DestinationAimedArrivalTime>2018-12-27T16:51:00Z</DestinationAimedArrivalTime>
                    <Monitored>true</Monitored>
                    <VehicleLocation>
                        <Longitude>-3.5089750591636</Longitude>
                        <Latitude>50.5476417184896</Latitude>
                    </VehicleLocation>
                    <Bearing>240</Bearing>
                    <Delay>PT5M32S</Delay>
                    <BlockRef>UN.DTCO.31-184-A-y10-1.1607.Inb</BlockRef>
                    <VehicleRef>DTCO-102</VehicleRef>
                </MonitoredVehicleJourney>
            </VehicleActivity>
        """)
        with patch('vehicles.management.commands.import_sirivm.logger') as logger:
            self.command.handle_item(item, None)
        self.assertTrue(logger.error.called)
        location = VehicleLocation.objects.get()
        self.assertEqual(240, location.heading)
        self.assertEqual('1607', location.journey.code)
        self.assertEqual('Rail Station', location.journey.destination)

    def test_create_vehicle_location_invalid_bearing(self):
        item = ET.fromstring("""
            <VehicleActivity xmlns="http://www.siri.org.uk/siri">
                <RecordedAtTime>2018-12-27T15:44:38Z</RecordedAtTime>
                <MonitoredVehicleJourney>
                    <VehicleLocation>
                        <Longitude>-3.4924729173875</Longitude>
                        <Latitude>50.7195777544765</Latitude>
                    </VehicleLocation>
                    <Bearing>-1</Bearing>
                </MonitoredVehicleJourney>
            </VehicleActivity>
        """)
        location = self.command.create_vehicle_location(item)
        self.assertIsNone(location.heading)
