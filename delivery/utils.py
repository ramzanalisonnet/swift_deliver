"""
Simulated map data, travel matrix, and route feasibility engine.
"""
from .models import Location
from datetime import timedelta

# ==================== DATA: 10 Locations for Simulated Map ====================
LOCATIONS_DATA = [
    {"matrix_id": 0, "name": "City Central Restaurant", "address": "100 Main Plaza", "is_restaurant": True,  "grid_x": 400, "grid_y": 300},
    {"matrix_id": 1, "name": "123 Maple Street",        "address": "123 Maple Street",        "is_restaurant": False, "grid_x": 150, "grid_y": 100},
    {"matrix_id": 2, "name": "456 Oak Avenue",          "address": "456 Oak Avenue",          "is_restaurant": False, "grid_x": 650, "grid_y": 120},
    {"matrix_id": 3, "name": "789 Pine Road",           "address": "789 Pine Road",           "is_restaurant": False, "grid_x": 700, "grid_y": 400},
    {"matrix_id": 4, "name": "321 Elm Drive",           "address": "321 Elm Drive",           "is_restaurant": False, "grid_x": 500, "grid_y": 500},
    {"matrix_id": 5, "name": "654 Birch Lane",          "address": "654 Birch Lane",          "is_restaurant": False, "grid_x": 200, "grid_y": 450},
    {"matrix_id": 6, "name": "987 Cedar Court",         "address": "987 Cedar Court",         "is_restaurant": False, "grid_x": 100, "grid_y": 250},
    {"matrix_id": 7, "name": "147 Spruce Way",          "address": "147 Spruce Way",          "is_restaurant": False, "grid_x": 350, "grid_y": 50},
    {"matrix_id": 8, "name": "258 Willow Blvd",         "address": "258 Willow Blvd",         "is_restaurant": False, "grid_x": 600, "grid_y": 300},
    {"matrix_id": 9, "name": "Northside Bistro",        "address": "200 North Avenue",        "is_restaurant": True,  "grid_x": 300, "grid_y": 150},
]

# ==================== DATA: 10x10 Asymmetric Travel Time Matrix (minutes) ====================
# Index corresponds to matrix_id. TRAVEL_TIMES[a][b] = minutes from location A to B.
TRAVEL_TIMES = [
    # 0    1    2    3    4    5    6    7    8    9
    [0,   15,  22,  30,  25,  20,  18,  12,  28,  10],  # 0: City Central Restaurant
    [18,  0,   10,  25,  22,  15,  12,  8,   20,  14],  # 1: Maple St
    [25,  12,  0,   15,  20,  28,  22,  14,  10,  18],  # 2: Oak Ave
    [32,  28,  18,  0,   12,  30,  25,  20,  15,  22],  # 3: Pine Rd
    [28,  20,  18,  10,  0,   15,  22,  18,  12,  16],  # 4: Elm Dr
    [22,  14,  25,  28,  16,  0,   10,  18,  22,  12],  # 5: Birch Ln
    [20,  10,  20,  28,  25,  12,  0,   15,  25,  14],  # 6: Cedar Ct
    [14,  8,   15,  22,  20,  18,  14,  0,   18,  9],   # 7: Spruce Way
    [30,  22,  12,  14,  15,  25,  28,  20,  0,   17],  # 8: Willow Blvd
    [11,  13,  19,  23,  17,  13,  14,  10,  18,  0],   # 9: Northside Bistro
]

# ==================== FUNCTION: ensure_locations ====================
def ensure_locations():
    """Seed the 10 simulated map locations into the database on startup."""
    from django.db import connection, OperationalError
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='delivery_location';")
            if not cursor.fetchone():
                return
    except OperationalError:
        return

    for loc in LOCATIONS_DATA:
        obj, created = Location.objects.get_or_create(matrix_id=loc["matrix_id"], defaults=loc)
        if not created:
            # Update existing record if fields changed
            updated = False
            for field in ["name", "address", "is_restaurant", "grid_x", "grid_y"]:
                if getattr(obj, field) != loc[field]:
                    setattr(obj, field, loc[field])
                    updated = True
            if updated:
                obj.save()

# ==================== FUNCTION: get_location_data ====================
def get_location_data(matrix_id):
    """Return location dict by matrix_id."""
    for loc in LOCATIONS_DATA:
        if loc["matrix_id"] == matrix_id:
            return loc
    return None

# ==================== FUNCTION: get_restaurant_locations ====================
def get_restaurant_locations():
    """Return list of restaurant location dicts."""
    return [loc for loc in LOCATIONS_DATA if loc["is_restaurant"]]

# ==================== FUNCTION: calculate_nearest_neighbor_route ====================
def calculate_nearest_neighbor_route(start_id, destination_ids):
    """
    Greedy nearest-neighbor TSP solver.
    Returns: (ordered_route_list, total_travel_minutes)
    """
    unvisited = set(destination_ids)
    current = start_id
    route = [start_id]
    total_time = 0

    while unvisited:
        nearest = None
        nearest_time = float('inf')
        for dest in unvisited:
            t = TRAVEL_TIMES[current][dest]
            if t < nearest_time:
                nearest_time = t
                nearest = dest
        route.append(nearest)
        total_time += nearest_time
        current = nearest
        unvisited.remove(nearest)

    return route, total_time

# ==================== FUNCTION: validate_route_feasibility ====================
def validate_route_feasibility(start_id, destination_ids, due_times, start_time):
    """
    Validates if a courier can visit all destinations before their due times.
    start_id: the actual restaurant location matrix_id (not hardcoded 0).
    All datetimes should be naive (local time) for accurate comparison.
    """
    route, _ = calculate_nearest_neighbor_route(start_id, destination_ids)
    cumulative = 0
    current = start_id
    details = []

    for i in range(1, len(route)):
        nxt = route[i]
        travel = TRAVEL_TIMES[current][nxt]
        cumulative += travel
        arrival = start_time + timedelta(minutes=cumulative)
        due = due_times.get(nxt)

        if due is not None and hasattr(due, 'tzinfo') and due.tzinfo is not None:
            due = due.replace(tzinfo=None)

        on_time = arrival <= due if due else True

        details.append({
            'matrix_id': nxt,
            'location_name': get_location_data(nxt)['name'],
            'travel_time': travel,
            'cumulative_time': cumulative,
            'arrival': arrival.isoformat(),
            'due_time': due.isoformat() if due else None,
            'on_time': on_time
        })
        current = nxt

    is_feasible = all(d['on_time'] for d in details)
    return is_feasible, route, details

# ==================== FUNCTION: calculate_due_time ====================
def calculate_due_time(restaurant_matrix_id, destination_matrix_id, base_time=None, buffer_minutes=15):
    """
    Calculate auto due-time based on travel distance from restaurant to destination.
    Adds buffer_minutes for food preparation.
    """
    from datetime import datetime
    if base_time is None:
        base_time = datetime.now()
    travel_time = TRAVEL_TIMES[restaurant_matrix_id][destination_matrix_id]
    total_minutes = travel_time + buffer_minutes
    return base_time + timedelta(minutes=total_minutes)