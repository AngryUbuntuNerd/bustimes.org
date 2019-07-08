import os
from datetime import timedelta, datetime, date
from pytz.exceptions import NonExistentTimeError, AmbiguousTimeError
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from timetables import txc, northern_ireland
from ...models import Region, Service, Journey, StopUsageUsage, StopPoint


ONE_DAY = timedelta(days=1)


def combine_date_time(date, time):
    combo = datetime.combine(date, time)
    try:
        return timezone.make_aware(combo)
    except NonExistentTimeError:
        return timezone.make_aware(combo + timedelta(hours=1))
    except AmbiguousTimeError:
        return timezone.make_aware(combo, is_dst=True)


def handle_transxchange(service, transxchange, day):
    if not transxchange.operating_period.contains(day):
        return
    stopusageusages = []
    transxchange.service = service
    stops = set()
    for journey_pattern in transxchange.journey_patterns.values():
        for section in journey_pattern.sections:
            for timinglink in section.timinglinks:
                stops.add(timinglink.origin.stop.atco_code)
                stops.add(timinglink.destination.stop.atco_code)
    existent_stops = StopPoint.objects.in_bulk(stops)
    for vj in transxchange.journeys:
        if not vj.should_show(day, transxchange):
            continue
        journey_stopusageusages = []
        date = day
        previous_time = None
        journey = Journey(service=service, datetime=combine_date_time(date, vj.departure_time))
        for i, cell in enumerate(vj.get_times()):
            su = cell.stopusage
            time = cell.departure_time
            if previous_time and previous_time > time:
                date += ONE_DAY
            if su.stop.atco_code in existent_stops:
                if not su.activity or su.activity.startswith('pickUp'):
                    journey_stopusageusages.append(
                        StopUsageUsage(datetime=combine_date_time(date, time),
                                       order=i, stop_id=su.stop.atco_code)
                    )
                journey.destination_id = su.stop.atco_code
            previous_time = time
        if journey.destination_id:
            journey.save()
            for suu in journey_stopusageusages:
                suu.journey = journey
            stopusageusages += journey_stopusageusages
    StopUsageUsage.objects.bulk_create(stopusageusages)


def handle_ni_grouping(service, grouping, day):
    for journey in grouping['Journeys']:
        if not northern_ireland.should_show(journey, day) or not journey['StopUsages']:
            continue
        stopusageusages = []
        previous_time = None
        date = day
        for i, su in enumerate(journey['StopUsages']):
            if su['Location'][0] != '7':
                continue
            destination = su['Location']
            if su['Departure']:
                departure = datetime.strptime(su['Departure'], '%H:%M').time()
                if su['Activity'] != 'S':
                    if previous_time and departure < previous_time:
                        date += ONE_DAY
                    stopusageusages.append(
                        StopUsageUsage(datetime=combine_date_time(date, departure),
                                       order=i, stop_id=su['Location'])
                    )
                previous_time = departure
        journey = Journey(service=service, datetime=stopusageusages[0].datetime, destination_id=destination)
        journey.save()
        for suu in stopusageusages:
            suu.journey = journey
        StopUsageUsage.objects.bulk_create(stopusageusages)


def do_ni_service(service, groupings, day):
    for grouping in groupings:
        if grouping['Journeys']:
            handle_ni_grouping(service, grouping, day)


def handle_region(region):
    today = date.today()
    if region.id == 'NI':
        NEXT_WEEK = today + ONE_DAY * 7
    else:  # not actually next week
        NEXT_WEEK = today + ONE_DAY * 2
    # delete journeys before today
    Journey.objects.filter(service__region=region, datetime__date__lt=today).delete()
    Journey.objects.filter(service__region=region, service__current=False).delete()
    # get the date of the last generated journey
    last_journey = Journey.objects.filter(service__region=region).order_by('datetime').last()
    if last_journey:
        today = last_journey.datetime.astimezone(timezone.get_current_timezone()).date() + ONE_DAY
        if today > NEXT_WEEK:
            return
    services = Service.objects.filter(region=region, current=True, timetable_wrong=False)
    with transaction.atomic():
        for service in services:
            if region.id == 'NI':
                path = os.path.join(settings.DATA_DIR, 'NI', service.pk + '.json')
                if not os.path.exists(path):
                    continue
                groupings = northern_ireland.get_data(path)
                day = today
                while day <= NEXT_WEEK:
                    do_ni_service(service, groupings, day)
                    day += ONE_DAY
            else:
                files = service.get_files_from_zipfile()
                for xml_file in files:
                    tranxchange = txc.TransXChange(xml_file)
                    day = today
                    while day <= NEXT_WEEK:
                        handle_transxchange(service, tranxchange, day)
                        day += ONE_DAY


class Command(BaseCommand):
    @staticmethod
    def add_arguments(parser):
        parser.add_argument('regions', nargs='+', type=str)

    def handle(self, regions, *args, **options):
        for region in Region.objects.filter(id__in=regions):
            handle_region(region)
