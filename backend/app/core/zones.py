"""Zone geometry. Polygons are normalized 0-1 on the first frame."""

from __future__ import annotations


def bbox_center(bbox: list[float]) -> tuple[float, float]:
    x, y, w, h = bbox
    return x + w / 2, y + h / 2


def polygon_area(polygon: list[list[float]]) -> float:
    area = 0.0
    if len(polygon) < 3:
        return 0.0
    for i, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(i + 1) % len(polygon)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    """Ray cast. A point on an edge counts as inside."""
    inside = False
    count = len(polygon)
    if count < 3:
        return False
    j = count - 1
    for i in range(count):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if _on_segment(x, y, xi, yi, xj, yj):
            return True
        intersects = (yi > y) != (yj > y)
        if intersects:
            denom = (yj - yi) or 1e-15
            cross_x = (xj - xi) * (y - yi) / denom + xi
            if x < cross_x:
                inside = not inside
        j = i
    return inside


def _on_segment(x: float, y: float, x1: float, y1: float, x2: float, y2: float) -> bool:
    cross = (y - y1) * (x2 - x1) - (x - x1) * (y2 - y1)
    if abs(cross) > 1e-9:
        return False
    dot = (x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)
    if dot < 0:
        return False
    length_sq = (x2 - x1) ** 2 + (y2 - y1) ** 2
    return dot <= length_sq + 1e-9


def zone_for_point(x: float, y: float, zones: dict[str, list[list[float]]]) -> str:
    """Return the smallest polygon that contains the point, or 'unknown'."""
    hits: list[tuple[float, str]] = []
    for name, polygon in zones.items():
        if point_in_polygon(x, y, polygon):
            hits.append((polygon_area(polygon), name))
    if not hits:
        return "unknown"
    hits.sort()
    return hits[0][1]


def zone_for_bbox(bbox: list[float], zones: dict[str, list[list[float]]]) -> str:
    x, y = bbox_center(bbox)
    return zone_for_point(x, y, zones)
