"""Ranking dostępnych punktów; szacowanie marszu, bez udawania routingu ulicznego."""
from urllib.parse import urlencode
from .availability import availability_now
from .normalizer import haversine, usable_coordinates


def nearest(records, lat, lon, now, radius_km=15):
    opened, excluded = [], {"closed_or_locked": 0, "unconfirmed": 0, "field_report": 0}
    for row in records:
        if not usable_coordinates(row) or row.get("is_demo") or row.get("is_preview"):
            continue
        distance = haversine(lat, lon, row["lat"], row["lon"])
        if distance > radius_km * 1000:
            continue
        state = availability_now(row, now)
        if row.get("field_access_alert"):
            excluded["field_report"] += 1; continue
        if state["otwarte_teraz"] is not True:
            excluded["unconfirmed" if state["otwarte_teraz"] is None else "closed_or_locked"] += 1
            continue
        walk_m = distance * 1.25
        one_way_s = walk_m / (5000 / 3600)
        opened.append({**row, **state, "straight_distance_m": round(distance), "walking_distance_m": round(walk_m),
                       "walking_time_seconds": round(one_way_s), "round_trip_seconds": round(2 * one_way_s),
                       "walking_minutes": round(one_way_s / 60, 1), "round_trip_minutes": round(one_way_s / 30, 1),
                       "within_five_minute_round_trip": 2 * one_way_s <= 300,
                       "estimated": True, "route_factor": 1.25, "walking_speed_kmh": 5,
                       "navigation_url": "https://www.google.com/maps/dir/?" + urlencode({"api": 1,
                           "origin": f"{lat},{lon}", "destination": f"{row['lat']},{row['lon']}", "travelmode": "walking"})})
    opened.sort(key=lambda r: (r["walking_time_seconds"], r["straight_distance_m"], -r.get("confidence_score", 0)))
    return {"evaluated_at": now.isoformat(), "timezone": "Europe/Warsaw", "origin": {"lat": lat, "lon": lon},
            "radius_km": radius_km, "count": len(opened), "top3": [{**r, "rank": i+1} for i,r in enumerate(opened[:3])],
            "excluded": excluded, "estimation_note": "Szacunek, nie trasa po chodnikach: odległość × 1,25; marsz 5 km/h. Czas powrotu nie obejmuje odnalezienia ani obsługi AED.",
            "rescue_note": "Dzwoń pod 112 i rozpocznij RKO. Po AED wyślij inną osobę; jeśli jesteś sam, nie przerywaj RKO na szukanie. 3–5 minut to pilny cel działania, nie gwarancja bezpieczeństwa."}
