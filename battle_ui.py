import json
import streamlit as st

# ── データ読み込み（キャッシュで高速化） ──────────
@st.cache_data
def load_characters(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["name"]: c for c in data}

def calculate_damage(ability_multiplier,base_atk,total_atk,total_def,dmg_dealt,dmg_taken,ele_res, ele_advantage_dmg):
    Ability_Damage_Base = ability_multiplier * base_atk * ((base_atk / 124) ** 1.2 + 12) / 20
    Defense_Factor = min((total_atk + 10) / (total_def + 10) * 0.12,2)
    Damage_Dealt_Factor = 1 + dmg_dealt
    Damage_Taken_Factor = 1 + dmg_taken
    Elemental_Resistance_Factor = 1 - ele_res
    Effective_Element_Factor = 1.2 + ele_advantage_dmg
    Break_Factor = BREAK/100
    return Ability_Damage_Base * Defense_Factor * Damage_Dealt_Factor * Damage_Taken_Factor * Elemental_Resistance_Factor * Effective_Element_Factor * Break_Factor

def get_all_buff_debuffs(chara: dict) -> list:
    all_bd = []

    # ultimate
    for ult in chara.get("ultimate", []):
        all_bd.extend(ult.get("meta", {}).get("buff_debuffs", []))

    # battle_skills
    for skill in chara.get("battle_skills", []):
        all_bd.extend(skill.get("meta", {}).get("buff_debuffs", []))

    # abilities（metaがなく直接buff_debuffsを持つ）
    for ability in chara.get("abilities", []):
        all_bd.extend(ability.get("buff_debuffs", []))

    return all_bd

# ── メイン ────────────────────────────────────
st.title("""魔法少女比較シミュレーター
         ※これは正確なダメージを計算するものではありません。また、すべてのバフ・デバフが発動している状態を想定しています。""")

roster = load_characters("characters.json")

# セレクトボックスでキャラ選択
attacker = st.selectbox("メインアタッカーを選択", [name for name, c in roster.items() if c.get("role") == "attacker"])
bd1 = st.selectbox("バッファー・デバッファーを選択", ["なし"] + [name for name, c in roster.items() if c.get("role") == "buffer" or c.get("role") == "debuffer"],key="bd1")
bd2 = st.selectbox("バッファー・デバッファーを選択", ["なし"] + [name for name, c in roster.items() if c.get("role") == "buffer" or c.get("role") == "debuffer"],key="bd2")
bd3 = st.selectbox("バッファー・デバッファーを選択", ["なし"] + [name for name, c in roster.items() if c.get("role") == "buffer" or c.get("role") == "debuffer"],key="bd3")
bd4 = st.selectbox("バッファー・デバッファーを選択", ["なし"] + [name for name, c in roster.items() if c.get("role") == "buffer" or c.get("role") == "debuffer"],key="bd4")
BREAK = st.slider("敵のブレイクボーナス（魔法少女同士の比較には影響しません）", min_value=100, max_value=999, value=1)
DEFENCE = st.number_input("敵の防御力", min_value=0.0, max_value=100000.0, value=1.0)

# 選択されたキャラのデータを取得
chara1 = roster[attacker]
chara2 = roster.get(bd1) if bd1 != "なし" else None
chara3 = roster.get(bd2) if bd2 != "なし" else None
chara4 = roster.get(bd3) if bd3 != "なし" else None
chara5 = roster.get(bd4) if bd4 != "なし" else None

all_bd = []
for i in [chara1,chara2,chara3,chara4,chara5]:
    all_bd += get_all_buff_debuffs(i) if i is not None else []

atk_buff_value = 0
atk_buff = [i for i in all_bd if i["type"] == "atk"]
for i in atk_buff:
        atk_buff_value += i["amount"]

def_debuff_value = 1
def_debuff = [i for i in all_bd if i["type"] == "def"]
for i in def_debuff:
        def_debuff_value *= 1-i["amount"]

crit_dmg = 1.1
crit_dmg_buff = [i for i in all_bd if i["type"] == "crit_dmg"]
for i in crit_dmg_buff:
        crit_dmg += i["amount"]

crit_rate = 0.05
crit_rate_buff = [i for i in all_bd if i["type"] == "crit_rate"]
for i in crit_rate_buff:
        crit_rate += i["amount"]

dmg_dealt_buff_value = 0
dmg_dealt_buff = [i for i in all_bd if i["type"] == "dmg_dealt"]
for i in dmg_dealt_buff:
        dmg_dealt_buff_value += i["amount"]

dmg_dealt_buff_value = 0
dmg_dealt_buff = [i for i in all_bd if i["type"] == "dmg_dealt"]
for i in dmg_dealt_buff:
        dmg_dealt_buff_value += i["amount"]

dmg_taken_debuff_value = 0
dmg_taken_debuff = [i for i in all_bd if i["type"] == "dmg_taken"]
for i in dmg_taken_debuff:
        dmg_taken_debuff_value += i["amount"]

speed_buff_value = 1
speed_buff = [i for i in all_bd if i["type"] == "speed"]
for i in speed_buff:
        speed_buff_value += i["amount"]

mp_buff_value = 1
mp_buff = [i for i in all_bd if i["type"] == "mp"]
for i in mp_buff:
        mp_buff_value += i["amount"]

ele_advantage_dmg = 1
ele_advantage_dmg_buff = [i for i in all_bd if i["type"] == "ele_advantage_dmg"]
for i in ele_advantage_dmg_buff:
        ele_advantage_dmg += i["amount"]

ability_flower = {"atk":st.number_input("能力晶花のサブステータスによる攻撃力（実数値）", min_value=0, max_value=180, value=1),
                  "spd":st.number_input("能力晶花のサブステータスによるスピード（実数値）", min_value=0, max_value=12, value=1),
                  "crit_dmg":st.number_input("能力晶花のサブステータスによるクリティカルダメージ（％）", min_value=0.0, max_value=30.0, value=0.1),
                  "crit_rate":st.number_input("能力晶花のサブステータスによるクリティカル率（％）", min_value=0.0, max_value=15.0, value=0.1)}
crit_dmg += ability_flower["crit_dmg"]
crit_rate += ability_flower["crit_rate"]

total_spd = chara1["speed"] * speed_buff_value + ability_flower["spd"]
base_atk = st.number_input("基礎攻撃力＝（魔法少女＋ポートレイト＋サポートキオク）の基礎攻撃力", min_value=0, max_value=9999, value=1)
total_atk = base_atk * (1 + atk_buff_value) + ability_flower["atk"]
total_def = DEFENCE * def_debuff_value
ele_res = 1

skill_damage = calculate_damage(chara1["battle_skills"][0]["power"],base_atk,total_atk,total_def,dmg_dealt_buff_value,dmg_taken_debuff_value,ele_res, ele_advantage_dmg)
ult_damage = calculate_damage(chara1["ultimate"][0]["power"],base_atk,total_atk,total_def,dmg_dealt_buff_value,dmg_taken_debuff_value,ele_res, ele_advantage_dmg)

sum_damage = 0
mp = 0
skill_dmg_crit = skill_damage * crit_dmg 
skill_dmg_noncrit = skill_damage 
ult_dmg_crit = ult_damage * crit_dmg 
ult_dmg_noncrit = ult_damage 
for _ in range(total_spd):
    sum_damage += skill_dmg_crit * crit_rate + skill_dmg_noncrit * (1-crit_rate)
    mp += 30 * mp_buff_value
    if mp >= chara1["ultimate"]["meta"]["cost_mp"]:
          mp = 5 * mp_buff_value
          sum_damage += ult_dmg_crit * crit_rate + ult_dmg_noncrit * (1-crit_rate)

st.write(skill_dmg_crit,skill_dmg_noncrit)
st.write(ult_dmg_crit,ult_dmg_noncrit)
st.write(sum_damage)