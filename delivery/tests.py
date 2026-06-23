# tests.py - Complete test suite for SwiftDeliver
# Place this file in: swift_deliver/delivery/tests.py

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import json

from delivery.models import UserProfile, Location, MenuItem, Order, OrderItem
from delivery.utils import (
    TRAVEL_TIMES,
    ensure_locations,
    calculate_nearest_neighbor_route,
    validate_route_feasibility,
    get_location_data
)


# ==================== TEST: Model Tests ====================

class UserProfileModelTest(TestCase):
    """Test UserProfile model creation and properties."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password123')
    
    def test_userprofile_auto_created(self):
        """UserProfile should be auto-created via signal."""
        self.assertTrue(hasattr(self.user, 'userprofile'))
        self.assertEqual(self.user.userprofile.role, 'CUSTOMER')
        self.assertTrue(self.user.userprofile.is_approved)
    
    def test_userprofile_roles(self):
        """Test different role assignments."""
        profile = self.user.userprofile
        profile.role = 'MERCHANT'
        profile.is_approved = False
        profile.save()
        
        refreshed = UserProfile.objects.get(id=profile.id)
        self.assertEqual(refreshed.role, 'MERCHANT')
        self.assertFalse(refreshed.is_approved)
    
    def test_userprofile_str(self):
        """Test string representation."""
        expected = "testuser (CUSTOMER)"
        self.assertEqual(str(self.user.userprofile), expected)


class LocationModelTest(TestCase):
    """Test Location model."""
    
    def setUp(self):
        self.location = Location.objects.create(
            name="Test Restaurant",
            address="123 Test St",
            is_restaurant=True,
            matrix_id=0,
            grid_x=100,
            grid_y=200
        )
    
    def test_location_creation(self):
        self.assertEqual(self.location.name, "Test Restaurant")
        self.assertTrue(self.location.is_restaurant)
        self.assertEqual(self.location.matrix_id, 0)
    
    def test_location_str(self):
        self.assertEqual(str(self.location), "Test Restaurant")


class MenuItemModelTest(TestCase):
    """Test MenuItem model."""
    
    def setUp(self):
        self.merchant = User.objects.create_user('merchant1', 'm@test.com', 'pass123')
        self.merchant.userprofile.role = 'MERCHANT'
        self.merchant.userprofile.is_approved = True
        self.merchant.userprofile.save()
        
        self.item = MenuItem.objects.create(
            merchant=self.merchant,
            name="Burger",
            description="Tasty burger",
            price=9.99
        )
    
    def test_menu_item_creation(self):
        self.assertEqual(self.item.name, "Burger")
        self.assertEqual(self.item.price, 9.99)
        self.assertEqual(self.item.merchant, self.merchant)
    
    def test_menu_item_str(self):
        self.assertEqual(str(self.item), "Burger")


class OrderModelTest(TestCase):
    """Test Order and OrderItem models."""
    
    def setUp(self):
        self.customer = User.objects.create_user('customer1', 'c@test.com', 'pass123')
        self.merchant = User.objects.create_user('merchant2', 'm2@test.com', 'pass123')
        self.merchant.userprofile.role = 'MERCHANT'
        self.merchant.userprofile.save()
        
        self.location = Location.objects.create(
            name="Test Address",
            address="456 Test Ave",
            is_restaurant=False,
            matrix_id=1,
            grid_x=200,
            grid_y=300
        )
        
        self.order = Order.objects.create(
            customer=self.customer,
            merchant=self.merchant,
            destination=self.location,
            status='PENDING',
            due_time=timezone.now() + timedelta(hours=2),
            notes="Test order"
        )
        
        self.item = MenuItem.objects.create(
            merchant=self.merchant,
            name="Pizza",
            price=12.99
        )
        
        self.order_item = OrderItem.objects.create(
            order=self.order,
            menu_item=self.item,
            quantity=2
        )
    
    def test_order_creation(self):
        self.assertEqual(self.order.customer, self.customer)
        self.assertEqual(self.order.merchant, self.merchant)
        self.assertEqual(self.order.status, 'PENDING')
    
    def test_order_item_line_total(self):
        self.assertEqual(self.order_item.line_total, 25.98)
    
    def test_order_str(self):
        expected = "Order #{} - PENDING".format(self.order.id)
        self.assertEqual(str(self.order), expected)


# ==================== TEST: Utility Function Tests ====================

class UtilsTest(TestCase):
    """Test utility functions in utils.py."""
    
    def test_ensure_locations_safe(self):
        """ensure_locations should not crash if table exists."""
        ensure_locations()
        count = Location.objects.count()
        self.assertEqual(count, 9)  # 9 locations seeded
    
    def test_get_location_data(self):
        data = get_location_data(0)
        self.assertIsNotNone(data)
        self.assertEqual(data['name'], "City Central Restaurant")
        self.assertTrue(data['is_restaurant'])
    
    def test_get_location_data_invalid(self):
        data = get_location_data(999)
        self.assertIsNone(data)
    
    def test_travel_times_matrix_size(self):
        self.assertEqual(len(TRAVEL_TIMES), 9)
        for row in TRAVEL_TIMES:
            self.assertEqual(len(row), 9)
    
    def test_travel_times_diagonal_zero(self):
        """Travel time from a location to itself should be 0."""
        for i in range(9):
            self.assertEqual(TRAVEL_TIMES[i][i], 0)
    
    def test_travel_times_asymmetric(self):
        """Travel times should be asymmetric (realistic)."""
        self.assertNotEqual(TRAVEL_TIMES[0][1], TRAVEL_TIMES[1][0])
    
    def test_calculate_nearest_neighbor_route(self):
        route, total_time = calculate_nearest_neighbor_route(0, [1, 2, 3])
        self.assertEqual(route[0], 0)  # Starts at restaurant
        self.assertEqual(len(route), 4)  # 4 stops total
        self.assertGreater(total_time, 0)
    
    def test_calculate_nearest_neighbor_single_destination(self):
        route, total_time = calculate_nearest_neighbor_route(0, [1])
        self.assertEqual(route, [0, 1])
        self.assertEqual(total_time, TRAVEL_TIMES[0][1])
    
    def test_validate_route_feasibility_success(self):
        """Route should be feasible with distant due time."""
        due_times = {1: timezone.now() + timedelta(hours=24)}
        is_feasible, route, details = validate_route_feasibility([1], due_times, timezone.now())
        self.assertTrue(is_feasible)
        self.assertEqual(route[0], 0)
        self.assertEqual(route[1], 1)
    
    def test_validate_route_feasibility_failure(self):
        """Route should fail with impossible due time."""
        due_times = {1: timezone.now() - timedelta(hours=1)}  # Past due time
        is_feasible, route, details = validate_route_feasibility([1], due_times, timezone.now())
        self.assertFalse(is_feasible)
        self.assertFalse(details[0]['on_time'])


# ==================== TEST: View Tests ====================

class AuthViewTest(TestCase):
    """Test authentication views."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password123')
        self.user.userprofile.role = 'CUSTOMER'
        self.user.userprofile.is_approved = True
        self.user.userprofile.save()
    
    def test_login_page_loads(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome Back")
    
    def test_login_success(self):
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['redirect'], '/dashboard/')
    
    def test_login_invalid_credentials(self):
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('error', data)
    
    def test_login_unapproved_merchant(self):
        merchant = User.objects.create_user('merchant', 'm@test.com', 'pass123')
        merchant.userprofile.role = 'MERCHANT'
        merchant.userprofile.is_approved = False
        merchant.userprofile.save()
        
        response = self.client.post(reverse('login'), {
            'username': 'merchant',
            'password': 'pass123'
        })
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('pending', data['error'].lower())
    
    def test_logout(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_register_page_loads(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
    
    def test_register_customer_auto_approved(self):
        response = self.client.post(reverse('register'), 
            data=json.dumps({
                'username': 'newcustomer',
                'email': 'new@test.com',
                'password': 'newpass123',
                'role': 'CUSTOMER'
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        user = User.objects.get(username='newcustomer')
        self.assertEqual(user.userprofile.role, 'CUSTOMER')
        self.assertTrue(user.userprofile.is_approved)
    
    def test_register_merchant_pending(self):
        response = self.client.post(reverse('register'), 
            data=json.dumps({
                'username': 'newmerchant',
                'email': 'merchant@test.com',
                'password': 'newpass123',
                'role': 'MERCHANT'
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        user = User.objects.get(username='newmerchant')
        self.assertEqual(user.userprofile.role, 'MERCHANT')
        self.assertFalse(user.userprofile.is_approved)
    
    def test_register_duplicate_username(self):
        response = self.client.post(reverse('register'), 
            data=json.dumps({
                'username': 'testuser',
                'email': 'test2@test.com',
                'password': 'pass123',
                'role': 'CUSTOMER'
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('already taken', data['error'])


class DashboardAccessTest(TestCase):
    """Test role-based dashboard access."""
    
    def setUp(self):
        self.client = Client()
        self.customer = User.objects.create_user('customer', 'c@test.com', 'pass123')
        self.customer.userprofile.role = 'CUSTOMER'
        self.customer.userprofile.is_approved = True
        self.customer.userprofile.save()
        
        self.merchant = User.objects.create_user('merchant', 'm@test.com', 'pass123')
        self.merchant.userprofile.role = 'MERCHANT'
        self.merchant.userprofile.is_approved = True
        self.merchant.userprofile.save()
        
        self.courier = User.objects.create_user('courier', 'co@test.com', 'pass123')
        self.courier.userprofile.role = 'COURIER'
        self.courier.userprofile.is_approved = True
        self.courier.userprofile.save()
        
        self.admin = User.objects.create_user('admin', 'a@test.com', 'pass123')
        self.admin.userprofile.role = 'ADMIN'
        self.admin.userprofile.is_approved = True
        self.admin.userprofile.save()
    
    def test_customer_dashboard_access(self):
        self.client.login(username='customer', password='pass123')
        response = self.client.get(reverse('customer_dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_customer_cannot_access_merchant_dashboard(self):
        self.client.login(username='customer', password='pass123')
        response = self.client.get(reverse('merchant_dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirected
    
    def test_merchant_dashboard_access(self):
        self.client.login(username='merchant', password='pass123')
        response = self.client.get(reverse('merchant_dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_courier_dashboard_access(self):
        self.client.login(username='courier', password='pass123')
        response = self.client.get(reverse('courier_dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_admin_dashboard_access(self):
        self.client.login(username='admin', password='pass123')
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_unauthenticated_redirect(self):
        response = self.client.get(reverse('customer_dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login


# ==================== TEST: API Endpoint Tests ====================

class MerchantAPITest(TestCase):
    """Test merchant API endpoints."""
    
    def setUp(self):
        self.client = Client()
        self.merchant = User.objects.create_user('merchant', 'm@test.com', 'pass123')
        self.merchant.userprofile.role = 'MERCHANT'
        self.merchant.userprofile.is_approved = True
        self.merchant.userprofile.save()
        
        self.client.login(username='merchant', password='pass123')
        
        # Seed locations
        ensure_locations()
        self.location = Location.objects.filter(is_restaurant=False).first()
    
    def test_add_menu_item(self):
        response = self.client.post(reverse('api_add_menu_item'),
            data=json.dumps({
                'name': 'Test Burger',
                'description': 'A test burger',
                'price': 10.99
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['name'], 'Test Burger')
        
        item = MenuItem.objects.get(id=data['item_id'])
        self.assertEqual(item.merchant, self.merchant)
    
    def test_add_menu_item_invalid_price(self):
        response = self.client.post(reverse('api_add_menu_item'),
            data=json.dumps({
                'name': 'Bad Item',
                'description': 'Test',
                'price': 0
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertFalse(data['success'])
    
    def test_create_order_with_items(self):
        # First add a menu item
        item = MenuItem.objects.create(
            merchant=self.merchant,
            name='Pizza',
            price=12.99
        )
        
        response = self.client.post(reverse('api_merchant_create_order'),
            data=json.dumps({
                'destination_id': self.location.id,
                'due_time': (timezone.now() + timedelta(hours=2)).isoformat(),
                'notes': 'Test order',
                'items': [{'id': item.id, 'quantity': 2}]
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        order = Order.objects.get(id=data['order_id'])
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().quantity, 2)


class CustomerAPITest(TestCase):
    """Test customer API endpoints."""
    
    def setUp(self):
        self.client = Client()
        self.customer = User.objects.create_user('customer', 'c@test.com', 'pass123')
        self.customer.userprofile.role = 'CUSTOMER'
        self.customer.userprofile.is_approved = True
        self.customer.userprofile.save()
        
        self.merchant = User.objects.create_user('merchant', 'm@test.com', 'pass123')
        self.merchant.userprofile.role = 'MERCHANT'
        self.merchant.userprofile.is_approved = True
        self.merchant.userprofile.save()
        
        self.client.login(username='customer', password='pass123')
        
        # Create menu items
        self.item1 = MenuItem.objects.create(merchant=self.merchant, name='Burger', price=8.99)
        self.item2 = MenuItem.objects.create(merchant=self.merchant, name='Fries', price=2.99)
        
        ensure_locations()
        self.location = Location.objects.filter(is_restaurant=False).first()
    
    def test_get_merchants(self):
        response = self.client.get(reverse('api_merchants'))
        data = json.loads(response.content)
        self.assertEqual(len(data['merchants']), 1)
        self.assertEqual(data['merchants'][0]['name'], 'merchant')
    
    def test_get_menu(self):
        response = self.client.get(reverse('api_menu', args=[self.merchant.id]))
        data = json.loads(response.content)
        self.assertEqual(len(data['items']), 2)
        self.assertEqual(data['items'][0]['name'], 'Burger')
    
    def test_place_order(self):
        response = self.client.post(reverse('api_place_order'),
            data=json.dumps({
                'merchant_id': self.merchant.id,
                'items': [
                    {'id': self.item1.id, 'quantity': 1},
                    {'id': self.item2.id, 'quantity': 2}
                ],
                'destination_id': self.location.id
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['total'], 14.97)  # 8.99 + (2.99 * 2)
        
        order = Order.objects.get(id=data['order_id'])
        self.assertEqual(order.customer, self.customer)
        self.assertEqual(order.items.count(), 2)
    
    def test_place_order_empty_cart(self):
        response = self.client.post(reverse('api_place_order'),
            data=json.dumps({
                'merchant_id': self.merchant.id,
                'items': [],
                'destination_id': self.location.id
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('empty', data['error'].lower())


class CourierAPITest(TestCase):
    """Test courier API endpoints."""
    
    def setUp(self):
        self.client = Client()
        
        # Seed locations
        ensure_locations()
        
        # Create users
        self.merchant = User.objects.create_user('merchant', 'm@test.com', 'pass123')
        self.merchant.userprofile.role = 'MERCHANT'
        self.merchant.userprofile.is_approved = True
        self.merchant.userprofile.save()
        
        self.customer = User.objects.create_user('customer', 'c@test.com', 'pass123')
        self.customer.userprofile.role = 'CUSTOMER'
        self.customer.userprofile.is_approved = True
        self.customer.userprofile.save()
        
        self.courier = User.objects.create_user('courier', 'co@test.com', 'pass123')
        self.courier.userprofile.role = 'COURIER'
        self.courier.userprofile.is_approved = True
        self.courier.userprofile.save()
        
        # Create orders
        self.location1 = Location.objects.get(matrix_id=1)
        self.location2 = Location.objects.get(matrix_id=2)
        
        self.order1 = Order.objects.create(
            customer=self.customer,
            merchant=self.merchant,
            destination=self.location1,
            status='PENDING',
            due_time=timezone.now() + timedelta(hours=24),
            notes='Order 1'
        )
        
        self.order2 = Order.objects.create(
            customer=self.customer,
            merchant=self.merchant,
            destination=self.location2,
            status='PENDING',
            due_time=timezone.now() + timedelta(hours=24),
            notes='Order 2'
        )
        
        self.client.login(username='courier', password='pass123')
    
    def test_get_available_orders(self):
        response = self.client.get(reverse('api_orders'))
        data = json.loads(response.content)
        # Courier has no orders yet, so should be empty or show available
        self.assertIn('orders', data)
    
    def test_accept_single_order(self):
        response = self.client.post(reverse('api_accept_orders'),
            data=json.dumps({
                'order_ids': [self.order1.id]
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        self.order1.refresh_from_db()
        self.assertEqual(self.order1.courier, self.courier)
        self.assertEqual(self.order1.status, 'ACCEPTED')
    
    def test_accept_multiple_orders(self):
        response = self.client.post(reverse('api_accept_orders'),
            data=json.dumps({
                'order_ids': [self.order1.id, self.order2.id]
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('route', data)
        self.assertIn('details', data)
    
    def test_accept_no_orders_selected(self):
        response = self.client.post(reverse('api_accept_orders'),
            data=json.dumps({
                'order_ids': []
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('No orders selected', data['error'])
    
    def test_update_status_to_delivered(self):
        # First accept the order
        self.order1.courier = self.courier
        self.order1.status = 'OUT_FOR_DELIVERY'
        self.order1.save()
        
        response = self.client.post(reverse('api_update_status'),
            data=json.dumps({
                'order_id': self.order1.id,
                'status': 'DELIVERED'
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        self.order1.refresh_from_db()
        self.assertEqual(self.order1.status, 'DELIVERED')
        self.assertIsNotNone(self.order1.delivered_at)
    
    def test_route_feasibility_rejection(self):
        """Test that impossible routes are rejected."""
        # Create order with past due time
        past_order = Order.objects.create(
            customer=self.customer,
            merchant=self.merchant,
            destination=self.location1,
            status='PENDING',
            due_time=timezone.now() - timedelta(hours=1),  # Already past
            notes='Late order'
        )
        
        response = self.client.post(reverse('api_accept_orders'),
            data=json.dumps({
                'order_ids': [past_order.id]
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Cannot deliver', data['error'])


class AdminAPITest(TestCase):
    """Test admin API endpoints."""
    
    def setUp(self):
        self.client = Client()
        
        self.admin = User.objects.create_user('admin', 'a@test.com', 'pass123')
        self.admin.userprofile.role = 'ADMIN'
        self.admin.userprofile.is_approved = True
        self.admin.userprofile.save()
        
        self.pending_merchant = User.objects.create_user('pending_m', 'pm@test.com', 'pass123')
        self.pending_merchant.userprofile.role = 'MERCHANT'
        self.pending_merchant.userprofile.is_approved = False
        self.pending_merchant.userprofile.save()
        
        self.customer = User.objects.create_user('customer', 'c@test.com', 'pass123')
        self.customer.userprofile.role = 'CUSTOMER'
        self.customer.userprofile.is_approved = True
        self.customer.userprofile.save()
        
        self.client.login(username='admin', password='pass123')
    
    def test_get_all_users(self):
        response = self.client.get(reverse('api_admin_users'))
        data = json.loads(response.content)
        self.assertEqual(len(data['users']), 3)  # admin, pending_m, customer
    
    def test_approve_user(self):
        response = self.client.post(reverse('api_approve_user'),
            data=json.dumps({
                'user_id': self.pending_merchant.id
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        self.pending_merchant.refresh_from_db()
        self.assertTrue(self.pending_merchant.userprofile.is_approved)
    
    def test_transfer_role(self):
        response = self.client.post(reverse('api_transfer_role'),
            data=json.dumps({
                'user_id': self.customer.id,
                'new_role': 'MERCHANT'
            }),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.userprofile.role, 'MERCHANT')
    
    def test_get_all_orders(self):
        response = self.client.get(reverse('api_admin_orders'))
        data = json.loads(response.content)
        self.assertIn('orders', data)
    
    def test_non_admin_cannot_access(self):
        self.client.logout()
        self.client.login(username='customer', password='pass123')
        
        response = self.client.get(reverse('api_admin_users'))
        self.assertEqual(response.status_code, 403)  # Forbidden


# ==================== TEST: Integration Tests ====================

class FullWorkflowTest(TestCase):
    """Test complete user workflow from registration to delivery."""
    
    def setUp(self):
        self.client = Client()
        ensure_locations()
    
    def test_complete_workflow(self):
        # 1. Register a merchant
        response = self.client.post(reverse('register'),
            data=json.dumps({
                'username': 'workflow_merchant',
                'email': 'wm@test.com',
                'password': 'pass123',
                'role': 'MERCHANT'
            }),
            content_type='application/json'
        )
        self.assertTrue(json.loads(response.content)['success'])
        
        merchant = User.objects.get(username='workflow_merchant')
        self.assertFalse(merchant.userprofile.is_approved)  # Pending
        
        # 2. Admin approves merchant
        admin = User.objects.create_user('workflow_admin', 'wa@test.com', 'pass123')
        admin.userprofile.role = 'ADMIN'
        admin.userprofile.is_approved = True
        admin.userprofile.save()
        
        self.client.login(username='workflow_admin', password='pass123')
        response = self.client.post(reverse('api_approve_user'),
            data=json.dumps({'user_id': merchant.id}),
            content_type='application/json'
        )
        self.assertTrue(json.loads(response.content)['success'])
        
        merchant.refresh_from_db()
        self.assertTrue(merchant.userprofile.is_approved)
        
        # 3. Merchant logs in and adds menu items
        self.client.login(username='workflow_merchant', password='pass123')
        response = self.client.post(reverse('api_add_menu_item'),
            data=json.dumps({
                'name': 'Special Burger',
                'description': 'Best burger in town',
                'price': 15.99
            }),
            content_type='application/json'
        )
        self.assertTrue(json.loads(response.content)['success'])
        
        # 4. Customer registers and places order
        self.client.post(reverse('register'),
            data=json.dumps({
                'username': 'workflow_customer',
                'email': 'wc@test.com',
                'password': 'pass123',
                'role': 'CUSTOMER'
            }),
            content_type='application/json'
        )
        
        self.client.login(username='workflow_customer', password='pass123')
        item = MenuItem.objects.get(name='Special Burger')
        location = Location.objects.filter(is_restaurant=False).first()
        
        response = self.client.post(reverse('api_place_order'),
            data=json.dumps({
                'merchant_id': merchant.id,
                'items': [{'id': item.id, 'quantity': 2}],
                'destination_id': location.id
            }),
            content_type='application/json'
        )
        self.assertTrue(json.loads(response.content)['success'])
        
        # 5. Courier accepts and delivers order
        courier = User.objects.create_user('workflow_courier', 'wco@test.com', 'pass123')
        courier.userprofile.role = 'COURIER'
        courier.userprofile.is_approved = True
        courier.userprofile.save()
        
        self.client.login(username='workflow_courier', password='pass123')
        order = Order.objects.first()
        
        response = self.client.post(reverse('api_accept_orders'),
            data=json.dumps({'order_ids': [order.id]}),
            content_type='application/json'
        )
        self.assertTrue(json.loads(response.content)['success'])
        
        # Update to OUT_FOR_DELIVERY
        self.client.post(reverse('api_update_status'),
            data=json.dumps({'order_id': order.id, 'status': 'OUT_FOR_DELIVERY'}),
            content_type='application/json'
        )
        
        # Mark as DELIVERED
        response = self.client.post(reverse('api_update_status'),
            data=json.dumps({'order_id': order.id, 'status': 'DELIVERED'}),
            content_type='application/json'
        )
        self.assertTrue(json.loads(response.content)['success'])
        
        order.refresh_from_db()
        self.assertEqual(order.status, 'DELIVERED')
        self.assertIsNotNone(order.delivered_at)
        

        # ==================== TEST: Route Feasibility Edge Case ====================
# This test verifies that a courier CANNOT accept orders with impossible deadlines

class RouteFeasibilityEdgeCaseTest(TestCase):
    """Test that impossible routes are properly rejected."""

    def setUp(self):
        self.client = Client()
        ensure_locations()

        # Create merchant
        self.merchant = User.objects.create_user('merchant_edge', 'me@test.com', 'pass123')
        self.merchant.userprofile.role = 'MERCHANT'
        self.merchant.userprofile.is_approved = True
        self.merchant.userprofile.save()

        # Create customer
        self.customer = User.objects.create_user('customer_edge', 'ce@test.com', 'pass123')
        self.customer.userprofile.role = 'CUSTOMER'
        self.customer.userprofile.is_approved = True
        self.customer.userprofile.save()

        # Create courier
        self.courier = User.objects.create_user('courier_edge', 'coe@test.com', 'pass123')
        self.courier.userprofile.role = 'COURIER'
        self.courier.userprofile.is_approved = True
        self.courier.userprofile.save()

        # Get locations
        self.maple_st = Location.objects.get(matrix_id=1)      # 123 Maple Street
        self.willow_blvd = Location.objects.get(matrix_id=8)  # 258 Willow Blvd

        # Create menu item
        self.item = MenuItem.objects.create(
            merchant=self.merchant,
            name='Test Burger',
            price=10.00
        )

    def test_cannot_accept_impossible_route_10_minutes(self):
        """
        Test Case: Courier tries to accept two orders:
        - Order 1: Restaurant -> 123 Maple Street (15 min travel)
        - Order 2: Restaurant -> 258 Willow Blvd (28 min travel)
        Due time: Only 10 minutes from now

        Expected: REJECTED - Even the closest destination takes 15 min,
        which exceeds the 10 min window.
        """
        # Create orders with 10-minute deadline (impossible)
        deadline = timezone.now() + timedelta(minutes=10)

        order1 = Order.objects.create(
            customer=self.customer,
            merchant=self.merchant,
            destination=self.maple_st,
            status='PENDING',
            due_time=deadline,
            notes='Order to Maple St'
        )
        OrderItem.objects.create(order=order1, menu_item=self.item, quantity=1)

        order2 = Order.objects.create(
            customer=self.customer,
            merchant=self.merchant,
            destination=self.willow_blvd,
            status='PENDING',
            due_time=deadline,
            notes='Order to Willow Blvd'
        )
        OrderItem.objects.create(order=order2, menu_item=self.item, quantity=1)

        # Courier attempts to accept both orders
        self.client.login(username='courier_edge', password='pass123')
        response = self.client.post(
            reverse('api_accept_orders'),
            data=json.dumps({'order_ids': [order1.id, order2.id]}),
            content_type='application/json'
        )

        data = json.loads(response.content)

        # MUST be rejected
        self.assertFalse(
            data['success'],
            'Courier should NOT be able to accept orders with impossible 10-minute deadline'
        )
        self.assertIn('Cannot deliver', data['error'])

        # Verify orders remain unassigned
        order1.refresh_from_db()
        order2.refresh_from_db()
        self.assertIsNone(order1.courier)
        self.assertIsNone(order2.courier)
        self.assertEqual(order1.status, 'PENDING')
        self.assertEqual(order2.status, 'PENDING')

    def test_can_accept_feasible_route_60_minutes(self):
        """
        Same destinations but with 60-minute deadline.
        Route: Restaurant -> Maple St (15 min) -> Willow Blvd (20 min) = 35 min total
        Expected: ACCEPTED - 35 min < 60 min deadline
        """
        deadline = timezone.now() + timedelta(minutes=60)

        order1 = Order.objects.create(
            customer=self.customer,
            merchant=self.merchant,
            destination=self.maple_st,
            status='PENDING',
            due_time=deadline,
            notes='Order to Maple St'
        )
        OrderItem.objects.create(order=order1, menu_item=self.item, quantity=1)

        order2 = Order.objects.create(
            customer=self.customer,
            merchant=self.merchant,
            destination=self.willow_blvd,
            status='PENDING',
            due_time=deadline,
            notes='Order to Willow Blvd'
        )
        OrderItem.objects.create(order=order2, menu_item=self.item, quantity=1)

        self.client.login(username='courier_edge', password='pass123')
        response = self.client.post(
            reverse('api_accept_orders'),
            data=json.dumps({'order_ids': [order1.id, order2.id]}),
            content_type='application/json'
        )

        data = json.loads(response.content)

        # Should be accepted
        self.assertTrue(
            data['success'],
            'Courier SHOULD be able to accept orders with 60-minute deadline'
        )

        # Verify orders assigned
        order1.refresh_from_db()
        order2.refresh_from_db()
        self.assertEqual(order1.courier, self.courier)
        self.assertEqual(order2.courier, self.courier)
        self.assertEqual(order1.status, 'ACCEPTED')
        self.assertEqual(order2.status, 'ACCEPTED')

        # Verify route data exists
        self.assertIn('route', data)
        self.assertIn('details', data)

        # Verify route starts at restaurant (0) and includes both destinations
        route = data['route']
        self.assertEqual(route[0], 0)  # Restaurant
        self.assertIn(1, route)         # Maple St
        self.assertIn(8, route)         # Willow Blvd

    def test_single_order_maple_street_10_minutes_rejected(self):
        """
        Even single order to Maple St (15 min away) with 10 min deadline should fail.
        """
        deadline = timezone.now() + timedelta(minutes=10)

        order = Order.objects.create(
            customer=self.customer,
            merchant=self.merchant,
            destination=self.maple_st,
            status='PENDING',
            due_time=deadline,
            notes='Single order to Maple St'
        )
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=1)

        self.client.login(username='courier_edge', password='pass123')
        response = self.client.post(
            reverse('api_accept_orders'),
            data=json.dumps({'order_ids': [order.id]}),
            content_type='application/json'
        )

        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Cannot deliver', data['error'])

        order.refresh_from_db()
        self.assertIsNone(order.courier)

    def test_single_order_maple_street_20_minutes_accepted(self):
        """
        Single order to Maple St (15 min away) with 20 min deadline should succeed.
        """
        deadline = timezone.now() + timedelta(minutes=20)

        order = Order.objects.create(
            customer=self.customer,
            merchant=self.merchant,
            destination=self.maple_st,
            status='PENDING',
            due_time=deadline,
            notes='Single order to Maple St'
        )
        OrderItem.objects.create(order=order, menu_item=self.item, quantity=1)

        self.client.login(username='courier_edge', password='pass123')
        response = self.client.post(
            reverse('api_accept_orders'),
            data=json.dumps({'order_ids': [order.id]}),
            content_type='application/json'
        )

        data = json.loads(response.content)
        self.assertTrue(data['success'])

        order.refresh_from_db()
        self.assertEqual(order.courier, self.courier)