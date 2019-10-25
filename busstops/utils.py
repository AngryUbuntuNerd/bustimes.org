from django.contrib.gis.geos import Polygon


def format_gbp(string):
    amount = float(string)
    if amount < 1:
        return '{}p'.format(int(amount * 100))
    return '£{:.2f}'.format(amount)


def get_bounding_box(request):
    return Polygon.from_bbox(
        [request.GET[key] for key in ('xmin', 'ymin', 'xmax', 'ymax')]
    )
