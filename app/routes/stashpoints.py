# write me a route to get all stashpoints

from flask import Blueprint, jsonify, request
from app.models import Stashpoint, Booking
from datetime import datetime
from sqlalchemy import func, select, and_
from app import db


bp = Blueprint("stashpoints", __name__)


@bp.route("/", methods=["GET"])
def get_stashpoints():
    # Handle query parameters
    lat = request.args.get("lat", type=float)
    if lat is None:
        return "Invalid lat", 400

    lng = request.args.get("lng", type=float)
    if lng is None:
        return "Invalid lng", 400

    radius_km = request.args.get("radius_km", type=float)

    dropoff_str = request.args.get("dropoff", type=str)
    if dropoff_str is None:
        return "Invalid dropoff", 400
    try:
        dropoff_str = dropoff_str.rstrip("Z")  # Remove Z if present
        dropoff_datetime = datetime.fromisoformat(dropoff_str)
        dropoff_time = dropoff_datetime.time()
    except ValueError:
        return "Invalid dropoff datetime format. Use ISO format", 400

    pickup_str = request.args.get("pickup", type=str)
    if pickup_str is None:
        return "Invalid pickup", 400
    try:
        pickup_str = pickup_str.rstrip("Z")  # Remove Z if present
        pickup_datetime = datetime.fromisoformat(pickup_str)
        pickup_time = pickup_datetime.time()
    except ValueError:
        return "Invalid pickup datetime format. Use ISO format", 400

    if pickup_datetime < dropoff_datetime:
        return "Pickup datetime must be after dropoff datetime", 400

    bag_count = request.args.get("bag_count", type=int)
    if bag_count is None:
        return "Invalid bag_count", 400

    # Add query to calculate distances
    distance_label = (
        func.ST_DistanceSphere(
            func.ST_MakePoint(lng, lat),
            func.ST_MakePoint(Stashpoint.longitude, Stashpoint.latitude),
        )
        / 1000
    ).label("distance_km")

    # Big subquery to handle calculating bag counts for overlapping bookings
    dropoff_times = (
        select(Booking.dropoff_time)
        .where(
            and_(
                Booking.is_cancelled == False,
                Booking.dropoff_time < pickup_datetime,
                Booking.pickup_time > dropoff_datetime,
            )
        )
        .distinct()
        .subquery()
    )

    concurrent_counts = (
        select(
            dropoff_times.c.dropoff_time,
            func.sum(Booking.bag_count).label("concurrent_bags"),
        )
        .select_from(
            dropoff_times.join(
                Booking,
                and_(
                    Booking.is_cancelled == False,
                    Booking.dropoff_time <= dropoff_times.c.dropoff_time,
                    Booking.pickup_time > dropoff_times.c.dropoff_time,
                ),
            )
        )
        .group_by(dropoff_times.c.dropoff_time)
        .subquery()
    )

    max_concurrent = select(
        func.max(concurrent_counts.c.concurrent_bags)
    ).scalar_subquery()

    available_capacity_label = Stashpoint.capacity - func.coalesce(
        max_concurrent, 0
    ).label("available_capacity")

    query = select(Stashpoint, distance_label, available_capacity_label).group_by(
        Stashpoint.id, distance_label, Stashpoint.capacity
    )
    # Ensure that the stashpoint is open during the requested times
    query = query.filter(
        (Stashpoint.open_from <= dropoff_time) & (Stashpoint.open_until >= pickup_time)
    )
    # If radius is specfied, filter by it
    if radius_km is not None:
        query = query.having(distance_label <= radius_km)

    # Only show stashpoints with enough capacity
    query = query.having(bag_count <= available_capacity_label)

    query = query.order_by("distance_km")
    stashpoints = db.session.execute(query).all()
    result = [
        {
            **stashpoint.to_dict(),
            "distance_km": distance_km,
            "available_capacity": available_capacity,
        }
        for stashpoint, distance_km, available_capacity in stashpoints
    ]
    return jsonify(result)
