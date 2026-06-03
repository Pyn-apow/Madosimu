import json
import streamlit as st

# ── データ読み込み（キャッシュで高速化） ──────────
@st.cache_data
def load_characters(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["name"]: c for c in data}

def calculate_damage(ability_multiplier,base_atk,total_atk,total_def,dmg_dealt,dmg_taken,ele_res, ele_advantage_dmg,break_value):
    Ability_Damage_Base = ability_multiplier * base_atk * ((base_atk / 124) ** 1.2 + 12) / 20
    Defense_Factor = min((total_atk + 10) / (total_def + 10) * 0.12,2)
    Damage_Dealt_Factor = 1 + dmg_dealt
    Damage_Taken_Factor = 1 + dmg_taken
    Elemental_Resistance_Factor = 1 - ele_res
    Effective_Element_Factor = 1.2 + ele_advantage_dmg
    Break_Factor = break_value/100
    return Ability_Damage_Base * Defense_Factor * Damage_Dealt_Factor * Damage_Taken_Factor * Elemental_Resistance_Factor * Effective_Element_Factor * Break_Factor

def get_all_buff_debuffs(chara: dict,totsu) -> list:
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

    all_bd = [bd for bd in all_bd if totsu >= bd.get("totsu", 0)]

    return all_bd

# ── メイン ────────────────────────────────────
st.title("""
         魔法少女用理論値・期待値比較シミュレーター
         ※すべてのバフ・デバフが発動している状態を想定しています。
         また、ランダム攻撃が必殺技に含まれる魔法少女は、計算上の理論値が実際の理論値より低く出ます。
         （これはこのシミュレーターが、ランダム攻撃のダメージを敵全員に等しく分配しているためです。
         しかしランダム攻撃を持つ魔法少女の必殺技で理論値を出すことは現実的に不可能なので、気にする必要はないと思われます。）
         期待値に影響はありません。
         """)

roster = load_characters("characters.json")

# セレクトボックスでキャラ選択
attacker = st.selectbox("メインアタッカーを選択", [name for name, c in roster.items() if c.get("role") == "attacker"])
bd1 = st.selectbox("バッファー・デバッファーを選択", ["なし"] + [name for name, c in roster.items() if c.get("role") == "buffer" or c.get("role") == "debuffer"],key="bd1")
bd2 = st.selectbox("バッファー・デバッファーを選択", ["なし"] + [name for name, c in roster.items() if c.get("role") == "buffer" or c.get("role") == "debuffer"],key="bd2")
bd3 = st.selectbox("バッファー・デバッファーを選択", ["なし"] + [name for name, c in roster.items() if c.get("role") == "buffer" or c.get("role") == "debuffer"],key="bd3")
bd4 = st.selectbox("バッファー・デバッファーを選択", ["なし"] + [name for name, c in roster.items() if c.get("role") == "buffer" or c.get("role") == "debuffer"],key="bd4")
totsu = [st.selectbox("限界突破数を選択", [0,1,2,3,4,5],key="totsu1"),st.selectbox("限界突破数を選択", [0,1,2,3,4,5],key="totsu2"),st.selectbox("限界突破数を選択", [0,1,2,3,4,5],key="totsu3"),st.selectbox("限界突破数を選択", [0,1,2,3,4,5],key="totsu4"),st.selectbox("限界突破数を選択", [0,1,2,3,4,5],key="totsu5")]
ENEMY_NUMBER = st.radio("敵の数",[1,2,3,4,5],horizontal=True)
BOSS_BREAK = st.slider("ボスのブレイクボーナス", min_value=100, max_value=999, value=200)
BOSS_DEFENCE = st.number_input("ボスの防御力", min_value=0.0, max_value=100000.0, value=1000.0)
if ENEMY_NUMBER != 1:
    ENEMY_BREAK = st.slider("ほかの敵のブレイクボーナス", min_value=100, max_value=999, value=200)
    ENEMY_DEFENCE = st.number_input("ほかの敵の防御力", min_value=0.0, max_value=100000.0, value=1000.0)
else:
    pass

# 選択されたキャラのデータを取得
chara1 = roster[attacker]
chara2 = roster.get(bd1) if bd1 != "なし" else None
chara3 = roster.get(bd2) if bd2 != "なし" else None
chara4 = roster.get(bd3) if bd3 != "なし" else None
chara5 = roster.get(bd4) if bd4 != "なし" else None

all_bd = []
for e,i in enumerate([chara1,chara2,chara3,chara4,chara5]):
    all_bd += get_all_buff_debuffs(i, totsu[e]) if i is not None else []
st.write(all_bd)
atk_buff_value = 0
atk_buff = [i for i in all_bd if i["type"] == "atk"]
for i in atk_buff:
    if "other" in i:
        if i["other"] == "enemy_number":
            atk_buff_value += i["amount"] * ENEMY_NUMBER
    else:
        atk_buff_value += i["amount"]

def_debuff_value = 1
def_debuff = [i for i in all_bd if i["type"] == "def"]
for i in def_debuff:
        def_debuff_value *= 1-i["amount"]

crit_dmg = 1.2
crit_dmg_buff = [i for i in all_bd if i["type"] == "crit_dmg"]
for i in crit_dmg_buff:
        crit_dmg += i["amount"]

crit_rate = 0.1
crit_rate_buff = [i for i in all_bd if i["type"] == "crit_rate"]
for i in crit_rate_buff:
        crit_rate += i["amount"]

dmg_dealt_buff_value = 0
dmg_dealt_buff = [i for i in all_bd if i["type"] == "dmg_dealt"]
for i in dmg_dealt_buff:
        dmg_dealt_buff_value += i["amount"]


dmg_taken_debuff_value = 0
dmg_taken_debuff = [i for i in all_bd if i["type"] == "dmg_taken"]
for i in dmg_taken_debuff:
        dmg_taken_debuff_value += i["amount"]

# speed_buff_value = 1
# speed_buff = [i for i in all_bd if i["type"] == "speed"]
# for i in speed_buff:
#         speed_buff_value += i["amount"]

# mp_buff_value = 1
# mp_buff = [i for i in all_bd if i["type"] == "mp"]
# for i in mp_buff:
#         mp_buff_value += i["amount"]

ele_advantage_dmg = 0
ele_advantage_dmg_buff = [i for i in all_bd if i["type"] == "ele_advantage_dmg"]
for i in ele_advantage_dmg_buff:
        ele_advantage_dmg += i["amount"]

# ability_flower = {"atk":st.number_input("能力晶花のサブステータスによる攻撃力（実数値）", min_value=0, max_value=180, value=0),
#                   "spd":st.number_input("能力晶花のサブステータスによるスピード（実数値）", min_value=0, max_value=12, value=0),
#                   "crit_dmg":st.number_input("能力晶花のサブステータスによるクリティカルダメージ（％）", min_value=0.0, max_value=30.0, value=0.0),
#                   "crit_rate":st.number_input("能力晶花のサブステータスによるクリティカル率（％）", min_value=0.0, max_value=15.0, value=0.0)}
ability_flower = {"atk":st.number_input("能力晶花のサブステータスによる攻撃力（実数値）", min_value=0, max_value=180, value=0),
                  "crit_rate":st.number_input("能力晶花のサブステータスによるクリティカル率（％）", min_value=0.0, max_value=15.0, value=0.0),
                  "crit_dmg":st.number_input("能力晶花のサブステータスによるクリティカルダメージ（％）", min_value=0.0, max_value=30.0, value=0.0)}
crit_dmg += ability_flower["crit_dmg"]/100

# total_spd = chara1["speed"] * speed_buff_value + ability_flower["spd"]
base_atk = st.number_input("基礎攻撃力＝（魔法少女＋ポートレイト＋サポートキオク）の基礎攻撃力", min_value=0, max_value=9999, value=0)
total_atk = base_atk * (1 + atk_buff_value) + ability_flower["atk"]
ele_res = 0

ult_multiplier = chara1["ultimate"][0]["power"]
if chara1["ultimate"][0]["meta"]["other"] == "random":
    ult_multiplier += chara1["ultimate"][0]["meta"]["power"]/ENEMY_NUMBER

boss_ult_damage = calculate_damage(ult_multiplier,base_atk,total_atk,BOSS_DEFENCE * def_debuff_value,dmg_dealt_buff_value,dmg_taken_debuff_value,ele_res, ele_advantage_dmg,BOSS_BREAK)
st.write((ult_multiplier,base_atk,total_atk,BOSS_DEFENCE * def_debuff_value,dmg_dealt_buff_value,dmg_taken_debuff_value,ele_res, ele_advantage_dmg,BOSS_BREAK))
enemy_ult_damage = calculate_damage(ult_multiplier,base_atk,total_atk,ENEMY_DEFENCE * def_debuff_value,dmg_dealt_buff_value,dmg_taken_debuff_value,ele_res, ele_advantage_dmg,ENEMY_BREAK)
if ENEMY_NUMBER != 1:
    st.write((ult_multiplier,base_atk,total_atk,ENEMY_DEFENCE * def_debuff_value,dmg_dealt_buff_value,dmg_taken_debuff_value,ele_res, ele_advantage_dmg,ENEMY_BREAK))
# sum_damage = 0
# mp = 0

# for _ in range(int(total_spd)):
#     sum_damage += skill_dmg_crit * crit_rate + skill_dmg_noncrit * (1-crit_rate)
#     mp += 30 * mp_buff_value
#     if mp >= chara1["ultimate"][0]["meta"]["cost_mp"]:
#           mp = 5 * mp_buff_value
#           sum_damage += ult_dmg_crit * crit_rate + ult_dmg_noncrit * (1-crit_rate)
attack_number = chara1["ultimate"][0]["attack_number"]
target_number = min(chara1["ultimate"][0]["meta"]["target"],ENEMY_NUMBER)
if attack_number > 0:   
    st.write(boss_ult_damage*crit_dmg + enemy_ult_damage*crit_dmg*(target_number-1),crit_rate**(target_number*attack_number))
else:
    st.write(boss_ult_damage*crit_dmg + enemy_ult_damage*crit_dmg*(target_number-1),"測定不能")
st.write(boss_ult_damage*(crit_dmg*crit_rate+(1-crit_rate)) + (enemy_ult_damage*(crit_dmg*crit_rate+(1-crit_rate))*(target_number-1)))
# st.write(sum_damage)