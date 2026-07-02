import pygame
import random
import os
from core.entity import Entity
from core.game_state import ResourceBundle

# --- CẤU HÌNH TỶ LỆ RỚT ĐỒ (LOOT TABLE) ---
# Format: { 'Tên_Class_Titan': [('tên_biến_vật_phẩm', xác_suất_rớt), ...] }
# Bạn có thể chỉnh sửa tự do bảng này. Hệ thống sẽ tự động bắt lấy thông số.
LOOT_TABLE = {
    'Titan': [('ore', 0.5), ('wood', 0.4), ('stone', 0.4)],  # Mặc định cho class Titan gốc
    'RegularTitan': [('ore', 0.6), ('gas', 0.2)],
    'ArmoredTitan': [('anti_armor_ore', 0.5), ('stone', 0.8), ('serum', 0.1)],
    'ColossalTitan': [('fire_ore', 0.8), ('serum', 0.5), ('titan_pheromone', 0.2)],
    'BeastTitan': [('titan_pheromone', 1.0), ('acid_ore', 0.5), ('wood', 0.8)],
    'FoundingTitan': [('serum', 1.0), ('titan_pheromone', 1.0), ('electric_ore', 0.8)]
}

class DroppedLoot(Entity):
    """Thực thể rơi trên mặt đất khi Titan chết. Click chuột để nhặt."""
    ENTITY_TYPE = "dropped_loot"
    _images_cache = {}

    def __init__(self, x: float, y: float, item_type: str, amount: int = 1):
        super().__init__(x, y)
        self.item_type = item_type
        self.amount = amount
        self.radius = 20  # Bán kính click chuột

        # Load hình ảnh tự động từ core/resource
        if item_type not in self._images_cache:
            try:
                base_dir = os.path.dirname(os.path.dirname(__file__))
                img_path = os.path.join(base_dir, 'core', 'resource', f'{item_type}.png')
                if os.path.exists(img_path):
                    raw = pygame.image.load(img_path).convert_alpha()
                    self._images_cache[item_type] = pygame.transform.scale(raw, (32, 32))
                else:
                    self._images_cache[item_type] = None
            except pygame.error:
                self._images_cache[item_type] = None
    def update(self, dt: float) -> None:
        pass

    def draw(self, screen):
        img = self._images_cache.get(self.item_type)
        if img:
            rect = img.get_rect(center=(int(self.x), int(self.y)))
            screen.blit(img, rect)
            
            # Draw glow circle behind the item to make it stand out
            import math
            import time
            glow_radius = int(24 + math.sin(time.time() * 5) * 4)
            # Cannot draw with alpha directly using draw.circle without a surface, so just use simple color
            pygame.draw.circle(screen, (255, 215, 0), (int(self.x), int(self.y)), glow_radius, 1)
        else:
            # Placeholder nếu không có hình ảnh
            pygame.draw.circle(screen, (255, 215, 0), (int(self.x), int(self.y)), self.radius)
            pygame.draw.circle(screen, (255, 255, 255), (int(self.x), int(self.y)), self.radius, 1)

class LootSystem:
    """Hệ thống xử lý rơi đồ từ Titan."""
    
    @staticmethod
    def spawn_loot(titan):
        """Được gọi khi Titan chết, dựa vào LOOT_TABLE để rớt đồ."""
        titan_class = type(titan).__name__
        
        # Lấy bảng tỷ lệ, fallback về Titan thường nếu không có tên
        if titan_class not in LOOT_TABLE:
            # Fallback to base class name if possible, or 'Titan'
            if 'Titan' in LOOT_TABLE:
                table = LOOT_TABLE['Titan']
            else:
                table = []
        else:
            table = LOOT_TABLE[titan_class]

        from systems.world_query import WorldQuery
        
        for item_type, prob in table:
            if random.random() <= prob:
                # Lượng rớt ngẫu nhiên từ 1 đến 3
                amount = random.randint(1, 3)
                # Tọa độ rớt ngẫu nhiên quanh xác Titan
                lx = titan.x + random.randint(-50, 50)
                ly = titan.y + random.randint(-50, 50)
                
                loot = DroppedLoot(lx, ly, item_type, amount)
                WorldQuery.spawn_entity(loot)

        # Cấp XP cho Tướng
        xp_table = {
            'Titan': 20,
            'RegularTitan': 25,
            'ArmoredTitan': 50,
            'ColossalTitan': 100,
            'BeastTitan': 80,
            'FoundingTitan': 200,
        }
        xp_reward = xp_table.get(titan_class, 20)
        for cmdr in getattr(WorldQuery, '_f_commanders', []):
            if hasattr(cmdr, 'gain_xp'):
                cmdr.gain_xp(xp_reward)
