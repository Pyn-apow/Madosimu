import json
import streamlit as st

# ── データ読み込み（キャッシュで高速化） ──────────
@st.cache_data
def load_characters(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["name"]: c for c in data}

# ── メイン ────────────────────────────────────
st.title("ダメージシミュレーター")

roster = load_characters("characters.json")

# セレクトボックスでキャラ選択
selected_name = st.selectbox("キャラクターを選択", list(roster.keys()))

# 選択されたキャラのデータを取得
chara = roster[selected_name]

# 基本ステータスを表示
st.subheader(f"{chara['name']}")
col1, col2 = st.columns(2)
col1.metric("ATK", chara["atk"])
col2.metric("SPD", chara["speed"])

Ability_Damage_Base = ability_multiplier * base_atk * ((base_atk / 124) ^ 1.2 + 12) / 20
Defense_Factor = min((total_atk + 10) / (total_def + 10) * 0.12,2)
Critical_Factor = 1 + crit_dmg
Damage_Dealt_Factor = 1 + dmg_dealt
Damage_Taken_Factor = 1 + dmg_taken
Elemental_Resistance_Factor = 1 - ele_res
Effective_Element_Factor = 1.2 + ele_advantage_dmg_up
Break_Factor = BREAK