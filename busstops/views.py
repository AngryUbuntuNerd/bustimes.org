from django.shortcuts import render
from django.views.generic.detail import DetailView
from busstops.models import StopPoint, Locality, AdminArea, Region, District, Operator, Service, ServiceVersion, JourneyPatternSection, JourneyPatternTimingLink, VehicleJourney, OperatingProfile
# from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import datetime, date

from django.contrib.gis.geos import *
from django.contrib.gis.measure import D

def index(request):
    context = {
        'regions': Region.objects.all(),
        'operators': Operator.objects.all()
    }
    return render(request, 'index.html', context)

def coordinates(request, latitude, longitude):
    point = Point(map(float, (longitude, latitude)))
    context = {
        'point': point,
        'stops': StopPoint.objects.distance(point).order_by('distance')[:10]
    }
    print context['stops']
    return render(request, 'coordinates.html', context)


class RegionDetailView(DetailView):
    model = Region

    def get_context_data(self, **kwargs):
        context = super(RegionDetailView, self).get_context_data(**kwargs)
        context['areas'] = AdminArea.objects.filter(region=self.object).exclude(stoppoint=None).order_by('name')
        return context


class AdminAreaDetailView(DetailView):
    model = AdminArea

    def get_context_data(self, **kwargs):
        context = super(AdminAreaDetailView, self).get_context_data(**kwargs)
        # Districts in this administrative area, if any
        context['districts'] = District.objects.filter(admin_area=self.object)
        # Localities in this administrative area that don't belong to any district, if any
        context['localities'] = Locality.objects.filter(admin_area=self.object, district=None).exclude(stoppoint=None).order_by('name')
        # Stops in this administrative area whose locality belongs to a different administrative area
        # These are usually National Rail/Air/Ferry, but also (more awkwardly) may be around the boundary of two areas
        context['stops'] = StopPoint.objects.filter(admin_area=self.object, active=True).exclude(locality__admin_area=self.object
            ).exclude(locality__admin_area__region=self.object.region).order_by('common_name')
        return context


class DistrictDetailView(DetailView):
    model = District

    def get_context_data(self, **kwargs):
        context = super(DistrictDetailView, self).get_context_data(**kwargs)
        context['localities'] = Locality.objects.filter(district=self.object).order_by('name')
        return context


class LocalityDetailView(DetailView):
    model = Locality

    def get_context_data(self, **kwargs):
        context = super(LocalityDetailView, self).get_context_data(**kwargs)
        context['stops'] = StopPoint.objects.filter(locality=self.object, active=True).order_by('common_name')
        return context


class StopPointDetailView(DetailView):
    model = StopPoint

    def get_context_data(self, **kwargs):
        context = super(StopPointDetailView, self).get_context_data(**kwargs)
        context['nearby'] = StopPoint.objects.filter(locality=self.object.locality)
        return context
