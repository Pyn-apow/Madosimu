import json
import streamlit as st
from itertools import combinations

st.set_page_config(page_title="魔法少女比較シミュレーター", layout="wide")

@st.cache_data
def load_characters(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["name"]: c for c in data}

def get_all_buff_debuffs(chara: dict, totsu: int) -> list:
    all_bd = []
    for ult in chara.get("ultimate", []):
        all_bd.extend(ult.get("meta", {}).get("buff_debuffs", []))
    for skill in chara.get("battle_skills", []):
        all_bd.extend(skill.get("meta", {}).get("buff_debuffs", []))
    for ability in chara.get("abilities", []):
        all_bd.extend(ability.get("buff_debuffs", []))
    all_bd = [bd for bd in all_bd if totsu >= bd.get("totsu", 0)]
    return all_bd

def calculate_damage(ability_multiplier, base_atk, total_atk, total_def, dmg_dealt, dmg_taken, ele_res, ele_advantage_dmg, break_value):
    Ability_Damage_Base = ability_multiplier * base_atk * ((base_atk / 124) ** 1.2 + 12) / 20
    Defense_Factor = min((total_atk + 10) / (total_def + 10) * 0.12, 2)
    Damage_Dealt_Factor = 1 + dmg_dealt
    Damage_Taken_Factor = 1 + dmg_taken
    Elemental_Resistance_Factor = 1 - ele_res
    Effective_Element_Factor = 1.2 + ele_advantage_dmg
    Break_Factor = break_value / 100
    return Ability_Damage_Base * Defense_Factor * Damage_Dealt_Factor * Damage_Taken_Factor * Elemental_Resistance_Factor * Effective_Element_Factor * Break_Factor

def compute_expected_damage(attacker, attacker_totsu, attacker_base_atk, supporters, supporter_totsus, enemy_number, boss_break, boss_defence, enemy_break, enemy_defence):
    all_bd = get_all_buff_debuffs(attacker, attacker_totsu)
    for i, sup in enumerate(supporters):
        if sup is not None:
            all_bd += get_all_buff_debuffs(sup, supporter_totsus[i])

    atk_buff_value = 0
    for bd in [i for i in all_bd if i["type"] == "atk"]:
        if "other" in bd and bd["other"] == "enemy_number":
            atk_buff_value += bd["amount"] * enemy_number
        else:
            atk_buff_value += bd["amount"]

    def_debuff_value = 1
    for bd in [i for i in all_bd if i["type"] == "def"]:
        def_debuff_value *= 1 - bd["amount"]

    crit_dmg = 1.2
    for bd in [i for i in all_bd if i["type"] == "crit_dmg"]:
        crit_dmg += bd["amount"]

    crit_rate = 0.1
    for bd in [i for i in all_bd if i["type"] == "crit_rate"]:
        crit_rate += bd["amount"]

    dmg_dealt = 0
    for bd in [i for i in all_bd if i["type"] == "dmg_dealt"]:
        dmg_dealt += bd["amount"]

    dmg_taken = 0
    for bd in [i for i in all_bd if i["type"] == "dmg_taken"]:
        dmg_taken += bd["amount"]

    ele_advantage_dmg = 0
    for bd in [i for i in all_bd if i["type"] == "ele_advantage_dmg"]:
        ele_advantage_dmg += bd["amount"]

    total_atk = attacker_base_atk * (1 + atk_buff_value)
    ele_res = 0

    ult_multiplier = attacker["ultimate"][0]["power"]
    if attacker["ultimate"][0]["meta"].get("other") == "random":
        ult_multiplier += attacker["ultimate"][0]["meta"]["power"] / enemy_number

    boss_dmg = calculate_damage(ult_multiplier, attacker_base_atk, total_atk, boss_defence * def_debuff_value, dmg_dealt, dmg_taken, ele_res, ele_advantage_dmg, boss_break)
    enemy_dmg = calculate_damage(ult_multiplier, attacker_base_atk, total_atk, enemy_defence * def_debuff_value, dmg_dealt, dmg_taken, ele_res, ele_advantage_dmg, enemy_break)

    target_number = min(attacker["ultimate"][0]["meta"].get("target", 1), enemy_number)
    expected = boss_dmg * (crit_dmg * crit_rate + (1 - crit_rate)) + enemy_dmg * (crit_dmg * crit_rate + (1 - crit_rate)) * (target_number - 1)
    theory = boss_dmg * crit_dmg + enemy_dmg * crit_dmg * (target_number - 1)

    return expected, theory

roster = load_characters("characters.json")
attacker_list = [name for name, c in roster.items() if c.get("role") == "attacker"]
supporter_list = [name for name, c in roster.items() if c.get("role") in ("buffer", "debuffer")]

if "registered" not in st.session_state:
    st.session_state.registered = {}

tab1, tab2 = st.tabs(["📋 キャラクター登録", "⚔️ シミュレーター"])

with tab1:
    st.header("所持キャラクターの登録")
    st.caption("所持しているキャラクターの基礎攻撃力と限界突破数を入力してください。")

    st.subheader("アタッカー")
    for name in attacker_list:
        with st.expander(name):
            owned = st.checkbox("所持している", key=f"own_{name}")
            if owned:
                col1, col2 = st.columns(2)
                base_atk = col1.number_input("基礎攻撃力", min_value=0, max_value=9999, value=st.session_state.registered.get(name, {}).get("base_atk", 0), key=f"atk_{name}")
                totsu = col2.selectbox("限界突破数", [0, 1, 2, 3, 4, 5], index=st.session_state.registered.get(name, {}).get("totsu", 0), key=f"totsu_{name}")
                st.session_state.registered[name] = {"base_atk": base_atk, "totsu": totsu, "role": "attacker"}
            else:
                st.session_state.registered.pop(name, None)

    st.subheader("バッファー・デバッファー")
    for name in supporter_list:
        with st.expander(name):
            owned = st.checkbox("所持している", key=f"own_{name}")
            if owned:
                totsu = st.selectbox("限界突破数", [0, 1, 2, 3, 4, 5], index=st.session_state.registered.get(name, {}).get("totsu", 0), key=f"totsu_{name}")
                st.session_state.registered[name] = {"totsu": totsu, "role": "supporter"}
            else:
                st.session_state.registered.pop(name, None)

with tab2:
    st.header("ダメージシミュレーター")

    registered_attackers = {n: v for n, v in st.session_state.registered.items() if v["role"] == "attacker"}
    registered_supporters = {n: v for n, v in st.session_state.registered.items() if v["role"] == "supporter"}

    if not registered_attackers:
        st.warning("タブ①でアタッカーを登録してください。")
        st.stop()

    st.subheader("敵の設定")
    col1, col2 = st.columns(2)
    enemy_number = col1.radio("敵の数", [1, 2, 3, 4, 5], horizontal=True)
    max_supporters = col2.radio("バッファー・デバッファーの人数", [0, 1, 2, 3, 4], horizontal=True)

    col3, col4 = st.columns(2)
    boss_break = col3.number_input("ボスのブレイクボーナス", min_value=100, max_value=999, value=200)
    boss_defence = col4.number_input("ボスの防御力", min_value=0.0, max_value=100000.0, value=1000.0)

    if enemy_number > 1:
        col5, col6 = st.columns(2)
        enemy_break = col5.number_input("他の敵のブレイクボーナス", min_value=100, max_value=999, value=200)
        enemy_defence = col6.number_input("他の敵の防御力", min_value=0.0, max_value=100000.0, value=1000.0)
    else:
        enemy_break = 0
        enemy_defence = 0.0

    sort_by = st.radio("ランキング基準", ["期待値", "理論値"], horizontal=True)

    st.subheader("計算結果（上位3件）")

    results = []

    supporter_names = list(registered_supporters.keys())
    supporter_combos = []
    for r in range(max_supporters + 1):
        supporter_combos += list(combinations(supporter_names, r))

    for atk_name, atk_data in registered_attackers.items():
        attacker = roster[atk_name]
        for combo in supporter_combos:
            supporters = [roster[n] for n in combo]
            supporter_totsus = [registered_supporters[n]["totsu"] for n in combo]
            padded_supporters = supporters + [None] * (4 - len(supporters))
            padded_totsus = supporter_totsus + [0] * (4 - len(supporter_totsus))

            expected, theory = compute_expected_damage(
                attacker, atk_data["totsu"], atk_data["base_atk"],
                padded_supporters, padded_totsus,
                enemy_number, boss_break, boss_defence, enemy_break, enemy_defence
            )

            combo_label = atk_name + " + " + "、".join(combo) if combo else atk_name + "（サポートなし）"
            results.append({"label": combo_label, "expected": expected, "theory": theory})

    results.sort(key=lambda x: x["expected"] if sort_by == "期待値" else x["theory"], reverse=True)
    top3 = results[:3]

    medals = ["🥇", "🥈", "🥉"]
    for rank, result in enumerate(top3):
        st.markdown(f"### {medals[rank]} {result['label']}")
        col_a, col_b = st.columns(2)
        col_a.metric("期待値", f"{result['expected']:,.0f}")
        col_b.metric("理論値", f"{result['theory']:,.0f}")
        st.divider()