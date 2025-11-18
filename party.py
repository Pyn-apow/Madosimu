# party.py
# party.py - パーティ編成UIとバトルデータ生成 (GUIバトル設定付き)

from __future__ import annotations
from typing import List, Optional, Dict, Any, Sequence, Tuple
import json
import pygame
import sys
import os
import subprocess
import time 

# --- 定数 ---
SCREEN_WIDTH = 1000 
SCREEN_HEIGHT = 600
BG_COLOR = (30, 30, 60)
SLOT_COLOR = (50, 50, 90)
EMPTY_SLOT_COLOR = (40, 40, 70)
SELECT_COLOR = (255, 255, 0)
FONT_COLOR = (255, 255, 255)
DETAIL_BG_COLOR = (40, 40, 80)
DETAIL_BORDER_COLOR = (70, 70, 140)

# --- UI要素の寸法と配置 ---
CARD_W, CARD_H = 120, 150
PADDING = 20
PARTY_SLOT_COUNT = 5

DETAIL_AREA_WIDTH = 280 
DETAIL_AREA_X = SCREEN_WIDTH - DETAIL_AREA_WIDTH - PADDING
DETAIL_AREA_Y = PADDING
DETAIL_AREA_RECT = pygame.Rect(DETAIL_AREA_X, DETAIL_AREA_Y, DETAIL_AREA_WIDTH, SCREEN_HEIGHT - PADDING * 2)

ROSTER_START_X = 50
ROSTER_START_Y = 280
ROSTER_AREA_W = DETAIL_AREA_X - ROSTER_START_X - PADDING # 控えエリアの描画幅
ROSTER_AREA_H = SCREEN_HEIGHT - ROSTER_START_Y - PADDING
ROSTER_AREA_RECT = pygame.Rect(ROSTER_START_X, ROSTER_START_Y, ROSTER_AREA_W, ROSTER_AREA_H)

ROSTER_PADDING = 10 # 控えリスト内のパディング
ROSTER_PER_ROW = (ROSTER_AREA_W - ROSTER_PADDING) // (CARD_W + ROSTER_PADDING)
ROSTER_ROW_HEIGHT = CARD_H + ROSTER_PADDING

# スクロール関連
SCROLL_MAX = 0 
ROSTER_SCROLL_OFFSET_Y = 0 # 縦方向のスクロールオフセット (負の値)
SCROLL_SPEED = 20 # ホイール一回での移動量

# --- バトルボタン、ソートボタンの位置 ---
BATTLE_BUTTON_RECT = pygame.Rect(SCREEN_WIDTH - 200 - 250, 20, 150, 40) 

ROSTER_SORT_KEYS = ["name", "atk", "hp", "defense", "speed", "rarity"] # ソートキー拡張
SORT_BUTTONS: Dict[str, pygame.Rect] = {}
BUTTON_W, BUTTON_H = 80, 30
button_start_x = ROSTER_START_X
button_y = 235

for i, key in enumerate(ROSTER_SORT_KEYS):
    x = button_start_x + i * (BUTTON_W + 10)
    if x + BUTTON_W > DETAIL_AREA_X - PADDING: # 詳細エリアと衝突しないように
        break
    SORT_BUTTONS[key] = pygame.Rect(x, button_y, BUTTON_W, BUTTON_H)

# --- 色とフォント (省略) ---

ROLE_COLORS = {
    "Buffer": (100, 100, 255), "Attacker": (255, 100, 100),
    "Healer": (100, 255, 100), "Default": (150, 150, 150),
    "Monster": (255, 150, 50), 
}
SKILL_ICON_COLORS = {
    "通常攻撃": (100, 100, 100), 
    "戦闘スキル": (50, 150, 255), 
    "必殺技": (200, 50, 255),    
    "アビリティ": (255, 200, 50), 
    "skill": (50, 150, 255), 
    "ability": (255, 200, 50), 
}
ELEMENT_COLORS: Dict[str, Tuple[int, int, int]] = {
    "無": (180, 180, 180),   
    "火": (255, 100, 100),   
    "水": (100, 150, 255),   
    "木": (100, 200, 100),   
    "光": (255, 255, 150),   
    "闇": (100, 50, 150),    
    "?": (150, 150, 150),    
}

# ---- ユーティリティ: 技・アビリティのフォーマットの補助関数 ----
def make_action(name: str, typ: str = "skill", power: float = 0.0, desc: str = "", 
                break_gauge: float = 0.0, element: str = "?", 
                meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """技／アビリティを統一フォーマットの辞書で作る簡易関数。"""
    return {
        "name": str(name),
        "type": str(typ),
        "power": float(power),
        "desc": str(desc),
        "break_gauge": float(break_gauge),
        "element": str(element),
        "meta": dict(meta) if meta else {},
    }
    
# ---- Characterクラス ----
class Character:
    # ... (Characterクラスの定義は元のまま) ...
    """キャラクターのデータコンテナ（統一フォーマット）"""
    _next_cid = 0
    def __init__(
        self,
        name: str,
        rarity: str = "?",
        element: str = "?",
        role: str = "?",
        hp: float = 0.0,
        atk: float = 0.0,
        defense: float = 0.0,
        speed: float = 0.0,
        ultimate: Optional[Sequence[Dict[str, Any]]] = None,
        battle_skills: Optional[Sequence[Dict[str, Any]]] = None,
        normal_attack: Optional[Sequence[Dict[str, Any]]] = None,
        abilities: Optional[Sequence[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.cid = Character._next_cid
        Character._next_cid += 1
        self.name = str(name)
        self.rarity = str(rarity)
        self.element = str(element)
        self.role = str(role)
        self.hp = float(hp)
        self.atk = float(atk)
        self.defense = float(defense)
        self.speed = float(speed)
        self.ultimate: List[Dict[str, Any]] = list(ultimate) if ultimate else []
        self.battle_skills: List[Dict[str, Any]] = list(battle_skills) if battle_skills else []
        self.normal_attack: List[Dict[str, Any]] = list(normal_attack) if normal_attack else []
        self.abilities: List[Dict[str, Any]] = list(abilities) if abilities else []
        self.metadata: Dict[str, Any] = dict(metadata) if metadata else {}
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cid": self.cid, "name": self.name, "rarity": self.rarity,
            "element": self.element, "role": self.role, "hp": self.hp,
            "atk": self.atk, "defense": self.defense, "speed": self.speed,
            "ultimate": list(self.ultimate), "battle_skills": list(self.battle_skills),
            "normal_attack": list(self.normal_attack), "abilities": list(self.abilities),
            "metadata": dict(self.metadata),
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        """JSONデータからCharacterオブジェクトを生成 (スキルロードにヘルパー関数を使用)"""
        return cls(
            name=data.get("name", ""), rarity=data.get("rarity", ""),
            element=data.get("element", ""), role=data.get("role", ""),
            hp=float(data.get("hp", 0.0)), atk=float(data.get("atk", 0.0)),
            defense=float(data.get("defense", 0.0)), speed=float(data.get("speed", 0.0)),
            # スキルリストはヘルパー関数で処理し、新しいキーに対応
            ultimate=[cls._load_skill_action(a) for a in data.get("ultimate", [])],
            battle_skills=[cls._load_skill_action(a) for a in data.get("battle_skills", [])],
            normal_attack=[cls._load_skill_action(a) for a in data.get("normal_attack", [])],
            abilities=[cls._load_skill_action(a) for a in data.get("abilities", [])],
            metadata=data.get("metadata", {}),
        )
        
    @staticmethod
    def _load_skill_action(action_data: Dict[str, Any]) -> Dict[str, Any]:
        """スキルデータ辞書をmake_action形式に変換するヘルパー関数"""
        return make_action(
            name=action_data.get("name", ""),
            typ=action_data.get("type", "skill"),
            power=action_data.get("power", 0.0),
            desc=action_data.get("desc", ""),
            break_gauge=action_data.get("break_gauge", 0.0), 
            element=action_data.get("element", "?"),       
            meta=action_data.get("meta", {}),
        )
        
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
    @classmethod
    def from_json(cls, s: str) -> "Character":
        return cls.from_dict(json.loads(s))
    def update_stat(self, key: str, value: Any) -> None:
        if key == "def" or key == "def_": key = "defense"
        if hasattr(self, key): setattr(self, key, value)
        else: self.metadata[key] = value
    def __repr__(self) -> str:
        return (
            f"Character(cid={self.cid}, name={self.name}, rarity={self.rarity}, "
            f"hp={self.hp}, atk={self.atk}, speed={self.speed})"
        )


# ----------------------------------------------------------------------
# ▼▼▼ バトルシミュレーション用 敵ユニット初期化関数 ▼▼▼
# ----------------------------------------------------------------------

def make_dummy_enemy(name: str, element: str, base_hp: float, base_atk: float, base_def: float, base_speed: float) -> Character:
    """敵ユニットのダミーデータを生成するヘルパー関数"""
    return Character(
        name=name, element=element, role="Monster", 
        hp=base_hp, atk=base_atk, defense=base_def, speed=base_speed, 
        normal_attack=[make_action("攻撃", power=1.0, break_gauge=20.0, element=element)],
        battle_skills=[make_action("強攻撃", typ="戦闘スキル", power=1.5, break_gauge=35.0, element=element, meta={"cost_mp": 50.0})],
        ultimate=[make_action("必殺技", typ="必殺技", power=3.0, break_gauge=60.0, element=element, meta={"cost_mp": 100.0})],
    )

def initialize_units(num_enemies: int, enemy_level: int) -> List[Character]:
    """
    指定された敵の数とレベルに基づき、敵ユニットを生成する。
    """
    
    # 敵の基本ステータスをレベルに基づいて設定
    base_hp = 300 + enemy_level * 70
    base_atk = 60 + enemy_level * 15
    base_def = 30 + enemy_level * 5
    base_speed = 70 + enemy_level * 5

    enemies: List[Character] = []
    enemy_names = ["Goblin", "Slime", "Orc", "Demon"]
    enemy_elements = ["火", "水", "木", "闇"]
    
    # 最大4体に制限
    for i in range(min(num_enemies, 4)):
        enemy = make_dummy_enemy(
            name=f"{enemy_names[i % len(enemy_names)]} L{enemy_level}", 
            element=enemy_elements[i % len(enemy_elements)], 
            base_hp=base_hp, 
            base_atk=base_atk, 
            base_def=base_def,
            base_speed=base_speed
        )
        enemies.append(enemy)
        
    return enemies

# ----------------------------------------------------------------------
# Partyクラス
# ----------------------------------------------------------------------
class Party:
    SLOT_COUNT = 5 
    # ... (Partyクラスの定義は元のまま) ...
    def __init__(self):
        self._slots: List[Optional[Character]] = [None] * self.SLOT_COUNT
    def set_character(self, slot_index: int, char: Optional[Character]) -> Optional[Character]:
        if not (0 <= slot_index < self.SLOT_COUNT):
            return None
        old_char_in_slot = self._slots[slot_index]
        self._slots[slot_index] = char
        return old_char_in_slot
    def get_character(self, slot_index: int) -> Optional[Character]:
        if 0 <= slot_index < self.SLOT_COUNT:
            return self._slots[slot_index]
        return None
    def remove_by_cid(self, cid: int) -> Optional[Character]:
        for i, char in enumerate(self._slots):
            if char and char.cid == cid:
                self._slots[i] = None
                return char
        return None
    def members(self) -> List[Character]:
        return [m for m in self._slots if m is not None]
    def slots(self) -> List[Optional[Character]]:
        return self._slots
    def __len__(self) -> int:
        return len(self.members())
    def __repr__(self) -> str:
        return f"Party(slots={self._slots})"
    def to_list(self) -> List[Optional[Dict[str, Any]]]:
        return [m.to_dict() if m else None for m in self._slots]
    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_list(), f, ensure_ascii=False, indent=2)
    @classmethod
    def load_json(cls, path: str) -> "Party":
        new_party = cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data_list = json.load(f)
            for i, data in enumerate(data_list):
                if i >= cls.SLOT_COUNT: break
                if data: new_party._slots[i] = Character.from_dict(data)
                else: new_party._slots[i] = None
        except FileNotFoundError:
            print(f"警告: ファイル {path} が見つかりませんでした。新しいPartyを作成します。")
        except json.JSONDecodeError:
            print(f"エラー: ファイル {path} のJSON形式が不正です。新しいPartyを作成します。")
            print("JSONエラーが発生しました。カンマ忘れや、meta内の無効な記述を確認してください。")
        return new_party


# --- アセット（素材）の読み込み ---
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Magia Exedra - パーティ編成 (5枠・DnD式・GUI設定)")
clock = pygame.time.Clock()

font_path = "noto.ttf" # 日本語フォント
# ... (フォントロード部分は元のまま) ...
try:
    font_l = pygame.font.Font(font_path, 30) 
    font_m = pygame.font.Font(font_path, 24)
    font_s = pygame.font.Font(font_path, 18)
    font_xs = pygame.font.Font(font_path, 14)
except OSError:
    print(f"警告: フォント '{font_path}' が見つかりません。デフォルトフォントを使用します。")
    try:
        if os.name == 'nt': # Windows
            sys_font_path = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'meiryo.ttc')
            font_l = pygame.font.Font(sys_font_path, 30)
            font_m = pygame.font.Font(sys_font_path, 24)
            font_s = pygame.font.Font(sys_font_path, 18)
            font_xs = pygame.font.Font(sys_font_path, 14)
            print("代わりにメイリオフォントを使用します。")
        else:
            font_l = pygame.font.Font(None, 36)
            font_m = pygame.font.Font(None, 30)
            font_s = pygame.font.Font(None, 24)
            font_xs = pygame.font.Font(None, 20)
    except Exception as e:
        print(f"システムフォントの読み込みにも失敗: {e}")
        font_l = pygame.font.Font(None, 36)
        font_m = pygame.font.Font(None, 30)
        font_s = pygame.font.Font(None, 24)
        font_xs = pygame.font.Font(None, 20)


# ======================================================================
# 初期データ作成
# ======================================================================

def load_roster_from_json(filename="characters.json") -> List[Character]:
    """外部JSONファイルから控えキャラクターリストをロードする"""
    character_list: List[Character] = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data_list = json.load(f)
            
        if not isinstance(data_list, list):
            print(f"エラー: {filename} の形式が不正です。リスト形式である必要があります。")
            return []
            
        for char_data in data_list:
            try:
                character_list.append(Character.from_dict(char_data))
            except Exception as e:
                print(f"キャラクターデータのロード中にエラー: {e} (データ: {char_data})")
                
    except FileNotFoundError:
        print(f"警告: {filename} が見つかりません。空の控えリストで開始します。")
    except json.JSONDecodeError:
        print(f"エラー: {filename} のJSON形式が不正です。空の控えリストで開始します。")
        print("JSONエラーが発生しました。カンマ忘れや、meta内の無効な記述を確認してください。")
        
    return character_list

# 外部JSONから控えキャラクターをロード
roster: List[Character] = load_roster_from_json("characters.json")

if not roster:
    print("警告: 控えキャラクターがロードできませんでした (characters.json を確認してください)。")

# パーティ編成 (5枠のスロット式 Party クラスを使用)
party = Party()


# ----------------------------------------------------------------------
# バトルデータ保存 (元のまま)
# ----------------------------------------------------------------------
def save_party_data_for_battle(party_members: List[Character], num_enemies: int, enemy_level: int, filename="battle_data.json"):
    """
    パーティメンバーと、指定されたパラメータで生成した敵ユニットをJSONに保存する。
    """
    party_to_save = party_members[:5] 
    data_to_save = [char.to_dict() for char in party_to_save if char is not None]
    
    # パラメータで敵を生成
    enemies: List[Character] = initialize_units(num_enemies, enemy_level)
    enemies_to_save = [char.to_dict() for char in enemies] 
    
    final_data = {
        "party": data_to_save,
        "enemies": enemies_to_save
    }
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"データ保存エラー: {e}")

def remove_battle_data(filename="battle_data.json"):
    try:
        if os.path.exists(filename):
            os.remove(filename)
    except Exception as e:
        print(f"バトルデータファイルの削除に失敗: {e}")


# --- 描画用のヘルパー関数 (元のまま) ---

def draw_character_card(surface: pygame.Surface, char: Character, rect: pygame.Rect, highlight: bool):
    # カードの背景
    pygame.draw.rect(surface, SLOT_COLOR, rect)
    # レアリティの枠線 (例として金色の枠)
    if char.rarity == "5": 
        pygame.draw.rect(surface, (255, 215, 0), rect, 3) 
    elif highlight:
        pygame.draw.rect(surface, SELECT_COLOR, rect, 3)
    else:
        pygame.draw.rect(surface, (70, 70, 100), rect, 1) 

    # キャラクター名
    name_text = font_s.render(char.name, True, FONT_COLOR)
    name_rect = name_text.get_rect(centerx=rect.centerx, y=rect.y + 10)
    surface.blit(name_text, name_rect)

    # ロール（役割）表示
    role_color = ROLE_COLORS.get(char.role, ROLE_COLORS["Default"])
    role_text = font_xs.render(f"ロール: {char.role}", True, role_color)
    role_rect = role_text.get_rect(midtop=(rect.centerx, name_rect.bottom + 5))
    surface.blit(role_text, role_rect)

    # 簡易ステータス
    atk_text = font_xs.render(f"ATK:{int(char.atk)}", True, FONT_COLOR)
    hp_text = font_xs.render(f"HP:{int(char.hp)}", True, FONT_COLOR)
    speed_text = font_xs.render(f"SPD:{int(char.speed)}", True, FONT_COLOR)

    # 配置を調整
    atk_rect = atk_text.get_rect(left=rect.x + 10, y=role_rect.bottom + 10)
    hp_rect = hp_text.get_rect(right=rect.right - 10, y=role_rect.bottom + 10)
    speed_rect = speed_text.get_rect(centerx=rect.centerx, y=atk_rect.bottom + 5)
    
    surface.blit(atk_text, atk_rect)
    surface.blit(hp_text, hp_rect)
    surface.blit(speed_text, speed_rect)


def draw_empty_slot(surface: pygame.Surface, rect: pygame.Rect, highlight: bool):
    if highlight:
        pygame.draw.rect(surface, SELECT_COLOR, rect, 3)
    else:
        pygame.draw.rect(surface, EMPTY_SLOT_COLOR, rect, 2)
    text = font_m.render("+", True, (100, 100, 150))
    text_rect = text.get_rect(center=rect.center)
    surface.blit(text, text_rect)


# スキル詳細を描画するヘルパー関数
def draw_skill_detail(surface: pygame.Surface, skill_data: Dict[str, Any], x: int, y: int):
    # スキルアイコン (円形)
    icon_color = SKILL_ICON_COLORS.get(skill_data.get("type", "skill"), SKILL_ICON_COLORS["skill"])
    pygame.draw.circle(surface, icon_color, (x + 15, y + 15), 12)
    pygame.draw.circle(surface, (255, 255, 255), (x + 15, y + 15), 12, 1) 

    # スキル名
    name_text = font_s.render(skill_data["name"], True, FONT_COLOR)
    surface.blit(name_text, (x + 40, y + 5))

    # 説明文
    desc_text = font_xs.render(skill_data.get("desc", ""), True, (200, 200, 200))
    surface.blit(desc_text, (x + 40, y + 25))

    # 詳細情報（簡略化）
    info_y = y + 45
    info_parts = []
    if skill_data.get("power", 0) > 0:
        info_parts.append(f"威力:{skill_data['power']:.0f}")
    if skill_data.get("break_gauge", 0) > 0:
        info_parts.append(f"ブレイク:{skill_data['break_gauge']:.0f}")
    if skill_data.get("element", "?") != "?":
        info_parts.append(f"属性:{skill_data['element']}")
    
    # meta情報からの追加
    meta = skill_data.get("meta", {})
    if meta.get("target"):
        info_parts.append(f"対象:{meta['target']}")
    if meta.get("magic_increase", 0) > 0:
        info_parts.append(f"魔力+{meta['magic_increase']:.0f}")

    info_text = font_xs.render(" ".join(info_parts), True, (180, 180, 255))
    surface.blit(info_text, (x + 5, info_y))
    info_y += 20 

    # バフ/デバフ表示
    buff_debuffs = meta.get("buff_debuffs", [])
    for bd in buff_debuffs:
        bd_type = bd.get("type", "")
        bd_amount = bd.get("amount")
        bd_duration = bd.get("duration")
        
        bd_str = bd_type
        if bd_amount is not None:
            if isinstance(bd_amount, float):
                if bd_amount == int(bd_amount): 
                    bd_str += f" ({int(bd_amount * 100)}%)" if bd_amount <= 1 else f" ({int(bd_amount)})"
                else: 
                    bd_str += f" ({bd_amount*100:.0f}%)" if bd_amount <= 1 else f" ({bd_amount:.2f})"
            else:
                bd_str += f" ({bd_amount})"
        if bd_duration is not None:
            if bd_duration == -1: bd_str += " (永続)"
            elif bd_duration > 0: bd_str += f" ({bd_duration}T)"
        
        bd_text = font_xs.render(f"- {bd_str}", True, (200, 255, 200) if "UP" in bd_type else (255, 200, 200))
        surface.blit(bd_text, (x + 10, info_y))
        info_y += 18
    return info_y 

def draw_battle_button(surface):
    pygame.draw.rect(surface, (0, 150, 0), BATTLE_BUTTON_RECT, border_radius=5)
    text = font_m.render("▶ バトル開始", True, FONT_COLOR)
    text_rect = text.get_rect(center=BATTLE_BUTTON_RECT.center)
    surface.blit(text, text_rect)

# ----------------------------------------------------------------------
# ▼▼▼ GUI バトル設定関連関数 (元のまま) ▼▼▼
# ----------------------------------------------------------------------

# ... (get_setting_button_rect, draw_setting_control, draw_battle_settings, update_setting_value は元のまま) ...
def get_setting_button_rect(key: str, control_type: str = "") -> pygame.Rect:
    """設定ポップアップ内のボタンの位置を返す"""
    rect = SETTING_RECT
    if key == "confirm":
        # 決定ボタン
        return pygame.Rect(rect.x + (SETTING_W - 100) // 2, rect.y + SETTING_H - 45, 100, 30)
    
    # 増減ボタン (control_type: num_enemies or enemy_level)
    y_offset = rect.y + 50 if control_type == "num_enemies" else rect.y + 90
    
    if key == "minus":
        return pygame.Rect(rect.x + 150, y_offset, 30, 30)
    elif key == "plus":
        return pygame.Rect(rect.x + 250, y_offset, 30, 30)
    elif key == "display":
        return pygame.Rect(rect.x + 185, y_offset, 60, 30)
    
    return pygame.Rect(0, 0, 0, 0)

def draw_setting_control(surface, control_type: str, x: int, y: int):
    """増減コントロールを描画する"""
    value = battle_settings[control_type]
    
    minus_rect = get_setting_button_rect("minus", control_type)
    plus_rect = get_setting_button_rect("plus", control_type)
    display_rect = get_setting_button_rect("display", control_type)
    
    # マイナスボタン
    pygame.draw.rect(surface, (200, 50, 50), minus_rect, border_radius=5)
    surface.blit(font_m.render("-", True, FONT_COLOR), font_m.render("-", True, FONT_COLOR).get_rect(center=minus_rect.center))

    # プラスボタン
    pygame.draw.rect(surface, (50, 200, 50), plus_rect, border_radius=5)
    surface.blit(font_m.render("+", True, FONT_COLOR), font_m.render("+", True, FONT_COLOR).get_rect(center=plus_rect.center))
    
    # 値表示
    pygame.draw.rect(surface, (30, 30, 60), display_rect, border_radius=5)
    value_text = font_m.render(str(value), True, SELECT_COLOR)
    surface.blit(value_text, value_text.get_rect(center=display_rect.center))

def draw_battle_settings(surface):
    """バトル設定ポップアップを描画する"""
    rect = SETTING_RECT
    
    # ポップアップ背景 (半透明の暗い色)
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 150)) # 黒の半透明
    surface.blit(overlay, (0, 0))

    # 設定ウィンドウ本体
    pygame.draw.rect(surface, (50, 50, 100), rect, border_radius=10)
    pygame.draw.rect(surface, (100, 100, 200), rect, 3, border_radius=10)
    
    # タイトル
    title = font_m.render("バトル設定", True, FONT_COLOR)
    surface.blit(title, title.get_rect(centerx=rect.centerx, y=rect.y + 15))
    
    x_start = rect.x + 30
    
    # 敵の数設定
    num_text = font_s.render("敵の数 (1~4):", True, FONT_COLOR)
    surface.blit(num_text, (x_start, rect.y + 55))
    draw_setting_control(surface, "num_enemies", x_start + 150, rect.y + 50)
    
    # 敵のレベル設定
    level_text = font_s.render("敵のレベル (1~10):", True, FONT_COLOR)
    surface.blit(level_text, (x_start, rect.y + 95))
    draw_setting_control(surface, "enemy_level", x_start + 150, rect.y + 90)
    
    # 決定ボタン
    button_rect = get_setting_button_rect("confirm")
    pygame.draw.rect(surface, (0, 180, 0), button_rect, border_radius=5)
    confirm_text = font_m.render("決定", True, FONT_COLOR)
    surface.blit(confirm_text, confirm_text.get_rect(center=button_rect.center))


def update_setting_value(control_type: str, delta: int):
    """設定値を更新する"""
    current_value = battle_settings[control_type]
    if control_type == "num_enemies":
        min_val, max_val = 1, 4
    elif control_type == "enemy_level":
        min_val, max_val = 1, 10
    else:
        return

    new_value = current_value + delta
    battle_settings[control_type] = max(min_val, min(max_val, new_value))


# --- ゲームの状態 (DnD用) ---
dragging_char: Optional[Character] = None
drag_offset: tuple[int, int] = (0, 0)
source_type: Optional[str] = None
source_index: Any = None 
highlighted_slot_index: Optional[int] = None 
selected_char: Optional[Character] = None # 新規: 詳細表示用の選択キャラクター

# 📌 GUIバトル設定用の状態と設定値
battle_settings_mode: bool = False
battle_settings: Dict[str, int] = {
    "num_enemies": 3,   # 1から4
    "enemy_level": 5    # 1から10
}
# 設定ウィンドウの定数
SETTING_W, SETTING_H = 350, 200
SETTING_RECT = pygame.Rect(
    (SCREEN_WIDTH - SETTING_W) // 2, 
    (SCREEN_HEIGHT - SETTING_H) // 2, 
    SETTING_W, SETTING_H
)


# --- ソート用の状態変数 ---
roster_sort_key: str = "name"
roster_sort_reverse: bool = False

# --- 描画とロジックのための位置決め (ROSTER_AREA_RECTの下で定義) ---
party_slot_rects: List[pygame.Rect] = []
total_party_width = (CARD_W * PARTY_SLOT_COUNT) + (PADDING * (PARTY_SLOT_COUNT - 1))
party_start_x = (SCREEN_WIDTH - DETAIL_AREA_WIDTH - total_party_width) // 2 
for i in range(PARTY_SLOT_COUNT):
    x = party_start_x + i * (CARD_W + PADDING)
    rect = pygame.Rect(x, 50, CARD_W, CARD_H)
    party_slot_rects.append(rect)

roster_rects: Dict[int, pygame.Rect] = {}

def find_char_in_roster_by_cid(cid: int) -> Optional[Character]:
    for c in roster:
        if c.cid == cid: return c
    return None

def find_char_in_party_by_cid(cid: int) -> Optional[Character]:
    for c in party.slots():
        if c and c.cid == cid: return c
    return None

# --- スクロール可能なロスター内のカード位置を計算する関数 ---
def get_roster_card_rect(i: int) -> pygame.Rect:
    global ROSTER_SCROLL_OFFSET_Y
    row = i // ROSTER_PER_ROW
    col = i % ROSTER_PER_ROW
    x = ROSTER_START_X + ROSTER_PADDING + col * (CARD_W + ROSTER_PADDING)
    y = ROSTER_START_Y + ROSTER_PADDING + row * ROSTER_ROW_HEIGHT + ROSTER_SCROLL_OFFSET_Y
    return pygame.Rect(x, y, CARD_W, CARD_H)

# --- ソート関数 ---
def sort_roster(key: str, reverse: bool):
    global roster, ROSTER_SCROLL_OFFSET_Y, SCROLL_MAX
    def get_sort_value(char: Character):
        # 拡張されたソートキーに対応
        if key == "rarity":
            return int(char.rarity) if char.rarity.isdigit() else 0
        return getattr(char, key, char.name) 
    try:
        roster.sort(key=get_sort_value, reverse=reverse)
    except AttributeError as e:
        print(f"エラー: ソート中に属性エラーが発生しました: {e}")
        roster.sort(key=lambda char: char.name, reverse=False)
    update_roster_data()
    
# --- ロスターデータ（Rects、スクロール最大値）を更新する関数 ---
def update_roster_data():
    global roster_rects, SCROLL_MAX, ROSTER_SCROLL_OFFSET_Y
    roster_rects.clear()
    
    num_rows = (len(roster) + ROSTER_PER_ROW - 1) // ROSTER_PER_ROW if len(roster) > 0 else 0
    content_height = num_rows * ROSTER_ROW_HEIGHT + ROSTER_PADDING
    
    # スクロール最大値 (コンテンツの高さ - エリアの高さ)
    SCROLL_MAX = max(0, content_height - ROSTER_AREA_H)
    
    # スクロールオフセットを範囲内に強制
    ROSTER_SCROLL_OFFSET_Y = max(-SCROLL_MAX, min(0, ROSTER_SCROLL_OFFSET_Y))

    # 表示範囲内のRectのみを更新
    for i, char in enumerate(roster):
        rect = get_roster_card_rect(i)
        # スクロール領域外にあるカードはRectを更新しない（描画しない）
        # if ROSTER_AREA_RECT.clipline(rect.x, rect.y, rect.x + rect.width, rect.y + rect.height):
        roster_rects[char.cid] = rect

# 初期ソートを実行
sort_roster(roster_sort_key, roster_sort_reverse)


# --- メインループ ---
if __name__ == "__main__": 
    running = True
    while running:
        
        # 1. イベント処理
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                click_pos = event.pos 
                
                if battle_settings_mode:
                    # バトル設定モード中のクリック処理 (元のまま)
                    if event.button == 1:
                        if get_setting_button_rect("confirm").collidepoint(click_pos):
                            num_enemies = battle_settings["num_enemies"]
                            enemy_level = battle_settings["enemy_level"]
                            active_members = party.members()
                            save_party_data_for_battle(active_members, num_enemies, enemy_level)
                            
                            pygame.quit()
                            try:
                                subprocess.run([sys.executable, "battle_ui.py"], check=True, stdout=sys.stdout, stderr=sys.stderr)
                                remove_battle_data() 
                            except Exception as e:
                                print(f"バトル実行エラー: {e}")
                            
                            pygame.init() 
                            screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
                            pygame.display.set_caption("Magia Exedra - パーティ編成 (5枠・DnD式・GUI設定)")
                            clock = pygame.time.Clock() 
                            try: 
                                font_l = pygame.font.Font(font_path, 30)
                                font_m = pygame.font.Font(font_path, 24)
                                font_s = pygame.font.Font(font_path, 18)
                                font_xs = pygame.font.Font(font_path, 14)
                            except Exception:
                                font_l = pygame.font.Font(None, 36)
                                font_m = pygame.font.Font(None, 30)
                                font_s = pygame.font.Font(None, 24)
                                font_xs = pygame.font.Font(None, 20)
                            
                            battle_settings_mode = False
                            selected_char = None 
                            continue 
                        
                        if get_setting_button_rect("minus", "num_enemies").collidepoint(click_pos):
                            update_setting_value("num_enemies", -1)
                        elif get_setting_button_rect("plus", "num_enemies").collidepoint(click_pos):
                            update_setting_value("num_enemies", 1)
                        elif get_setting_button_rect("minus", "enemy_level").collidepoint(click_pos):
                            update_setting_value("enemy_level", -1)
                        elif get_setting_button_rect("plus", "enemy_level").collidepoint(click_pos):
                            update_setting_value("enemy_level", 1)

                        if not SETTING_RECT.collidepoint(click_pos):
                            battle_settings_mode = False
                            
                    continue 
                
                # 通常モードのクリック処理 (ボタン1/左クリック)
                if event.button == 1:
                    
                    # バトル開始ボタン
                    if BATTLE_BUTTON_RECT.collidepoint(click_pos):
                        active_members = party.members()
                        if not active_members:
                            print("警告: パーティに誰も編成されていません。バトルを開始できません。")
                            continue
                        battle_settings_mode = True
                        continue 

                    # ソートボタン
                    is_button_clicked = False
                    for key, rect in SORT_BUTTONS.items():
                        if rect.collidepoint(click_pos):
                            is_button_clicked = True
                            if roster_sort_key == key:
                                roster_sort_reverse = not roster_sort_reverse
                            else:
                                roster_sort_key = key
                                roster_sort_reverse = False if key in ["name", "hp", "defense", "speed"] else True # 逆順の初期値を調整
                            sort_roster(roster_sort_key, roster_sort_reverse)
                            break 
                    if is_button_clicked: continue 
                    
                    # --- キャラクター選択 / ドラッグ開始 ---
                    selected_char = None # 新しいクリックで選択解除
                    
                    # 1. パーティスロット内のクリック判定
                    for i, rect in enumerate(party_slot_rects):
                        char_in_slot = party.get_character(i)
                        if rect.collidepoint(click_pos):
                            if char_in_slot:
                                # DnD開始 (長押し判定は省略し、すぐにドラッグ可能に)
                                dragging_char = char_in_slot
                                drag_offset = (rect.x - click_pos[0], rect.y - click_pos[1])
                                source_type = 'party'
                                source_index = i 
                                selected_char = char_in_slot # 選択も兼ねる
                            else:
                                # 空スロットをクリックした場合、選択解除（またはスロット選択状態）
                                selected_char = None 
                            break # スロット内をクリックしたらロスターはチェックしない

                    # 2. ロスター内のクリック判定
                    if not dragging_char and ROSTER_AREA_RECT.collidepoint(click_pos):
                        for cid, rect in roster_rects.items():
                            # クリック位置とロスターカードの位置を比較
                            # ロスターカードの位置はスクロールオフセットを考慮済み
                            if rect.collidepoint(click_pos):
                                char_in_roster = find_char_in_roster_by_cid(cid)
                                if char_in_roster:
                                    # DnD開始
                                    dragging_char = char_in_roster
                                    drag_offset = (rect.x - click_pos[0], rect.y - click_pos[1])
                                    source_type = 'roster'
                                    source_index = cid 
                                    selected_char = char_in_roster # 選択も兼ねる
                                    break
                                
                    # どこもクリックしなかった場合
                    if not dragging_char:
                        pass # 詳細表示はそのまま or None (ロスター内もパーティ内もクリックしなかったらそのまま)

                # スクロールホイール処理
                elif event.button == 4 or event.button == 5:
                    if ROSTER_AREA_RECT.collidepoint(click_pos):
                        delta = SCROLL_SPEED if event.button == 4 else -SCROLL_SPEED
                        ROSTER_SCROLL_OFFSET_Y += delta
                        update_roster_data() # スクロールオフセット更新に伴いデータも更新

            # --- ドラッグ中のマウス移動 ---
            if event.type == pygame.MOUSEMOTION and dragging_char and not battle_settings_mode:
                mouse_pos = event.pos
                highlighted_slot_index = None
                for i, rect in enumerate(party_slot_rects):
                    if rect.collidepoint(mouse_pos):
                        highlighted_slot_index = i
                        break

            # --- ドラッグ終了 (マウスリリース) ---
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and dragging_char and not battle_settings_mode:
                drop_pos = event.pos
                target_slot_index: Optional[int] = None
                for i, rect in enumerate(party_slot_rects):
                    if rect.collidepoint(drop_pos):
                        target_slot_index = i
                        break
                
                # パーティスロット内にドロップ
                if target_slot_index is not None:
                    char_to_place = dragging_char 
                    old_char = party.set_character(target_slot_index, char_to_place)
                    
                    if source_type == 'party':
                        # スロット内移動/交換
                        if source_index != target_slot_index:
                            if old_char: party.set_character(source_index, old_char)
                            else: party.set_character(source_index, None)
                    elif source_type == 'roster':
                        # ロスターから編成
                        char_in_roster = find_char_in_roster_by_cid(source_index)
                        if char_in_roster in roster: roster.remove(char_in_roster)
                        if old_char: roster.append(old_char)
                    
                    sort_roster(roster_sort_key, roster_sort_reverse) # ソート＆ロスター位置更新
                
                # パーティスロット外にドロップ (パーティからロスターへ戻す操作)
                elif source_type == 'party':
                    if party.get_character(source_index): # 念のためスロットにまだあるか確認
                        roster.append(dragging_char)
                        party.set_character(source_index, None)
                        sort_roster(roster_sort_key, roster_sort_reverse)
                        
                # ロスターからロスター外へドロップした場合（何もしない）
                
                dragging_char = None
                source_type = None
                source_index = None
                highlighted_slot_index = None
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if battle_settings_mode:
                        battle_settings_mode = False
                    else:
                        running = False

        # 2. ロジック更新
        # ロスター関連データは sort_roster や update_roster_data で更新済み

        # 3. 描画
        screen.fill(BG_COLOR)
        draw_battle_button(screen)
        
        # パーティ編成エリア
        screen.blit(font_m.render("パーティ編成 (5枠)", True, FONT_COLOR), (party_start_x, 10))
        party_slots = party.slots()
        for i, rect in enumerate(party_slot_rects):
            char_in_slot = party_slots[i]
            is_selected = (selected_char and char_in_slot and selected_char.cid == char_in_slot.cid)
            is_highlighted = (highlighted_slot_index == i) # DnD時のターゲットハイライト
            
            highlight = is_selected or is_highlighted
            
            if char_in_slot is None:
                draw_empty_slot(screen, rect, highlight)
            else:
                # ドラッグ中のキャラは元スロットを空表示にする
                if dragging_char and source_type == 'party' and source_index == i:
                    draw_empty_slot(screen, rect, is_highlighted)
                else:
                    draw_character_card(screen, char_in_slot, rect, highlight)

        # 控えキャラクターエリア
        screen.blit(font_m.render("控えキャラクター", True, FONT_COLOR), (ROSTER_START_X, 210))
        
        # ソートボタン
        for key, rect in SORT_BUTTONS.items():
            is_active = (roster_sort_key == key)
            bg_color = (60, 60, 120) if is_active else (40, 40, 80)
            pygame.draw.rect(screen, bg_color, rect, border_radius=5)
            key_label = {"name": "名前", "atk": "攻撃力", "hp": "HP", "defense": "防御力", "speed": "速さ", "rarity": "レア度"}.get(key, key)
            arrow = ""
            if is_active: arrow = " ▲" if not roster_sort_reverse else " ▼"
            text_content = key_label + arrow
            text = font_s.render(text_content, True, FONT_COLOR)
            text_rect = text.get_rect(center=rect.center)
            screen.blit(text, text_rect)
        
        # --- 控えのキャラクターカードの描画（スクロール対応） ---
        
        # 描画対象をROSTER_AREA_RECTでクリップ
        roster_surface = pygame.Surface((ROSTER_AREA_W, ROSTER_AREA_H))
        roster_surface.fill(BG_COLOR)
        
        # **注意:** 描画はroster_surfaceの (0, 0) を基準に行い、最後に全体をblitする
        
        for char in roster:
            rect_with_offset = roster_rects.get(char.cid)
            if rect_with_offset:
                # ROSTER_AREA_RECTに対する相対位置に変換
                x_rel = rect_with_offset.x - ROSTER_START_X
                y_rel = rect_with_offset.y - ROSTER_START_Y
                
                # ROSTER_AREA_RECT内に収まるかチェック
                if 0 <= y_rel + CARD_H and y_rel <= ROSTER_AREA_H:
                    
                    is_selected_in_roster = (selected_char and selected_char.cid == char.cid)
                    
                    if dragging_char and source_type == 'roster' and source_index == char.cid:
                        # ドラッグ中のキャラはロスター上では描画しない
                        pass 
                    else:
                        # 描画用の一時Rectを生成
                        temp_rect = pygame.Rect(x_rel, y_rel, CARD_W, CARD_H)
                        draw_character_card(roster_surface, char, temp_rect, is_selected_in_roster) 

        # 描画したロスターSurfaceをメイン画面にblit
        screen.blit(roster_surface, ROSTER_AREA_RECT.topleft)
        
        # ロスターエリアの境界線
        pygame.draw.rect(screen, (80, 80, 120), ROSTER_AREA_RECT, 2)
        
        # キャラクター詳細表示エリア
        pygame.draw.rect(screen, DETAIL_BG_COLOR, DETAIL_AREA_RECT, border_radius=5)
        pygame.draw.rect(screen, DETAIL_BORDER_COLOR, DETAIL_AREA_RECT, 2, border_radius=5)
        
        if selected_char:
            detail_x = DETAIL_AREA_X + PADDING
            detail_y = DETAIL_AREA_Y + PADDING
            
            # キャラクター名
            name_text = font_l.render(selected_char.name, True, FONT_COLOR)
            screen.blit(name_text, (detail_x, detail_y))
            detail_y += 35

            # 基本ステータス
            role_text = font_m.render(f"ロール: {selected_char.role} ({selected_char.element}属性)", True, ROLE_COLORS.get(selected_char.role, FONT_COLOR))
            screen.blit(role_text, (detail_x, detail_y))
            detail_y += 30

            stat_texts = [
                f"HP: {int(selected_char.hp)}",
                f"ATK: {int(selected_char.atk)}",
                f"DEF: {int(selected_char.defense)}",
                f"SPD: {int(selected_char.speed)}"
            ]
            for stat_text in stat_texts:
                text_surf = font_s.render(stat_text, True, FONT_COLOR)
                screen.blit(text_surf, (detail_x, detail_y))
                detail_y += 20
            
            detail_y += 10 # 区切り

            # スキル表示
            skill_types = {
                "通常攻撃": selected_char.normal_attack,
                "戦闘スキル": selected_char.battle_skills,
                "必殺技": selected_char.ultimate,
                "アビリティ": selected_char.abilities,
            }

            for skill_type_name, skills in skill_types.items():
                if skills:
                    type_title_text = font_m.render(skill_type_name, True, (200, 200, 255))
                    screen.blit(type_title_text, (detail_x, detail_y))
                    detail_y += 25
                    
                    for skill in skills:
                        detail_y = draw_skill_detail(screen, skill, detail_x, detail_y)
                        detail_y += 10 # スキル間の余白

        # ドラッグ中のキャラクター描画 (最前面)
        if dragging_char and not battle_settings_mode:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            drag_rect = pygame.Rect(mouse_x + drag_offset[0], mouse_y + drag_offset[1], CARD_W, CARD_H)
            
            # 描画用のSurfaceをSRCALPHAで作成し、透過を有効にする
            temp_surface = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
            temp_surface.fill((255, 255, 255, 0)) # 透明で初期化
            
            def draw_drag_card(surface, char, rect, highlight):
                # 描画処理は元のまま
                # ... (元の draw_drag_card の定義をここにコピーして使用) ...
                
                # カードの背景
                pygame.draw.rect(surface, SLOT_COLOR, surface.get_rect())
                # レアリティの枠線 (例として金色の枠)
                if char.rarity == "5": 
                    pygame.draw.rect(surface, (255, 215, 0), surface.get_rect(), 3) 
                elif highlight:
                    pygame.draw.rect(surface, SELECT_COLOR, surface.get_rect(), 3)
                else:
                    pygame.draw.rect(surface, (70, 70, 100), surface.get_rect(), 1) 

                # キャラクター名
                name_text = font_s.render(char.name, True, FONT_COLOR)
                name_rect = name_text.get_rect(centerx=rect.width // 2, y=10)
                surface.blit(name_text, name_rect)

                # ロール（役割）表示
                role_color = ROLE_COLORS.get(char.role, ROLE_COLORS["Default"])
                role_text = font_xs.render(f"ロール: {char.role}", True, role_color)
                role_rect = role_text.get_rect(midtop=(rect.width // 2, name_rect.bottom + 5))
                surface.blit(role_text, role_rect)

                # 簡易ステータス
                atk_text = font_xs.render(f"ATK:{int(char.atk)}", True, FONT_COLOR)
                hp_text = font_xs.render(f"HP:{int(char.hp)}", True, FONT_COLOR)
                speed_text = font_xs.render(f"SPD:{int(char.speed)}", True, FONT_COLOR)

                # 配置を調整
                atk_rect = atk_text.get_rect(left=10, y=role_rect.bottom + 10)
                hp_rect = hp_text.get_rect(right=rect.width - 10, y=role_rect.bottom + 10)
                speed_rect = speed_text.get_rect(centerx=rect.width // 2, y=atk_rect.bottom + 5)
                
                surface.blit(atk_text, atk_rect)
                surface.blit(hp_text, hp_rect)
                surface.blit(speed_text, speed_rect)
            # --- ここまで元の draw_drag_card ---

            draw_drag_card(temp_surface, dragging_char, temp_surface.get_rect(), False)
            # アルファ値を設定して半透明にする (任意)
            temp_surface.set_alpha(200) 
            screen.blit(temp_surface, drag_rect)

        # バトル設定ポップアップの描画 (最前面)
        if battle_settings_mode:
            draw_battle_settings(screen)

        # 4. 画面更新
        pygame.display.flip()
        clock.tick(60)

# --- 終了処理 ---
pygame.quit()
sys.exit()