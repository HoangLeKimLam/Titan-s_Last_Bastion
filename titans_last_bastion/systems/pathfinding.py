import math
import heapq
from systems.world_query import WorldQuery

class AStarPathfinder:
    """A* trên lưới 64px — dùng cho lính khi cần chuyển tháp CỰ LY XA (băng
    qua tường, không phải lỗ hổng gần). Khác `pathmove.follow_path()`
    (steering nhẹ O(1)/frame, chỉ né tường cục bộ): A* tính TRƯỚC toàn bộ
    tuyến đường 1 lần, tốn hơn nhưng tìm được đường VÒNG QUA tường dài mà
    steering không thể tự thoát ra. Toàn bộ method là `@classmethod` —
    class này không có state instance, chỉ là namespace thuật toán."""
    CELL_SIZE = 64.0

    @classmethod
    def get_cell(cls, x: float, y: float) -> tuple[int, int]:
        """Quy đổi toạ độ thế giới (px) → chỉ số ô lưới A* (chia nguyên cho
        `CELL_SIZE`=64px)."""
        return (int(x // cls.CELL_SIZE), int(y // cls.CELL_SIZE))

    @classmethod
    def _get_search_bounds(cls, sx: float, sy: float, tx: float, ty: float):
        """Thu hẹp phạm vi tìm kiếm A* về ĐÚNG 1 VÒNG TƯỜNG (Sina/Rose/Maria)
        thay vì quét TOÀN BẢN ĐỒ — tối ưu hiệu năng cho trường hợp phổ biến
        (lính chuyển tháp cùng vùng hoặc vùng liền kề).

        Thuật toán: xác định điểm bắt đầu/đích thuộc "outermost box" nào
        (vùng NGOÀI CÙNG chứa nó, kể cả nới rộng 64px — ưu tiên Sina trong
        cùng, tới Rose, tới Maria, không khớp gì → 'field' ngoài mọi vòng
        tường). Lấy `max_order` giữa 2 điểm (vùng NGOÀI HƠN quyết định) —
        NẾU CẢ 2 đều ở 'field' (order 4, ngoài mọi vòng tường) → return
        None (không giới hạn được, phải quét toàn map ở `find_path`).
        NGƯỢC LẠI, dùng bounding box của vòng tường tương ứng `max_order`,
        MỞ RỘNG THÊM 16px mỗi cạnh (đủ bao trọn tâm ô chứa chính bức tường,
        nhưng CHƯA đủ để lọt sang ô field kế tiếp cách 64px — biên an toàn
        có chủ đích).
        """
        boxes = getattr(WorldQuery, '_zone_boxes', {})
        if not boxes:
            return None

        def _get_outermost_box(x, y):
            """Tìm vòng tường NGOÀI CÙNG (theo thứ tự sina→rose→maria) mà
            (x,y) nằm trong (nới rộng 64px mỗi cạnh) — 'field' nếu không
            khớp vòng nào (ở ngoài mọi bức tường)."""
            for z in ['sina', 'rose', 'maria']:
                if z in boxes:
                    l, t, r, b = boxes[z]
                    if l - 64 <= x <= r + 64 and t - 64 <= y <= b + 64:
                        return z
            return 'field'
            
        sz = _get_outermost_box(sx, sy)
        tz = _get_outermost_box(tx, ty)
        
        order = {'sina': 1, 'rose': 2, 'maria': 3, 'field': 4}
        max_order = max(order[sz], order[tz])
        
        if max_order == 4:
            return None
            
        target_z = 'sina' if max_order == 1 else 'rose' if max_order == 2 else 'maria'
        l, t, r, b = boxes[target_z]
        # Mở rộng đúng 16px ra phía ngoài để bao trọn nốt tâm của ô chứa tường,
        # nhưng tuyệt đối không cho phép lọt sang ô ngoài Field (cách đó 64px)
        return (l - 16.0, t - 16.0, r + 16.0, b + 16.0)

    @classmethod
    def find_path(cls, sx: float, sy: float, tx: float, ty: float,
                  radius: float = 16.0, buffer: float = 12.0) -> list[tuple[float, float]]:
        """API công khai — tìm đường từ (sx,sy) tới (tx,ty), trả list
        waypoint (px) đã VUỐT MƯỢT (không phải từng ô lưới thô).

        Thuật toán 2 tầng: (1) thử tìm trong phạm vi thu hẹp bởi
        `_get_search_bounds()` (nhanh, đủ cho ca thường gặp); (2) nếu KHÔNG
        tìm được đường thật (kết quả chỉ là fallback 1-điểm-đích, nghĩa là
        A* bị giới hạn quá chặt bởi bounds) → CHẠY LẠI không giới hạn
        (`bounds=None`) trên toàn bản đồ — chấp nhận chậm hơn để tìm được
        đường vòng xa khi cần.
        """
        bounds = cls._get_search_bounds(sx, sy, tx, ty)
        if bounds:
            # Ưu tiên tìm trong vùng giới hạn (cùng vùng hoặc xuyên vùng gần nhất)
            path = cls._internal_find_path(sx, sy, tx, ty, radius, buffer, bounds)
            # Nếu tìm thấy đường (không phải trả về fallback 1 điểm đích), thì dùng
            if not (len(path) == 1 and path[0] == (float(tx), float(ty))):
                return path
                
        # Fallback: Chạy bình thường toàn bản đồ (tìm đường vòng, xuyên vùng xa)
        return cls._internal_find_path(sx, sy, tx, ty, radius, buffer, None)

    @classmethod
    def _internal_find_path(cls, sx: float, sy: float, tx: float, ty: float,
                  radius: float = 16.0, buffer: float = 12.0, bounds: tuple = None) -> list[tuple[float, float]]:
        """
        Tìm đường A* dựa trên grid. Chỉ dùng cho lính khi được lệnh chuyển tháp (cự ly xa).
        Dùng tường (và buffer) làm vật cản.
        """
        # Lính đi trong cùng 1 vùng (cùng Zone), chỉ cần đi vòng qua tường
        # Không cần chui lỗ hẹp nên dùng nguyên bán kính an toàn (bao gồm buffer)
        check_radius = radius + buffer
        
        start_cell = cls.get_cell(sx, sy)
        target_cell = cls.get_cell(tx, ty)

        # Nếu chung 1 ô lưới, đi thẳng
        if start_cell == target_cell:
            return [(float(tx), float(ty))]

        open_set = []
        heapq.heappush(open_set, (0, start_cell))
        
        came_from = {}
        g_score = {start_cell: 0}
        
        # Giới hạn số bước duyệt: Bản đồ 170x136 = 23120 ô
        # Tăng lên 30000 để đảm bảo tìm được đường đi vòng quanh tường dài
        max_iterations = 30000
        iterations = 0

        while open_set and iterations < max_iterations:
            iterations += 1
            current = heapq.heappop(open_set)[1]

            if current == target_cell:
                path = []
                while current in came_from:
                    path.append(current)
                    current = came_from[current]
                path.reverse()
                # Vuốt đường (smoothing) để loại bỏ các điểm thừa (zigzag grid)
                return cls.smooth_path(sx, sy, tx, ty, path, check_radius)

            cx, cy = current
            
            # 8 hướng di chuyển (thẳng và chéo)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                neighbor = (cx + dx, cy + dy)
                
                px = neighbor[0] * cls.CELL_SIZE + cls.CELL_SIZE / 2
                py = neighbor[1] * cls.CELL_SIZE + cls.CELL_SIZE / 2
                
                # Check giới hạn khu vực (nếu có)
                if bounds:
                    if not (bounds[0] <= px <= bounds[2] and bounds[1] <= py <= bounds[3]):
                        continue
                        
                # Chi phí di chuyển chéo đắt hơn
                move_cost = 1.414 if dx != 0 and dy != 0 else 1.0
                tentative_g_score = g_score[current] + move_cost
                
                if tentative_g_score < g_score.get(neighbor, float('inf')):
                    # Kiểm tra xem ô neighbor có tường không
                    px = neighbor[0] * cls.CELL_SIZE + cls.CELL_SIZE / 2
                    py = neighbor[1] * cls.CELL_SIZE + cls.CELL_SIZE / 2
                    
                    # Ngoại lệ: Cho phép các ô nằm sát điểm bắt đầu và điểm đích (bán kính 120px) 
                    # được phép đi qua dù bị tường chặn. Vì tháp (đích) có thể nằm sâu trong tường,
                    dist_to_target = math.hypot(px - tx, py - ty)
                    dist_to_start = math.hypot(px - sx, py - sy)
                    
                    is_special = (dist_to_target < 150.0) or (dist_to_start < 150.0)
                    
                    if is_special or not WorldQuery.is_wall_blocked(px, py, radius=check_radius):
                        came_from[neighbor] = current
                        g_score[neighbor] = tentative_g_score
                        # Heuristic: Khoảng cách đường chim bay đến đích
                        hx, hy = target_cell
                        f_score = tentative_g_score + math.hypot(neighbor[0] - hx, neighbor[1] - hy)
                        heapq.heappush(open_set, (f_score, neighbor))
                        
        # Fallback: Không tìm được đường (hoặc quá xa), trả về đích luôn để lính tự trượt
        return [(float(tx), float(ty))]

    @classmethod
    def line_of_sight_grid(cls, cell1: tuple[int, int], cell2: tuple[int, int], check_radius: float) -> bool:
        """Kiểm tra Line-of-Sight cực nhanh bằng thuật toán Bresenham trên Grid."""
        x0, y0 = cell1
        x1, y1 = cell2
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        x, y = x0, y0
        n = 1 + dx + dy
        x_inc = 1 if x1 > x0 else -1
        y_inc = 1 if y1 > y0 else -1
        error = dx - dy
        dx *= 2
        dy *= 2
        
        for _ in range(n):
            px = x * cls.CELL_SIZE + cls.CELL_SIZE / 2
            py = y * cls.CELL_SIZE + cls.CELL_SIZE / 2
            # Nếu là ô đích hoặc ô bắt đầu thì bỏ qua check
            if (x, y) == cell1 or (x, y) == cell2:
                pass
            elif WorldQuery.is_wall_blocked(px, py, radius=check_radius):
                return False
                
            if error > 0:
                x += x_inc
                error -= dy
            else:
                y += y_inc
                error += dx
        return True

    @classmethod
    def smooth_path(cls, sx: float, sy: float, tx: float, ty: float, 
                    cell_path: list[tuple[int, int]], check_radius: float) -> list[tuple[float, float]]:
        """Vuốt đường (Path Smoothing) loại bỏ các điểm không cần thiết."""
        if not cell_path or len(cell_path) <= 1:
            return [(float(tx), float(ty))]
            
        smoothed_cells = [cls.get_cell(sx, sy)]
        current_idx = 0
        
        while current_idx < len(cell_path) - 1:
            furthest_visible = current_idx + 1
            # Tìm điểm xa nhất có thể nhìn thấy (Line of sight)
            for j in range(len(cell_path) - 1, current_idx, -1):
                if cls.line_of_sight_grid(smoothed_cells[-1], cell_path[j], check_radius):
                    furthest_visible = j
                    break
            smoothed_cells.append(cell_path[furthest_visible])
            current_idx = furthest_visible
            
        # Chuyển cells về tọa độ thế giới (lấy tâm ô)
        waypoints = []
        for cell in smoothed_cells[1:]:
            px = cell[0] * cls.CELL_SIZE + cls.CELL_SIZE / 2
            py = cell[1] * cls.CELL_SIZE + cls.CELL_SIZE / 2
            waypoints.append((px, py))
            
        # Ghi đè điểm cuối cùng bằng điểm target chính xác
        waypoints[-1] = (float(tx), float(ty))
        return waypoints
