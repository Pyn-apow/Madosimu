# battle_ui.py (アニメーション・バフ管理・最終安定版)

from __future__ import annotations
from typing import List, Optional, Dict, Any, Sequence, Tuple
import json
import pygame
import sys
import os
import time
import math
import copy
import random

# --- グローバル変数 (状態管理用) ---
SP_MAX = 6
current_sp = 5

selected_action_index = 0
selected_target: Optional['Character'] = None
acting_unit: Optional['Character'] = None
party_members: List['Character'] = []
enemies: List['Character'] = []
party_rects: Dict[int, pygame.Rect] = {}
enemy_rects: Dict[int, pygame.Rect] = {}
damage_texts: List[Dict[str, Any]] = []

# --- ターン管理のためのグローバル変数 ---
current_turn_count = 1

# --- 状態管理用定数 ---
STATE_COMMAND = 0           # コマンド選択中（プレイヤーターン）
STATE_ANIMATION = 1         # アクションアニメーション中（移動、スキル名表示、ダメージ）
STATE_ENEMY_TURN = 2        # 敵の行動中（自動）
STATE_BATTLE_END = 3        # 戦闘終了

# --- アニメーション関連定数 ---
ANIMATION_SPEED = 10        # 移動速度 (ピクセル/フレーム)
ATTACK_DURATION = 30        # 攻撃エフェクトの表示フレーム数
SKILL_NAME_DURATION = 60    # スキル名の表示フレーム数
SKILL_NAME_Y = 180          # スキル名が表示されるY座標

# --- グローバル状態変数 ---
current_state = STATE_COMMAND # 初期状態
attacking_unit_info: Optional[Dict[str, Any]] = None # アニメーション用の情報


# --- ユーティリティ: 技・アビリティのフォーマットの補助関数 ---
def make_action(name: str, typ: str = "skill", power: float = 0.0, desc: str = "",
                break_gauge: float = 0.0, element: str = "?",
                meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "name": str(name),
        "type": str(typ),
        "power": float(power),
        "desc": str(desc),
        "break_gauge": float(break_gauge),
        "element": str(element),
        "meta": dict(meta) if meta else {},
    }

# --- Characterクラス (バフ/デバフ機能) ---
class Character:
    _next_cid = 0
    BASE_ACT_FACTOR = 10000.0

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
        current_hp: float = 0.0,
        current_mp: float = 0.0,
        break_gauge_max: float = 100.0,
        current_break_gauge: float = 100.0,
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

        max_ult_cost = 0.0
        for action in self.ultimate:
            cost = action.get("meta", {}).get("cost_mp", 0.0)
            max_ult_cost = max(max_ult_cost, cost)
        self.mp_max = max(max_ult_cost, 0.0) 

        self.current_hp = float(current_hp) if current_hp else self.hp
        self.current_mp = 0.0
        self.break_gauge_max = float(break_gauge_max)
        self.current_break_gauge = float(current_break_gauge)

        self.active_effects: List[Dict[str, Any]] = [] 
        
        self.combat_stats: Dict[str, Any] = {
            'atk_buff': 0.0, 'def_debuff': 0.0, 'crit_dmg': 0.2, 'dmg_inc': 0.0,
            'weak_dmg_buff': 0.0, 'dmg_taken_inc': 0.0, 'break_bonus': 1.0,
            'is_critical_hit': False, 'is_weakness_hit': False, 'current_magic': 0.0,
            'speed_buff': 0.0, 'act_buff': 0.0,
            'face_color': None,
        }
        
        self._apply_initial_effects() 
        self._update_combat_stats_from_effects() 

        initial_speed_buff = self.combat_stats.get('speed_buff', 0.0)
        self.speed_act_time = self._calculate_act_time(self.speed, initial_speed_buff)
        self.next_action_time = self.speed_act_time

        self.short_name = self.name[:2].upper() if self.name else "??"
        
    def _apply_initial_effects(self):
        """アビリティなどから永続効果を初期適用する"""
        for ability in self.abilities:
            meta = ability.get("meta", {})
            for effect in meta.get("buff_debuffs", []):
                if effect.get("duration") == -1:
                    new_effect = effect.copy()
                    new_effect['source_name'] = ability['name']
                    self.active_effects.append(new_effect)

    def _update_combat_stats_from_effects(self):
        """アクティブな効果の合計値に基づいて combat_stats を更新する"""
        new_stats = {
            'atk_buff': 0.0, 'def_debuff': 0.0, 'crit_dmg': 0.5, 'dmg_inc': 0.0,
            'weak_dmg_buff': 0.0, 'dmg_taken_inc': 0.0, 'break_bonus': 1.0,
            'speed_buff': 0.0, 'act_buff': 0.0,
        }
        
        for effect in self.active_effects:
            effect_type = effect.get("type", "")
            amount = effect.get("amount", 0.0)
            
            # ★ 修正: バフ名に合わせた判定ロジック
            if "攻撃力UP" in effect_type: new_stats['atk_buff'] += amount
            elif "防御力DOWN" in effect_type: new_stats['def_debuff'] += amount 
            elif "防御力UP" in effect_type: new_stats['def_debuff'] -= amount # UPはデバフの逆（ダメージ軽減）として作用
            elif "スピードUP" in effect_type: new_stats['speed_buff'] += amount

        for key, value in new_stats.items():
            if key in self.combat_stats:
                self.combat_stats[key] = value

    # Character.apply_effect_from_action 関数内（該当部分のみ）
    def apply_effect_from_action(self, action: Dict[str, Any], target: 'Character', current_turn: int):
        """アクションのメタ情報に基づいてバフ/デバフをターゲットに適用する"""
        
        action_name = action.get('name', '特殊効果') 
        
        meta = action.get("meta", {})
        for effect in meta.get("buff_debuffs", []):
            effect_type = effect.get("type", "")
            amount = effect.get("amount", 0.0)
            duration = effect.get("duration", 0)

            old_next_action_time = target.next_action_time

            if "行動順UP" in effect_type: 
                target.apply_action_advance(amount)
                # ★ 修正: ログ出力 (action_name を使用)
                new_next_action_time = target.next_action_time
                print(f"[{target.name}] 行動順UP: {amount}. next_action_time: {old_next_action_time:.2f} -> {new_next_action_time:.2f} (効果元: {action_name})") 
                
            elif duration != 0:
                new_effect = effect.copy()
                new_effect['source_name'] = action_name
                new_effect['start_turn'] = current_turn
                
                is_found = False
                for active in target.active_effects:
                    if active.get('type') == effect_type and active.get('duration') != -1: 
                        active['duration'] = duration 
                        active['start_turn'] = current_turn
                        is_found = True
                        break
                
                if not is_found:
                    target.active_effects.append(new_effect)
                
                target._update_combat_stats_from_effects()
                
                if "スピード" in effect_type: # スピードUPが変化した場合
                    new_next_action_time = target.next_action_time
                    print(f"[{target.name}] {effect_type} 適用. next_action_time: {old_next_action_time:.2f} -> {new_next_action_time:.2f} (効果元: {action_name})")
                
                print(f"[{target.name}] {effect_type} 適用: {amount} ({duration}T) (効果元: {action['name']})")


    def check_and_decay_effects(self, current_turn: int):
        """ターン経過をチェックし、持続ターンが切れた効果を解除する"""
        
        effects_before = len(self.active_effects)
        
        self.active_effects = [
            effect for effect in self.active_effects 
            if effect.get("duration") == -1 or effect.get("start_turn", current_turn) + effect.get("duration", 0) > current_turn
        ]
        
        if effects_before != len(self.active_effects):
             print(f"[{self.name}] バフ/デバフが解除されました。")
             self._update_combat_stats_from_effects()
             self.apply_speed_buff(0) 

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        return cls(
            name=data.get("name", ""), rarity=data.get("rarity", ""),
            element=data.get("element", ""), role=data.get("role", ""),
            hp=float(data.get("hp", 0.0)), atk=float(data.get("atk", 0.0)),
            defense=float(data.get("defense", 0.0)), speed=float(data.get("speed", 0.0)),
            ultimate=[cls._load_skill_action(a) for a in data.get("ultimate", [])],
            battle_skills=[cls._load_skill_action(a) for a in data.get("battle_skills", [])],
            normal_attack=[cls._load_skill_action(a) for a in data.get("normal_attack", [])],
            abilities=[cls._load_skill_action(a) for a in data.get("abilities", [])],
            metadata=data.get("metadata", {}),
        )

    @staticmethod
    def _load_skill_action(action_data: Dict[str, Any]) -> Dict[str, Any]:
        return make_action(
            name=action_data.get("name", ""), typ=action_data.get("type", "skill"),
            power=action_data.get("power", 0.0), desc=action_data.get("desc", ""),
            break_gauge=action_data.get("break_gauge", 0.0), element=action_data.get("element", "?"),
            meta=action_data.get("meta", {}),
        )

    def get_all_actions(self) -> List[Dict[str, Any]]:
        actions = []
        if self.normal_attack:
            default_attack = self.normal_attack[0].copy()
            if default_attack.get("power", 0.0) == 0.0:
                default_attack["power"] = 1.0
            actions.append(default_attack)
        actions.extend(self.battle_skills)
        return actions

    def get_ultimate_action(self) -> Optional[Dict[str, Any]]:
        if self.ultimate:
            return self.ultimate[0]
        return None

    def _calculate_act_time(self, base_speed: float, speed_buff: float) -> float:
        modified_speed = base_speed * (1.0 + speed_buff)
        if modified_speed <= 0:
            return float("inf")
        return self.BASE_ACT_FACTOR / modified_speed

    def apply_speed_buff(self, num: float):
        old_buff = self.combat_stats.get('speed_buff', 0.0)
        old_act_time = self._calculate_act_time(self.speed, old_buff)
        
        progress_ratio = self.next_action_time / old_act_time if old_act_time and old_act_time != float("inf") else 1.0
        
        new_buff = self.combat_stats['speed_buff'] 

        self.speed_act_time = self._calculate_act_time(self.speed, new_buff)
        if self.speed_act_time == float("inf"):
            self.next_action_time = float("inf")
        else:
            self.next_action_time = self.speed_act_time * progress_ratio

    def apply_action_advance(self, num: float):
        if self.speed_act_time == float("inf"):
            return
        advance_amount = self.speed_act_time * num
        self.next_action_time = max(0.0, self.next_action_time - advance_amount)

    def add_mp(self, amount: float):
        self.current_mp = min(self.mp_max, (self.current_mp or 0.0) + amount)
        self.current_mp = max(0.0, self.current_mp)


def calculate_damage(
    attacker: Character, defender: Character, skill_power: float,
    is_critical: bool, is_weakness: bool
) -> float:
    base_atk = attacker.atk
    atk_ratio = max(1.0, base_atk) / 124.0
    power_term = (atk_ratio ** 1.2 + 12.0) / 20.0
    base_damage = base_atk * skill_power * power_term

    atk_buff_term = 1.0 + attacker.combat_stats.get('atk_buff', 0.0)
    def_debuff_term = 1.0 + defender.combat_stats.get('def_debuff', 0.0)

    dmg_inc = attacker.combat_stats.get('dmg_inc', 0.0)
    dmg_taken_inc = defender.combat_stats.get('dmg_taken_inc', 0.0)
    dmg_bonus_term = 1.0 + dmg_inc + dmg_taken_inc

    break_bonus_factor = defender.combat_stats.get('break_bonus', 1.0)

    intermediate_damage = (
        base_damage * atk_buff_term * def_debuff_term * dmg_bonus_term * break_bonus_factor
    )

    crit_term = 1.0
    if is_critical:
        crit_dmg = attacker.combat_stats.get('crit_dmg', 0.0)
        crit_term = 1.0 + crit_dmg

    weakness_term = 1.0
    if is_weakness:
        weak_dmg_buff = attacker.combat_stats.get('weak_dmg_buff', 0.0)
        weakness_term = 1.2 + weak_dmg_buff

    final_damage = intermediate_damage * crit_term * weakness_term
    return max(0.0, final_damage)


# --- 定数 ---
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
BG_COLOR = (20, 20, 40)

TURN_LIST_X = 20
TURN_LIST_Y = 20
TURN_ICON_SIZE = 40
TURN_ICON_SPACING = 15
MAX_TURN_ICONS = 8

UNIT_ICON_SIZE = 80
UNIT_BAR_HEIGHT = 10
UNIT_CARD_TOTAL_H = UNIT_ICON_SIZE + UNIT_BAR_HEIGHT * 2 + 10
PARTY_COUNT = 4
PARTY_AREA_Y = SCREEN_HEIGHT - UNIT_CARD_TOTAL_H - 20
UNIT_PADDING_X = 30

COMMAND_PANEL_CENTER_X = SCREEN_WIDTH - 200
COMMAND_PANEL_CENTER_Y = SCREEN_HEIGHT - 100
ACTION_BUTTON_RADIUS = 60
ACTION_BUTTON_BG_COLOR = (50, 50, 80)
ACTION_BUTTON_HIGHLIGHT_COLOR = (255, 255, 50)
ACTION_BUTTON_DISABLED_COLOR = (30, 30, 50)

ULT_GAUGE_HIGHLIGHT_COLOR = (255, 255, 100)
DARK_COLOR_FACTOR = 0.3

HP_BAR_COLOR = (50, 255, 50)
MP_BAR_COLOR = (0, 150, 255)
BREAK_BAR_COLOR = (255, 100, 100)
BAR_BG_COLOR = (10, 10, 20)
FONT_COLOR = (255, 255, 255) 
HIGHLIGHT_BORDER_COLOR = (255, 255, 50)

MP_INCREASE_NORMAL = 15.0
MP_INCREASE_SKILL = 30.0
MP_INCREASE_ULT_AFTER = 5.0
MP_INCREASE_DEFEAT = 10.0

DAMAGE_TEXT_DURATION = 90
DAMAGE_TEXT_SPEED = 0.5

SP_GAUGE_X = COMMAND_PANEL_CENTER_X - 250 
SP_GAUGE_Y = COMMAND_PANEL_CENTER_Y + 50
SP_ICON_SIZE = 20
SP_ICON_SPACING = 5
SP_COLOR_ACTIVE = (50, 255, 255) 
SP_COLOR_INACTIVE = (30, 80, 80)

ELEMENT_COLORS: Dict[str, Tuple[int, int, int]] = {
    "無": (180, 180, 180),
    "火": (255, 100, 100),
    "水": (100, 150, 255),
    "木": (100, 200, 100),
    "光": (255, 255, 150),
    "闇": (100, 50, 150),
    "?": (150, 150, 150),
}

# --- Pygame 初期化 ---
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Magia Exedra - バトルシミュレーション")
clock = pygame.time.Clock()

font_path = "noto.ttf"
try:
    font_s = pygame.font.Font(font_path, 24)
    font_m_icon = pygame.font.Font(font_path, 32)
    font_xs = pygame.font.Font(font_path, 14)
    font_xxs = pygame.font.Font(font_path, 10)
    font_ready = pygame.font.Font(font_path, 18)
    font_progress = pygame.font.Font(font_path, 16)
    font_damage = pygame.font.Font(font_path, 36)
    font_crit = pygame.font.Font(font_path, 48)
    font_action_name = pygame.font.Font(font_path, 40)
except Exception:
    font_s = pygame.font.Font(None, 24)
    font_m_icon = pygame.font.Font(None, 32)
    font_xs = pygame.font.Font(None, 14)
    font_xxs = pygame.font.Font(None, 10)
    font_ready = pygame.font.Font(None, 18)
    font_progress = pygame.font.Font(None, 16)
    font_damage = pygame.font.Font(None, 36)
    font_crit = pygame.font.Font(None, 48)
    font_action_name = pygame.font.Font(None, 40)


def darken_color(color: Tuple[int, int, int], factor: float = DARK_COLOR_FACTOR) -> Tuple[int, int, int]:
    r, g, b = color
    return (int(r * factor), int(g * factor), int(b * factor))

# 属性色と白をミックスするヘルパー関数
def mix_color_with_white(color: Tuple[int, int, int], mix_ratio: float = 0.5) -> Tuple[int, int, int]:
    r, g, b = color
    wr, wg, wb = FONT_COLOR # 白 (255, 255, 255)
    
    r_mix = int(r * (1 - mix_ratio) + wr * mix_ratio)
    g_mix = int(g * (1 - mix_ratio) + wg * mix_ratio)
    b_mix = int(b * (1 - mix_ratio) + wb * mix_ratio)
    
    return (r_mix, g_mix, b_mix)


def get_party_unit_rects(units: List[Character]) -> Dict[int, pygame.Rect]:
    rects = {}
    if not units:
        return rects
    total_width = len(units) * UNIT_ICON_SIZE + (len(units) - 1) * UNIT_PADDING_X
    party_area_start_x = (SCREEN_WIDTH - total_width) // 2
    for i, unit in enumerate(units):
        x = party_area_start_x + i * (UNIT_ICON_SIZE + UNIT_PADDING_X)
        y = PARTY_AREA_Y
        rect = pygame.Rect(x, y, UNIT_ICON_SIZE, UNIT_CARD_TOTAL_H)
        rects[unit.cid] = rect
    return rects


def get_enemy_unit_rects(units: List[Character]) -> Dict[int, pygame.Rect]:
    rects = {}
    if not units:
        return rects
    total_width = len(units) * UNIT_ICON_SIZE + (len(units) - 1) * UNIT_PADDING_X
    start_x = SCREEN_WIDTH // 2 - total_width // 2
    for i, unit in enumerate(units):
        x = start_x + i * (UNIT_ICON_SIZE + UNIT_PADDING_X)
        y = SCREEN_HEIGHT // 2 - UNIT_CARD_TOTAL_H
        rect = pygame.Rect(x, y, UNIT_ICON_SIZE, UNIT_CARD_TOTAL_H)
        rects[unit.cid] = rect
    return rects


def get_action_button_centers(num_actions: int) -> List[Tuple[int, int]]:
    centers: List[Tuple[int, int]] = []
    center_y_base = COMMAND_PANEL_CENTER_Y
    # ★ 修正: 元のコードのボタン位置ロジックを正確に復元
    centers.append((COMMAND_PANEL_CENTER_X + ACTION_BUTTON_RADIUS*0.5, center_y_base + ACTION_BUTTON_RADIUS*0.5))
    centers.append((COMMAND_PANEL_CENTER_X + ACTION_BUTTON_RADIUS*2, center_y_base - ACTION_BUTTON_RADIUS))
    centers.append((COMMAND_PANEL_CENTER_X, center_y_base - ACTION_BUTTON_RADIUS))
    return centers[:num_actions]


def load_battle_data(filename="battle_data.json") -> Dict[str, List[Character]]:
    data = {"party": [], "enemies": []}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        for i, char_data in enumerate(raw_data.get("party", [])):
            member = Character.from_dict(char_data)
            member.combat_stats['face_color'] = ELEMENT_COLORS.get(member.element, ELEMENT_COLORS["?"])
            member.next_action_time = member.speed_act_time * 0.1 * (i + 1)
            data["party"].append(member)

        for i, char_data in enumerate(raw_data.get("enemies", [])):
            enemy = Character.from_dict(char_data)
            enemy.current_break_gauge = enemy.break_gauge_max
            enemy.combat_stats['face_color'] = ELEMENT_COLORS.get(enemy.element, ELEMENT_COLORS["?"])
            enemy.next_action_time = enemy.speed_act_time * 0.2 * (i + 1) + enemy.speed_act_time * 0.5
            data["enemies"].append(enemy)

    except Exception as e:
        print(f"データロード中に致命的なエラーが発生しました: {e}")
        print("ファイル 'battle_data.json' が見つからないか破損しています。終了します。")
        pygame.quit()
        sys.exit()

    return data


# 初期ロード
try:
    battle_data = load_battle_data()
    party_members = battle_data["party"]
    enemies = battle_data["enemies"]
except Exception as e:
    print(f"データロード失敗: {e}。ダミーデータを使用します。")
    party_members = []
    enemies = []

# グローバル変数の初期化 (ロード後)
party_rects = get_party_unit_rects(party_members)
enemy_rects = get_enemy_unit_rects(enemies)


# --- SP変更ヘルパー関数 (ログ追加) ---
def change_global_sp(amount: int):
    """パーティ共通SPを変更し、上限・下限を適用する。"""
    global current_sp, SP_MAX
    old_sp = current_sp
    current_sp = max(0, min(SP_MAX, current_sp + amount))
    # デバッグログ
    if old_sp != current_sp:
        action_type = "増加" if amount > 0 else "消費"
        if acting_unit:
            unit_name = f"{acting_unit.name} ({'味方' if acting_unit in party_members else '敵'})"
        else:
            unit_name = "システム"
        print(f"SPログ: {unit_name} がSPを{amount} {action_type}。 ({old_sp} -> {current_sp})")


def draw_bar(surface: pygame.Surface, rect: pygame.Rect, current_val: float, max_val: float, color: tuple):
    pygame.draw.rect(surface, BAR_BG_COLOR, rect)
    if max_val > 0 and current_val is not None:
        cv = max(0.0, min(current_val, max_val))
        fill_width = rect.width * (cv / max_val)
        fill_rect = pygame.Rect(rect.x, rect.y, fill_width, rect.height)
        pygame.draw.rect(surface, color, fill_rect)
    pygame.draw.rect(surface, (100, 100, 100), rect, 1)


def draw_unit_icon(surface: pygame.Surface, unit: Character, rect: pygame.Rect, highlight: bool, is_enemy: bool, is_acting: bool):
    icon_rect = pygame.Rect(rect.x, rect.y, UNIT_ICON_SIZE, UNIT_ICON_SIZE)
    icon_center = icon_rect.center
    icon_radius = UNIT_ICON_SIZE // 2
    face_color = unit.combat_stats.get('face_color') or ELEMENT_COLORS["?"]

    if not is_enemy:
        mp_ratio = 0.0
        if unit.mp_max and unit.current_mp is not None:
            mp_ratio = max(0.0, min(unit.current_mp / unit.mp_max, 1.0))
        dark_color = darken_color(face_color)

        temp_surface = pygame.Surface((UNIT_ICON_SIZE, UNIT_ICON_SIZE), pygame.SRCALPHA)
        temp_center = (icon_radius, icon_radius)

        pygame.draw.circle(temp_surface, dark_color, temp_center, icon_radius)

        if mp_ratio > 0:
            fill_surface = pygame.Surface((UNIT_ICON_SIZE, UNIT_ICON_SIZE), pygame.SRCALPHA)
            pygame.draw.circle(fill_surface, face_color, temp_center, icon_radius)
            unfilled_height = UNIT_ICON_SIZE - int(UNIT_ICON_SIZE * mp_ratio)
            mask_rect = pygame.Rect(0, 0, UNIT_ICON_SIZE, unfilled_height)
            fill_surface.fill((0, 0, 0, 0), mask_rect)
            temp_surface.blit(fill_surface, (0, 0))

        surface.blit(temp_surface, icon_rect.topleft)

        # 必殺技即時発動のためのハイライトを追加
        if unit.current_mp >= unit.mp_max and unit.mp_max > 0:
            blink_speed = 3.0
            blink_alpha = int((math.sin(time.time() * blink_speed) + 1) / 2 * 255)
            r, g, b = ULT_GAUGE_HIGHLIGHT_COLOR
            blink_surface = pygame.Surface((UNIT_ICON_SIZE, UNIT_ICON_SIZE), pygame.SRCALPHA)
            blinking_color = (r, g, b, blink_alpha)
            pygame.draw.circle(blink_surface, blinking_color, temp_center, icon_radius, 4)
            surface.blit(blink_surface, icon_rect.topleft)
    else:
        pygame.draw.circle(surface, face_color, icon_center, icon_radius)

    name_text_surface = font_m_icon.render(unit.short_name, True, FONT_COLOR)
    name_text_rect = name_text_surface.get_rect(center=icon_center)
    surface.blit(name_text_surface, name_text_rect)

    border_thickness = 2
    border_color = (80, 80, 80)
    if is_acting:
        border_thickness = 5
        border_color = HIGHLIGHT_BORDER_COLOR
    elif highlight:
        border_thickness = 5
        border_color = (255, 0, 0) if is_enemy else HIGHLIGHT_BORDER_COLOR

    pygame.draw.circle(surface, border_color, icon_center, icon_radius, border_thickness)

    hp_bar_rect = pygame.Rect(rect.x, rect.y + UNIT_ICON_SIZE + 5, UNIT_ICON_SIZE, UNIT_BAR_HEIGHT)
    draw_bar(surface, hp_bar_rect, unit.current_hp, unit.hp, HP_BAR_COLOR)

    if not is_enemy:
        hp_text = f"{int(unit.current_hp)}/{int(unit.hp)}"
        hp_text_surface = font_xxs.render(hp_text, True, FONT_COLOR)
        hp_text_rect = hp_text_surface.get_rect(center=(hp_bar_rect.centerx, hp_bar_rect.centery))
        surface.blit(hp_text_surface, hp_text_rect)

    bar2_rect = pygame.Rect(rect.x, hp_bar_rect.bottom + 2, UNIT_ICON_SIZE, UNIT_BAR_HEIGHT)
    if not is_enemy:
        draw_bar(surface, bar2_rect, unit.current_mp, unit.mp_max, MP_BAR_COLOR)
    else:
        draw_bar(surface, bar2_rect, unit.current_break_gauge, unit.break_gauge_max, BREAK_BAR_COLOR)


def draw_turn_order(surface: pygame.Surface, turn_order_with_time: List[Tuple[Character, float]]):
    x_pos = TURN_LIST_X
    y_pos = TURN_LIST_Y
    radius = TURN_ICON_SIZE // 2

    title_text = font_ready.render("行動順:", True, FONT_COLOR)
    surface.blit(title_text, (x_pos, y_pos))
    y_pos += 30

    # 修正: タプルリスト (unit, predicted_time) を展開
    for i, (unit, predicted_time) in enumerate(turn_order_with_time):
        if i >= MAX_TURN_ICONS: break
        center_x = x_pos + radius
        center_y = y_pos + radius
        face_color = unit.combat_stats.get('face_color', ELEMENT_COLORS["?"])
        is_enemy = unit in enemies
        pygame.draw.circle(surface, face_color, (center_x, center_y), radius)
        name_text_surface = font_xs.render(unit.short_name, True, FONT_COLOR)
        name_text_rect = name_text_surface.get_rect(center=(center_x, center_y))
        surface.blit(name_text_surface, name_text_rect)
        border_color = (255, 0, 0) if is_enemy else (200, 200, 200)
        pygame.draw.circle(surface, border_color, (center_x, center_y), radius, 1)

        # 修正: 累積予測時間を表示
        if predicted_time != float("inf"):
            # 累積時間を丸めて表示 (最初の行動は 0 に近く、その次の行動は 100 程度の値になるはず)
            progress_val = int(predicted_time)
            progress_text = f"{progress_val}"
            progress_surface = font_progress.render(progress_text, True, FONT_COLOR)
            progress_x = x_pos + TURN_ICON_SIZE + 5
            progress_y = y_pos + radius - (font_progress.get_height() // 2)
            surface.blit(progress_surface, (progress_x, progress_y))

        y_pos += TURN_ICON_SIZE + TURN_ICON_SPACING


def draw_action_button(surface: pygame.Surface, center: Tuple[int, int], radius: int, action: Dict[str, Any], is_selected: bool, is_affordable: bool):
    """
    アクションボタンを描画し、SPとMPの両方のコストと可用性を考慮する。
    """
    global current_sp

    current_radius = int(radius * (1.0 if is_selected else 0.7))
    mp_cost = action.get("meta", {}).get("cost_mp", 0.0)
    is_skill = "戦闘スキル" in action.get("type", "") or "skill" in action.get("type", "")
    
    sp_cost = 1 if is_skill else 0
    is_mp_affordable = is_affordable
    is_sp_affordable = True
    if is_skill:
        is_sp_affordable = current_sp >= sp_cost

    final_affordable = is_mp_affordable and is_sp_affordable

    if not final_affordable and (mp_cost > 0 or sp_cost > 0):
        bg_color = ACTION_BUTTON_DISABLED_COLOR
        border_color = (50, 50, 50)
    else:
        bg_color = ACTION_BUTTON_BG_COLOR
        border_color = ACTION_BUTTON_HIGHLIGHT_COLOR if is_selected else (80, 80, 100)

    pygame.draw.circle(surface, bg_color, center, current_radius)
    pygame.draw.circle(surface, border_color, center, current_radius, 10)

    name_text = action.get("name", "")
    type_text = action.get("type", "")
    name_surface = font_s.render(name_text, True, FONT_COLOR)
    type_surface = font_xs.render(f"({type_text})", True, FONT_COLOR)
    name_rect = name_surface.get_rect(center=(center[0], center[1] - 5))
    type_rect = type_surface.get_rect(center=(center[0], center[1] + 20))
    surface.blit(name_surface, name_rect)
    surface.blit(type_surface, type_rect)

    cost_info = []
    if mp_cost > 0:
        cost_info.append(f"MP: {int(mp_cost)}")
    if sp_cost > 0:
        cost_info.append(f"SP: {int(sp_cost)}")

    if cost_info:
        cost_text = " / ".join(cost_info)
        cost_surface = font_xxs.render(cost_text, True, FONT_COLOR)
        cost_rect = cost_surface.get_rect(center=(center[0], center[1] + current_radius - 10))
        surface.blit(cost_surface, cost_rect)


# --- SPゲージ描画関数 (グローバルSPを参照) ---
def draw_sp_gauge(surface: pygame.Surface):
    """
    画面下部、コマンドアイコンの左にパーティ共通SPゲージを描画する
    """
    global current_sp, SP_MAX
    
    start_x = SP_GAUGE_X
    center_y = SP_GAUGE_Y
    radius = SP_ICON_SIZE // 2
    
    # タイトル
    title_text = font_s.render("SP", True, SP_COLOR_ACTIVE)
    surface.blit(title_text, (start_x - 35, center_y - radius - 5))
    
    for i in range(SP_MAX):
        center_x = start_x + (SP_ICON_SIZE + SP_ICON_SPACING) * i + radius
        
        if i < current_sp:
            color = SP_COLOR_ACTIVE
        else:
            color = SP_COLOR_INACTIVE

        pygame.draw.circle(surface, color, (center_x, center_y), radius)
        # 枠線
        pygame.draw.circle(surface, FONT_COLOR, (center_x, center_y), radius, 1)


def draw_damage_texts(surface: pygame.Surface, texts: List[Dict[str, Any]]):
    for text_data in texts:
        value = text_data["value"]
        pos_x, pos_y = text_data["pos"]
        is_crit = text_data["is_crit"]
        is_enemy = text_data["is_enemy"] # True: 敵へのダメージ（味方の攻撃）, False: 味方へのダメージ（敵の攻撃）
        
        unit = next((u for u in party_members + enemies if u.cid == text_data.get('attacker_cid')), None)
        
        # --- ダメージ値の符号に基づいて色と表示を決定 ---
        abs_value = abs(value)
        text_content = str(int(abs_value))

        if value < 0: # 回復 (負のダメージ)
            color = (50, 255, 50) # 緑色
            text_content = f"+{int(abs_value)}"
            font = font_damage
        elif is_crit:
            color = mix_color_with_white(unit.combat_stats['face_color'], mix_ratio=0.3) 
            font = font_crit
        elif is_enemy and unit and unit.combat_stats.get('face_color'):
            # 味方の攻撃（敵へのダメージ）: 属性色と白をミックス
            color = mix_color_with_white(unit.combat_stats['face_color'], mix_ratio=0.7) 
            font = font_damage
        else:
            color = (255, 100, 100) # 敵の攻撃（味方へのダメージ）を赤色に
            font = font_damage

        # 文字列と描画用Surfaceを生成
        text_surface = font.render(text_content, True, color)
        text_rect = text_surface.get_rect(center=(int(pos_x), int(pos_y)))
        
        # 簡易的な縁取り（黒いアウトライン）
        outline_color = (0, 0, 0)
        outline_size = 2
        for dx in [-outline_size, 0, outline_size]:
            for dy in [-outline_size, 0, outline_size]:
                if dx == 0 and dy == 0: continue
                outline_surface = font.render(text_content, True, outline_color)
                surface.blit(outline_surface, (text_rect.x + dx, text_rect.y + dy))

        # 本体を描画
        surface.blit(text_surface, text_rect)


def add_damage_text(unit: Character, damage_value: float, is_critical: bool, is_enemy: bool, attacker_unit: Character):
    """ダメージテキスト表示リストに情報を追加する"""
    if abs(damage_value) < 0.1 and damage_value >= 0: return 
    
    # ダメージを受けるユニットのアイコン中央上部の位置を取得
    rects = enemy_rects if is_enemy else party_rects
    unit_rect = rects.get(unit.cid)
    
    if unit_rect:
        pos_x = unit_rect.centerx
        pos_y = unit_rect.y - UNIT_ICON_SIZE // 4 # アイコンより少し上の位置
        
        damage_texts.append({
            "value": damage_value,
            "pos": [pos_x, pos_y], 
            "is_crit": is_critical,
            "is_enemy": is_enemy, 
            "time_left": DAMAGE_TEXT_DURATION,
            "attacker_cid": attacker_unit.cid # 攻撃元のCIDを追加
        })
        
def get_next_turn_unit(units: List[Character], temp_units: Optional[List[Dict]] = None) -> Tuple[Optional[Character], float]:
    """
    次に最も早く行動するユニットとその時間（または、temp_unitsのシミュレーション時間）を返す。
    """
    # ターンリスト予測時 (temp_units が存在する場合)
    if temp_units is not None:
        active_temp_units = [t for t in temp_units if t['original'].current_hp > 0]
        if not active_temp_units: return None, 0.0
        
        min_time = min(t['next_action_time'] for t in active_temp_units)
        
        # 速度が最速のユニットを選ぶロジック
        candidates = [t for t in active_temp_units if math.isclose(t['next_action_time'], min_time, abs_tol=1e-9)]
        if not candidates:
            next_temp_unit = min(active_temp_units, key=lambda t: t['next_action_time'])
        else:
            # next_action_time が同じ場合は、元のユニットの speed が速い方を優先
            next_temp_unit = min(candidates, key=lambda t: t['speed'])
            
        return next_temp_unit['original'], min_time
    
    # 通常の行動判定時 (temp_units がない場合) 
    else:
        active_units = [u for u in units if u.current_hp > 0]
        if not active_units: return None, 0.0
        min_time = min(u.next_action_time for u in active_units)
        
        candidates = [u for u in active_units if math.isclose(u.next_action_time, min_time, abs_tol=1e-9)]
        if not candidates:
            next_unit = min(active_units, key=lambda u: u.next_action_time)
        else:
            next_unit = min(candidates, key=lambda u: u.speed)
            
        return next_unit, min_time

def get_turn_order_list(units: List[Character]) -> List[Tuple[Character, float]]:
    """
    行動順リストを、予測される行動の「絶対時間」と共に返す。（干渉なしソート）
    """
    if not units: return []
    active_units = [u for u in units if u.current_hp > 0]
    if not active_units: return []

    all_action_times: List[Tuple[Character, float]] = []
    
    for u in active_units:
        current_time = u.next_action_time  # 次の行動までの残り時間
        act_time = u.speed_act_time        # ゲージ全長

        if act_time == float("inf"):
            continue

        # 1. 最初の行動時刻: 現在の絶対時間 + 残り時間
        # プレビューでは「行動開始時」の absolute_time = 0 と見なす
        absolute_time = current_time 
        
        all_action_times.append((u, absolute_time))
        
        # 2. 2回目以降の行動時刻（MAX_TURN_ICONS - 1 回分）を計算
        for i in range(1, MAX_TURN_ICONS):
            absolute_time += act_time 
            all_action_times.append((u, absolute_time))

    # 3. 絶対時間でソートし、最初の MAX_TURN_ICONS 個を抽出
    all_action_times.sort(key=lambda x: x[1])
    
    return all_action_times[:MAX_TURN_ICONS]

# battle_ui.py 内の get_preview_turn_order_list 関数を以下に置き換え

def get_preview_turn_order_list(units: List[Character], action: Dict[str, Any], attacker: Character, preview_target_unit: Optional[Character]) -> List[Tuple[Character, float]]:
    """
    指定されたアクションが実行された後の仮想的な行動順リストを返す。
    （加速効果を「次の行動までの残り時間」に直接適用してシミュレート）
    """
    if not units or not action: return get_turn_order_list(units)
    active_units = [u for u in units if u.current_hp > 0]
    if not active_units: return []

    # 1. 仮想実行のためのディープコピーリストを作成 (全アクティブユニット)
    temp_units_map: Dict[int, 'Character'] = {}
    for u in active_units:
        # ディープコピーを行い、元の状態を破壊しないようにする
        copied_unit = copy.deepcopy(u)
        copied_unit.next_action_time = u.next_action_time
        temp_units_map[u.cid] = copied_unit

    # 2. 仮想実行の初期状態設定: 行動者は行動後の状態から開始
    if attacker.cid in temp_units_map:
        acting_copy = temp_units_map[attacker.cid]
        # 行動者は next_action_time が speed_act_time にリセットされたと仮定
        acting_copy.next_action_time = acting_copy.speed_act_time

    # 3. バフ/デバフの適用ロジック
    accelerate_amount = 0.0
    for effect_data in action.get("meta", {}).get("buff_debuffs", []):
        if "行動順UP" in effect_data.get("type", ""):
            accelerate_amount = effect_data.get("amount", 0.0)
            break

    is_attacker_player = attacker in party_members
    player_cids = {m.cid for m in party_members}
    
    ATTACKER_ALLIES = [t for t in temp_units_map.values() if t.cid in player_cids] if is_attacker_player else [t for t in temp_units_map.values() if t.cid not in player_cids]

    # 4. 加速の適用 (次の行動までの残り時間のみを短縮)
    if accelerate_amount > 0:
        for u in ATTACKER_ALLIES:
            if u.current_hp > 0:
                u.next_action_time *= (1.0 - accelerate_amount)
                u.apply_speed_buff(0)

    # 5. 仮想実行後のターンリストを再計算のためのデータ構築 (干渉なしの絶対時間ソート)
    all_action_times: List[Tuple[Character, float]] = []
    
    for u in temp_units_map.values():
        u.apply_speed_buff(0) 
        
        current_time = u.next_action_time
        act_time = u.speed_act_time

        if act_time == float("inf"):
            continue

        absolute_time = current_time 
        
        # 最初の行動（加速された行動）は、next_action_time をそのまま使用
        all_action_times.append((u, absolute_time))
        
        for i in range(1, MAX_TURN_ICONS):
            absolute_time += act_time 
            all_action_times.append((u, absolute_time))

    # ★ 最終修正: リストの先頭に attacker (0.0) を強制挿入し、重複する最初の要素を削除しない
    final_preview_list = [(attacker, 0.0)]
    final_preview_list.extend(all_action_times)

    # 最終ソート (0.0s が先頭に固定される)
    final_preview_list.sort(key=lambda x: x[1])
    
    return final_preview_list[:MAX_TURN_ICONS]

def get_target_center_pos(targets: List['Character'], is_enemy_target: bool, attacker_cid: int) -> Tuple[int, int]:
    """
    攻撃者が「味方」ならターゲットの下側、「敵」ならターゲットの上側に位置するよう、
    X軸はターゲット群の中心に合わせ、移動すべき位置（アイコンの左上座標）を決定する。
    """
    # ... (前略: ターゲット矩形の計算) ...
    
    rects = enemy_rects if is_enemy_target else party_rects
    target_rects = [rects[t.cid] for t in targets if t.cid in rects]
    
    if not target_rects:
        return (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)

    # ターゲット群の全体範囲を取得
    min_x = min(r.left for r in target_rects)
    max_x = max(r.right for r in target_rects)
    min_y = min(r.top for r in target_rects)
    max_y = max(r.bottom for r in target_rects)
    
    # ターゲット群の X 中心（アイコンの中心X座標）を計算
    target_center_x = (min_x + max_x) // 2
    
    # 目標 X 座標: 攻撃ユニットのアイコンの中心Xをターゲット群の中心Xに合わせる
    target_x = target_center_x - UNIT_ICON_SIZE // 2 
    
    # Y軸オフセット（近接演出用）
    NEAR_OFFSET_Y = UNIT_ICON_SIZE * 0.25 

    # 攻撃者の陣営を判定（attacker_cidが味方Rectにあるかで判断）
    is_attacker_player = attacker_cid in party_rects.keys()

    # ★ Y座標ロジックの修正: 攻撃者の陣営（味方/敵）によって目標Yを選択
    if is_attacker_player:
        # 攻撃者が味方: ターゲットの下側（手前、Y大）に移動
        # ターゲット群の最下端 (max_y) の少し下（手前）に攻撃ユニットの上端を合わせる
        target_y = max_y + NEAR_OFFSET_Y
    else:
        # 攻撃者が敵: ターゲットの上側（奥、Y小）に移動
        # ターゲット群の最上端 (min_y) の少し上（奥）に攻撃ユニットの下端を合わせる
        target_y = min_y - UNIT_ICON_SIZE - NEAR_OFFSET_Y

    return int(target_x), int(target_y)


def draw_action_name(surface: pygame.Surface, action_name: str):
    """画面上部にアクション名称を演出する"""
    global attacking_unit_info
    
    if attacking_unit_info and attacking_unit_info.get('action_name_timer', 0) > 0:
        timer = attacking_unit_info['action_name_timer']
        
        alpha = int(255 * (timer / SKILL_NAME_DURATION))
        
        text_surface = font_action_name.render(action_name, True, FONT_COLOR)
        text_surface.set_alpha(alpha)
        
        shadow_surface = font_action_name.render(action_name, True, (0, 0, 0))
        shadow_surface.set_alpha(int(alpha * 0.8))

        text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, SKILL_NAME_Y))
        
        surface.blit(shadow_surface, (text_rect.x + 2, text_rect.y + 2))
        surface.blit(text_surface, text_rect)
        
        attacking_unit_info['action_name_timer'] -= 1


def main():
    global selected_action_index, selected_target, selected_party_member, action_is_selected
    global enemies, party_members
    global all_units
    global party_rects, enemy_rects
    global damage_texts
    global acting_unit
    global current_sp
    global current_turn_count 
    global current_state, attacking_unit_info

    if not enemies or not party_members:
        print("警告: パーティまたは敵が空です。battle_data.json を確認してください。")
        return
    
    for unit in party_members + enemies:
        unit._update_combat_stats_from_effects()
        unit.apply_speed_buff(0)

    # ★ 修正: 戦闘開始時に「味方全体」アビリティバフを適用するロジック
    for member in party_members:
        for ability in member.abilities:
            for effect in ability.get("meta", {}).get("buff_debuffs", []):
                if effect.get("duration") == -1 and effect.get("target") == "味方全体":
                    # 永続かつ味方全体バフの場合、パーティ全体に適用
                    for target_unit in party_members:
                        if target_unit.cid != member.cid: # 既に_apply_initial_effectsで適用済みのため、自分自身はスキップ
                             # target_unit の active_effects に効果を追加し、ステータスを更新
                             new_effect = effect.copy()
                             new_effect['source_name'] = ability['name']
                             target_unit.active_effects.append(new_effect)
                             target_unit._update_combat_stats_from_effects()
                             target_unit.apply_speed_buff(0) # 速度の再計算を強制

    selected_party_member = None
    selected_target = enemies[0] if enemies else None
    selected_action_index = 0
    action_is_selected = False

    all_units = party_members + enemies
    acting_unit = None

    _, min_time_init = get_next_turn_unit(all_units)
    for unit in all_units:
        if unit.next_action_time != float("inf"):
            unit.next_action_time -= min_time_init

    turn_order_list = get_turn_order_list(all_units)
    
    current_state = STATE_COMMAND 

    preview_turn_order_list: Optional[List[Tuple[Character, float]]] = None
    
    running = True
    while running:
        
        # 1. ユニット行動判定 (コマンド選択中の場合のみターンを進める)
        if acting_unit is None and all_units and current_state == STATE_COMMAND:
            next_unit, time_to_act = get_next_turn_unit(all_units)

            if next_unit and time_to_act <= 1e-9:
                acting_unit = next_unit
                selected_party_member = acting_unit if acting_unit in party_members else None
                
                # ターン開始時のバフ/デバフ更新
                if acting_unit.current_hp > 0:
                    acting_unit.check_and_decay_effects(current_turn_count)
                    print(f"--- ターン {current_turn_count} 開始: {acting_unit.name} ---")
                    current_turn_count += 1
                else:
                    acting_unit = None 
                    continue
                
                if acting_unit in party_members:
                    # プレイヤーユニットの行動開始: コマンド選択へ
                    preview_turn_order_list=None
                    selected_target = enemies[0] if enemies else None
                    selected_action_index = 0
                    action_is_selected = True
                    current_state = STATE_COMMAND
                else:
                    # 敵ユニットの行動 (自動) -> アニメーションへ移行
                    current_state = STATE_ANIMATION 
                    enemy_attacker = acting_unit
                    if enemy_attacker.current_hp > 0 and party_members:
                        
                        active_party_members = [m for m in party_members if m.current_hp > 0]
                        if active_party_members:
                            target_member = random.choice(active_party_members)
                            target_list = [target_member] # 敵は単体攻撃のみ（現状の想定）
                        else:
                            current_state = STATE_COMMAND 
                            enemy_attacker.next_action_time = enemy_attacker.speed_act_time
                            turn_order_list = get_turn_order_list(all_units)
                            acting_unit = None
                            continue

                        attack_action = enemy_attacker.normal_attack[0] if enemy_attacker.normal_attack else make_action("通常攻撃", power=1.0)
                        
                        is_crit = False
                        is_weak = False
                        target_member.combat_stats['break_bonus'] = 1.0
                        
                        calculated_damage = calculate_damage(
                            enemy_attacker, target_member, attack_action.get("power", 1.0), is_crit, is_weak
                        )
                        calculated_damage = max(10, calculated_damage)
                        
                        attacker_rect = enemy_rects.get(enemy_attacker.cid)

                        # アニメーション情報の設定
                        attacking_unit_info = {
                            'attacker': enemy_attacker,
                            'targets': target_list,
                            'action_name': attack_action.get('name', '攻撃'),
                            'start_pos': attacker_rect.topleft if attacker_rect else (0, 0),
                            'current_pos': attacker_rect.topleft if attacker_rect else (0, 0),
                            'is_player': False,
                            'state': 'move_to_target',
                            'target_pos': get_target_center_pos(target_list, False, enemy_attacker.cid), 
                            'action_name_timer': SKILL_NAME_DURATION,
                            'damage_data': {
                                'damage': calculated_damage,
                                'is_crit': is_crit,
                                'is_enemy_target': False,
                                'action_executed': False,
                            },
                            # 敵の行動時のHP適用はアニメーション後に行うため、コールバックとして設定
                            'post_action_cleanup': lambda: target_member.current_hp <= 0 and None 
                        }
                    else:
                        current_state = STATE_COMMAND 
                        acting_unit = None


            elif next_unit and time_to_act > 1e-9:
                for unit in all_units:
                    if unit.next_action_time != float("inf"):
                        unit.next_action_time -= time_to_act
                turn_order_list = get_turn_order_list(all_units)

        # 2. アニメーション処理 (メインループ内で毎フレーム実行)
        if current_state == STATE_ANIMATION and attacking_unit_info:
            info = attacking_unit_info
            
            attacker_rect_base = party_rects.get(info['attacker'].cid) if info['is_player'] else enemy_rects.get(info['attacker'].cid)
            
            if not attacker_rect_base:
                current_state = STATE_COMMAND 

            # --- A. 移動アニメーション ---
            if info['state'] == 'move_to_target' or info['state'] == 'move_back':
                target_x, target_y = info['target_pos'] if info['state'] == 'move_to_target' else attacker_rect_base.topleft
                current_x, current_y = info['current_pos']
                
                dist = math.hypot(target_x - current_x, target_y - current_y)
                
                if dist > ANIMATION_SPEED:
                    angle = math.atan2(target_y - current_y, target_x - current_x)
                    move_x = ANIMATION_SPEED * math.cos(angle)
                    move_y = ANIMATION_SPEED * math.sin(angle)
                    
                    info['current_pos'] = (current_x + move_x, current_y + move_y)
                else:
                    info['current_pos'] = (target_x, target_y)

                if info['current_pos'] == (target_x, target_y):
                    if info['state'] == 'move_to_target':
                        # 攻撃位置に到着 -> 攻撃フェーズへ
                        info['state'] = 'attack'
                        info['timer'] = ATTACK_DURATION
                        
                        # 攻撃ロジックを実行 (ダメージをここで適用)
                        if not info['damage_data']['action_executed']:
                            damage = info['damage_data']['damage']
                            is_crit = info['damage_data']['is_crit']
                            is_enemy_target = info['damage_data']['is_enemy_target']
                            attacker = info['attacker']
                            
                            # ダメージテキストを追加
                            for target_unit in info['targets']:
                                add_damage_text(target_unit, damage, is_crit, is_enemy_target, attacker)
                                
                                # HP/ゲージの最終適用
                                # プレイヤー行動時のダメージ適用は、ボタンクリック時に行われている（必殺技、通常スキル）
                                # 敵の通常攻撃のみここでHPを適用
                                if not info['is_player']: 
                                    target_unit.current_hp = max(0, target_unit.current_hp - damage)
                                    
                            info['damage_data']['action_executed'] = True
                            
                    elif info['state'] == 'move_back':
                        # 帰還位置に到着 -> ターン終了
                        info['state'] = 'finished'
                        
            # --- B. 攻撃フェーズ ---
            elif info['state'] == 'attack':
                info['timer'] -= 1
                if info['timer'] <= 0:
                    # 攻撃終了 -> 帰還移動へ
                    info['state'] = 'move_back'
                    info['target_pos'] = attacker_rect_base.topleft
            
            # --- C. ターン終了処理 ---
            elif info['state'] == 'finished':
                # 撃破後の処理（コールバックを実行）
                if info.get('post_action_cleanup'):
                    info['post_action_cleanup']()
                
                # ユニットを行動終了としてマーク (次ターン開始時に自動的に行われるため、ここでは不要だが念のため)
                info['attacker'].next_action_time = info['attacker'].speed_act_time
                
                # グローバル変数をリセット
                attacking_unit_info = None
                acting_unit = None 
                selected_action_index = 0
                action_is_selected = False
                selected_party_member = None
                turn_order_list = get_turn_order_list(all_units)
                current_state = STATE_COMMAND 

        # 3. イベント処理 (STATE_COMMAND の場合のみ、アクションボタン/ターゲットのクリックを受け付ける)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if current_state == STATE_COMMAND and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                click_pos = event.pos
                
                # --- 必殺技の即時発動判定 ---
                is_ult_executed = False
                for member in party_members:
                    rect = party_rects.get(member.cid)
                    if rect and rect.collidepoint(click_pos):
                        
                        is_ultimate_unit = (member.current_mp >= member.mp_max)
                        ultimate_action = member.get_ultimate_action()
                        
                        if is_ultimate_unit and ultimate_action:
                            target_enemy = selected_target if selected_target and selected_target.current_hp > 0 else enemies[0] if enemies else None
                            if target_enemy is None: continue
                            
                            # ★ 修正: UnboundLocalError を避けるため、target_listをここで定義
                            target_meta = ultimate_action.get("meta", {}).get("target", "単体")
                            target_list: List[Character] = [] 
                            if target_meta == "味方全体": target_list = [m for m in party_members if m.current_hp > 0]
                            elif target_meta == "敵全体": target_list = [e for e in enemies if e.current_hp > 0]
                            elif target_meta == "単体" and target_enemy: target_list.append(target_enemy)
                            elif target_meta == "自バフ": target_list.append(member)
                            elif target_meta == "味方単体": target_list.append(member)
                            
                            # コスト消費
                            mp_cost = ultimate_action.get("meta", {}).get("cost_mp", 0.0)
                            if mp_cost > 0.0: member.current_mp = max(0, member.current_mp - mp_cost)
                            member.add_mp(MP_INCREASE_ULT_AFTER)
                            # バフ適用ロジック
                            buff_debuffs_list = ultimate_action.get("meta", {}).get("buff_debuffs", [])
                            is_attacker_player = member in party_members 

                            for effect_data in buff_debuffs_list:
                                target_meta_override = effect_data.get("target") or ultimate_action.get("meta", {}).get("target", "単体")
                                effect_type = effect_data.get("type", "")
                                
                                target_list_base: List[Character] = []
                                # アクションのターゲット設定に基づくベースリストの決定
                                if target_meta_override in ["味方全体", "全体"]: target_list_base = [m for m in party_members if m.current_hp > 0]
                                elif target_meta_override in ["敵全体", "全体"]: target_list_base = [e for e in enemies if e.current_hp > 0]
                                elif target_meta_override in ["単体", "敵単体"] and target_enemy: target_list_base.append(target_enemy)
                                elif target_meta_override in ["自バフ", "味方単体"]: target_list_base.append(member)
                                
                                # 攻撃者の陣営と効果タイプに基づき、適用ターゲットをフィルタリング
                                filtered_targets = []
                                is_buff = ("UP" in effect_type) 
                                is_debuff = ("DOWN" in effect_type)
                                
                                for t in target_list_base:
                                    if is_buff and (t in party_members) == is_attacker_player:
                                        filtered_targets.append(t)
                                    elif is_debuff and (t in party_members) != is_attacker_player:
                                        filtered_targets.append(t)

                                # 各ターゲットに効果を適用
                                for t in filtered_targets:
                                    member.apply_effect_from_action(ultimate_action, t, current_turn_count)
                            
                            # ダメージ計算 (単体攻撃を想定)
                            skill_power = ultimate_action.get("power", 0.0)
                            break_dmg = ultimate_action.get("break_gauge", 0.0)
                            is_crit = (time.time() * 100 % 100) < 50
                            is_weak = True
                            if target_enemy.current_break_gauge <= 0: target_enemy.combat_stats['break_bonus'] = 2.0
                            else: target_enemy.combat_stats['break_bonus'] = 1.0
                            calculated_damage = calculate_damage(member, target_enemy, skill_power, is_crit, is_weak)

                            # --- 撃破処理 (アニメーション後のコールバックとして設定) ---
                            def cleanup_ult():
                                global enemies, all_units, party_rects, enemy_rects, turn_order_list, selected_target
                                if target_enemy.current_hp <= 0:
                                    target_cid_to_remove = target_enemy.cid 
                                    enemies = [e for e in enemies if e.current_hp > 0]
                                    all_units = party_members + enemies                               
                                    party_rects = get_party_unit_rects(party_members)
                                    enemy_rects = get_enemy_unit_rects(enemies)                              
                                    turn_order_list = [
                                        (unit, time) for unit, time in turn_order_list if unit.cid != target_cid_to_remove
                                    ]                           
                                    for party_member in party_members:
                                        party_member.add_mp(MP_INCREASE_DEFEAT)                             
                                    if selected_target and target_enemy.cid == selected_target.cid:
                                        selected_target = enemies[0] if enemies else None
                                print(f"味方行動ログ: {member.name} が必殺技 '{ultimate_action['name']}' を即時発動")
                                
                            # ダメージ適用はアニメーションの「攻撃フェーズ」に移動
                            target_enemy.current_hp = max(0, target_enemy.current_hp - calculated_damage)
                            target_enemy.current_break_gauge = max(0, target_enemy.current_break_gauge - break_dmg)
                            
                            # アニメーションへ移行
                            current_state = STATE_ANIMATION
                            attacker_rect = party_rects.get(member.cid)
                            
                            attacking_unit_info = {
                                'attacker': member,
                                'targets': [target_enemy], 
                                'action_name': ultimate_action.get('name', '必殺技'),
                                'start_pos': attacker_rect.topleft,
                                'current_pos': attacker_rect.topleft,
                                'is_player': True,
                                'state': 'move_to_target',
                                'target_pos': get_target_center_pos(target_list, True, member.cid), 
                                'action_name_timer': SKILL_NAME_DURATION,
                                'damage_data': {
                                    'damage': calculated_damage,
                                    'is_crit': is_crit,
                                    'is_enemy_target': True,
                                    'action_executed': False, 
                                },
                                'post_action_cleanup': cleanup_ult
                            }
                            is_ult_executed = True
                            if acting_unit: acting_unit = None 
                            break

                if is_ult_executed:
                    continue 

                # --- 通常の行動選択・実行ロジック (acting_unit が味方でいる場合のみ) ---
                # main 関数内、通常スキル実行ブロック (該当部分のみ)

                # --- 通常の行動選択・実行ロジック (acting_unit が味方でいる場合のみ) ---
                if acting_unit and acting_unit in party_members:
                    attacker = acting_unit
                    current_actions = attacker.get_all_actions()
                    action_button_centers = get_action_button_centers(len(current_actions))
                    
                    action_clicked_index = -1
                    # ★ 修正: UnboundLocalError を避けるため、ここで初期化
                    target_list: List[Character] = [] 
                    
                    for i, center in enumerate(action_button_centers):
                        distance = math.hypot(click_pos[0] - center[0], click_pos[1] - center[1])
                        current_radius = int(ACTION_BUTTON_RADIUS * (1.05 if action_is_selected and i == selected_action_index else 1.0))
                        if distance <= current_radius:
                            action_clicked_index = i
                            break

                    if action_clicked_index != -1:
                        clicked_action = current_actions[action_clicked_index]
                        mp_cost = clicked_action.get("meta", {}).get("cost_mp", 0.0)
                        is_affordable = attacker.current_mp >= mp_cost
                        
                        is_skill = "戦闘スキル" in clicked_action.get("type", "") or "skill" in clicked_action.get("type", "")
                        is_normal = "通常攻撃" in clicked_action.get("type", "") or "normal_attack" in clicked_action.get("type", "")
                        
                        sp_cost = 1 if is_skill else 0
                        is_sp_affordable = current_sp >= sp_cost 

                        final_affordable = is_affordable and is_sp_affordable

                        # ★ 修正: target_list の定義 (clicked_action が確定した後)
                        target_meta = clicked_action.get("meta", {}).get("target", "単体")
                        if target_meta == "味方全体": target_list = [m for m in party_members if m.current_hp > 0]
                        elif target_meta == "敵全体": target_list = [e for e in enemies if e.current_hp > 0]
                        elif target_meta == "単体" and selected_target: target_list.append(selected_target)
                        elif target_meta == "自バフ": target_list.append(attacker)
                        elif target_meta == "味方単体": target_list.append(selected_party_member or attacker)


                        # アクション実行
                        if action_is_selected and selected_action_index == action_clicked_index and final_affordable:
                            target_enemy = selected_target
                            if target_enemy is None: continue
                            
                            # コスト消費/リソース変化
                            if mp_cost > 0.0: attacker.current_mp = max(0, attacker.current_mp - mp_cost)
                            
                            if is_skill:
                                change_global_sp(-1) 
                                attacker.add_mp(MP_INCREASE_SKILL) 
                                print(f"味方行動ログ: {attacker.name} が戦闘スキル '{clicked_action['name']}' を実行 (SP消費: -1)")
                            elif is_normal:
                                change_global_sp(1) 
                                attacker.add_mp(MP_INCREASE_NORMAL) 
                                print(f"味方行動ログ: {attacker.name} が通常攻撃を実行 (SP増加: +1)")
                            
                            attacker.next_action_time = attacker.speed_act_time
                            
                            # ダメージ計算
                            skill_power = clicked_action.get("power", 0.0)
                            break_dmg = clicked_action.get("break_gauge", 0.0)
                            is_crit = (time.time() * 100 % 100) < 20
                            is_weak = True
                            if target_enemy.current_break_gauge <= 0: target_enemy.combat_stats['break_bonus'] = 2.0
                            else: target_enemy.combat_stats['break_bonus'] = 1.0
                            
                            calculated_damage = calculate_damage(attacker, target_enemy, skill_power, is_crit, is_weak)

                            # スキルによるバフの適用ロジック
                            buff_debuffs_list = clicked_action.get("meta", {}).get("buff_debuffs", [])
                            is_attacker_player = attacker in party_members 
                            
                            ATTACKER_ALLIES = party_members if is_attacker_player else enemies
                            ATTACKER_FOES = enemies if is_attacker_player else party_members

                            for effect_data in buff_debuffs_list:
                                target_meta_override = effect_data.get("target") or clicked_action.get("meta", {}).get("target", "単体")
                                effect_type = effect_data.get("type", "")

                                target_list_base: List[Character] = []
                                
                                # ターゲットの決定: スキル使用者（attacker）の視点から「味方」「敵」を解釈
                                if target_meta_override in ["味方全体", "全体"]: 
                                    target_list_base = [u for u in ATTACKER_ALLIES if u.current_hp > 0]
                                elif target_meta_override in ["敵全体"]: 
                                    target_list_base = [u for u in ATTACKER_FOES if u.current_hp > 0]
                                elif target_meta_override in ["単体", "敵単体"] and target_enemy: 
                                    target_list_base.append(target_enemy)
                                elif target_meta_override in ["自バフ", "味方単体"]: 
                                    target_list_base.append(attacker)
                                
                                # 攻撃者の陣営と効果タイプに基づき、適用ターゲットをフィルタリング
                                filtered_targets = []
                                is_buff = ("UP" in effect_type) 
                                is_debuff = ("DOWN" in effect_type)
                                
                                for t in target_list_base:
                                    if is_buff and t in ATTACKER_ALLIES:
                                        filtered_targets.append(t)
                                    elif is_debuff and t in ATTACKER_FOES:
                                        filtered_targets.append(t)

                                # 各ターゲットに効果を適用
                                for t in filtered_targets:
                                    attacker.apply_effect_from_action(clicked_action, t, current_turn_count)
                            
                            # --- 撃破処理 (アニメーション後のコールバックとして設定) ---z
                            def cleanup_normal():
                                global enemies, all_units, party_rects, enemy_rects, selected_target,turn_order_list
                                if target_enemy.current_hp <= 0:
                                    # 修正: turn_order_list をグローバル宣言に追加
                                    target_cid_to_remove = target_enemy.cid
                                    enemies = [e for e in enemies if e.current_hp > 0]
                                    all_units = party_members + enemies                                   
                                    party_rects = get_party_unit_rects(party_members)
                                    enemy_rects = get_enemy_unit_rects(enemies)                                   
                                    # 3. turn_order_list から死亡キャラをフィルタリングして削除
                                    turn_order_list=[]
                                    turn_order_list = [
                                        (unit, time) for unit, time in turn_order_list if unit.cid != target_cid_to_remove
                                    ]                           
                                    for member in party_members:
                                        member.add_mp(MP_INCREASE_DEFEAT)                                       
                                    if selected_target and target_enemy.cid == selected_target.cid:
                                        selected_target = enemies[0] if enemies else None
                                global preview_turn_order_list
                                preview_turn_order_list = None
                            
                            # ダメージ適用はアニメーションの「攻撃フェーズ」に移動
                            target_enemy.current_hp = max(0, target_enemy.current_hp - calculated_damage)
                            target_enemy.current_break_gauge = max(0, target_enemy.current_break_gauge - break_dmg)
                            
                            # アニメーションへ移行
                            current_state = STATE_ANIMATION
                            attacker_rect = party_rects.get(attacker.cid)
                            
                            attacking_unit_info = {
                                'attacker': attacker,
                                'targets': [target_enemy], 
                                'action_name': clicked_action.get('name', '攻撃'),
                                'start_pos': attacker_rect.topleft,
                                'current_pos': attacker_rect.topleft,
                                'is_player': True,
                                'state': 'move_to_target',
                                'target_pos': get_target_center_pos(target_list, True, attacker.cid), 
                                'action_name_timer': SKILL_NAME_DURATION,
                                'damage_data': {
                                    'damage': calculated_damage,
                                    'is_crit': is_crit,
                                    'is_enemy_target': True,
                                    'action_executed': False, 
                                },
                                'post_action_cleanup': cleanup_normal
                            }
                            continue 

                        # アクション選択/再選択
                        elif action_clicked_index != selected_action_index or not final_affordable:
                            selected_action_index = action_clicked_index
                            action_is_selected = True
                            
                            preview_turn_order_list = None

                            # ★ プレビューロジック: 選択されたアクションが行動順に影響する場合
                            buff_debuffs = clicked_action.get("meta", {}).get("buff_debuffs", [])
                            is_speed_buff = any("行動順" in effect.get("type", "") or "スピード" in effect.get("type", "") for effect in buff_debuffs)

                            if is_speed_buff:
                                # プレビューリストを生成
                                preview_turn_order_list = get_preview_turn_order_list(
                                    all_units, 
                                    clicked_action, 
                                    attacker, 
                                    selected_target
                                )
                            else:
                                # 影響しない場合はクリア
                                preview_turn_order_list = None
                            continue

                    # ターゲット選択 (行動中ユニットのターンでアイコンをクリックした際の処理)
                    for enemy in enemies:
                        rect = enemy_rects.get(enemy.cid)
                        if rect:
                            icon_center = (rect.x + UNIT_ICON_SIZE // 2, rect.y + UNIT_ICON_SIZE // 2)
                            distance = math.hypot(click_pos[0] - icon_center[0], click_pos[1] - icon_center[1])
                            if distance <= UNIT_ICON_SIZE // 2:
                                selected_target = enemy
                                clicked_action = current_actions[selected_action_index]
                                buff_debuffs = clicked_action.get("meta", {}).get("buff_debuffs", [])
                                is_speed_buff = any("行動順" in effect.get("type", "") or "スピード" in effect.get("type", "") for effect in buff_debuffs)
                                
                                if is_speed_buff:
                                     preview_turn_order_list = get_preview_turn_order_list(
                                        all_units, 
                                        clicked_action, 
                                        attacker, 
                                        selected_target
                                    )
                                else:
                                    preview_turn_order_list = None

                                break
                    
                # ターゲット選択 (行動中でない場合に敵アイコンをクリックした際の処理)
                else:
                    for enemy in enemies:
                        rect = enemy_rects.get(enemy.cid)
                        if rect:
                            icon_center = (rect.x + UNIT_ICON_SIZE // 2, rect.y + UNIT_ICON_SIZE // 2)
                            distance = math.hypot(click_pos[0] - icon_center[0], click_pos[1] - icon_center[1])
                            if distance <= UNIT_ICON_SIZE // 2:
                                selected_target = enemy
                                preview_turn_order_list = None 
                                break

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
        
        # 4. ダメージテキストの更新とクリーンアップ
        updated_damage_texts = []
        for text_data in damage_texts:
            text_data["time_left"] -= 1
            text_data["pos"][1] -= DAMAGE_TEXT_SPEED
            if text_data["time_left"] > 0:
                updated_damage_texts.append(text_data)
        damage_texts = updated_damage_texts


        # 5. 描画
        screen.fill(BG_COLOR)

        party_rects = get_party_unit_rects(party_members)
        enemy_rects = get_enemy_unit_rects(enemies)

        if current_state == STATE_COMMAND and preview_turn_order_list:
            draw_turn_order(screen, preview_turn_order_list)
        else:
            draw_turn_order(screen, turn_order_list)

        # ユニット描画
        all_units_list = enemies + party_members 
        for unit in all_units_list:
            is_enemy = unit in enemies
            rects_dict = enemy_rects if is_enemy else party_rects
            rect = rects_dict.get(unit.cid)

            # アニメーション中のユニットは、グローバル位置情報で描画するためスキップ
            if attacking_unit_info and unit.cid == attacking_unit_info['attacker'].cid:
                 continue
            
            if rect:
                is_highlighted = (selected_target and selected_target.cid == unit.cid)
                is_acting = (acting_unit and acting_unit.cid == unit.cid and current_state == STATE_COMMAND) 
                draw_unit_icon(screen, unit, rect, is_highlighted, is_enemy, is_acting)

        if acting_unit and acting_unit in party_members and action_is_selected and current_state == STATE_COMMAND:
            # コマンド選択中のUI
            draw_sp_gauge(screen)
            
            current_actions = acting_unit.get_all_actions()
            action_button_centers = get_action_button_centers(len(current_actions))
            for i, center in enumerate(action_button_centers):
                action = current_actions[i]
                mp_cost = action.get("meta", {}).get("cost_mp", 0.0)
                is_affordable = acting_unit.current_mp >= mp_cost
                is_selected = (i == selected_action_index)
                
                draw_action_button(screen, center, ACTION_BUTTON_RADIUS, action, is_selected, is_affordable)

        # --- アニメーション中のユニット描画 (最前面) ---
        if current_state == STATE_ANIMATION and attacking_unit_info:
             info = attacking_unit_info
             attacker = info['attacker']
             is_player = info['is_player']
             
             # 現在位置に描画
             current_pos = info['current_pos']
             unit_rect = pygame.Rect(current_pos[0], current_pos[1], UNIT_ICON_SIZE, UNIT_CARD_TOTAL_H)
             
             is_highlighted = (selected_target and selected_target.cid == attacker.cid)
             draw_unit_icon(screen, attacker, unit_rect, is_highlighted, not is_player, True) 

             # スキル名描画
             draw_action_name(screen, info['action_name'])
             
        # --- ダメージテキストの描画 ---
        draw_damage_texts(screen, damage_texts)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()