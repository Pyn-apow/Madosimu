# home.py - ホーム画面とガチャ機能

from __future__ import annotations
from typing import List, Optional, Dict, Any, Tuple
import json
import pygame
import sys
import os
import subprocess
import random

# --- 定数 ---
SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 600
BG_COLOR = (30, 30, 60)
FONT_COLOR = (255, 255, 255)
BUTTON_COLOR = (50, 50, 90)
BUTTON_HIGHLIGHT_COLOR = (80, 80, 130)
DIAMOND_COLOR = (100, 200, 255)
GACHA_RESULT_OVERLAY_COLOR = (0, 0, 0, 180) # 半透明の黒

# レアリティごとの色
RARITY_COLORS = {
    "5": (255, 215, 0),  # 金色
    "4": (200, 50, 255),   # 紫色
    "3": (50, 150, 255),   # 青色
}

# --- Pygame 初期化 ---
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("ホーム画面")
clock = pygame.time.Clock()

# フォントの読み込み
font_path = "noto.ttf"
try:
    font_l = pygame.font.Font(font_path, 48)
    font_m = pygame.font.Font(font_path, 30)
    font_s = pygame.font.Font(font_path, 24)
    font_xs = pygame.font.Font(font_path, 18)
except Exception:
    font_l = pygame.font.Font(None, 48)
    font_m = pygame.font.Font(None, 30)
    font_s = pygame.font.Font(None, 24)
    font_xs = pygame.font.Font(None, 18)

# --- データ管理 ---
def load_player_data(filename="player_data.json") -> Dict[str, Any]:
    """プレイヤーデータ（ダイヤ、所持キャラ）をロードする。なければ新規作成。"""
    if not os.path.exists(filename):
        # プレイヤーデータが存在しない場合、初期データを作成
        default_data = {"diamonds": 5000, "roster": []}
        save_player_data(default_data, filename)
        return default_data
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        # ファイルが破損している場合も初期データを作成
        default_data = {"diamonds": 5000, "roster": []}
        save_player_data(default_data, filename)
        return default_data

def save_player_data(data: Dict[str, Any], filename="player_data.json"):
    """プレイヤーデータを保存する。"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_all_characters(filename="characters.json") -> List[Dict[str, Any]]:
    """ガチャの排出対象となる全キャラクターをロードする。"""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print(f"エラー: {filename} が見つからないか、形式が不正です。")
        return []

# --- ガチャのロジック ---
def perform_gacha(num_pulls: int, all_characters_pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """指定された回数ガチャを回し、結果のキャラクターリストを返す。"""
    if not all_characters_pool:
        return []

    # レアリティごとにキャラクターを分類
    pool_by_rarity = {"3": [], "4": [], "5": []}
    for char in all_characters_pool:
        rarity = char.get("rarity", "3")
        if rarity in pool_by_rarity:
            pool_by_rarity[rarity].append(char)
            
    results = []
    # 確率に基づいてレアリティを決定
    rarities = ["5", "4", "3"]
    weights = [3, 17, 80] # 確率
    
    chosen_rarities = random.choices(rarities, weights=weights, k=num_pulls)
    
    # 各レアリティからランダムにキャラクターを選択
    for rarity in chosen_rarities:
        if pool_by_rarity[rarity]:
            chosen_char = random.choice(pool_by_rarity[rarity])
            results.append(chosen_char)
            
    return results

# --- 描画関数 ---
def draw_button(surface: pygame.Surface, text: str, rect: pygame.Rect, font: pygame.font.Font, enabled: bool = True):
    """汎用的なボタンを描画する。"""
    mouse_pos = pygame.mouse.get_pos()
    color = BUTTON_COLOR
    if enabled and rect.collidepoint(mouse_pos):
        color = BUTTON_HIGHLIGHT_COLOR
    
    pygame.draw.rect(surface, color, rect, border_radius=10)
    
    text_color = FONT_COLOR if enabled else (100, 100, 100)
    text_surf = font.render(text, True, text_color)
    text_rect = text_surf.get_rect(center=rect.center)
    surface.blit(text_surf, text_rect)

def draw_diamond_display(surface: pygame.Surface, diamonds: int):
    """ダイヤの所持数を画面右上に表示する。"""
    text = f"♦ {diamonds}"
    text_surf = font_m.render(text, True, DIAMOND_COLOR)
    text_rect = text_surf.get_rect(topright=(SCREEN_WIDTH - 20, 20))
    surface.blit(text_surf, text_rect)

def draw_home_screen(surface: pygame.Surface, diamonds: int):
    """ホーム画面を描画する。"""
    surface.fill(BG_COLOR)
    draw_diamond_display(surface, diamonds)
    
    title_surf = font_l.render("ホーム", True, FONT_COLOR)
    title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 100))
    surface.blit(title_surf, title_rect)
    
    draw_button(surface, "パーティ編成", party_button_rect, font_m)
    draw_button(surface, "ガチャ", gacha_button_rect, font_m)
    
def draw_gacha_screen(surface: pygame.Surface, diamonds: int):
    """ガチャ画面を描画する。"""
    surface.fill(BG_COLOR)
    draw_diamond_display(surface, diamonds)

    title_surf = font_l.render("ガチャ", True, FONT_COLOR)
    title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 100))
    surface.blit(title_surf, title_rect)
    
    # ボタンの有効/無効を判定
    can_pull_1 = diamonds >= 300
    can_pull_10 = diamonds >= 3000

    draw_button(surface, "1回ガチャ (♦ 300)", gacha_pull1_rect, font_s, enabled=can_pull_1)
    draw_button(surface, "10回ガチャ (♦ 3000)", gacha_pull10_rect, font_s, enabled=can_pull_10)
    draw_button(surface, "戻る", back_button_rect, font_s)
    
def draw_gacha_result_screen(surface: pygame.Surface, results: List[Dict[str, Any]]):
    """ガチャ結果画面を描画する。"""
    # 背景に半透明のオーバーレイ
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill(GACHA_RESULT_OVERLAY_COLOR)
    surface.blit(overlay, (0, 0))

    title_surf = font_m.render("ガチャ結果", True, FONT_COLOR)
    title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 50))
    surface.blit(title_surf, title_rect)

    # キャラクターカードの描画
    card_w, card_h = 150, 50
    start_x = (SCREEN_WIDTH - 5 * card_w - 4 * 20) // 2
    start_y = 120
    
    for i, char in enumerate(results):
        row = i // 5
        col = i % 5
        x = start_x + col * (card_w + 20)
        y = start_y + row * (card_h + 20)
        
        card_rect = pygame.Rect(x, y, card_w, card_h)
        rarity_color = RARITY_COLORS.get(char.get("rarity", "3"), (100, 100, 100))
        pygame.draw.rect(surface, (40, 40, 70), card_rect)
        pygame.draw.rect(surface, rarity_color, card_rect, 3)

        char_name = f"★{char['rarity']} {char['name']}"
        name_surf = font_xs.render(char_name, True, FONT_COLOR)
        name_rect = name_surf.get_rect(center=card_rect.center)
        surface.blit(name_surf, name_rect)

    draw_button(surface, "確認", confirm_button_rect, font_s)

# --- メインループ ---
if __name__ == "__main__":
    
    # データのロード
    player_data = load_player_data()
    all_characters_pool = load_all_characters()
    
    # 画面の状態管理
    current_screen = "HOME" # "HOME", "GACHA", "GACHA_RESULT"
    
    # UI要素のRect
    party_button_rect = pygame.Rect(SCREEN_WIDTH // 2 - 150, 200, 300, 60)
    gacha_button_rect = pygame.Rect(SCREEN_WIDTH // 2 - 150, 280, 300, 60)
    
    gacha_pull1_rect = pygame.Rect(SCREEN_WIDTH // 2 - 150, 200, 300, 60)
    gacha_pull10_rect = pygame.Rect(SCREEN_WIDTH // 2 - 150, 280, 300, 60)
    back_button_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, 400, 200, 50)
    
    confirm_button_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, SCREEN_HEIGHT - 80, 200, 50)
    
    gacha_results = []

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_pos = event.pos
                
                # --- 画面ごとのクリック処理 ---
                if current_screen == "HOME":
                    if party_button_rect.collidepoint(mouse_pos):
                        print("パーティ編成画面へ")
                        # party.py を実行
                        try:
                            subprocess.run([sys.executable, "party.py"], check=True)
                            # 戻ってきたらプレイヤーデータを再読み込み（キャラクターが増えている可能性があるため）
                            player_data = load_player_data()
                        except Exception as e:
                            print(f"party.pyの起動に失敗しました: {e}")
                            
                    elif gacha_button_rect.collidepoint(mouse_pos):
                        print("ガチャ画面へ")
                        current_screen = "GACHA"
                        
                elif current_screen == "GACHA":
                    if back_button_rect.collidepoint(mouse_pos):
                        current_screen = "HOME"
                    
                    elif gacha_pull1_rect.collidepoint(mouse_pos) and player_data["diamonds"] >= 300:
                        player_data["diamonds"] -= 300
                        gacha_results = perform_gacha(1, all_characters_pool)
                        player_data["roster"].extend(gacha_results)
                        save_player_data(player_data)
                        current_screen = "GACHA_RESULT"
                        
                    elif gacha_pull10_rect.collidepoint(mouse_pos) and player_data["diamonds"] >= 3000:
                        player_data["diamonds"] -= 3000
                        gacha_results = perform_gacha(10, all_characters_pool)
                        player_data["roster"].extend(gacha_results)
                        save_player_data(player_data)
                        current_screen = "GACHA_RESULT"

                elif current_screen == "GACHA_RESULT":
                    if confirm_button_rect.collidepoint(mouse_pos):
                        current_screen = "GACHA"

        # --- 描画処理 ---
        screen.fill(BG_COLOR)
        
        if current_screen == "HOME":
            draw_home_screen(screen, player_data["diamonds"])
        elif current_screen == "GACHA":
            draw_gacha_screen(screen, player_data["diamonds"])
        elif current_screen == "GACHA_RESULT":
            # Gacha画面を背景に描画してから結果を表示
            draw_gacha_screen(screen, player_data["diamonds"])
            draw_gacha_result_screen(screen, gacha_results)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()