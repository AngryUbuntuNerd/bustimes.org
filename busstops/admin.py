from django import forms
from django.contrib import admin
from django.contrib.gis.db.models import PointField
from django.contrib.gis.forms import OSMWidget
from django.contrib.postgres.aggregates import StringAgg
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import Count, Q, F, Exists, OuterRef, CharField, Subquery
from django.db.models.functions import Cast
from django.urls import reverse
from django.utils.safestring import mark_safe
from bustimes.models import Route
from vehicles.models import Vehicle
from vehicles.admin import ServiceIsNullFilter
from .models import (
    Region, AdminArea, District, Locality, StopArea, StopPoint, StopCode, Operator, Service, ServiceLink,
    ServiceCode, OperatorCode, DataSource, Place, SIRISource, PaymentMethod, ServiceColour
)


@admin.register(AdminArea)
class AdminAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'atco_code', 'region_id')
    list_filter = ('region_id',)
    search_fields = ('atco_code',)


class StopCodeInline(admin.TabularInline):
    model = StopCode
    raw_id_fields = ['source']


@admin.register(StopPoint)
class StopPointAdmin(admin.ModelAdmin):
    list_display = ['atco_code', 'naptan_code', 'locality', 'admin_area', '__str__']
    list_select_related = ['locality', 'admin_area']
    list_filter = ['stop_type', 'service__region', 'admin_area']
    raw_id_fields = ['places', 'admin_area']
    search_fields = ['atco_code']
    ordering = ['atco_code']
    formfield_overrides = {
        PointField: {'widget': OSMWidget}
    }
    inlines = [StopCodeInline]
    show_full_result_count = False

    def get_search_results(self, request, queryset, search_term):
        if not search_term:
            return super().get_search_results(request, queryset, search_term)

        query = SearchQuery(search_term, search_type="websearch", config="english")
        rank = SearchRank(F('locality__search_vector'), query)
        query = Q(locality__search_vector=query)
        if ' ' not in search_term:
            query |= Q(atco_code=search_term)
        queryset = queryset.annotate(rank=rank).filter(query).order_by("-rank")
        return queryset, False


@admin.register(StopCode)
class StopCodeAdmin(admin.ModelAdmin):
    list_display = ['stop', 'code', 'source']
    raw_id_fields = ['stop', 'source']


class OperatorCodeInline(admin.TabularInline):
    model = OperatorCode


class OperatorAdminForm(forms.ModelForm):
    class Meta:
        widgets = {
            'address': forms.Textarea,
            'twitter': forms.Textarea,
        }


@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    form = OperatorAdminForm
    list_display = ['name', 'operator_codes', 'id', 'vehicle_mode', 'parent', 'region_id',
                    'services', 'vehicles', 'twitter']
    list_filter = ('region', 'vehicle_mode', 'payment_methods', 'parent')
    search_fields = ('id', 'name')
    raw_id_fields = ('region', 'regions', 'siblings', 'colour')
    inlines = [OperatorCodeInline]
    readonly_fields = ['search_vector']
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ('licences',)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if 'changelist' in request.resolver_match.view_name:
            return queryset.annotate(
                services=Subquery(
                    Service.objects.filter(
                        current=True,
                        operator=OuterRef('id')
                    ).values('operator').annotate(count=Count('pk')).values('count')
                ),
                vehicles=Subquery(
                    Vehicle.objects.filter(
                        operator=OuterRef('id')
                    ).values('operator').annotate(count=Count('pk')).values('count')
                ),
            ).prefetch_related('operatorcode_set')
        return queryset

    @admin.display(ordering='services')
    def services(self, obj):
        url = reverse('admin:busstops_service_changelist')
        return mark_safe(f'<a href="{url}?operator__id__exact={obj.id}">{obj.services or 0}</a>')

    @admin.display(ordering='vehicles')
    def vehicles(self, obj):
        url = reverse('admin:vehicles_vehicle_changelist')
        return mark_safe(f'<a href="{url}?operator__id__exact={obj.id}">{obj.vehicles or 0}</a>')

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        if request.path.endswith('/autocomplete/'):
            queryset = queryset.filter(Exists(Service.objects.filter(operator=OuterRef('pk'), current=True)))

        return queryset, use_distinct

    @staticmethod
    def payment(obj):
        return ', '.join(str(code) for code in obj.payment_methods.all())

    @staticmethod
    def operator_codes(obj):
        return ', '.join(str(code) for code in obj.operatorcode_set.all())


class ServiceCodeInline(admin.TabularInline):
    model = ServiceCode


class RouteInline(admin.TabularInline):
    model = Route
    show_change_link = True
    fields = ['source', 'code', 'service_code']
    raw_id_fields = ['source']


class FromServiceLinkInline(admin.TabularInline):
    model = ServiceLink
    fk_name = 'from_service'
    autocomplete_fields = ['to_service']


class ToServiceLinkInline(FromServiceLinkInline):
    fk_name = 'to_service'
    autocomplete_fields = ['from_service']


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'service_code', 'mode', 'region_id',
                    'current', 'show_timetable', 'timetable_wrong', 'colour', 'line_brand')
    list_filter = ('current', 'show_timetable', 'timetable_wrong', 'mode', 'region',
                   ('source', admin.RelatedOnlyFieldListFilter),
                   ('operator', admin.RelatedOnlyFieldListFilter))
    search_fields = ('service_code', 'line_name', 'line_brand', 'description')
    raw_id_fields = ('operator', 'stops', 'colour', 'source')
    inlines = [ServiceCodeInline, RouteInline, FromServiceLinkInline, ToServiceLinkInline]
    readonly_fields = ['search_vector']
    list_editable = ['colour', 'line_brand']
    list_select_related = ['colour']

    def get_search_results(self, request, queryset, search_term):
        if search_term and request.path.endswith('/autocomplete/'):
            queryset = queryset.filter(current=True)

            query = SearchQuery(search_term, search_type="websearch", config="english")
            rank = SearchRank(F('search_vector'), query)
            queryset = (
                queryset.annotate(rank=rank)
                .filter(Q(search_vector=query) | Q(service_code=search_term))
                .order_by("-rank")
            )
            return queryset, False

        return super().get_search_results(request, queryset, search_term)


@admin.register(ServiceLink)
class ServiceLinkAdmin(admin.ModelAdmin):
    save_as = True
    list_display = ('from_service', 'from_service__current', 'to_service', 'to_service__current', 'how')
    list_filter = ('from_service__current', 'to_service__current', 'from_service__source', 'to_service__source')
    autocomplete_fields = ('from_service', 'to_service')

    @staticmethod
    def from_service__current(obj):
        return obj.from_service.current

    @staticmethod
    def to_service__current(obj):
        return obj.to_service.current


@admin.register(Locality)
class LocalityAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug')
    search_fields = ('id', 'name')
    raw_id_fields = ('adjacent',)
    list_filter = ('admin_area', 'admin_area__region')


@admin.register(OperatorCode)
class OperatorCodeAdmin(admin.ModelAdmin):
    save_as = True
    list_display = ('id', 'operator', 'source', 'code')
    list_filter = [
        ('source', admin.RelatedOnlyFieldListFilter)
    ]
    search_fields = ('code',)
    raw_id_fields = ('operator',)


@admin.register(ServiceCode)
class ServiceCodeAdmin(admin.ModelAdmin):
    list_display = ('id', 'service', 'scheme', 'code')
    list_filter = (
        'scheme',
        'service__current',
        ('service__operator', admin.RelatedOnlyFieldListFilter),
        'service__stops__admin_area'
    )
    search_fields = ('code', 'service__line_name', 'service__description')
    autocomplete_fields = ['service']


@admin.register(ServiceColour)
class ServiceColourAdmin(admin.ModelAdmin):
    list_display = ('preview', 'foreground', 'background', 'services')
    search_fields = ['name']
    list_filter = ('service__operator', ServiceIsNullFilter)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if 'changelist' in request.resolver_match.view_name:
            queryset = queryset.annotate(services=Count('service', filter=Q(service__current=True)))
        return queryset

    def services(self, obj):
        return obj.services


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_filter = ('source',)
    search_fields = ('name',)


class RouteIsNullFilter(ServiceIsNullFilter):
    title = 'route is null'
    parameter_name = 'route__isnull'


class VehicleJourneyIsNullFilter(ServiceIsNullFilter):
    title = 'vehicle journey is null'
    parameter_name = 'vehiclejourney__isnull'


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    search_fields = ('name', 'url')
    list_display = ('name', 'url', 'datetime', 'settings', 'routes', 'services', 'journeys')
    list_editable = ['datetime']
    list_filter = [RouteIsNullFilter, ServiceIsNullFilter, VehicleJourneyIsNullFilter]
    actions = ['delete_routes', 'remove_datetimes']
    show_full_result_count = False

    def routes(self, obj):
        url = reverse('admin:bustimes_route_changelist')
        return mark_safe(f'<a href="{url}?source__id__exact={obj.id}">routes</a>')

    def services(self, obj):
        url = reverse('admin:busstops_service_changelist')
        return mark_safe(f'<a href="{url}?source__id__exact={obj.id}">services</a>')

    def journeys(self, obj):
        url = reverse('admin:vehicles_vehiclejourney_changelist')
        return mark_safe(f'<a href="{url}?source__id__exact={obj.id}">journeys</a>')

    def delete_routes(self, request, queryset):
        result = Route.objects.filter(source__in=queryset).delete()
        self.message_user(request, result)

    def remove_datetimes(self, request, queryset):
        result = queryset.order_by().update(datetime=None)
        self.message_user(request, result)


@admin.register(SIRISource)
class SIRISourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'requestor_ref', 'areas', 'get_poorly')

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if 'changelist' in request.resolver_match.view_name:
            return queryset.annotate(
                areas=StringAgg(Cast('admin_areas__atco_code', output_field=CharField()), ', ')
            )
        return queryset

    @staticmethod
    def areas(obj):
        return obj.areas


class PaymentMethodOperatorInline(admin.TabularInline):
    model = PaymentMethod.operator_set.through
    autocomplete_fields = ['operator']


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'operators')
    inlines = [PaymentMethodOperatorInline]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if 'changelist' in request.resolver_match.view_name:
            return queryset.annotate(operators=StringAgg('operator', ', ', distinct=True))
        return queryset

    @staticmethod
    def operators(obj):
        return obj.operators


admin.site.register(Region)
admin.site.register(District)
admin.site.register(StopArea)
