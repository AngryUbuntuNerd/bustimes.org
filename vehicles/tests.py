import time_machine
from django.test import TestCase, override_settings
from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from accounts.models import User
from busstops.models import DataSource, Region, Operator, Service
from .models import (Vehicle, VehicleType, VehicleFeature, Livery,
                     VehicleJourney, VehicleLocation, VehicleEdit, VehicleRevision, VehicleEditFeature)


class VehiclesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.datetime = '2020-10-19 23:47+00:00'

        source = DataSource.objects.create(name='HP', datetime=cls.datetime)

        ea = Region.objects.create(id='EA', name='East Anglia')

        cls.wifi = VehicleFeature.objects.create(name='Wi-Fi')
        cls.usb = VehicleFeature.objects.create(name='USB')

        cls.bova = Operator.objects.create(region=ea, name='Bova and Over', id='BOVA', slug='bova-and-over',
                                           parent='Madrigal Electromotive')
        cls.lynx = Operator.objects.create(region=ea, name='Lynx', id='LYNX', slug='lynx',
                                           parent='Madrigal Electromotive')
        cls.chicken = Operator.objects.create(region=ea, name='Chicken Bus', id='CLUCK', slug='chicken')

        tempo = VehicleType.objects.create(name='Optare Tempo', coach=False, double_decker=False)
        spectra = VehicleType.objects.create(name='Optare Spectra', coach=False, double_decker=True)

        service = Service.objects.create(service_code='49', region=ea, date='2018-12-25', tracking=True,
                                         description='Spixworth - Hunworth - Happisburgh')
        service.operator.add(cls.lynx)
        service.operator.add(cls.bova)

        cls.vehicle_1 = Vehicle.objects.create(code='2', fleet_number=1, reg='FD54JYA', vehicle_type=tempo,
                                               colours='#FF0000', notes='Trent Barton', operator=cls.lynx)
        cls.livery = Livery.objects.create(name='black with lemon piping', colours='#FF0000 #0000FF')
        cls.vehicle_2 = Vehicle.objects.create(code='50', fleet_number=50, reg='UWW2X', livery=cls.livery,
                                               vehicle_type=spectra, operator=cls.lynx)

        cls.vehicle_3 = Vehicle.objects.create(code='10', branding='Coastliner', colours='#c0c0c0')

        cls.journey = VehicleJourney.objects.create(vehicle=cls.vehicle_1, datetime=cls.datetime, source=source,
                                                    service=service, route_name='2')

        cls.location = VehicleLocation.objects.create(datetime=cls.datetime, latlong=Point(0, 51),
                                                      journey=cls.journey, current=True)
        # cls.vehicle_1.latest_location = cls.location
        cls.vehicle_1.latest_journey = cls.journey
        cls.vehicle_1.save()

        cls.vehicle_1.features.set([cls.wifi])

        cls.staff_user = User.objects.create(username='josh', is_staff=True, is_superuser=True, email='j@example.com')
        cls.trusted_user = User.objects.create(username='norma', trusted=True, email='n@example.com')
        cls.user = User.objects.create(username='ken', trusted=None, email='ken@example.com')
        cls.untrusted_user = User.objects.create(username='clem', trusted=False, email='c@example.com')

    def test_untrusted_user(self):
        self.client.force_login(self.untrusted_user)

        with self.assertNumQueries(2):
            response = self.client.get(self.vehicle_1.get_edit_url())
        self.assertEqual(response.status_code, 403)

        with self.assertNumQueries(3):
            response = self.client.get('/operators/lynx/vehicles/edit')
        self.assertEqual(response.status_code, 403)

    def test_parent(self):
        response = self.client.get('/groups/Madrigal Electromotive/vehicles')
        self.assertContains(response, 'Lynx')
        self.assertContains(response, 'Madrigal Electromotive')
        self.assertContains(response, 'Optare')

    def test_vehicle(self):
        vehicle = Vehicle(reg='3990ME')
        self.assertEqual(str(vehicle), '3990 ME')
        self.assertIn('search/?text=3990ME%20or%20%223990%20ME%22&sort', vehicle.get_flickr_url())

        vehicle.reg = 'J122018'
        self.assertEqual(str(vehicle), 'J122018')

        vehicle.notes = 'Spare ticket machine'
        self.assertEqual('', vehicle.get_flickr_link())

        vehicle = Vehicle(code='RML2604')
        self.assertIn('search/?text=RML2604&sort', vehicle.get_flickr_url())

        vehicle.operator = Operator(name='Lynx')
        self.assertIn('search/?text=Lynx%20RML2604&sort', vehicle.get_flickr_url())

        vehicle.fleet_number = '11111'
        self.assertIn('search/?text=Lynx%2011111&sort', vehicle.get_flickr_url())

        vehicle.reg = 'YN69GHA'
        vehicle.operator.parent = 'Stagecoach'
        vehicle.fleet_number = '11111'

        self.assertIn('search/?text=YN69GHA%20or%20%22YN69%20GHA%22%20or%20Stagecoach%2011111&sort',
                      vehicle.get_flickr_url())

        vehicle.code = 'YN_69_GHA'
        self.assertFalse(vehicle.fleet_number_mismatch())
        vehicle.code = 'YN19GHA'
        self.assertTrue(vehicle.fleet_number_mismatch())

    def test_fleet_lists(self):
        with self.assertNumQueries(2):
            response = self.client.get('/operators/bova-and-over/vehicles')
        self.assertEqual(404, response.status_code)
        self.assertFalse(str(response.context['exception']))

        # last seen today - should only show time
        with time_machine.travel('2020-10-20 12:00+01:00'):
            with self.assertNumQueries(2):
                response = self.client.get('/operators/lynx/vehicles')
        self.assertNotContains(response, '20 Oct')
        self.assertContains(response, '00:47')

        # last seen yesterday - should show date
        with time_machine.travel('2020-10-21 00:10+01:00'):
            with self.assertNumQueries(2):
                response = self.client.get('/operators/lynx/vehicles')
        self.assertContains(response, '20 Oct 00:47')

        self.assertTrue(response.context['code_column'])
        self.assertContains(response, '<td class="number">2</td>')

    def test_vehicle_views(self):
        with self.assertNumQueries(8):
            response = self.client.get(self.vehicle_1.get_absolute_url() + '?date=poop')
        self.assertContains(response, 'Optare Tempo')
        self.assertContains(response, 'Trent Barton')
        self.assertContains(response, '#FF0000')

        with self.assertNumQueries(7):
            response = self.client.get(self.vehicle_2.get_absolute_url())
        self.assertEqual(200, response.status_code)

        # can't connect to redis - no drama
        with override_settings(REDIS_URL='redis://localhose:69'):
            with self.assertNumQueries(1):
                response = self.client.get(f'/journeys/{self.journey.id}.json')
        self.assertEqual({}, response.json())

        self.journey.refresh_from_db()
        self.assertEqual(str(self.journey), '19 Oct 20 23:47 2  ')
        self.assertEqual(
            self.journey.get_absolute_url(),
            f'/vehicles/{self.vehicle_1.id}?date=2020-10-19#journeys/{self.journey.id}'
        )

        self.location.refresh_from_db()
        self.assertEqual(str(self.location), '19 Oct 2020 23:47:00')

    def test_location_json(self):
        location = VehicleLocation.objects.get()
        self.assertEqual(location.get_redis_json()['coordinates'], (0.0, 51.0))

        location.occupancy = 'seatsAvailable'
        self.assertEqual(location.get_redis_json()['seats'], 'Seats available')

        location.wheelchair_occupancy = 0
        location.wheelchair_capacity = 0
        self.assertNotIn('wheelchair', location.get_redis_json())

        location.wheelchair_capacity = 1
        self.assertEqual(location.get_redis_json()['wheelchair'], 'free')

    def test_vehicle_json(self):
        vehicle = Vehicle.objects.get(id=self.vehicle_2.id)
        vehicle.feature_names = "foo, bar"

        self.assertEqual(vehicle.get_json(2)["features"], "Double decker<br>foo, bar")

        vehicle = Vehicle.objects.get(id=self.vehicle_1.id)
        vehicle.feature_names = ""

        self.assertEqual(vehicle.get_json(2)["css"], "#FF0000")

    def test_vehicle_admin(self):
        self.client.force_login(self.staff_user)

        # test copy type, livery actions
        self.client.post('/admin/vehicles/vehicle/', {
            'action': 'copy_type',
            '_selected_action': [self.vehicle_1.id, self.vehicle_2.id]
        })
        self.client.post('/admin/vehicles/vehicle/', {
            'action': 'copy_livery',
            '_selected_action': [self.vehicle_1.id, self.vehicle_2.id]
        })
        self.client.post('/admin/vehicles/vehicle/', {
            'action': 'spare_ticket_machine',
            '_selected_action': [self.vehicle_1.id, self.vehicle_2.id]
        })
        response = self.client.get('/admin/vehicles/vehicle/')
        self.assertContains(response, "Copied Optare Spectra to 2 vehicles.")
        self.assertContains(response, "Copied black with lemon piping to 2 vehicles.")

        # test make livery
        self.client.post('/admin/vehicles/vehicle/', {
            'action': 'make_livery',
            '_selected_action': [self.vehicle_1.id]
        })
        response = self.client.get('/admin/vehicles/vehicle/')
        self.assertContains(response, "Select a vehicle with colours and branding.")
        self.client.post('/admin/vehicles/vehicle/', {
            'action': 'make_livery',
            '_selected_action': [self.vehicle_3.id]
        })
        response = self.client.get('/admin/vehicles/vehicle/')
        self.assertContains(response, "Updated 1 vehicles.")

        self.assertEqual(Vehicle.objects.all().count(), 3)

        # test merge 2 vehicles
        self.client.post('/admin/vehicles/vehicle/', {
            'action': 'merge',
            '_selected_action': [self.vehicle_1.id, self.vehicle_2.id]
        })
        self.assertEqual(Vehicle.objects.all().count(), 2)

    def test_livery_admin(self):
        self.client.force_login(self.staff_user)

        response = self.client.get('/admin/vehicles/livery/')
        self.assertContains(response, '<td class="field-name">black with lemon piping</td>')
        self.assertContains(response, '<td class="field-vehicles">1</td>')
        self.assertContains(response, '<td class="field-left">\
<div style="height:1.5em;width:2.25em;background:linear-gradient(to right,#FF0000 50%,#0000FF 50%)">\
</div></td>')
        self.assertContains(response, '<td class="field-right">\
<div style="height:1.5em;width:2.25em;background:linear-gradient(to left,#FF0000 50%,#0000FF 50%)">\
</div></td>')

    def test_vehicle_type_admin(self):
        self.client.force_login(self.staff_user)

        response = self.client.get('/admin/vehicles/vehicletype/')
        self.assertContains(response, "Optare Spectra")
        self.assertContains(response, '<td class="field-vehicles">1</td>', 2)

        self.client.post('/admin/vehicles/vehicletype/', {
            'action': 'merge',
            '_selected_action': [self.vehicle_1.vehicle_type_id, self.vehicle_2.vehicle_type_id]
        })
        response = self.client.get('/admin/vehicles/vehicletype/')
        self.assertContains(response, '<td class="field-vehicles">2</td>', 1)
        self.assertContains(response, '<td class="field-vehicles">0</td>', 1)

    def test_journey_admin(self):
        self.client.force_login(self.staff_user)

        response = self.client.get('/admin/vehicles/vehiclejourney/?trip__isnull=1')
        self.assertContains(response, '0 of 1 selected')

    def test_search(self):
        response = self.client.get('/search?q=fd54jya')
        self.assertContains(response, '1 vehicle')

    def test_livery(self):
        livery = Livery(name='Go-Coach')
        self.assertEqual('Go-Coach', str(livery))
        self.assertIsNone(livery.preview())

        livery.colours = '#7D287D #FDEE00 #FDEE00'
        livery.horizontal = True
        livery.save()
        self.assertEqual('<div style="height:1.5em;width:2.25em;background:linear-gradient' +
                         '(to top,#7D287D 34%,#FDEE00 34%)" title="Go-Coach"></div>', livery.preview())
        livery.horizontal = False
        livery.angle = 45
        livery.save()
        self.assertEqual('linear-gradient(45deg,#7D287D 34%,#FDEE00 34%)', livery.left_css)
        self.assertEqual('linear-gradient(315deg,#7D287D 34%,#FDEE00 34%)', livery.right_css)

        livery.angle = None
        livery.save()
        self.vehicle_1.livery = livery
        self.assertEqual('linear-gradient(to left,#7D287D 34%,#FDEE00 34%)',
                         self.vehicle_1.get_livery(179))
        self.assertIsNone(self.vehicle_1.get_text_colour())

        self.vehicle_1.livery.colours = '#c0c0c0'
        self.vehicle_1.livery.save()
        self.assertEqual('#c0c0c0', self.vehicle_1.get_livery(200))

        livery.css = 'linear-gradient(45deg,#ED1B23 35%,#fff 35%,#fff 45%,#ED1B23 45%)'
        livery.set_css()
        self.assertEqual(livery.left_css, 'linear-gradient(45deg,#ED1B23 35%,#fff 35%,#fff 45%,#ED1B23 45%)')
        self.assertEqual(livery.right_css, 'linear-gradient(315deg,#ED1B23 35%,#fff 35%,#fff 45%,#ED1B23 45%)')

        response = self.client.get('/liveries.44.css')
        self.assertContains(
            response,
            "{background:linear-gradient(to right,#FF0000 50%,#0000FF 50%);color:#fff}.livery-"
        )

    def test_vehicle_edit_1(self):
        url = self.vehicle_1.get_edit_url()

        with self.assertNumQueries(0):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f'/accounts/login/?next={url}')

        with self.assertNumQueries(0):
            response = self.client.get(response.url)
        self.assertContains(response, '<p>To edit vehicle details, please log in.</p>')

        self.client.force_login(self.staff_user)

        with self.assertNumQueries(12):
            response = self.client.get(url)
        self.assertNotContains(response, 'already')

        initial = {
            'fleet_number': '1',
            'reg': 'FD54JYA',
            'vehicle_type': self.vehicle_1.vehicle_type_id,
            'features': self.wifi.id,
            'operator': self.lynx.id,
            'colours': '#FF0000',
            'other_colour': '#ffffff',
            'notes': 'Trent Barton',
        }

        # edit nothing
        with self.assertNumQueries(15):
            response = self.client.post(url, initial)
        self.assertFalse(response.context['form'].has_changed())
        self.assertNotContains(response, 'already')

        # edit fleet number
        initial['fleet_number'] = '2'
        initial['previous_reg'] = 'cock'
        with self.assertNumQueries(14):
            response = self.client.post(url, initial)
        self.assertIsNone(response.context['form'])
        self.assertContains(response, 'Changed fleet number from 1 to 2')
        self.assertContains(response, 'I’ll update the other details')

        edit = VehicleEdit.objects.filter(approved=None).get()
        self.assertEqual(edit.colours, '')
        self.assertEqual(edit.get_changes(), {
            'Previous reg': 'COCK'
        })

        # edit type, livery and name with bad URL
        initial['colours'] = self.livery.id
        with self.assertNumQueries(15):
            response = self.client.post(url, {
                **initial,
                'url': 'http://localhost',
                'vehicle_type': self.vehicle_2.vehicle_type_id,
                'name': 'Colin'
            })
        self.assertTrue(response.context['form'].has_changed())
        self.assertContains(response, 'That URL does')
        self.assertContains(response, '/edit-vehicle.')

        response = self.client.get('/admin/vehicles/vehicleedit/')
        self.assertContains(response, '<td class="field-reg">FD54JYA</td>')
        self.assertContains(response, '<td class="field-vehicle_type">Optare Tempo</td>')

        # should not create an edit
        with self.assertNumQueries(15):
            initial['colours'] = '#FFFF00'
            response = self.client.post(url, initial)
        self.assertTrue(response.context['form'].has_changed())
        self.assertContains(response, 'Select a valid choice. #FFFF00 is not one of the available choices')
        self.assertContains(response, 'already')

        self.assertEqual(1, VehicleEdit.objects.all().count())

        response = self.client.get('/admin/accounts/user/')
        self.assertContains(
            response,
            '<td class="field-approved">'
            f'<a href="/admin/vehicles/vehicleedit/?user={self.staff_user.id}&approved__exact=1">0</a></td>'
            '<td class="field-disapproved">'
            f'<a href="/admin/vehicles/vehicleedit/?user={self.staff_user.id}&approved__exact=0">0</a></td>'
            '<td class="field-pending">'
            f'<a href="/admin/vehicles/vehicleedit/?user={self.staff_user.id}&approved__isnull=True">1</a></td>'
        )

        with self.assertNumQueries(9):
            response = self.client.get('/admin/vehicles/vehicleedit/')
        self.assertContains(response, '<ins>COCK</ins>')
        self.assertEqual(1, response.context_data['cl'].result_count)

        del initial['colours']

        # staff user can fully edit branding and notes
        initial['branding'] = 'Crag Hopper'
        initial['notes'] = 'West Coast Motors'
        with self.assertNumQueries(14):
            response = self.client.post(url, initial)
        self.assertContains(response, 'Changed notes from Trent Barton to West Coast Motors')
        self.assertContains(response, 'Changed branding to Crag Hopper')

        del initial['previous_reg']

        # remove a feature
        del initial['features']
        with self.assertNumQueries(13):
            response = self.client.post(url, initial)

        vef = VehicleEditFeature.objects.get()
        self.assertEqual(str(vef), '<del>Wi-Fi</del>')

        edit = vef.edit
        self.assertEqual(edit.get_changes(), {'features': [vef]})

    def test_vehicle_edit_2(self):
        self.client.force_login(self.staff_user)

        url = self.vehicle_2.get_edit_url()

        initial = {
            'fleet_number': '50',
            'reg': 'UWW2X',
            'vehicle_type': self.vehicle_2.vehicle_type_id,
            'colours': self.livery.id,
            'other_colour': '#ffffff',
            'notes': '',
        }

        with self.assertNumQueries(12):
            response = self.client.post(url, initial)
        # self.assertTrue(response.context['form'].fields['fleet_number'].disabled)
        self.assertFalse(response.context['form'].has_changed())
        self.assertNotContains(response, 'already')

        self.assertEqual(0, VehicleEdit.objects.count())

        self.assertNotContains(response, '/operators/bova-and-over')

        initial['notes'] = 'Ex Ipswich Buses'
        initial['name'] = 'Luther Blisset'
        initial['branding'] = 'Coastliner'
        with self.assertNumQueries(12):
            initial['reg'] = ''
            response = self.client.post(url, initial)
        self.assertIsNone(response.context['form'])

        self.assertContains(response, '<p>I’ll update the other details shortly</p>')

        edit = VehicleEdit.objects.get()
        self.assertEqual(edit.get_changes(), {'reg': ''})

        response = self.client.get('/vehicles/history')
        self.assertContains(response, 'Luther Blisset')

        response = self.client.get(f'{self.vehicle_2.get_absolute_url()}/history')
        self.assertContains(response, 'Luther Blisset')

        with self.assertNumQueries(11):
            response = self.client.get(url)
        self.assertContains(response, 'already')

    def test_vehicle_edit_colour(self):
        self.client.force_login(self.staff_user)
        url = self.vehicle_2.get_edit_url()

        initial = {
            'fleet_number': '50',
            'reg': 'UWW2X',
            'vehicle_type': self.vehicle_2.vehicle_type_id,
            'colours': self.livery.id,
            'other_colour': '',
            'notes': '',
        }

        with self.assertNumQueries(12):
            response = self.client.post(url, initial)
            self.assertContains(response, 'You haven&#x27;t changed anything')

        initial['colours'] = 'Other'
        initial['other_colour'] = 'Bath is my favourite spa town, and so is Harrogate'
        with self.assertNumQueries(12):
            response = self.client.post(url, initial)
            self.assertEqual(response.context['form'].errors, {'other_colour': [
                'An HTML5 simple color must be a Unicode string exactly seven characters long.'
            ]})

    def test_remove_fleet_number(self):
        self.client.force_login(self.staff_user)

        url = self.vehicle_1.get_edit_url()

        with self.assertNumQueries(14):
            self.client.post(url, {
                'fleet_number': '',
                'reg': '',
                'operator': self.lynx.id,
            })

        revision = VehicleRevision.objects.get()
        self.assertEqual(str(revision), 'notes: Trent Barton → ')

        edit = VehicleEdit.objects.get()

        with self.assertNumQueries(16):
            self.client.post('/admin/vehicles/vehicleedit/', {
                'action': 'apply_edits',
                '_selected_action': edit.id
            })

        edit.refresh_from_db()
        self.assertIsNone(edit.approved)

        vehicle = Vehicle.objects.get(id=self.vehicle_1.id)
        self.assertIsNone(vehicle.fleet_number)
        self.assertEqual('', vehicle.fleet_code)
        self.assertEqual('', vehicle.reg)

        # test user view
        response = self.client.get(self.staff_user.get_absolute_url())
        self.assertContains(response, '1 other edit,')
        self.assertContains(response, 'Trent Barton')

    def test_vehicle_edit_3(self):
        self.client.force_login(self.user)

        with self.assertNumQueries(7):
            response = self.client.get(self.vehicle_3.get_edit_url())
        self.assertNotContains(response, 'livery')
        self.assertNotContains(response, 'notes')

        with self.assertNumQueries(5):
            # new user - can create a VehicleEdit
            response = self.client.post(self.vehicle_3.get_edit_url(), {
                'reg': 'D19 FOX',
                'previous_reg': 'QC FBPE',
                'withdrawn': True
            })
        self.assertContains(response, "I’ll update those details shortly")

        edit = VehicleEdit.objects.get()
        self.assertFalse(edit.vehicle.withdrawn)
        edit.apply(save=False)
        self.assertTrue(edit.vehicle.withdrawn)

        with self.assertNumQueries(10):
            response = self.client.post(self.vehicle_2.get_edit_url(), {
                'reg': self.vehicle_2.reg,
                'vehicle_type': self.vehicle_2.vehicle_type_id,
                'colours': 'Other',
            })
            self.assertContains(response, "I’ll update those details shortly")

        self.client.force_login(self.trusted_user)

        with self.assertNumQueries(6):
            # trusted user - can edit reg and remove branding
            response = self.client.post(self.vehicle_3.get_edit_url(), {
                'reg': 'DA04 DDA',
                'branding': ''
            })
        self.assertContains(response, 'Changed reg to DA04DDA')
        self.assertContains(response, 'Changed branding from Coastliner to')

        with self.assertNumQueries(12):
            # trusted user - can edit colour
            response = self.client.post(self.vehicle_2.get_edit_url(), {
                'reg': self.vehicle_2.reg,
                'vehicle_type': self.vehicle_2.vehicle_type_id,
                'operator': self.vehicle_2.operator_id,
                'colours': 'Other',
            })
        self.assertContains(response, 'Changed livery from black with lemon piping to None')
        self.assertContains(response, 'Changed colours to Other')

        revision = VehicleRevision.objects.last()
        self.assertEqual(list(revision.revert()), [
            f'vehicle {revision.vehicle_id} colours not reverted',
            f"vehicle {revision.vehicle_id} reverted ['livery']"
        ])
        revision = VehicleRevision.objects.first()
        self.assertEqual(list(revision.revert()), [
            f'vehicle {revision.vehicle_id} branding not reverted',
            f"vehicle {revision.vehicle_id} reverted ['reg']"
        ])
        self.assertEqual(revision.vehicle.reg, '')

    def test_vehicles_edit(self):
        self.client.force_login(self.trusted_user)

        with self.assertNumQueries(8):
            response = self.client.post('/operators/lynx/vehicles/edit')
        self.assertContains(response, 'Select vehicles to update')
        self.assertFalse(VehicleEdit.objects.all())
        self.assertFalse(VehicleRevision.objects.all())

        # change vehicle type and colours:
        with self.assertNumQueries(17):
            response = self.client.post('/operators/lynx/vehicles/edit', {
                'vehicle': self.vehicle_1.id,
                'operator': self.lynx.id,  # (no change)
                'vehicle_type': self.vehicle_2.vehicle_type_id,
                'colours': self.livery.id
            })
        self.assertContains(response, '1 vehicle updated')
        revision = VehicleRevision.objects.get()
        self.assertIsNone(revision.from_livery)
        self.assertTrue(revision.to_livery)
        self.assertEqual('Optare Tempo', revision.from_type.name)
        self.assertEqual('Optare Spectra', revision.to_type.name)
        self.assertContains(response, 'FD54 JYA')

        # withdraw
        with self.assertNumQueries(13):
            response = self.client.post('/operators/lynx/vehicles/edit', {
                'vehicle': self.vehicle_1.id,
                'withdrawn': 'on',
            })
        revision = VehicleRevision.objects.last()
        self.assertEqual(revision.changes, {'withdrawn': '-No\n+Yes'})
        self.assertContains(response, '1 vehicle updated')
        self.assertNotContains(response, 'FD54 JYA')

        self.client.force_login(self.staff_user)

        # revert
        self.client.post('/admin/vehicles/vehiclerevision/', {
            'action': 'revert',
            '_selected_action': revision.id
        })
        response = self.client.get('/admin/vehicles/vehiclerevision/')
        self.assertContains(response, "reverted [&#x27;withdrawn&#x27;]")

    def test_validation(self):
        vehicle = Vehicle(colours='ploop')
        with self.assertRaises(ValidationError):
            vehicle.clean()

        vehicle.colours = ''
        vehicle.clean()

    def test_big_map(self):
        with self.assertNumQueries(0):
            self.client.get('/map')

    def test_vehicles(self):
        with self.assertNumQueries(2):
            self.client.get('/vehicles')

    def test_journey_debug(self):
        with self.assertNumQueries(1):
            response = self.client.get(f'/journeys/{self.journey.id}/debug')
        self.assertEqual({}, response.json())

    def test_service_vehicle_history(self):
        with self.assertNumQueries(5):
            response = self.client.get('/services/spixworth-hunworth-happisburgh/vehicles?date=poop')
        self.assertContains(response, 'Vehicles')
        self.assertContains(response, '/vehicles/')
        self.assertContains(response, '<option selected value="2020-10-20">Tuesday 20 October 2020</option>')
        self.assertContains(response, '1 - FD54 JYA')

        with self.assertNumQueries(5):
            response = self.client.get('/services/spixworth-hunworth-happisburgh/vehicles?date=2004-04-04')
        self.assertNotContains(response, '1 - FD54 JYA')

    def test_api(self):
        with self.assertNumQueries(2):
            response = self.client.get('/api/vehicles/?limit=2')
        self.assertEqual(
            response.json(),
            {'count': 3, 'next': 'http://testserver/api/vehicles/?limit=2&offset=2', 'previous': None, 'results': [
                {'id': self.vehicle_1.id,
                    'operator': {'id': 'LYNX', 'name': 'Lynx', 'parent': 'Madrigal Electromotive'},
                    'livery': {'id': None, 'name': None, 'left': '#FF0000', 'right': '#FF0000'},
                    'fleet_number': 1, 'fleet_code': '1', 'reg': 'FD54JYA', 'name': '',
                    'branding': '', 'notes': 'Trent Barton', 'withdrawn': False,
                    'vehicle_type': {
                        'id': self.vehicle_1.vehicle_type_id,
                        'name': 'Optare Tempo', 'double_decker': False, 'coach': False, 'electric': None}},
                {'id': self.vehicle_2.id,
                    'operator': {'id': 'LYNX', 'name': 'Lynx', 'parent': 'Madrigal Electromotive'},
                    'livery': {'id': self.livery.id, 'name': 'black with lemon piping',
                               'left': 'linear-gradient(to right,#FF0000 50%,#0000FF 50%)',
                               'right': 'linear-gradient(to left,#FF0000 50%,#0000FF 50%)'},
                    'fleet_number': 50, 'fleet_code': '50', 'reg': 'UWW2X', 'name': '', 'branding': '', 'notes': '',
                    'withdrawn': False,
                    'vehicle_type': {
                        'id': self.vehicle_2.vehicle_type_id,
                        'name': 'Optare Spectra', 'double_decker': True, 'coach': False, 'electric': None}}
            ]}
        )

        with self.assertNumQueries(1):
            response = self.client.get('/api/vehicles/?reg=sa60twp')
        self.assertEqual(0, response.json()['count'])

        with self.assertNumQueries(2):
            response = self.client.get('/api/vehicles/?search=fd54jya')
        self.assertEqual(1, response.json()['count'])
