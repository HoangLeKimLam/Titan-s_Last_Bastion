"""
exceptions.py — Custom exceptions cho Titan's Last Bastion.

Tại sao cần file này?
    Thay vì raise ValueError("không đủ tài nguyên") rải rác khắp nơi,
    ta dùng exception riêng để:
      - Bắt lỗi chính xác bằng except InsufficientResourceError
      - Thêm thông tin (cần bao nhiêu, có bao nhiêu) vào exception
      - Code dễ debug hơn khi nhìn traceback

Ai dùng file này:
    - ResourceManager  → raise InsufficientResourceError khi spend() không đủ
    - WallSection      → raise WallBreachError khi HP <= 0
    - Bất kỳ caller nào muốn bắt 2 lỗi trên bằng except cụ thể
"""


class InsufficientResourceError(Exception):
    """
    Raise khi người chơi không đủ tài nguyên để thực hiện hành động
    (xây tháp, upgrade, train lính, sửa tường…).

    Attributes:
        resource (str): Tên loại tài nguyên thiếu, vd. 'stone', 'gas'.
        required (int): Lượng cần có.
        available (int): Lượng hiện có trong kho.
        message (str): Mô tả lỗi tự động tạo từ 3 field trên.

    Cách dùng — bên trong ResourceManager.spend():
        if not self.can_afford(cost):
            # Tìm loại tài nguyên đầu tiên bị thiếu
            raise InsufficientResourceError(
                resource='stone',
                required=50,
                available=30,
            )

    Cách bắt lỗi — bên ngoài (UI / Tower placement):
        try:
            resource_manager.spend(tower_cost)
        except InsufficientResourceError as e:
            hud.show_warning(str(e))   # "Thiếu stone: cần 50, có 30"
    """

    def __init__(self, resource: str, required: int, available: int):
        
        """
        Khởi tạo exception với thông tin tài nguyên bị thiếu.

        Args:
            resource  (str): Tên loại tài nguyên, vd. 'stone'.
            required  (int): Lượng cần để thực hiện hành động.
            available (int): Lượng thực tế đang có trong kho.

        Hướng dẫn code:
            Gọi super().__init__(message) để Python in message khi traceback.
            Lưu 3 tham số vào self để caller có thể đọc lại:
                self.resource  = resource
                self.required  = required
                self.available = available
                message = f"Thiếu {resource}: cần {required}, có {available}"
                super().__init__(message)
        """
        self.resource  = resource
        self.required  = required
        self.available = available
        message = f"Thiếu {resource}: cần {required}, có {available}"
        super().__init__(message)
        pass


class WallBreachError(Exception):
    """
    Raise khi một WallSection bị phá hoàn toàn (HP xuống 0 hoặc âm).

    Attributes:
        wall_name (str): Tên vòng tường bị phá, vd. 'Wall Maria'.
        section_id (str): ID của đoạn tường cụ thể bị phá.
        message (str): Mô tả tự động.

    Lưu ý quan trọng:
        Exception này là tuỳ chọn — WallSection đã publish event
        'wall_breached' qua GameEventBus. WallBreachError chỉ raise
        thêm nếu caller cần bắt exception (vd. kiểm thử, logging đặc biệt).
        KHÔNG bắt buộc raise ở mọi nơi.

    Cách dùng — bên trong WallSection.take_damage():
        self._hp -= amount
        if self._hp <= 0:
            self.is_alive = False
            GameEventBus.get_instance().publish('wall_breached', {...})
            raise WallBreachError(
                wall_name='Wall Maria',
                section_id=self.id,
            )

    Cách bắt lỗi:
        try:
            wall_section.take_damage(500, 'ram')
        except WallBreachError as e:
            logger.critical(str(e))
    """

    def __init__(self, wall_name: str, section_id: str):
        """
        Khởi tạo exception với thông tin đoạn tường bị phá.

        Args:
            wall_name  (str): Tên vòng tường, vd. 'Wall Maria'.
            section_id (str): ID đoạn tường, vd. 'maria_section_3'.

        Hướng dẫn code:
            self.wall_name  = wall_name
            self.section_id = section_id
            message = f"{wall_name} (section {section_id}) đã bị phá!"
            super().__init__(message)
        """
        self.wall_name  = wall_name
        self.section_id = section_id
        message = f"{wall_name} (section {section_id}) đã bị phá!"
        super().__init__(message)
        pass
