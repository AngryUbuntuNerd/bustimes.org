import os
from multiprocessing import Pool
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from txc import txc, ni
from ...models import Region, Service, Journey, StopUsageUsage, StopPoint
from ...utils import get_files_from_zipfile


ONE_DAY = timedelta(days=1)


def handle_timetable(service, timetable, day):
    if hasattr(timetable, 'operating_profile') and day.weekday() not in timetable.operating_profile.regular_days:
        return
    if not timetable.operating_period.contains(day):
        return
    # if not hasattr(timetable, 'groupings'):
        # return
    for grouping in timetable.groupings:
        stops = {row.part.stop.atco_code for row in grouping.rows}
        existent_stops = StopPoint.objects.filter(atco_code__in=stops).values_list('atco_code', flat=True)
        for vj in grouping.journeys:
            if not vj.should_show(day):
                continue
            date = day
            previous_time = None
            stopusageusages = []
            journey = Journey(service=service, datetime='{} {}'.format(date, vj.departure_time))
            for i, (su, time) in enumerate(vj.get_times()):
                if previous_time and previous_time > time:
                    date += ONE_DAY
                if su.stop.atco_code in existent_stops:
                    if not su.activity or su.activity.startswith('pickUp'):
                        stopusageusages.append(
                            StopUsageUsage(datetime='{} {}'.format(date, time),
                                           order=i, stop_id=su.stop.atco_code)
                        )
                    journey.destination_id = su.stop.atco_code
                previous_time = time
            if journey.destination_id:
                journey.save()
                for suu in stopusageusages:
                    suu.journey = journey
                StopUsageUsage.objects.bulk_create(stopusageusages)


def do_ni_service(service, groupings, day):
    previous_time = None
    for grouping in groupings:
        for journey in grouping['Journeys']:
            if not ni.should_show(journey, day):
                continue

            stopusageusages = []
            for i, su in enumerate(journey['StopUsages']):
                if su['Location'][0] != '7':
                    print(service, su)
                    continue
                destination = su['Location']
                if su['Activity'] != 'S' and su['Departure']:
                    if previous_time and su['Departure'] < previous_time:
                        print(service, su)
                    stopusageusages.append(
                        StopUsageUsage(datetime='{} {}'.format(day, su['Departure']),
                                       order=i, stop_id=su['Location'])
                    )
                previous_time = su['Departure']

            departure = stopusageusages[0].datetime
            journey = Journey(service=service, datetime=departure, destination_id=destination)
            journey.save()
            for suu in stopusageusages:
                suu.journey = journey
            StopUsageUsage.objects.bulk_create(stopusageusages)


@transaction.atomic
def handle_region(region):
    print(region)
    today = date.today()
    NEXT_WEEK = today + ONE_DAY * 7
    # delete journeys before today
    print('deleting journeys before', today)
    print(Journey.objects.filter(service__region=region, datetime__date__lt=today).delete())
    # get the date of the last generated journey
    last_journey = Journey.objects.filter(service__region=region).order_by('datetime').last()
    if last_journey:
        today = last_journey.datetime.date() + ONE_DAY
        if today > NEXT_WEEK:
            return

    for service in Service.objects.filter(region=region, current=True):
        if region.id == 'NI':
            path = os.path.join(settings.DATA_DIR, 'NI', service.pk + '.json')
            if not os.path.exists(path):
                continue
            groupings = ni.get_data(path)
            day = today
            while day <= NEXT_WEEK:
                do_ni_service(service, groupings, day)
                day += ONE_DAY
            continue

        for i, xml_file in enumerate(get_files_from_zipfile(service)):
            timetable = txc.Timetable(xml_file, None)
            day = today
            while day <= NEXT_WEEK:
                handle_timetable(service, timetable, day)
                day += ONE_DAY


class Command(BaseCommand):
    def handle(self, *args, **options):
        pool = Pool(processes=4)
        pool.map(handle_region, Region.objects.all().exclude(id__in=('L', 'Y')))
