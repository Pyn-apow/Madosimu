import json
import streamlit as st
from itertools import combinations
import base64
import math

st.set_page_config(page_title="魔法少女比較シミュレーター", layout="wide")

@st.cache_data
def load_characters(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["name"]: c for c in data}

@st.cache_data
def load_weapons(filepath: str) -> list:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def format_prob(p: float) -> str:
    pct = p * 100
    if pct == 0:
        return "0%"
    if pct >= 1.0:
        return f"{pct:.2f}%"
    exp = math.floor(math.log10(pct))
    base = pct / (10 ** exp)
    return f"{base:.2f}×10^{exp}%"

def get_all_buff_debuffs(chara: dict, totsu: int) -> list:
    all_bd = []
    for ult in chara.get("ultimate", []):
        all_bd.extend(ult.get("meta", {}).get("buff_debuffs", []))
    for skill in chara.get("battle_skills", []):
        all_bd.extend(skill.get("meta", {}).get("buff_debuffs", []))
    for ability in chara.get("abilities", []):
        all_bd.extend(ability.get("buff_debuffs", []))
    result = []
    for bd in all_bd:
        if totsu < bd.get("totsu", 0):
            continue
        if isinstance(bd.get("amount"), list):
            bd = dict(bd)
            bd["amount"] = bd["amount"][totsu]
        result.append(bd)
    return result

def get_support_ability_bds(chara: dict, attacker_element: str, attacker_role: str) -> list:
    all_bd = []
    for sa in chara.get("support_abilities", []):
        condition = sa.get("condition")
        if condition == attacker_element or condition == attacker_role:
            all_bd.extend(sa.get("buff_debuffs", []))
    return all_bd

def get_weapon_bds(weapon: dict, attacker_element: str) -> list:
    condition = weapon.get("condition")
    if condition and condition != attacker_element:
        return []
    return weapon.get("buff_debuffs", [])

def collect_buffs(all_bd: list, enemy_number: int, boss_break: int, enemy_break: int) -> dict:
    def sum_type(bd_type, other=None):
        total = 0
        for bd in all_bd:
            if bd["type"] != bd_type:
                continue
            if other is not None and bd.get("other") != other:
                continue
            if other is None and bd.get("other") in ("more", "break_200"):
                continue
            total += bd["amount"]
        return total

    atk_flat = sum_type("atk")
    atk_more = sum_type("atk", other="more") * enemy_number
    def_debuff = 1.0
    for bd in all_bd:
        if bd["type"] == "def":
            def_debuff *= 1 - bd["amount"]
    crit_dmg = 1.2 + sum_type("crit_dmg")
    crit_rate = min(0.1 + sum_type("crit_rate"), 1.0)
    dmg_taken = sum_type("dmg_taken")
    ele_advantage_dmg = sum_type("ele_advantage_dmg")
    dmg_dealt_base = sum_type("dmg_dealt") + sum_type("dmg_dealt", other="more") * enemy_number
    dmg_dealt_boss = dmg_dealt_base + (sum_type("dmg_dealt", other="break_200") if boss_break >= 200 else 0)
    dmg_dealt_enemy = dmg_dealt_base + (sum_type("dmg_dealt", other="break_200") if enemy_break >= 200 else 0)
    return {
        "atk_multiplier": 1 + atk_flat + atk_more,
        "def_debuff": def_debuff,
        "crit_dmg": crit_dmg,
        "crit_rate": crit_rate,
        "dmg_taken": dmg_taken,
        "ele_advantage_dmg": ele_advantage_dmg,
        "dmg_dealt_boss": dmg_dealt_boss,
        "dmg_dealt_enemy": dmg_dealt_enemy,
    }

def calculate_damage(multiplier, base_atk, total_atk, total_def, dmg_dealt, dmg_taken, ele_res, ele_advantage_dmg, break_value):
    if multiplier == 0:
        return 0
    base = multiplier * base_atk * ((base_atk / 124) ** 1.2 + 12) / 20
    defense = min((total_atk + 10) / (total_def + 10) * 0.12, 2)
    return (base * defense * (1 + dmg_dealt) * (1 + dmg_taken) * (1 - ele_res) * (1.2 + ele_advantage_dmg) * (break_value / 100))

def compute_hit_damage(hit, base_atk, total_atk, buffs, enemy_number, boss_defence, enemy_defence, boss_break, enemy_break, attacker_totsu=0):
    scale = hit.get("scale")
    power = hit["power"]
    if isinstance(power, list):
        power = power[attacker_totsu]
    raw_target = hit["target"]
    target = enemy_number if raw_target == -1 else min(raw_target, enemy_number)

    if scale == "less":
        multiplier = power * (5 - enemy_number)
    else:
        multiplier = power

    boss_dmg = calculate_damage(multiplier, base_atk, total_atk, boss_defence * buffs["def_debuff"], buffs["dmg_dealt_boss"], buffs["dmg_taken"], 0, buffs["ele_advantage_dmg"], boss_break)
    if target <= 1:
        return boss_dmg, 0, 1, scale
    enemy_dmg = calculate_damage(multiplier, base_atk, total_atk, enemy_defence * buffs["def_debuff"], buffs["dmg_dealt_enemy"], buffs["dmg_taken"], 0, buffs["ele_advantage_dmg"], enemy_break)
    return boss_dmg, enemy_dmg, target, scale

def compute_expected_damage(attacker, attacker_totsu, attacker_base_atk, supporters, supporter_totsus, support_ability_bds, weapon, enemy_number, boss_break, boss_defence, enemy_break, enemy_defence):
    attacker_element = attacker.get("element", "")
    all_bd = get_all_buff_debuffs(attacker, attacker_totsu)
    for sup, totsu in zip(supporters, supporter_totsus):
        if sup is not None:
            all_bd += get_all_buff_debuffs(sup, totsu)
    all_bd += support_ability_bds
    if weapon:
        all_bd += get_weapon_bds(weapon, attacker_element)

    buffs = collect_buffs(all_bd, enemy_number, boss_break, enemy_break)
    weapon_atk = weapon["atk"] if weapon else 0
    base_atk = attacker_base_atk + weapon_atk
    total_atk = base_atk * buffs["atk_multiplier"]
    crit_rate = buffs["crit_rate"]
    crit_dmg = buffs["crit_dmg"]
    crit_factor = crit_dmg * crit_rate + (1 - crit_rate)

    hits = attacker["ultimate"][0]["meta"]["hits"]
    total_expected = 0
    total_theory = 0
    theory_prob = 1.0

    for hit in hits:
        scale = hit.get("scale")
        count = hit.get("count", 1)
        boss_dmg, enemy_dmg, target, _ = compute_hit_damage(hit, base_atk, total_atk, buffs, enemy_number, boss_defence, enemy_defence, boss_break, enemy_break, attacker_totsu)

        if scale == "random":
            count = hit.get("count", 1)
            if enemy_number > 1:
                expected_per_hit = boss_dmg * (1/enemy_number) + enemy_dmg * ((enemy_number-1)/enemy_number)
                total_expected += expected_per_hit * crit_factor * count
                if boss_dmg >= enemy_dmg:
                    total_theory += boss_dmg * crit_dmg * count
                    theory_prob *= (crit_rate / enemy_number) ** count
                else:
                    total_theory += enemy_dmg * crit_dmg * count
                    theory_prob *= (crit_rate / enemy_number) ** count * (enemy_number - 1)
            else:
                total_expected += boss_dmg * crit_factor * count
                total_theory += boss_dmg * crit_dmg * count
                theory_prob *= crit_rate ** count
        else:
            total_expected += boss_dmg * crit_factor + enemy_dmg * crit_factor * (target - 1)
            total_theory += boss_dmg * crit_dmg + enemy_dmg * crit_dmg * (target - 1)
            if scale == "less":
                extra = 5 - enemy_number
                theory_prob *= crit_rate ** (extra * enemy_number) if extra > 0 else 1.0
            else:
                theory_prob *= crit_rate ** target

    return total_expected, total_theory, theory_prob

roster = load_characters("characters.json")
weapons = load_weapons("weapons.json")
attacker_list = [name for name, c in roster.items() if c.get("role") == "attacker"]
supporter_list = [name for name, c in roster.items() if c.get("role") in ("buffer", "debuffer")]

if "registered" not in st.session_state:
    st.session_state.registered = {}

load_input = st.text_area("ロードデータ(ペーストしてロード)", height=68, key="load_input")
if st.button("ロードする"):
    try:
        decoded = base64.b64decode(load_input.strip().encode()).decode()
        loaded = json.loads(decoded)
        st.session_state["pending_load"] = loaded
        st.rerun()
    except Exception as e:
        st.error(f"データが正しくありません。{e}")

if "pending_load" in st.session_state:
    loaded = st.session_state.pop("pending_load")
    for name, data in loaded.items():
        if name in roster:
            role = roster[name].get("role")
            st.session_state.registered[name] = {"totsu": data["totsu"], "role": role}
            if role == "attacker":
                st.session_state.registered[name]["base_atk"] = data.get("base_atk", 0)
            st.session_state[f"own_{name}"] = True
            st.session_state[f"totsu_{name}"] = data["totsu"]
            if role == "attacker":
                st.session_state[f"atk_{name}"] = data.get("base_atk", 0)
    st.success("ロードしました!")

with st.sidebar:
    if st.button("キャッシュクリア"):
        st.cache_data.clear()
        st.rerun()
    st.subheader("敵の設定")
    enemy_number = st.radio("敵の数", [1, 2, 3, 4, 5], horizontal=True)
    max_supporters = st.radio("バッファー人数", [0, 1, 2, 3, 4], horizontal=True)
    boss_break = st.number_input("ボスのブレイクボーナス", min_value=100, max_value=999, value=200)
    boss_defence = st.number_input("ボスの防御力", min_value=0.0, max_value=100000.0, value=1000.0)
    col5, col6 = st.columns(2)
    enemy_break = col5.number_input("他の敵のブレイク", min_value=100, max_value=999, value=200, disabled=enemy_number==1)
    enemy_defence = col6.number_input("他の敵の防御力", min_value=0.0, max_value=100000.0, value=1000.0, disabled=enemy_number==1)
    if enemy_number == 1:
        enemy_break = 0
        enemy_defence = 0.0
    sort_by = st.radio("ソート:ランキングの基準", ["期待値", "理論値"], horizontal=True)
    if sort_by == "理論値":
        min_prob = st.number_input("フィルター:理論値が起こり得る最低確率 (%)", min_value=0.0, max_value=100.0, value=0.0) / 100
    else:
        min_prob = 0.0

tab1, tab2, tab3, tab4 = st.tabs(["魔法少女登録", "ダメージシミュレーター", "セーブ・ロード", "使い方・よくある質問"])

with tab1:
    st.header("所持魔法少女の登録")
    st.caption("所持している魔法少女の基礎攻撃力と限界突破数を入力してください。")
    st.subheader("アタッカー")
    for name in attacker_list:
        with st.expander(name):
            owned = st.checkbox("所持している", key=f"own_{name}")
            if owned:
                col1, col2 = st.columns(2)
                base_atk = col1.number_input("基礎攻撃力", min_value=0, max_value=9999, value=st.session_state.registered.get(name, {}).get("base_atk", 0), key=f"atk_{name}")
                totsu = col2.number_input("限界突破数", min_value=0, max_value=5, step=1, value=st.session_state.registered.get(name, {}).get("totsu", 0), key=f"totsu_{name}")
                st.session_state.registered[name] = {"base_atk": int(base_atk), "totsu": int(totsu), "role": "attacker"}
            else:
                st.session_state.registered.pop(name, None)

    st.subheader("バッファー・デバッファー")
    for name in supporter_list:
        with st.expander(name):
            owned = st.checkbox("所持している", key=f"own_{name}")
            if owned:
                totsu = st.number_input("限界突破数", min_value=0, max_value=5, step=1, value=st.session_state.registered.get(name, {}).get("totsu", 0), key=f"totsu_{name}")
                st.session_state.registered[name] = {"totsu": int(totsu), "role": "supporter"}
            else:
                st.session_state.registered.pop(name, None)

with tab2:
    st.header("ダメージシミュレーター")
    registered_attackers = {n: v for n, v in st.session_state.registered.items() if v["role"] == "attacker"}
    registered_supporters = {n: v for n, v in st.session_state.registered.items() if v["role"] == "supporter"}

    if not registered_attackers:
        st.warning("タブ1でアタッカーを登録してください。")

    results = []
    supporter_names = list(registered_supporters.keys())
    supporter_combos = []
    for r in range(max_supporters + 1):
        supporter_combos += list(combinations(supporter_names, r))

    for atk_name, atk_data in registered_attackers.items():
        attacker = roster[atk_name]
        attacker_element = attacker.get("element", "")
        attacker_role = attacker.get("role", "")
        party_names_base = {atk_name}
        valid_weapons = [w for w in weapons if not w.get("condition") or w.get("condition") == attacker_element]
        weapon_candidates = [None] + valid_weapons

        for combo in supporter_combos:
            party_names = party_names_base | set(combo)
            supporters = [roster[n] for n in combo]
            supporter_totsus = [registered_supporters[n]["totsu"] for n in combo]
            sa_candidates_names = [
                n for n in roster
                if n not in party_names and any(
                    sa.get("condition") in (attacker_element, attacker_role)
                    for sa in roster[n].get("support_abilities", [])
                )
            ]
            sa_candidates = [None] + [get_support_ability_bds(roster[n], attacker_element, attacker_role) for n in sa_candidates_names]
            sa_labels = ["なし"] + sa_candidates_names

            for weapon in weapon_candidates:
                for sa_idx, sa_bds in enumerate(sa_candidates):
                    expected, theory, theory_prob = compute_expected_damage(
                        attacker, atk_data["totsu"], atk_data["base_atk"],
                        supporters, supporter_totsus,
                        sa_bds if sa_bds else [],
                        weapon,
                        enemy_number, boss_break, boss_defence, enemy_break, enemy_defence
                    )
                    parts = [atk_name]
                    if combo:
                        parts.append("、".join(combo))
                    if weapon:
                        parts.append(f"武器:{weapon['name']}")
                    if sa_bds:
                        parts.append(f"SA:{sa_labels[sa_idx]}")
                    results.append({"label": " + ".join(parts), "expected": expected, "theory": theory, "theory_prob": theory_prob})

    results.sort(key=lambda x: x["expected"] if sort_by == "期待値" else x["theory"], reverse=True)
    filtered_results = [r for r in results if r["theory_prob"] >= min_prob]
    top3 = filtered_results[:3]

    st.subheader("計算結果(上位3件)")
    medals = ["🥇", "🥈", "🥉"]
    for rank, result in enumerate(top3):
        st.markdown(f"### {medals[rank]} {result['label']}")
        if sort_by == "理論値":
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("期待値", f"{result['expected']:,.0f}")
            col_b.metric("理論値", f"{result['theory']:,.0f}")
            col_c.metric("理論値の確率", format_prob(result['theory_prob']))
        else:
            col_a, col_b = st.columns(2)
            col_a.metric("期待値", f"{result['expected']:,.0f}")
            col_b.metric("理論値", f"{result['theory']:,.0f}")
        st.divider()

    st.subheader("キャラクター別最高ダメージ")
    for atk_name in registered_attackers:
        chara_results = [r for r in filtered_results if r["label"].startswith(atk_name)]
        if chara_results:
            best = max(chara_results, key=lambda x: x["expected"] if sort_by == "期待値" else x["theory"])
            with st.expander(atk_name):
                st.write(f"**ビルド:** {best['label']}")
                if sort_by == "理論値":
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("期待値", f"{best['expected']:,.0f}")
                    col_b.metric("理論値", f"{best['theory']:,.0f}")
                    col_c.metric("理論値の確率", format_prob(best['theory_prob']))
                else:
                    col_a, col_b = st.columns(2)
                    col_a.metric("期待値", f"{best['expected']:,.0f}")
                    col_b.metric("理論値", f"{best['theory']:,.0f}")

with tab3:
    st.header("セーブ・ロード")
    if st.button("セーブデータを表示"):
        save_data = json.dumps(
            {n: {"base_atk": v.get("base_atk"), "totsu": v["totsu"]} for n, v in st.session_state.registered.items()},
            ensure_ascii=False, separators=(',', ':')
        )
        compressed = base64.b64encode(save_data.encode()).decode()
        st.text_area("セーブデータ(コピーして保存)", value=compressed, height=68)

with tab4:
    st.header("使い方・よくある質問")
    st.subheader("使い方")
    st.write("1. 魔法少女登録タブで、手持ちのアタッカー・バッファー・デバッファーを登録")
    st.write("2. 左側の設定で条件を設定(敵の防御力やブレイクボーナスは、海外wikiを参照することをお勧めします。)")
    st.write("3. ダメージシミュレータータブでランキングを見る")
    st.subheader("Q&A")
    st.write("Q. 対応している魔法少女・ポートレイトが少ないです。")
    st.write("A. 随時増やしていきます。リクエストをいただければ早めに実装する可能性もあります。")
    st.write("Q. 必殺技だけでなく、スキルや追撃も考慮しないと強さが比較できないと思います。")
    st.write("A. 総合的な強さに関してはその通りです。しかしこのシミュレーターは必殺技の最高ダメージを求めるという目的で作られています。")
    st.write("Q. このシミュレーターって何に使うんですか?")
    st.write("A. 決まってはいないですが、スコアアタックなどに活用できるのではないでしょうか。")