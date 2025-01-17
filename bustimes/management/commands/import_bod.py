"""Import timetable data "fresh from the cow"
"""
import logging
import requests
import hashlib
import zipfile
import xml.etree.cElementTree as ET
from pathlib import Path
from django.db.models import Q, OuterRef, Exists
from io import StringIO
from ciso8601 import parse_datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import DataError
from django.utils import timezone
from busstops.models import DataSource, Operator, Service
from .import_transxchange import Command as TransXChangeCommand
from ...utils import download, download_if_changed
from ...models import Route


logger = logging.getLogger(__name__)
session = requests.Session()


def clean_up(operators, sources, incomplete=False):
    service_operators = Service.operator.through.objects.filter(service=OuterRef('service'))
    routes = Route.objects.filter(
        ~Q(source__in=sources),
        ~Q(source__name__in=('L', 'bustimes.org')),
        Exists(service_operators.filter(operator__in=operators)),
        ~Exists(service_operators.filter(~Q(operator__in=operators)))  # exclude joint services
    )
    if incomplete:  # leave other sources alone
        routes = routes.filter(source__url__contains='bus-data.dft.gov.uk')
    routes.delete()
    Service.objects.filter(operator__in=operators, current=True, route=None).update(current=False)


def get_operator_ids(source):
    operators = Operator.objects.filter(service__route__source=source).distinct().values('id')
    return [operator['id'] for operator in operators]


def get_command():
    command = TransXChangeCommand()
    command.set_up()
    return command


def handle_file(command, path, qualify_filename=False):
    # the downloaded file might be plain XML, or a zipped archive - we just don't know yet
    full_path = settings.DATA_DIR / path

    try:
        with zipfile.ZipFile(full_path) as archive:
            for filename in archive.namelist():
                if filename.endswith('.csv'):
                    continue
                with archive.open(filename) as open_file:
                    if qualify_filename:
                        # source has multiple versions (Passsenger) so add a prefix like 'gonortheast_123.zip/'
                        filename = str(Path(path) / filename)
                    try:
                        try:
                            command.handle_file(open_file, filename)
                        except ET.ParseError:
                            open_file.seek(0)
                            content = open_file.read().decode('utf-16')
                            fake_file = StringIO(content)
                            command.handle_file(fake_file, filename)
                    except (ET.ParseError, ValueError, AttributeError, DataError) as e:
                        if filename.endswith('.xml'):
                            logger.info(filename)
                            logger.error(e, exc_info=True)
    except zipfile.BadZipFile:
        with full_path.open() as open_file:
            try:
                command.handle_file(open_file, str(path))
            except (AttributeError, DataError) as e:
                logger.error(e, exc_info=True)

    if not qualify_filename:
        sha1 = hashlib.sha1()
        with full_path.open('rb') as open_file:
            while True:
                data = open_file.read(65536)
                if data:
                    sha1.update(data)
                else:
                    break
        command.source.sha1 = sha1.hexdigest()


def get_bus_open_data_paramses(api_key, operator):
    if operator:
        nocs = [operator]
    else:
        nocs = [operator[0] for operator in settings.BOD_OPERATORS]

    searches = [noc for noc in nocs if ' ' in noc]  # e.g. 'TM Travel'
    nocs = [noc for noc in nocs if ' ' not in noc]  # e.g. 'TMTL'

    nocses = [nocs[i:i+20] for i in range(0, len(nocs), 20)]

    base_params = {
        'api_key': api_key,
        'status': ['published', 'expiring'],
    }

    for search in searches:
        yield {
            **base_params,
            'search': search
        }

    for nocs in nocses:
        yield {
            **base_params,
            'noc': ','.join(nocs)
        }


def bus_open_data(api_key, operator):
    assert len(api_key) == 40

    command = get_command()

    datasets = []

    for params in get_bus_open_data_paramses(api_key, operator):
        url = 'https://data.bus-data.dft.gov.uk/api/v1/dataset/'
        while url:
            response = session.get(url, params=params)
            json = response.json()
            results = json['results']
            if not results:
                logger.warning(f'no results: {response.url}')
            for dataset in results:
                dataset['modified'] = parse_datetime(dataset['modified'])
                datasets.append(dataset)
            url = json['next']
            params = None

    all_source_ids = []

    for noc, region_id, operator_codes_dict, incomplete in settings.BOD_OPERATORS:
        if operator_codes_dict:
            operators = operator_codes_dict.values()
        else:
            operators = [noc]

        if operator and operator not in operators:
            continue

        if ' ' in noc:
            operator_datasets = [item for item in datasets if noc in item['name'] or noc in item['description']]
        else:
            operator_datasets = [item for item in datasets if noc in item['noc']]

        command.operators = operator_codes_dict
        command.region_id = region_id

        sources = []
        service_ids = set()

        for dataset in operator_datasets:
            if noc == 'FBOS':
                # only certain First operators
                if not any(code in dataset['description'] for code in operator_codes_dict):
                    continue
                if 'FECS' in dataset['description']:
                    # ignore FECS datasets older than 1 sep 2021
                    if dataset['modified'] < parse_datetime('2021-09-01T00:00:00+00:00'):
                        continue
            if noc == 'EYMS' and not any(area["atco_code"] == "229" for area in dataset["adminAreas"]):
                continue

            filename = dataset['name']
            url = dataset['url']
            path = settings.DATA_DIR / filename

            dataset['source'], created = DataSource.objects.get_or_create(
                {'name': dataset['name']},
                url=dataset['url']
            )

            command.source = dataset['source']
            sources.append(command.source)

            if operator or dataset['source'].datetime != dataset['modified']:
                logger.info(filename)
                command.service_ids = set()
                command.route_ids = set()
                command.garages = {}

                command.source.datetime = dataset['modified']
                command.source.name = filename

                download(path, url)
                handle_file(command, filename)

                command.source.save()

                operator_ids = get_operator_ids(command.source)
                logger.info(f'  {operator_ids}')
                logger.info(f'  {[o for o in operator_ids if o not in operators]}')

                command.mark_old_services_as_not_current()

                service_ids |= command.service_ids

        # delete routes from any sources that have been made inactive
        for o in operators:
            if Service.objects.filter(
                Q(source__in=sources) | Q(route__source__in=sources), current=True, operator=o
            ).exists():
                clean_up([o], sources, incomplete)
            elif len(operators) == 1 or Service.objects.filter(current=True, operator=o).exists():
                logger.warning(f'{o} has no current data')

        command.service_ids = service_ids
        command.finish_services()
        all_source_ids += [source.id for source in sources]

    if not operator:
        to_delete = DataSource.objects.filter(
            ~Q(id__in=all_source_ids),
            ~Exists(Route.objects.filter(source=OuterRef('id'))),
            url__startswith="https://data.bus-data.dft.gov.uk/timetable/dataset/"
        )
        if to_delete:
            logger.info(to_delete)
            logger.info(to_delete.delete())

    command.debrief()


def ticketer(specific_operator=None):
    command = get_command()

    base_dir = settings.DATA_DIR / 'ticketer'

    if not base_dir.exists():
        base_dir.mkdir()

    for setting in settings.TICKETER_OPERATORS:
        if len(setting) == 3:
            region_id, operators, name = setting
        else:
            region_id, operators = setting
            name = operators[0].replace('_', ' ')

        noc = operators[0]
        if noc == 'AMTM':  # AMTM data is only in the AKSS dataset...
            operators = operators[1:]

        if specific_operator and specific_operator != noc:
            continue

        url = f'https://opendata.ticketer.com/uk/{noc}/routes_and_timetables/current.zip'
        filename = f'{noc}.zip'
        path = base_dir / filename
        command.source, created = DataSource.objects.get_or_create({'name': name}, url=url)
        command.garages = {}

        modified, last_modified = download_if_changed(path, url)

        if noc == specific_operator or not command.source.datetime or last_modified > command.source.datetime:
            logger.info(f"{url} {last_modified}")

            command.region_id = region_id
            command.service_ids = set()
            command.route_ids = set()

            # avoid importing old data
            command.source.datetime = timezone.now()

            handle_file(command, path)

            command.mark_old_services_as_not_current()

            clean_up(operators, [command.source])

            command.finish_services()

            command.source.datetime = last_modified
            command.source.save()

            logger.info(f"  {command.source.route_set.order_by('end_date').distinct('end_date').values('end_date')}")
            logger.info(f"  {get_operator_ids(command.source)}")

    command.debrief()


def stagecoach(operator=None):
    command = get_command()

    for region_id, noc, name, nocs in settings.STAGECOACH_OPERATORS:
        if operator and operator != noc:  # something like 'sswl'
            continue

        filename = f'stagecoach-{noc}-route-schedule-data-transxchange_2_4.zip'
        if noc not in ('scek', 'syrk', 'sdvn'):  # 'sccm', 'sblb', 'sccu', 'scfi', 'schi', 'scem', 'sswl'):
            filename = filename.replace('_2_4', '')
        url = f'https://opendata.stagecoachbus.com/{filename}'
        path = settings.DATA_DIR / filename

        command.source, created = DataSource.objects.get_or_create({'url': url}, name=name)
        if not created:
            command.source.url = url

        modified, last_modified = download_if_changed(path, url)

        if modified and not command.source.older_than(last_modified):
            modified = False

        if modified or operator:
            logger.info(f'{url} {last_modified}')

            command.region_id = region_id
            command.service_ids = set()
            command.route_ids = set()
            command.garages = {}
            command.operators = {  # sort of ~homogenise~ all the different OperatorCodes in the data
                o: nocs[0] for o in nocs
            }

            # avoid importing old data
            command.source.datetime = timezone.now()

            handle_file(command, filename)

            command.mark_old_services_as_not_current()

            clean_up(nocs, [command.source])

            command.finish_services()

            command.source.datetime = last_modified
            command.source.save()

            logger.info(f"  {command.source.route_set.order_by('end_date').distinct('end_date').values('end_date')}")
            operators = get_operator_ids(command.source)
            logger.info(f'  {operators}')
            logger.info(f'  {[o for o in operators if o not in nocs]}')

    command.debrief()


class Command(BaseCommand):
    @staticmethod
    def add_arguments(parser):
        parser.add_argument('api_key', type=str)
        parser.add_argument('operator', type=str, nargs='?')

    def handle(self, api_key, operator, **options):
        if api_key == 'stagecoach':
            stagecoach(operator)
        elif api_key == 'ticketer':
            ticketer(operator)
        else:
            bus_open_data(api_key, operator)
