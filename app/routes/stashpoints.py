# write me a route to get all stashpoints

from flask import Blueprint, jsonify, request
from app.models import Stashpoint, Booking
from datetime import datetime
from sqlalchemy import func, select, outerjoin, and_
from app import db


bp = Blueprint("stashpoints", __name__)


@bp.route("/", methods=["GET"])
def get_stashpoints():
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

    distance_label = (
        func.ST_DistanceSphere(
            func.ST_MakePoint(lng, lat),
            func.ST_MakePoint(Stashpoint.longitude, Stashpoint.latitude),
        )
        / 1000
    ).label("distance_km")

    available_capacity_label = func.greatest(
        func.coalesce(
            Stashpoint.capacity - func.coalesce(func.sum(Booking.bag_count), 0), 0
        ),
        0,
    ).label("available_capacity")

    query = (
        select(Stashpoint, distance_label, available_capacity_label)
        .select_from(
            outerjoin(
                Stashpoint,
                Booking,
                and_(
                    Stashpoint.id == Booking.stashpoint_id,
                    Booking.is_cancelled == False,
                    Booking.dropoff_time < pickup_datetime,
                    Booking.pickup_time > dropoff_datetime,
                ),
            ),
        )
        .group_by(Stashpoint.id, distance_label, Stashpoint.capacity)
    )

    query = query.filter(
        (Stashpoint.open_from <= dropoff_time) & (Stashpoint.open_until >= pickup_time)
    )

    if radius_km is not None:
        query = query.having(distance_label <= radius_km)

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
