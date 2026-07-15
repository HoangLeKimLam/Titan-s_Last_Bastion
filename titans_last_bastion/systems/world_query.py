# systems/world_query.py — WorldQuery Singleton
#
# Quản lý toàn bộ entity đang sống trong thế giới game.
# Các class khác (Soldier, Commander, Tower, Projectile, Building) gọi trực tiếp
# qua class method: WorldQuery.spawn_entity(e), WorldQuery.find_in_radius(...), v.v.
#
# API:
#   spawn_entity(entity)                          — đăng ký entity vào thế giới
#   remove_entity(entity)                         — xoá entity khỏi danh sách
#   purge_dead()                                  — dọn entity có is_alive=False
#   all()                                         — tất cả entity còn sống
#   find_in_radius(cx, cy, radius, entity_type)   — entity trong vùng tròn
#   find_nearest(cx, cy, entity_type)             — entity gần nhất
#   structures()                                  — list pygame.Rect của towers
#   register_structure(rect)                      — đăng ký rect tháp
#   unregister_structure(rect)                    — xoá rect tháp
#   get_all_buildings()                           — entity có ENTITY_TYPE="building"
#   reset()                                       — xoá sạch (dùng khi load màn mới)
from __future__ import annotations

import heapq
import math
from typing import Optional


class WorldQuery:
    """Class-level Singleton — gọi thẳng qua class, không cần get_instance()."""

    # Danh sách tất cả entity trong thế giới (bao gồm cả entity đã chết chưa purge)
    _entities: list = []

    # Danh sách pygame.Rect của các công trình (tháp) — dùng cho E-swing targeting
    _structures: list = []
    _wall_colliders: dict = {}

    # ODM static anchors: decoration (tree/stair/arch) + ground tower rects (world coords).
    # Cho phép commander đu dây lên cây, cầu thang, tháp đất.
    _static_anchors: list = []  # [(pygame.Rect, anchor_id), ...]

    # Danh sách riêng tất cả wall entity từng được đăng ký — kể cả đã bể (is_alive=False).
    # Không bị purge_dead() xóa → luôn dùng được để tìm lỗ hổng (dead section = gap).
    _wall_refs: list = []

    # ── Spatial hash tường (tăng tốc is_wall_blocked) ────────────────────
    # Tường tĩnh → băm theo ô lưới 1 lần lúc register. is_wall_blocked chỉ
    # quét tường trong vài ô quanh điểm, thay vì TOÀN BỘ entity mỗi lần gọi.
    _wall_grid: dict = {}           # (cellx, celly) -> [wall, ...]
    _wall_orient: dict = {}         # id(wall) -> section_type ('wall_h'/'wall_Y'/...)
    _WALL_CELL: int = 96

    # ── Cache theo FRAME (dựng 1 lần/frame, dùng lại cho mọi titan) ───────
    # build_context + find_nearest_gap_center vốn quét lại toàn bộ entity/tường
    # cho TỪNG titan mỗi frame (giống nhau y hệt) → siêu lag khi đông titan.
    # Cache lại: phân loại entity còn sống + cụm lỗ hổng. Vô hiệu hóa khi
    # spawn/remove/purge (ranh giới frame). Stale tối đa 1 frame — AI chịu được.
    _cache_valid: bool = False
    _f_walls: list = []
    _f_towers: list = []
    _f_soldiers: list = []
    _f_commanders: list = []
    _f_hq: object = None
    _f_dead_clusters: list = []     # [(cx, cy, size, is_h, lo, hi), ...] cụm lỗ

    # Cờ chỉ báo cụm lỗ hổng tường cần tính lại.
    # Chỉ đặt True khi CẤU TRÚC TƯỜNG thay đổi (bể/sửa/spawn/remove).
    # Với mọi frame bình thường, _f_dead_clusters được dùng lại nguyên vẹn.
    _dead_clusters_dirty: bool = True

    # ── Pathfinding grid (A*) ────────────────────────────────────────────
    # Lưới ô đi-được: tường = ô chặn, section đã bể = ô đi được.
    _pf_cell: int = 32              # kích thước ô (px)
    _pf_cols: int = 0
    _pf_rows: int = 0
    _pf_blocked: set = set()        # {(col,row)} ô bị tường chặn
    _pf_dirty: bool = True          # cần dựng lại lưới
    _pf_built_walls: int = -1       # số wall collider lúc dựng (phát hiện thay đổi)

    # ── Zone system (vùng theo vòng tường) ──────────────────────────────
    # _zone_boxes: {'maria': (l,t,r,b), 'rose': (...), 'sina': (...)} tính bằng PIXEL.
    # 4 vùng lồng nhau: sina (trong cùng) ⊂ rose ⊂ maria ⊂ field (ngoài Maria).
    _zone_boxes: dict = {}
    # Mỗi tường giáp 2 vùng (trong, ngoài)
    WALL_ZONE_PAIRS: dict = {
        'maria': ('maria', 'field'),
        'rose':  ('rose', 'maria'),
        'sina':  ('sina', 'rose'),
    }

    @classmethod
    def register_zones(cls, maria_box, rose_box, sina_box) -> None:
        """Đăng ký bounding box (PIXEL: left, top, right, bottom) của 3 vòng tường.
        Co vào 16.0 (nửa tile) mỗi cạnh để viền bounding box nằm ĐÚNG CHÍNH GIỮA
        bức tường — left/top CỘNG (tiến vào trong), right/bottom phải TRỪ (cũng
        tiến vào trong, vì trục tăng dần ra ngoài ở 2 cạnh này).

        FIX: bản cũ cộng đều +16.0 cho CẢ 4 giá trị — đúng cho left/top nhưng
        SAI DẤU cho right/bottom (lẽ ra phải trừ để tiến vào trong, cộng lại
        đẩy biên ra NGOÀI xa hơn mép tường thật). Hậu quả: mọi zone (maria/
        rose/sina) đều "rò" 16px ở cạnh NAM và ĐÔNG (bắc/tây thì đúng vì dấu
        cộng vốn đúng ở 2 cạnh đó) — điểm vừa ra khỏi tường ở phía nam/đông
        vẫn bị tính nhầm là "trong vùng", khiến titan/prey 2 bên 1 bức tường
        còn nguyên vẹn ở phía nam bị same_zone() coi là cùng vùng.
        """
        def _center_box(box):
            """Co bounding box vào 16px (nửa tile) MỖI CẠNH ĐÚNG DẤU (left/top
            CỘNG, right/bottom TRỪ — cả 2 đều "tiến vào trong") để viền box
            nằm giữa TÂM bức tường thay vì mép ngoài của nó."""
            l, t, r, b = box
            return (float(l) + 16.0, float(t) + 16.0, float(r) - 16.0, float(b) - 16.0)

        cls._zone_boxes = {
            'maria': _center_box(maria_box),
            'rose':  _center_box(rose_box),
            'sina':  _center_box(sina_box),
        }

    @classmethod
    def zone_of(cls, x: float, y: float) -> str:
        """Trả về vùng chứa điểm (x, y): 'sina' | 'rose' | 'maria' | 'field'."""
        def _inside(box) -> bool:
            """(x,y) có nằm trong `box` (AABB, đã co tâm bởi `_center_box`)
            không — dùng test lần lượt sina→rose→maria (trong ra ngoài)."""
            l, t, r, b = box
            return l <= x <= r and t <= y <= b
        z = cls._zone_boxes
        if not z:
            return 'field'
        if 'sina' in z and _inside(z['sina']):
            return 'sina'
        if 'rose' in z and _inside(z['rose']):
            return 'rose'
        if 'maria' in z and _inside(z['maria']):
            return 'maria'
        return 'field'

    @classmethod
    def zones_for_wall(cls, wall_name: str) -> tuple:
        """2 vùng giáp tường `wall_name`. Vô danh → tuple rỗng."""
        return cls.WALL_ZONE_PAIRS.get(wall_name, ())

    # Vòng tường BIÊN của mỗi vùng (để gộp mục tiêu gắn TRÊN tường biên vào vùng,
    # KHÔNG mở rộng sang vùng kề). field giáp Maria; maria giáp Maria+Rose; v.v.
    _BORDER_RINGS = {
        'field': ('maria',),
        'maria': ('maria', 'rose'),
        'rose':  ('rose', 'sina'),
        'sina':  ('sina',),
    }

    @staticmethod
    def _dist_to_box_perimeter(box, x: float, y: float) -> float:
        """Khoảng cách từ (x,y) tới VIỀN hình chữ nhật `box` (vòng tường)."""
        l, t, r, b = box
        dx = max(l - x, 0.0, x - r)
        dy = max(t - y, 0.0, y - b)
        if dx == 0.0 and dy == 0.0:        # bên trong box → tới cạnh gần nhất
            return min(x - l, r - x, y - t, b - y)
        return math.hypot(dx, dy)          # ngoài box → tới box

    @classmethod
    def same_zone(cls, ax: float, ay: float, bx: float, by: float,
                  wall_margin: float = 90.0, strict: bool = False,
                  strict_margin: float = 24.0) -> bool:
        """Kiểm tra (ax, ay) và (bx, by) có ở cùng một khu vực (zone) không.

        Nếu strict=True, áp dụng luật giao tranh nghiêm ngặt: 
        - Phải cùng chung zone.
        - Phải cách xa tâm tường ít nhất strict_margin (mặc định 24px) để tránh
          đứng đè lên tường mà vẫn giao tranh.
        """
        za = cls.zone_of(ax, ay)
        zb = cls.zone_of(bx, by)

        if strict:
            # Ở chế độ nghiêm ngặt (Combat): cho phép giao tranh ngay khi đã cùng vùng (cùng bên tường).
            # Không áp đặt strict_margin chặn đứng giao tranh khi đã ở cùng zone.
            return za == zb

        if zb == za:
            return True
        for ring in cls._BORDER_RINGS.get(za, ()):
            box = cls._zone_boxes.get(ring)
            if box is not None and cls._dist_to_box_perimeter(box, bx, by) <= wall_margin:
                return True
        return False

    # -----------------------------------------------------------------------
    # Quản lý entity
    # -----------------------------------------------------------------------

    @classmethod
    def spawn_entity(cls, entity) -> None:
        """Thêm entity vào thế giới. Gọi ngay sau khi tạo object."""
        cls._entities.append(entity)
        cls._cache_valid = False
        # Tường mới → cụm lỗ hổng có thể thay đổi (tường sửa lấp lỗ cũ)
        if getattr(entity, 'ENTITY_TYPE', None) == 'wall':
            cls._dead_clusters_dirty = True

    @classmethod
    def remove_entity(cls, entity) -> None:
        """Xoá entity khỏi danh sách (dùng khi muốn xoá ngay, không chờ purge)."""
        try:
            cls._entities.remove(entity)
        except ValueError:
            pass
        cls._cache_valid = False
        if getattr(entity, 'ENTITY_TYPE', None) == 'wall':
            cls._dead_clusters_dirty = True

    @classmethod
    def purge_dead(cls) -> None:
        """Dọn entity có is_alive=False ra khỏi danh sách.

        Gọi 1 lần mỗi frame (ở cuối game loop) để tránh accumulate.
        Chỉ vô hiệu hóa cache frame khi THỰC SỰ có entity bị dọn dẹp.
        """
        dead_entities = [e for e in cls._entities if not getattr(e, 'is_alive', True)]
        if dead_entities:
            cls._entities = [e for e in cls._entities
                             if getattr(e, 'is_alive', True)]
            cls._cache_valid = False
            # Nếu có tường bị dọn → cụm lỗ hổng cần tính lại
            if any(getattr(e, 'ENTITY_TYPE', None) == 'wall' for e in dead_entities):
                cls._dead_clusters_dirty = True

    @classmethod
    def _ensure_frame_cache(cls) -> None:
        """Dựng cache 1 lần/frame: phân loại entity còn sống + cụm lỗ hổng tường.

        Dùng lại cho mọi titan trong frame thay vì quét lại toàn bộ entity cho
        từng con (nguồn lag chính khi đông titan).

        Tối ưu hóa: _f_dead_clusters chỉ tính lại khi _dead_clusters_dirty=True
        (tức khi cấu trúc tường thực sự thay đổi). Với frame bình thường (không
        có tường vỡ/sửa), cụm lỗ hổng được tái sử dụng hoàn toàn — tránh O(D²)
        clustering loop chạy mọi frame.
        """
        if cls._cache_valid:
            return
        walls = []; towers = []; soldiers = []; commanders = []; hq = None
        for e in cls._entities:
            if not getattr(e, 'is_alive', True):
                continue
            et = getattr(e, 'ENTITY_TYPE', None)
            if et == 'wall':
                walls.append(e)
            elif et == 'tower':
                towers.append(e)
            elif et == 'soldier':
                soldiers.append(e)
            elif et == 'commander':
                commanders.append(e)
            elif et == 'hq':
                hq = e
        cls._f_walls = walls
        cls._f_towers = towers
        cls._f_soldiers = soldiers
        cls._f_commanders = commanders
        cls._f_hq = hq

        # Cụm dead-section: CHỈ tính lại khi cấu trúc tường thay đổi.
        # Bình thường: dùng lại _f_dead_clusters từ frame trước → không lag.
        if cls._dead_clusters_dirty:
            dead = []
            for w in cls._wall_refs:
                if getattr(w, 'is_alive', True):
                    continue
                is_h_wall = (getattr(w, 'section_type', 'wall_h') == 'wall_h')
                # Tọa độ tâm gốc của ô 32x32
                base_cx = w.x + 16.0
                base_cy = w.y + 16.0
                
                # Điều chỉnh tâm hổng (gap center) khớp với tâm hitbox thực tế
                # để lính không bị lệch (deviate) khỏi lỗ hổng khi lách qua.
                # wall_h: hitbox là ry-=16, rh=124 -> tâm y = y + 46
                # wall_Y: hitbox là rx-=10, rw=76 -> tâm x = x + 28
                if is_h_wall:
                    cx = base_cx
                    cy = w.y + 46.0
                else:
                    cx = w.x + 28.0
                    cy = base_cy

                if cls.is_wall_blocked(base_cx, base_cy, radius=10.0):
                    continue   # đã bị tường khác xây bít lại
                dead.append((cx, cy, is_h_wall))
            clusters: list = []
            adj2 = 70.0 * 70.0
            for c in dead:
                joined = None
                for cl in clusters:
                    if any((c[0] - m[0]) ** 2 + (c[1] - m[1]) ** 2 <= adj2 for m in cl):
                        joined = cl
                        break
                if joined is None:
                    clusters.append([c])
                else:
                    joined.append(c)
            out = []
            for cl in clusters:
                xs = [p[0] for p in cl]
                ys = [p[1] for p in cl]
                cx = sum(xs) / len(cl)
                cy = sum(ys) / len(cl)
                # Lấy hướng tường từ tile gốc (chuẩn xác cho cả lỗ 1-tile)
                is_h = cl[0][2]
                # Khoảng trải (lo..hi) trên TRỤC DỌC THEO TƯỜNG (x nếu ngang, y nếu dọc)
                if is_h:
                    lo, hi = min(xs), max(xs)
                else:
                    lo, hi = min(ys), max(ys)
                out.append((cx, cy, len(cl), is_h, lo, hi))
            cls._f_dead_clusters = out
            cls._dead_clusters_dirty = False

        cls._cache_valid = True

    # -----------------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------------

    @classmethod
    def all(cls) -> list:
        """Trả về tất cả entity còn sống (is_alive=True)."""
        return [e for e in cls._entities if getattr(e, "is_alive", True)]

    @classmethod
    def find_in_radius(cls, cx: float, cy: float,
                       radius: float,
                       entity_type: Optional[str] = None) -> list:
        """Entity còn sống trong vòng tròn bán kính `radius` tâm (cx, cy).

        Args:
            cx, cy:       Toạ độ tâm vùng tìm kiếm.
            radius:       Bán kính (pixel).
            entity_type:  Lọc theo ENTITY_TYPE (vd. "titan", "soldier").
                          None = không lọc loại.

        Returns:
            list: Các entity thoả điều kiện, thứ tự không đảm bảo.
        """
        r2 = radius * radius
        result = []
        for e in cls._entities:
            if not getattr(e, "is_alive", True):
                continue
            if entity_type is not None:
                if getattr(e, "ENTITY_TYPE", None) != entity_type:
                    continue
            dx = e.x - cx
            dy = e.y - cy
            if dx * dx + dy * dy <= r2:
                result.append(e)
        return result

    @classmethod
    def find_nearest(cls, cx: float, cy: float,
                     entity_type: Optional[str] = None) -> Optional[object]:
        """Entity còn sống gần nhất với (cx, cy).

        Args:
            cx, cy:       Toạ độ tham chiếu.
            entity_type:  Lọc theo ENTITY_TYPE. None = không lọc.

        Returns:
            Entity gần nhất, hoặc None nếu không có.
        """
        best = None
        best_d2 = math.inf
        for e in cls._entities:
            if not getattr(e, "is_alive", True):
                continue
            if entity_type is not None:
                if getattr(e, "ENTITY_TYPE", None) != entity_type:
                    continue
            dx = e.x - cx
            dy = e.y - cy
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                best = e
        return best

    # -----------------------------------------------------------------------
    # Structures (công trình / tháp) — dùng cho E-swing aim targeting
    # -----------------------------------------------------------------------

    @classmethod
    def register_structure(cls, rect) -> None:
        """Đăng ký pygame.Rect của một tháp vào danh sách structures."""
        cls._structures.append(rect)

    @classmethod
    def unregister_structure(cls, rect) -> None:
        """Xoá rect tháp khi tháp bị phá huỷ."""
        try:
            cls._structures.remove(rect)
        except ValueError:
            pass

    @classmethod
    def structures(cls) -> list:
        """Trả về list pygame.Rect của tất cả công trình còn tồn tại."""
        return list(cls._structures)

    @classmethod
    def register_static_anchor(cls, rect, anchor_id) -> None:
        """Đăng ký rect world-coords làm điểm đu dây ODM (decoration / ground tower).

        anchor_id: (tx, ty, kind) cho decoration, id(entity) cho ground tower.
        """
        cls._static_anchors.append((rect, anchor_id))

    @classmethod
    def remove_static_anchor(cls, anchor_id) -> None:
        """Xoá anchor theo id khi decoration bị phá hoặc tower bị huỷ."""
        cls._static_anchors = [(r, i) for r, i in cls._static_anchors
                               if i != anchor_id]

    @classmethod
    def static_anchors(cls) -> list:
        """Trả về list pygame.Rect của tất cả static ODM anchor còn hoạt động."""
        return [r for r, _ in cls._static_anchors]

    @classmethod
    def register_wall_collider(cls, wall, rect) -> None:
        """Register a wall collision rect as (left, top, width, height).

        Đồng thời lưu vào `_wall_refs` để gap-detection luôn tìm thấy
        dead sections dù purge_dead() đã chạy.
        """
        rect = (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
        cls._wall_colliders[id(wall)] = rect
        cls._wall_orient[id(wall)] = getattr(wall, 'section_type', 'wall_h')
        # Chỉ thêm 1 lần (wall có thể được register nhiều lần khi reload)
        if wall not in cls._wall_refs:
            cls._wall_refs.append(wall)
        # Băm vào spatial grid (tường tĩnh — vị trí không đổi; query lọc is_alive)
        cell = cls._WALL_CELL
        rx, ry, rw, rh = rect
        c0, c1 = int(rx // cell), int((rx + rw) // cell)
        r0, r1 = int(ry // cell), int((ry + rh) // cell)
        for cc in range(c0, c1 + 1):
            for rr in range(r0, r1 + 1):
                cls._wall_grid.setdefault((cc, rr), []).append(wall)

    @classmethod
    def is_wall_blocked(cls, x: float, y: float, radius: float = 12.0,
                        exclude=None, extend_down: float = 0.0,
                        is_passing_gap: bool = False,
                        gap_center: tuple | None = None,
                        force_visual_expand: bool = False) -> bool:
        """True when a circular actor footprint overlaps an alive wall section.

        Dùng spatial hash: chỉ quét tường trong các ô lưới phủ vùng (x±r, y±r).
        exclude: wall entity (hoặc id) để skip khi check — dùng khi titan đang
                 tiến về đúng section đó (tránh tự block chính section target).
        extend_down: mở rộng rect tường XUỐNG phía dưới (Y tăng) trước khi check.
                     Dùng cho commander để phủ toàn thân sprite tường.
                     Mặc định 0 — lính không bị ảnh hưởng.
        """
        is_passing = is_passing_gap or (gap_center is not None)
        cell = cls._WALL_CELL
        x = float(x); y = float(y)
        c0, c1 = int((x - radius) // cell), int((x + radius) // cell)
        r0, r1 = int((y - radius) // cell), int((y + radius) // cell)
        
        # Nếu là lính (radius < 30), do ta mở rộng hitbox của tường lên kích thước
        # của visual sprite (lên tới 155px, tương đương ~2.5 cells), hitbox mới có
        # thể tràn sang cell lân cận mà circle của lính không chạm tới.
        # Ta cần quét thêm 2 cell xung quanh để không bỏ sót tường bị ẩn.
        if radius < 30.0 and not is_passing:
            c0 -= 2; c1 += 2
            r0 -= 2; r1 += 2

        if extend_down > 0:
            # Tường được hash theo rect gốc (phần trên). Khi extend_down > 0, vòng
            # tròn có thể nằm DƯỚI rect gốc nhưng vẫn chạm extended rect → cần tìm
            # tường ở các cell phía trên vòng tròn (y - radius - extend_down).
            r0 = min(r0, int((y - radius - extend_down) // cell))
        r2 = radius * radius
        grid = cls._wall_grid
        # exclude: single entity OR iterable of entities (set/list)
        if exclude is None:
            _excl_ids = None
        elif hasattr(exclude, '__iter__') and not hasattr(exclude, 'is_alive'):
            _excl_ids = {id(e) for e in exclude}
        else:
            _excl_ids = {id(exclude)}
        for cc in range(c0, c1 + 1):
            for rr in range(r0, r1 + 1):
                bucket = grid.get((cc, rr))
                if not bucket:
                    continue
                for w in bucket:
                    if _excl_ids and id(w) in _excl_ids:
                        continue
                    if not getattr(w, 'is_alive', True):
                        continue

                    # Nếu lính đang chui lỗ và wall này nằm quanh lỗ (bán kính 96px ~ 3 tiles),
                    # bỏ qua va chạm hoàn toàn để tránh bị kẹt góc/mép/vùng cấm quanh lỗ.
                    if gap_center is not None:
                        cx, cy, _ = gap_center
                        wx = float(w.x) + 16.0
                        wy = float(w.y) + 16.0
                        if (wx - cx) ** 2 + (wy - cy) ** 2 < 9216.0:  # 96^2 px
                            continue

                    rect = cls._wall_colliders.get(id(w))
                    if rect is None:
                        rect = (float(w.x), float(w.y), 32.0, 32.0)
                    rx, ry, rw, rh = rect
                    
                    # Khắc phục lỗi "bít lỗ": CHỈ mở rộng hitbox vuông góc với chiều dài của tường.
                    # Mở rộng dọc theo trục tường sẽ làm hitbox tràn vào lỗ hổng kế bên và chặn lính.
                    orient = cls._wall_orient.get(id(w), 'wall_h')
                    if (radius < 30.0 or force_visual_expand) and not is_passing_gap:
                        if orient == 'wall_Y' or orient == 'wall_path' or orient == 'chantuong':
                            # Trục tường là Y -> giữ nguyên rh=32 để không bít lỗ dọc.
                            # Mở rộng bề ngang (X) để che thân tường (sprite rộng 74).
                            rx -= 10.0
                            rw = 76.0
                        elif orient == 'wall_h':
                            # Trục tường là X -> giữ nguyên rw=32 để không bít lỗ ngang.
                            # Mở rộng chiều cao (Y) để che mặt tường (sprite cao 122).
                            ry -= 16.0
                            rh = 124.0
                        else:  # corners
                            # Góc tường: giữ nguyên độ mở rộng nhỏ bé ban đầu của user
                            # để tránh việc hitbox khổng lồ tràn sang bít lỗ của ô bên cạnh.
                            rx -= 10.0
                            ry -= 16.0
                            rw = 52.0
                            rh = 64.0

                    # Chỉ extend wall_h (tường ngang, tiles cạnh nhau theo X).
                    # wall_Y tiles chồng theo Y → extend_down làm tràn vào gap.
                    rh_eff = rh + extend_down if orient == 'wall_h' else rh
                    # Commander only: dịch rect tường dọc xuống để phủ chân sprite
                    ry_eff = ry + 40 if (extend_down > 0 and orient == 'wall_Y') else ry
                    nearest_x = rx if x < rx else (rx + rw if x > rx + rw else x)
                    nearest_y = ry_eff if y < ry_eff else (ry_eff + rh_eff if y > ry_eff + rh_eff else y)
                    dx = x - nearest_x
                    dy = y - nearest_y
                    if dx * dx + dy * dy <= r2:
                        return True
        return False

    # Wall sprites extend well beyond the 32x32 collision box:
    # wall_h: 70x122px, wall_Y: 74x105px, corners up to 78x155px.
    # These constants cover the largest sprite so spawn positions stay visually
    # outside all wall graphics.
    _WALL_VISUAL_W: float = 82.0
    _WALL_VISUAL_H: float = 160.0

    @classmethod
    def is_wall_visual_blocked(cls, x: float, y: float,
                               radius: float = 0.0) -> bool:
        """True if (x,y) falls inside the visual sprite rect of any alive wall section.

        Use this for spawn-position checks so soldiers don't appear embedded in
        wall graphics even when they are outside the 32x32 gameplay collision box.
        """
        vw = cls._WALL_VISUAL_W
        vh = cls._WALL_VISUAL_H
        for w in cls._wall_refs:
            if not getattr(w, 'is_alive', True):
                continue
            wx, wy = float(w.x), float(w.y)
            nearest_x = max(wx, min(float(x), wx + vw))
            nearest_y = max(wy, min(float(y), wy + vh))
            dx = float(x) - nearest_x
            dy = float(y) - nearest_y
            if dx * dx + dy * dy <= radius * radius:
                return True
        return False

    # -----------------------------------------------------------------------
    # Pathfinding (A* trên lưới ô) — né tường, đi qua lỗ hổng (section đã bể)
    # -----------------------------------------------------------------------

    @classmethod
    def configure_pathfinding(cls, world_w: float, world_h: float, cell: int = 32) -> None:
        """Cấu hình lưới đi-được theo kích thước thế giới (px)."""
        cls._pf_cell = int(cell)
        cls._pf_cols = int(math.ceil(world_w / cell))
        cls._pf_rows = int(math.ceil(world_h / cell))
        cls._pf_dirty = True

    @classmethod
    def invalidate_pathfinding(cls) -> None:
        """Đánh dấu lưới cần dựng lại (gọi khi tường bị phá / tạo lỗ hổng mới)."""
        cls._pf_dirty = True

    @classmethod
    def _alive_wall_count(cls) -> int:
        """Đếm số WallSection CÒN SỐNG hiện tại — dùng làm "chữ ký thay đổi"
        rẻ tiền: `_ensure_pf_grid()` so số này với `_pf_built_walls` (số lúc
        dựng lưới lần trước) để phát hiện tường vừa sập/vá MÀ KHÔNG CẦN gọi
        `invalidate_pathfinding()` tường minh ở mọi nơi tường có thể đổi
        trạng thái — lưới đường A* tự phát hiện lỗi thời."""
        return sum(1 for w in cls._entities
                   if getattr(w, 'ENTITY_TYPE', None) == 'wall'
                   and getattr(w, 'is_alive', True))

    @classmethod
    def _rebuild_pf_grid(cls) -> None:
        """Raster hoá collider tường CÒN SỐNG vào tập ô chặn."""
        blocked: set = set()
        cell = cls._pf_cell
        for w in cls._entities:
            if getattr(w, 'ENTITY_TYPE', None) != 'wall':
                continue
            if not getattr(w, 'is_alive', True):
                continue  # tường đã bể → ô đi được (lỗ hổng)
            rect = cls._wall_colliders.get(id(w))
            if rect is None:
                rect = (float(w.x), float(w.y), 32.0, 32.0)
            rx, ry, rw, rh = rect
            c0 = int(rx // cell); c1 = int((rx + rw) // cell)
            r0 = int(ry // cell); r1 = int((ry + rh) // cell)
            for cc in range(c0, c1 + 1):
                for rr in range(r0, r1 + 1):
                    blocked.add((cc, rr))
        cls._pf_blocked = blocked
        cls._pf_built_walls = cls._alive_wall_count()
        cls._pf_dirty = False

    @classmethod
    def _ensure_pf_grid(cls) -> None:
        """Dựng lại lưới pathfinding NẾU CẦN — gọi ở ĐẦU MỌI thao tác dùng
        lưới (`find_path`), lazy-rebuild thay vì rebuild mỗi frame. Điều
        kiện rebuild: cờ `_pf_dirty` (set tường minh bởi `invalidate_pathfinding`)
        HOẶC số tường sống đã đổi so với lần dựng trước (`_alive_wall_count`)
        — bắt được cả những thay đổi KHÔNG gọi invalidate tường minh."""
        if cls._pf_cols == 0:
            return  # chưa configure
        if cls._pf_dirty or cls._alive_wall_count() != cls._pf_built_walls:
            cls._rebuild_pf_grid()

    @classmethod
    def _pf_in_bounds(cls, c: int, r: int) -> bool:
        """Ô lưới (c,r) có nằm trong biên bản đồ đã `configure_pathfinding()` không."""
        return 0 <= c < cls._pf_cols and 0 <= r < cls._pf_rows

    @classmethod
    def _pf_blocked_cell(cls, c: int, r: int) -> bool:
        """Ô lưới (c,r) có bị tường chặn không (tra tập `_pf_blocked` đã raster hoá)."""
        return (c, r) in cls._pf_blocked

    @classmethod
    def _pf_nearest_free(cls, c: int, r: int, max_ring: int = 6):
        """Ô trống gần (c,r) nhất (nếu (c,r) bị chặn) — quét theo vòng."""
        if not cls._pf_blocked_cell(c, r) and cls._pf_in_bounds(c, r):
            return (c, r)
        for ring in range(1, max_ring + 1):
            for dc in range(-ring, ring + 1):
                for dr in range(-ring, ring + 1):
                    if max(abs(dc), abs(dr)) != ring:
                        continue
                    nc, nr = c + dc, r + dr
                    if cls._pf_in_bounds(nc, nr) and not cls._pf_blocked_cell(nc, nr):
                        return (nc, nr)
        return None

    @classmethod
    def find_path(cls, sx: float, sy: float, gx: float, gy: float,
                  max_nodes: int = 6000) -> Optional[list]:
        """A* né tường. Trả list waypoint [(x,y), ...] (world px) hoặc None nếu
        KHÔNG có đường (bị tường bao kín) → caller quyết định phá tường."""
        cls._ensure_pf_grid()
        if cls._pf_cols == 0:
            return None
        cell = cls._pf_cell
        start = (int(sx // cell), int(sy // cell))
        goal_raw = (int(gx // cell), int(gy // cell))
        # Đích nằm trong tường? (vd tâm tháp) → dừng ở ô trống gần nhất, KHÔNG đi vào
        goal_in_wall = cls._pf_blocked_cell(*goal_raw)
        start = cls._pf_nearest_free(*start)
        goal  = cls._pf_nearest_free(*goal_raw)
        if start is None or goal is None:
            return None
        if start == goal:
            # Đích ô trống → tới thẳng; đích trong tường → tới tâm ô trống gần nhất
            return [(gx, gy)] if not goal_in_wall else [
                (goal[0] * cell + cell / 2.0, goal[1] * cell + cell / 2.0)]

        def h(a, b):
            """Heuristic A* — khoảng cách OCTILE giữa 2 ô lưới (cho phép đi
            chéo): bằng Manhattan (`dc+dr`) trừ bù phần "tiết kiệm" khi đi
            chéo thay vì răng cưa (`(sqrt(2)-2) * min(dc,dr)`, hệ số âm vì
            sqrt(2)≈1.414 < 2). Chính xác hơn Manhattan thuần cho lưới
            8-hướng, admissible (không bao giờ đánh giá CAO HƠN chi phí
            thật) nên A* vẫn đảm bảo tìm đường ngắn nhất."""
            dc = abs(a[0] - b[0]); dr = abs(a[1] - b[1])
            return (dc + dr) + (math.sqrt(2) - 2) * min(dc, dr)

        open_heap = [(h(start, goal), 0.0, start)]
        came: dict = {}
        gscore: dict = {start: 0.0}
        nodes = 0
        DIRS = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                (1, 1, 1.41421), (1, -1, 1.41421), (-1, 1, 1.41421), (-1, -1, 1.41421))
        while open_heap:
            _f, g, cur = heapq.heappop(open_heap)
            if cur == goal:
                break
            nodes += 1
            if nodes > max_nodes:
                return None
            cc, cr = cur
            for dc, dr, cost in DIRS:
                nc, nr = cc + dc, cr + dr
                if not cls._pf_in_bounds(nc, nr) or cls._pf_blocked_cell(nc, nr):
                    continue
                # Chặn cắt góc qua khe chéo giữa 2 ô tường
                if dc != 0 and dr != 0:
                    if cls._pf_blocked_cell(cc + dc, cr) or cls._pf_blocked_cell(cc, cr + dr):
                        continue
                ng = g + cost
                if ng < gscore.get((nc, nr), 1e18):
                    gscore[(nc, nr)] = ng
                    came[(nc, nr)] = cur
                    heapq.heappush(open_heap, (ng + h((nc, nr), goal), ng, (nc, nr)))
        if goal not in came and goal != start:
            return None

        # Dựng lại đường (cell) rồi rút gọn điểm thẳng hàng
        cells = [goal]
        cur = goal
        while cur in came:
            cur = came[cur]
            cells.append(cur)
        cells.reverse()
        pts = []
        for i, (c, r) in enumerate(cells):
            if 0 < i < len(cells) - 1:
                pc, pr = cells[i - 1]; nc, nr = cells[i + 1]
                if (c - pc, r - pr) == (nc - c, nr - r):
                    continue  # cùng hướng → bỏ điểm giữa
            pts.append((c * cell + cell / 2.0, r * cell + cell / 2.0))
        # Chỉ thêm điểm đích THẬT nếu nó không nằm trong tường (tránh đi xuyên)
        if not goal_in_wall:
            pts.append((gx, gy))
        return pts

    @classmethod
    def can_path_to(cls, entity, gx: float, gy: float,
                    throttle: int = 20) -> bool:
        """Có đường A* né tường tới (gx,gy) không? (cache throttle trên entity
        để khỏi chạy A* mỗi frame). Dùng cho titan quyết: đi vòng qua lỗ hổng
        hay phá tường."""
        n = getattr(entity, '_pf_reach_n', 0)
        if n <= 0:
            path = cls.find_path(entity.x, entity.y, gx, gy)
            entity._pf_reach = path is not None
            entity._pf_reach_n = throttle
        else:
            entity._pf_reach_n = n - 1
        return getattr(entity, '_pf_reach', True)

    # -----------------------------------------------------------------------
    # Buildings
    # -----------------------------------------------------------------------

    @classmethod
    def get_all_buildings(cls) -> list:
        """Tất cả entity có ENTITY_TYPE='building' còn sống."""
        return [e for e in cls._entities
                if getattr(e, "ENTITY_TYPE", None) == "building"
                and getattr(e, "is_alive", True)]

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    # -----------------------------------------------------------------------
    # Titan AI helpers — dùng bởi Titan._find_best_target() và boss.py
    # -----------------------------------------------------------------------

    @classmethod
    def get_headquarters(cls):
        """Trả về entity có ENTITY_TYPE='hq' còn sống, hoặc None."""
        for e in cls._entities:
            if getattr(e, 'is_alive', True) and getattr(e, 'ENTITY_TYPE', None) == 'hq':
                return e
        return None

    @classmethod
    def find_blocking_wall(cls, titan, hq=None, block_radius: float = 70.0):
        """Tìm wall còn sống nằm chắn trên đường titan → hq.

        Thuật toán: chiếu điểm lên đoạn thẳng titan→hq, kiểm tra khoảng
        cách vuông góc. Trả về wall gần titan nhất nếu có.
        """
        if hq is None:
            hq = cls.get_headquarters()
        if hq is None or not getattr(hq, 'is_alive', True):
            return None

        ax, ay = titan.x, titan.y
        bx, by = hq.x, hq.y
        seg_dx, seg_dy = bx - ax, by - ay
        seg_len2 = seg_dx * seg_dx + seg_dy * seg_dy
        if seg_len2 == 0:
            return None

        cls._ensure_frame_cache()
        best, best_d = None, math.inf
        for w in cls._f_walls:          # tường còn sống (cache frame)
            t = ((w.x - ax) * seg_dx + (w.y - ay) * seg_dy) / seg_len2
            if t <= 0.0 or t >= 1.0:
                continue
            px = ax + t * seg_dx
            py = ay + t * seg_dy
            perp = math.sqrt((w.x - px) ** 2 + (w.y - py) ** 2)
            if perp <= block_radius:
                dx = w.x - ax
                dy = w.y - ay
                d = math.sqrt(dx * dx + dy * dy)
                if d < best_d:
                    best_d, best = d, w
        return best

    @classmethod
    def can_reach_direct(cls, titan, target, block_radius: float = 70.0) -> bool:
        """True nếu đường thẳng titan → target không bị wall nào chặn."""
        if target is None:
            return False
        ax, ay = titan.x, titan.y
        bx, by = target.x, target.y
        seg_dx, seg_dy = bx - ax, by - ay
        seg_len2 = seg_dx * seg_dx + seg_dy * seg_dy
        if seg_len2 == 0:
            return True
        for w in cls._entities:
            if not getattr(w, 'is_alive', True):
                continue
            if getattr(w, 'ENTITY_TYPE', None) != 'wall':
                continue
            t = ((w.x - ax) * seg_dx + (w.y - ay) * seg_dy) / seg_len2
            if t <= 0.0 or t >= 1.0:
                continue
            px = ax + t * seg_dx
            py = ay + t * seg_dy
            perp = math.sqrt((w.x - px) ** 2 + (w.y - py) ** 2)
            if perp <= block_radius:
                return False
        return True

    @classmethod
    def find_wall_gap(cls, ex: float, ey: float,
                      tx: float, ty: float,
                      vision_range: float):
        """Tìm lỗ hổng tường (section đã bể) gần nhất trong tầm nhìn,
        ưu tiên theo hướng entity→target.

        Dùng `_wall_refs` thay vì `_entities` — đảm bảo tìm thấy dead sections
        ngay cả sau khi purge_dead() đã chạy.

        Dùng bởi TitanAI._move() khi greedy bị tường chặn hoàn toàn —
        titan đi vòng qua lỗ thay vì phá tường ngay.

        Args:
            ex, ey:        Vị trí entity (titan/lính).
            tx, ty:        Vị trí target (đích muốn tới).
            vision_range:  Tầm nhìn tối đa (px).

        Returns:
            (gx, gy) tọa độ lỗ hổng gần nhất, hoặc None.
        """
        vr2 = vision_range * vision_range
        dx_t = tx - ex
        dy_t = ty - ey
        len_t = math.sqrt(dx_t * dx_t + dy_t * dy_t)

        best = None
        best_d2 = float('inf')

        # Quét _wall_refs — chỉ chứa wall entities, kể cả đã bể (dead)
        for w in cls._wall_refs:
            if getattr(w, 'is_alive', True):
                continue  # còn sống → không phải lỗ hổng

            # Xác nhận vị trí này không bị tường mới xây/trùng bít lại
            if cls.is_wall_blocked(w.x + 16.0, w.y + 16.0, radius=10.0):
                continue

            wdx = w.x - ex
            wdy = w.y - ey
            wd2 = wdx * wdx + wdy * wdy
            if wd2 > vr2:
                continue  # ngoài tầm nhìn

            # Bỏ qua lỗ hổng nằm quá xa phía sau entity (>110° so với hướng titan→target)
            # Dùng cosine chuẩn hóa để tránh lỗi scale khi titan/target ở xa
            if len_t > 0 and wd2 > 0:
                cos_a = (wdx * dx_t + wdy * dy_t) / (math.sqrt(wd2) * len_t)
                if cos_a < -0.35:  # cos(110°) ≈ -0.34
                    continue

            if wd2 < best_d2:
                best_d2 = wd2
                best = w

        return (best.x, best.y) if best is not None else None

    @classmethod
    def find_gap_span_center(cls, gx: float, gy: float) -> tuple:
        """Từ một dead tile tại (gx, gy), mở rộng sang các tile dead liền kề để tìm
        trung tâm của span liền kề rộng nhất (ngang hoặc dọc).

        Ví dụ: 2 tile dead (gx,gy) và (gx+32,gy) → span rộng 64px, center = (gx+32, gy+16).
        Titan đi đúng vào giữa lỗ thay vì mãi đập tường kề cạnh.
        """
        dead: set = set()
        for w in cls._wall_refs:
            if not getattr(w, 'is_alive', True):
                if not cls.is_wall_blocked(w.x + 16.0, w.y + 16.0, radius=10.0):
                    dead.add((round(w.x / 32) * 32, round(w.y / 32) * 32))

        igx = round(gx / 32) * 32
        igy = round(gy / 32) * 32

        # Mở rộng ngang
        horiz = [igx]
        cx = igx - 32
        while (cx, igy) in dead:
            horiz.append(cx)
            cx -= 32
        cx = igx + 32
        while (cx, igy) in dead:
            horiz.append(cx)
            cx += 32

        # Mở rộng dọc
        vert = [igy]
        cy = igy - 32
        while (igx, cy) in dead:
            vert.append(cy)
            cy -= 32
        cy = igy + 32
        while (igx, cy) in dead:
            vert.append(cy)
            cy += 32

        horiz_w = max(horiz) + 32 - min(horiz)
        vert_h  = max(vert)  + 32 - min(vert)

        if horiz_w >= vert_h:
            return (min(horiz) + max(horiz) + 32) / 2.0, float(igy) + 16.0
        else:
            return float(igx) + 16.0, (min(vert) + max(vert) + 32) / 2.0

    @classmethod
    def find_nearest_gap_center(cls, ex: float, ey: float,
                                tx: float, ty: float,
                                vision_range: float,
                                min_sections: int = 1):
        """Tâm THỰC (không snap lưới 32) của lỗ hổng tường mà đường titan→target
        nên đi qua.

        Khác find_wall_gap/find_gap_span_center (giả định lưới 32px — SAI với
        tường thật cách nhau 59/54px): hàm này gom các dead section liền kề theo
        KHOẢNG CÁCH thật rồi trả về tâm cụm gần đường đi nhất, ở phía trước.

        Args:
            ex, ey:       Vị trí titan.
            tx, ty:       Vị trí target.
            vision_range: Tầm nhìn tối đa (px).

        Returns:
            (gx, gy, is_horizontal) — ĐIỂM TIẾN VÀO của lỗ nên đi qua, hoặc None.
            Lỗ ngắn (≤3 tile) → giữa lỗ. Lỗ dài (≥4) → bám đường titan nhưng cách
            mép → titan vào ĐA HƯỚNG, không dồn hết vào giữa.
        """
        dx_t = tx - ex
        dy_t = ty - ey
        len_t = math.hypot(dx_t, dy_t)
        if len_t == 0:
            return None
        vr2 = vision_range * vision_range

        # Cụm lỗ hổng đã dựng sẵn 1 lần/frame (xem _ensure_frame_cache) →
        # ở đây chỉ chọn cụm phù hợp, KHÔNG quét lại toàn bộ tường.
        cls._ensure_frame_cache()
        if not cls._f_dead_clusters:
            return None

        msec = int(min_sections)
        best = None
        best_key = None
        for (mx, my, size, is_h, lo, hi) in cls._f_dead_clusters:
            if size < msec:
                continue
            # Đại diện = ĐIỂM GẦN TITAN NHẤT trên dải lỗ (kẹp toạ độ titan vào
            # [lo,hi] trên trục dọc tường), KHÔNG dùng tâm. Dãy DÀI → tâm ở xa →
            # lọt tầm-nhìn/hướng sai → "ở gần mà không nhận diện". Điểm gần này
            # phản ánh đúng chỗ titan sẽ băng qua.
            if is_h:
                rx = lo if ex < lo else (hi if ex > hi else ex)
                ry = my
            else:
                rx = mx
                ry = lo if ey < lo else (hi if ey > hi else ey)
            wdx = rx - ex
            wdy = ry - ey
            wd2 = wdx * wdx + wdy * wdy
            if wd2 > vr2:
                continue                # ngoài tầm nhìn
            if wd2 > 0:
                cos_a = (wdx * dx_t + wdy * dy_t) / (math.sqrt(wd2) * len_t)
                if cos_a < -0.2:        # bỏ lỗ nằm sau lưng (>~100° lệch hướng)
                    continue
            t = ((rx - ex) * dx_t + (ry - ey) * dy_t) / (len_t * len_t)
            px = ex + t * dx_t
            py = ey + t * dy_t
            perp = math.hypot(rx - px, ry - py)
            key = (perp, math.sqrt(wd2))   # gần đường đi nhất, hòa → gần titan
            if best_key is None or key < best_key:
                best_key = key
                best = (mx, my, size, is_h, lo, hi)
        if best is None:
            return None

        mx, my, size, is_h, lo, hi = best
        center = (lo + hi) * 0.5
        if size >= 4:
            # Lỗ DÀI: vào CÁCH MÉP (>=MARGIN) nhưng theo vị trí titan → đa hướng,
            # tránh mọi titan dồn vào giữa. Kẹp toạ-độ-titan vào [lo+M, hi-M].
            M = 55.0
            a_lo, a_hi = lo + M, hi - M
            if a_lo > a_hi:
                entry = center
            else:
                titan_axis = ex if is_h else ey
                entry = a_lo if titan_axis < a_lo else (a_hi if titan_axis > a_hi else titan_axis)
        else:
            entry = center            # lỗ 2-3 tile → đi GIỮA
        if is_h:
            return (entry, my, is_h)
        return (mx, entry, is_h)

    @classmethod
    def find_adjacent_wall_to_widen(cls, cx: float, cy: float, is_h=None):
        """Section tường CÒN SỐNG kề lỗ (CÙNG HÀNG hoặc CÙNG CỘT) để phá MỞ RỘNG
        lỗ thành 2-tile LIỀN KỀ.

        Dùng bởi TitanAI: phá ô kề XÁC ĐỊNH (thay vì "tường gần nhất" đổi mỗi frame)
        → không giật, lỗ nối liền nhau qua được.

        KHÔNG phụ thuộc `is_h`: với lỗ 1-tile, hướng tường KHÔNG suy ra được từ 1 ô
        đơn (is_h mặc định True → sai cho tường DỌC). Nên xét cả 2 trục: chọn ô còn
        sống GẦN NHẤT mà cùng hàng (|Δy|≤24) HOẶC cùng cột (|Δx|≤24) với tâm lỗ.

        Returns:
            Wall entity kề gần nhất (cùng hàng/cột), hoặc None.
        """
        cls._ensure_frame_cache()
        best, best_d = None, 100.0
        for w in cls._f_walls:
            wx, wy = w.x + 16.0, w.y + 16.0
            same_row = abs(wy - cy) <= 24.0
            same_col = abs(wx - cx) <= 24.0
            if not (same_row or same_col):
                continue
            d = math.hypot(wx - cx, wy - cy)
            if d < best_d:
                best_d, best = d, w
        return best

    @classmethod
    def has_dead_wall_near(cls, cx: float, cy: float, radius: float,
                           min_sections: int = 1) -> bool:
        """True nếu có ít nhất 1 section tường đã bể trong bán kính (cx, cy).

        Dùng `_wall_refs` (chỉ wall entities, không bị purge) để scan
        trong phạm vi `radius` thay vì toàn bộ _entities.

        Args:
            cx, cy:   Tâm tìm kiếm (thường = home_pos của soldier).
            radius:   Bán kính quét (px).
        """
        r2 = radius * radius
        dead = []
        for w in cls._wall_refs:
            if getattr(w, 'is_alive', True):
                continue  # còn sống → không phải lỗ

            # Xác nhận vị trí này không bị tường mới xây/trùng bít lại
            if cls.is_wall_blocked(w.x + 16.0, w.y + 16.0, radius=10.0):
                continue

            wx = w.x + 16.0
            wy = w.y + 16.0
            dx = wx - cx
            dy = wy - cy
            if dx * dx + dy * dy <= r2:
                dead.append((wx, wy))

        need = max(1, int(min_sections))
        if need <= 1:
            return bool(dead)

        ADJ = 70.0
        clusters: list[list[tuple]] = []
        for p in dead:
            target_cl = None
            for cl in clusters:
                if any(math.hypot(p[0] - q[0], p[1] - q[1]) <= ADJ for q in cl):
                    target_cl = cl
                    break
            if target_cl is None:
                clusters.append([p])
            else:
                target_cl.append(p)
        for cl in clusters:
            if len(cl) >= need:
                return True
        return False

    @classmethod
    def get_dead_wall_zone_pairs_near(cls, cx: float, cy: float, radius: float,
                                      min_sections: int = 1) -> set:
        """Trả về tập hợp các cặp zone (inner, outer) của các mảng tường đã bể.
        
        Giống has_dead_wall_near nhưng trả về đích danh bức tường bị vỡ 
        để lính mở zone chính xác thay vì mở bừa bãi.
        """
        r2 = radius * radius
        dead = []
        for w in cls._wall_refs:
            if getattr(w, 'is_alive', True):
                continue
            if cls.is_wall_blocked(w.x + 16.0, w.y + 16.0, radius=10.0):
                continue

            wx = w.x + 16.0
            wy = w.y + 16.0
            dx = wx - cx
            dy = wy - cy
            if dx * dx + dy * dy <= r2:
                dead.append((wx, wy))

        need = max(1, int(min_sections))
        valid_dead_points = []
        if need <= 1:
            valid_dead_points = dead
        else:
            ADJ = 70.0
            clusters: list[list[tuple]] = []
            for p in dead:
                target_cl = None
                for cl in clusters:
                    if any(math.hypot(p[0] - q[0], p[1] - q[1]) <= ADJ for q in cl):
                        target_cl = cl
                        break
                if target_cl is None:
                    clusters.append([p])
                else:
                    target_cl.append(p)
            for cl in clusters:
                if len(cl) >= need:
                    valid_dead_points.extend(cl)

        pairs = set()
        for p in valid_dead_points:
            for wall_name, box in cls._zone_boxes.items():
                if cls._dist_to_box_perimeter(box, p[0], p[1]) < 32.0:
                    pair = cls.WALL_ZONE_PAIRS.get(wall_name)
                    if pair:
                        pairs.add(pair)
        return pairs

    @classmethod
    def find_blocking_wall_to(cls, ex: float, ey: float,
                              tx: float, ty: float,
                              block_radius: float = 55.0):
        """Tìm wall còn sống nằm chắn trên đường (ex,ey)→(tx,ty).

        Dùng bởi:
            • TitanAI.decide() — kiểm tra soldier/tower có bị tường chặn không.
            • TitanAI._break_blocking_wall() — xác định tường cần phá.

        Args:
            ex, ey:        Điểm xuất phát (titan).
            tx, ty:        Điểm đích (target).
            block_radius:  Khoảng cách vuông góc tối đa để coi là chặn (px).

        Returns:
            Wall entity gần (ex,ey) nhất trên đường, hoặc None.
        """
        seg_dx, seg_dy = tx - ex, ty - ey
        seg_len2 = seg_dx * seg_dx + seg_dy * seg_dy
        if seg_len2 == 0:
            return None

        cls._ensure_frame_cache()
        best, best_d = None, math.inf
        for w in cls._f_walls:          # tường còn sống (cache frame)
            t = ((w.x - ex) * seg_dx + (w.y - ey) * seg_dy) / seg_len2
            if t <= 0.0 or t >= 1.0:
                continue
            px = ex + t * seg_dx
            py = ey + t * seg_dy
            perp = math.sqrt((w.x - px) ** 2 + (w.y - py) ** 2)
            if perp <= block_radius:
                wdx = w.x - ex
                wdy = w.y - ey
                d = math.sqrt(wdx * wdx + wdy * wdy)
                if d < best_d:
                    best_d, best = d, w
        return best

    @classmethod
    def find_nearest_attacker(cls, titan):
        """Tìm tower/soldier/commander/wall còn sống gần titan nhất.

        Dùng cho FoundingTitan.update() và Titan._find_best_target().
        Coi tower/soldier/commander/wall là "kẻ tấn công tiềm năng".
        """
        attacker_types = {'tower', 'soldier', 'commander', 'wall'}
        best = None
        best_d2 = math.inf
        for e in cls._entities:
            if not getattr(e, 'is_alive', True):
                continue
            if getattr(e, 'ENTITY_TYPE', None) not in attacker_types:
                continue
            dx = e.x - titan.x
            dy = e.y - titan.y
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                best = e
        return best

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    @classmethod
    def reset(cls) -> None:
        """Xoá sạch toàn bộ entity và structures.

        Gọi khi load màn mới hoặc restart game.
        """
        cls._entities = []
        cls._structures = []
        cls._static_anchors = []
        cls._wall_colliders = {}
        cls._wall_refs = []
        cls._wall_grid = {}
        cls._wall_orient = {}
        cls._cache_valid = False
        cls._dead_clusters_dirty = True
        cls._f_walls = []
        cls._f_towers = []
        cls._f_soldiers = []
        cls._f_commanders = []
        cls._f_hq = None
        cls._f_dead_clusters = []
        cls._pf_blocked = set()
        cls._pf_dirty = True
        cls._pf_built_walls = -1
