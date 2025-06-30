# write me a route to get all stashpoints

from flask import Blueprint, jsonify, request
from app.models import Stashpoint
from datetime import datetime
from sqlalchemy import and_, func, select
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
        dropoff_time = datetime.fromisoformat(dropoff_str).time()
    except ValueError:
        return "Invalid dropoff datetime format. Use ISO format", 400

    pickup_str = request.args.get("pickup", type=str)
    if pickup_str is None:
        return "Invalid pickup", 400
    try:
        pickup_time = datetime.fromisoformat(pickup_str).time()
    except ValueError:
        return "Invalid pickup datetime format. Use ISO format", 400

    bag_count = request.args.get("bag_count", type=int)
    if bag_count is None:
        return "Invalid bag_count", 400

    distance_expr = (
        func.ST_DistanceSphere(
            func.ST_MakePoint(lng, lat),
            func.ST_MakePoint(Stashpoint.longitude, Stashpoint.latitude),
        )
        / 1000
    ).label("distance_km")

    query = select(Stashpoint, distance_expr)

    query = query.filter(
        and_(Stashpoint.open_from <= dropoff_time, Stashpoint.open_until >= pickup_time)
    )

    if radius_km is not None:
        query = query.group_by(Stashpoint.id).having(distance_expr <= radius_km)

    query = query.order_by("distance_km")
    stashpoints = db.session.execute(query).all()
    result = [
        {**stashpoint.to_dict(), "distance_km": distance_km}
        for stashpoint, distance_km in stashpoints
    ]
    return jsonify(result)
