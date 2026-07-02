# systems/pathmove.py — Di chuyển né tường (nhẹ, real-time)
#
# Né tường kiểu "steering": đi thẳng về đích; nếu bị tường chặn thì lách góc
# (±35°, ±70°, ±90°, ±110°) để trượt quanh tường / lọt qua lỗ hổng. O(1) mỗi
# frame — KHÔNG dùng A* (A* trên lưới lớn gây lag + kẹt khi đường xa).
#
#   res = follow_path(entity, gx, gy, speed, dt, radius=12)
#   res == 'arrived' : đã tới đích (trong bán kính radius)
#   res == 'moved'   : đã nhích được 1 bước
#   res == 'blocked' : mọi hướng đều bị tường chặn → caller xử lý (phá tường)
from __future__ import annotations

import math

from systems.world_query import WorldQuery

# Các góc lệch thử khi đi thẳng bị chặn (radian).
# Thêm ±90° (1.5708) vào giữa để trượt thuần dọc/ngang khi tường dài chặn.
_SIDE_ANGLES = (
    0.0,                          # thẳng
    0.61,  -0.61,                 # ±35°  (lách nhẹ)
    1.22,  -1.22,                 # ±70°  (lách vừa)
    1.5708, -1.5708,              # ±90°  (trượt dọc/ngang)
    1.92,  -1.92,                 # ±110° (quay ngược bên nhẹ)
    2.35,  -2.35,                 # ±135° (thoát góc trong - inner corner escape)
    2.79,  -2.79,                 # ±160° (gần như quay đầu)
)


def follow_path(entity, gx: float, gy: float, speed: float, dt: float,
                radius: float = 12.0, collide_radius: float = None,
                exclude=None, **_kw) -> str:
    """Đi về (gx, gy), né tường bằng cách lách góc + trượt wall. Không xuyên tường."""
    if collide_radius is None:
        collide_radius = radius
    dx, dy = gx - entity.x, gy - entity.y
    dist = (dx * dx + dy * dy) ** 0.5
    if dist <= radius:
        return 'arrived'

    step = speed * dt
    if step <= 0:
        return 'moved'

    ux, uy = dx / dist, dy / dist

    is_soldier = getattr(entity, 'ENTITY_TYPE', '') == 'soldier'
    passing_gap = _kw.get('is_passing_gap', False) or _kw.get('gap_center') is not None
    ignore_buffer = _kw.get('ignore_buffer', False)
    use_buffer = is_soldier and not passing_gap and not ignore_buffer

    if use_buffer:
        # Cấu trúc lớp bọc (Buffer Layers):
        # Tạo lực đẩy mềm mại để lính trượt ở vòng ngoài, không dính vào vùng cấm
        def get_depth(cx, cy):
            # Depth 5: Lõi vật lý 32x32 (kẹt cứng)
            p_kw = dict(_kw)
            p_kw.pop('ignore_buffer', None)
            p_kw['is_passing_gap'] = True
            if WorldQuery.is_wall_blocked(cx, cy, collide_radius, exclude=exclude, **p_kw):
                return 5
            # Depth 4: Vùng cấm hình ảnh gốc (Visual expanded wall)
            v_kw = dict(_kw)
            v_kw.pop('ignore_buffer', None)
            v_kw['is_passing_gap'] = False
            v_kw['force_visual_expand'] = True
            if WorldQuery.is_wall_blocked(cx, cy, collide_radius, exclude=exclude, **v_kw):
                return 4
            # Depth 3, 2, 1: Các lớp bọc mềm bên ngoài (dày thêm 4, 8, 12px)
            if WorldQuery.is_wall_blocked(cx, cy, collide_radius + 4.0, exclude=exclude, **v_kw): return 3
            if WorldQuery.is_wall_blocked(cx, cy, collide_radius + 8.0, exclude=exclude, **v_kw): return 2
            if WorldQuery.is_wall_blocked(cx, cy, collide_radius + 12.0, exclude=exclude, **v_kw): return 1
            return 0

        nx_straight = entity.x + ux * step
        ny_straight = entity.y + uy * step
        
        slide_vx = getattr(entity, '_pf_slide_vx', 0.0)
        slide_vy = getattr(entity, '_pf_slide_vy', 0.0)
        if slide_vx != 0.0 or slide_vy != 0.0:
            if slide_vx * ux + slide_vy * uy < -0.1:
                slide_vx = 0.0
                slide_vy = 0.0
                entity._pf_slide_vx = 0.0
                entity._pf_slide_vy = 0.0
                
        # Danh sách ứng viên lách
        candidates = []
        slide_x = step if ux >= 0 else -step
        slide_y = step if uy >= 0 else -step
        if abs(ux) >= abs(uy):
            slides = ((slide_x, 0.0), (0.0, slide_y), (0.0, -slide_y))
        else:
            slides = ((0.0, slide_y), (slide_x, 0.0), (-slide_x, 0.0))
            
        for sx, sy in slides:
            if sx * ux + sy * uy >= -0.05:
                candidates.append((entity.x + sx, entity.y + sy))
                
        for ang in _SIDE_ANGLES:
            ca, sa = round(math.cos(ang), 5), round(math.sin(ang), 5)
            candidates.append((entity.x + (ux * ca - uy * sa) * step, 
                               entity.y + (ux * sa + uy * ca) * step))
            
        current_depth = get_depth(entity.x, entity.y)
        
        # 1. Thử đi thẳng (để tự động thoát slide khi hết tường)
        if get_depth(nx_straight, ny_straight) <= current_depth:
            entity._pf_slide_vx = 0.0
            entity._pf_slide_vy = 0.0
            entity.x, entity.y = nx_straight, ny_straight
            return 'moved'
            
        # 2. Thử trượt tiếp theo hướng đã lưu
        if slide_vx != 0.0 or slide_vy != 0.0:
            nx = entity.x + slide_vx * step
            ny = entity.y + slide_vy * step
            if get_depth(nx, ny) <= current_depth:
                entity.x, entity.y = nx, ny
                return 'moved'
                
        # 3. Lách qua các ứng viên
        for nx, ny in candidates:
            if get_depth(nx, ny) <= current_depth:
                dx, dy = nx - entity.x, ny - entity.y
                d = math.hypot(dx, dy)
                if d > 0:
                    entity._pf_slide_vx = dx / d
                    entity._pf_slide_vy = dy / d
                entity.x, entity.y = nx, ny
                return 'moved'
                
        # Nếu kẹt cứng (buộc phải tăng depth), thử lún sâu thêm 1 chút
        for allowed_depth in range(current_depth, 6):
            if get_depth(nx_straight, ny_straight) <= allowed_depth:
                entity._pf_slide_vx = 0.0
                entity._pf_slide_vy = 0.0
                entity.x, entity.y = nx_straight, ny_straight
                return 'moved'
            for nx, ny in candidates:
                if get_depth(nx, ny) <= allowed_depth:
                    dx, dy = nx - entity.x, ny - entity.y
                    d = math.hypot(dx, dy)
                    if d > 0:
                        entity._pf_slide_vx = dx / d
                        entity._pf_slide_vy = dy / d
                    entity.x, entity.y = nx, ny
                    return 'moved'
                    
        # Fallback an toàn (thoát khỏi lõi tháp)
        entity._pf_slide_vx = 0.0
        entity._pf_slide_vy = 0.0
        entity.x, entity.y = nx_straight, ny_straight
        return 'moved'
        
    else:
        # GIỮ NGUYÊN HOÀN TOÀN LOGIC CŨ CHO TITAN, COMMANDER, VÀ LÍNH QUA LỖ
        check_kw = dict(_kw)
        check_kw.pop('ignore_buffer', None)
        check_kw['is_passing_gap'] = False
        is_stuck_expanded = WorldQuery.is_wall_blocked(entity.x, entity.y, collide_radius, exclude=exclude, **check_kw)

        run_kw = dict(_kw)
        if run_kw.pop('ignore_buffer', None):
            run_kw['is_passing_gap'] = True
            
        if is_stuck_expanded:
            run_kw['is_passing_gap'] = True

        nx_straight = entity.x + ux * step
        ny_straight = entity.y + uy * step
        slide_vx = getattr(entity, '_pf_slide_vx', 0.0)
        slide_vy = getattr(entity, '_pf_slide_vy', 0.0)
        if slide_vx != 0.0 or slide_vy != 0.0:
            if slide_vx * ux + slide_vy * uy < -0.1:
                slide_vx = 0.0
                slide_vy = 0.0
                entity._pf_slide_vx = 0.0
                entity._pf_slide_vy = 0.0
                
        if not WorldQuery.is_wall_blocked(nx_straight, ny_straight, collide_radius, exclude=exclude, **run_kw):
            entity._pf_slide_vx = 0.0
            entity._pf_slide_vy = 0.0
            entity.x, entity.y = nx_straight, ny_straight
            return 'moved'
            
        if slide_vx != 0.0 or slide_vy != 0.0:
            nx = entity.x + slide_vx * step
            ny = entity.y + slide_vy * step
            if not WorldQuery.is_wall_blocked(nx, ny, collide_radius, exclude=exclude, **run_kw):
                entity.x, entity.y = nx, ny
                return 'moved'
            
        slide_x = step if ux >= 0 else -step
        slide_y = step if uy >= 0 else -step
        if abs(ux) >= abs(uy):
            slides = ((slide_x, 0.0), (0.0, slide_y), (0.0, -slide_y))
        else:
            slides = ((0.0, slide_y), (slide_x, 0.0), (-slide_x, 0.0))
            
        for sx, sy in slides:
            if sx * ux + sy * uy >= -0.05:
                nx, ny = entity.x + sx, entity.y + sy
                if not WorldQuery.is_wall_blocked(nx, ny, collide_radius, exclude=exclude, **run_kw):
                    dx, dy = nx - entity.x, ny - entity.y
                    d = math.hypot(dx, dy)
                    if d > 0:
                        entity._pf_slide_vx = dx / d
                        entity._pf_slide_vy = dy / d
                    entity.x, entity.y = nx, ny
                    return 'moved'

        for ang in _SIDE_ANGLES:
            ca, sa = round(math.cos(ang), 5), round(math.sin(ang), 5)
            nx = entity.x + (ux * ca - uy * sa) * step
            ny = entity.y + (ux * sa + uy * ca) * step
            if not WorldQuery.is_wall_blocked(nx, ny, collide_radius, exclude=exclude, **run_kw):
                dx, dy = nx - entity.x, ny - entity.y
                d = math.hypot(dx, dy)
                if d > 0:
                    entity._pf_slide_vx = dx / d
                    entity._pf_slide_vy = dy / d
                entity.x, entity.y = nx, ny
                return 'moved'
                
        # Rơi xuống đây tức là kẹt cứng mọi hướng (vd: xuất phát từ trong tháp)
        # Bắt buộc nhích thẳng để lọt ra ngoài lõi vật lý
        entity._pf_slide_vx = 0.0
        entity._pf_slide_vy = 0.0
        entity.x, entity.y = nx_straight, ny_straight
        return 'moved'

def gap_aim(ax: float, ay: float, tx: float, ty: float,
            gc, wall_r: float, align_tol: float = 12.0) -> tuple:
    """Điểm nhắm 2-PHA để actor vào GIỮA lỗ rồi mới xuyên qua (dùng chung
    titan & lính). KHÔNG vào mép, không kẹt trong dải tường.

    gc = (cx, cy, is_horizontal). Trục CHẮN (vuông góc tường) phải căn giữa;
    trục TỰ DO (dọc hướng xuyên) cứ tiến.
      • Pha 1 (lệch trục chắn > align_tol): nhắm tâm-lỗ trên trục chắn nhưng đứng
        ở PHÍA ACTOR (chưa qua) → căn giữa trước.
      • Pha 2 (đã căn): lật sang PHÍA TARGET → xuyên qua đúng giữa.
    LƯU Ý: bán kính 'arrived' của follow_path phải < align_tol, nếu không actor
    'arrived' lúc còn lệch → kẹt pha 1.
    """
    cx, cy, is_h = gc
    near = 120.0 if is_h else 80.0
    funnel_dist = 40.0  # Điểm an toàn cách tâm lỗ 40px, tránh kẹt góc tường

    if is_h:                                    # tường ngang: căn X, xuyên theo Y
        my_side = 1.0 if ay > cy else -1.0
        if abs(ax - cx) > align_tol:
            # Pha 1: Nhắm vào 'funnel point' nằm ngay trước tâm lỗ.
            # Giúp lính lách xa khỏi tường trong khi căn giữa, tránh ma sát cọ quẹt.
            return cx, cy + my_side * funnel_dist, False
        else:
            # Pha 2: Đã thẳng hàng X, giờ chui lỗ theo trục Y.
            side = 1.0 if ty > cy else -1.0
            if my_side != side and abs(ay - cy) > 12.0:
                return cx, cy, True
            return cx, cy + side * near, True
    else:                                       # tường dọc: căn Y, xuyên theo X
        my_side = 1.0 if ax > cx else -1.0
        if abs(ay - cy) > align_tol:
            # Pha 1: Nhắm vào 'funnel point' nằm ngay trước tâm lỗ.
            return cx + my_side * funnel_dist, cy, False
        else:
            # Pha 2: Đã thẳng hàng Y, giờ chui lỗ theo trục X.
            side = 1.0 if tx > cx else -1.0
            if my_side != side and abs(ax - cx) > 12.0:
                return cx, cy, True
            return cx + side * near, cy, True

def clear_path(entity) -> None:
    pass
