import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe
from google.oauth2.service_account import Credentials
import math

# --- HEADLINE & PAGE CONFIG ---
st.set_page_config(page_title="PoE Bulk Item Banking App", layout="wide")
st.title("PoE Bulk Item Banking App")
st.caption("Bulk community banking for PoE item pooling and tracking")

# ---- CONFIGURATION ----
ORIGINAL_ITEM_CATEGORIES = {
    "Waystones": [
        "Waystone EXP + Delirious",
        "Waystone EXP 35%",
        "Waystone EXP"
    ],
    "White Item Bases": [
        "Stellar Amulet",
        "Breach ring level 82",
        "Heavy Belt"
    ],
    "Tablets": [
        "Tablet Exp 9%+10% (random)",
        "Quantity Tablet (6%+)",
        "Grand Project Tablet"
    ],
    "Various": [
        "Logbook level 79-80"
    ]
}
ALL_ITEMS = sum(ORIGINAL_ITEM_CATEGORIES.values(), [])

CATEGORY_COLORS = {
    "Waystones": "#FFD700",   # Gold/Yellow
    "White Item Bases": "#FFFFFF",      # White
    "Tablets": "#AA66CC",     # Purple
    "Various": "#42A5F5",     # Blue
}

ITEM_COLORS = {
    "Breach ring level 82": "#D6A4FF",   # purple
    "Stellar Amulet": "#FFD700",         # gold/yellow
    "Heavy Belt": "#A4FFA3",             # greenish
    "Waystone EXP + Delirious": "#FF6961",
    "Waystone EXP 35%": "#FFB347",
    "Waystone EXP": "#FFB347",
    "Tablet Exp 9%+10% (random)": "#7FDBFF",
    "Quantity Tablet (6%+)": "#B0E0E6",
    "Grand Project Tablet": "#FFDCB9",
    "Logbook level 79-80": "#42A5F5",
}
def get_item_color(item):
    return ITEM_COLORS.get(item, "#FFF")

SHEET_NAME = "poe_item_bank"
SHEET_TAB = "Sheet1"
TARGETS_TAB = "Targets"
ADMIN_LOGS_TAB = "AdminLogs"
PENDING_DUPES_TAB = "PendingDupes"

DEFAULT_BANK_BUY_PCT = 80   # percent

# ---- GOOGLE SHEETS FUNCTIONS ----
def get_gsheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = st.secrets["gcp_service_account"]
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(credentials)
    return client

def load_data():
    gc = get_gsheet_client()
    sheet = gc.open(SHEET_NAME).worksheet(SHEET_TAB)
    df = get_as_dataframe(sheet, evaluate_formulas=True, dtype=str)
    df = df.dropna(how='all')
    if not df.empty:
        df = df.fillna("")
        expected_cols = ["User", "Item", "Quantity"]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""
        df = df[expected_cols]
    else:
        df = pd.DataFrame(columns=["User", "Item", "Quantity"])
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
    return df

def save_data(df):
    gc = get_gsheet_client()
    sheet = gc.open(SHEET_NAME).worksheet(SHEET_TAB)
    set_with_dataframe(sheet, df[["User", "Item", "Quantity"]], include_index=False)

def load_targets():
    gc = get_gsheet_client()
    sh = gc.open(SHEET_NAME)
    try:
        ws = sh.worksheet(TARGETS_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=TARGETS_TAB, rows=50, cols=3)
        ws.append_row(["Item", "Target", "Divines"])
    df = get_as_dataframe(ws, evaluate_formulas=True, dtype=str).dropna(how='all')

    targets = {}
    divines = {}
    bank_buy_pct = DEFAULT_BANK_BUY_PCT

    if not df.empty and "Item" in df.columns:
        settings_row = df[df["Item"] == "_SETTINGS"]
        if not settings_row.empty:
            try:
                bank_buy_pct = int(float(settings_row.iloc[0]["Target"]))
            except Exception:
                bank_buy_pct = DEFAULT_BANK_BUY_PCT
        df = df[df["Item"] != "_SETTINGS"]
        if "Target" not in df.columns:
            df["Target"] = 100
        if "Divines" not in df.columns:
            df["Divines"] = ""
        for idx, row in df.iterrows():
            item = row["Item"]
            try:
                targets[item] = int(float(row["Target"]))
            except Exception:
                targets[item] = 100
            try:
                divines[item] = float(row["Divines"]) if str(row["Divines"]).strip() != "" else 0
            except Exception:
                divines[item] = 0
    for item in ALL_ITEMS:
        if item not in targets:
            targets[item] = 100
        if item not in divines:
            divines[item] = 0
    return targets, divines, bank_buy_pct, ws

def save_targets(targets, divines, bank_buy_pct, ws):  # links removed
    data_rows = [{"Item": item, "Target": targets[item], "Divines": divines[item]} for item in ALL_ITEMS]
    data_rows.append({"Item": "_SETTINGS", "Target": bank_buy_pct, "Divines": ""})
    df = pd.DataFrame(data_rows)
    ws.clear()
    set_with_dataframe(ws, df, include_index=False)

# ---- ADMIN LOGGING FUNCTIONS ----
def append_admin_log(action, details="", admin_user=""):
    gc = get_gsheet_client()
    try:
        ws = gc.open(SHEET_NAME).worksheet(ADMIN_LOGS_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = gc.open(SHEET_NAME).add_worksheet(title=ADMIN_LOGS_TAB, rows=100, cols=4)
        ws.append_row(["Timestamp", "AdminUser", "AdminAction", "Details"])
    timestamp = pd.Timestamp.now(tz='Europe/Berlin').strftime("%Y-%m-%d %H:%M:%S")
    ws.append_row([timestamp, admin_user, action, details])

def load_admin_logs(n=20):
    gc = get_gsheet_client()
    try:
        ws = gc.open(SHEET_NAME).worksheet(ADMIN_LOGS_TAB)
        logs = get_as_dataframe(ws, evaluate_formulas=True).dropna(how='all')
        logs = logs.fillna("")
        if not logs.empty:
            return logs.tail(n).iloc[::-1]
    except Exception:
        return pd.DataFrame(columns=["Timestamp", "AdminUser", "AdminAction", "Details"])
    return pd.DataFrame(columns=["Timestamp", "AdminUser", "AdminAction", "Details"])

# ---- DUPLICATE HANDLING ----
def append_pending_dupe(user, item, quantity):
    gc = get_gsheet_client()
    try:
        ws = gc.open(SHEET_NAME).worksheet(PENDING_DUPES_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = gc.open(SHEET_NAME).add_worksheet(title=PENDING_DUPES_TAB, rows=100, cols=3)
        ws.append_row(["User", "Item", "Quantity"])
    ws.append_row([user, item, quantity])

def load_pending_dupes():
    gc = get_gsheet_client()
    try:
        ws = gc.open(SHEET_NAME).worksheet(PENDING_DUPES_TAB)
        df = get_as_dataframe(ws, evaluate_formulas=True, dtype=str)
        df = df.dropna(how='all')
        if not df.empty:
            df = df.fillna("")
            expected_cols = ["User", "Item", "Quantity"]
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = ""
            df = df[expected_cols]
            df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype(int)
        else:
            df = pd.DataFrame(columns=["User", "Item", "Quantity"])
        return df, ws
    except Exception:
        return pd.DataFrame(columns=["User", "Item", "Quantity"]), None

def remove_pending_dupe(ws, row_idx):
    ws.delete_rows(row_idx+2)  # +2: 1 for header, 1-based index

# ---- ADMIN LOGIN STATE HANDLING ----
if 'is_editor' not in st.session_state:
    st.session_state['is_editor'] = False
if 'show_login' not in st.session_state:
    st.session_state['show_login'] = False
if 'login_failed' not in st.session_state:
    st.session_state['login_failed'] = False
if 'admin_user' not in st.session_state:
    st.session_state['admin_user'] = ""

ADMIN_USERS = {
    "POEconomics": "ADMINPOECONOMICS",
    "LT_Does_it_better": "LT_Does_it_betterPOECONOMICS",
    "JESUS (Spector)": "JESUS (Spector)POECONOMICS"
}

def logout():
    st.session_state['is_editor'] = False
    st.session_state['show_login'] = False
    st.session_state['login_failed'] = False
    st.session_state['admin_user'] = ""

def show_admin_login():
    with st.form("admin_login"):
        st.write("**Admin Login**")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        if submit:
            if username in ADMIN_USERS and password == ADMIN_USERS[username]:
                st.session_state['is_editor'] = True
                st.session_state['admin_user'] = username
                st.session_state['show_login'] = False
                st.session_state['login_failed'] = False
            else:
                st.session_state['is_editor'] = False
                st.session_state['admin_user'] = ""
                st.session_state['login_failed'] = True

# ---- TOP-CENTER ADMIN LOGIN BUTTON OR LOGOUT ----
col1, col2, col3 = st.columns([1,2,1])
with col2:
    if not st.session_state['is_editor']:
        if st.button("Admin login"):
            st.session_state['show_login'] = not st.session_state['show_login']
    else:
        if st.button("Admin logout"):
            logout()

if st.session_state['show_login'] and not st.session_state['is_editor']:
    col_spacer1, col_login, col_spacer2 = st.columns([1,2,1])
    with col_login:
        show_admin_login()
    if st.session_state['login_failed']:
        st.error("Incorrect username or password.")

if st.session_state['is_editor']:
    st.caption(f"**Admin mode enabled: {st.session_state['admin_user']}**")
else:
    st.caption("**Read only mode** (progress & deposit info only)")

# ---- DATA LOADING ----
df = load_data()
targets, divines, bank_buy_pct_loaded, ws_targets = load_targets()

if 'bank_buy_pct' not in st.session_state:
    st.session_state['bank_buy_pct'] = bank_buy_pct_loaded

with st.sidebar:
    st.header("Per-Item Targets & Divine Value")
    if st.session_state['is_editor']:
        st.subheader("Bank Instant Buy Settings")
        bank_buy_pct = st.number_input(
            "Bank buy % of sell price (instant sell payout)",
            min_value=10, max_value=100, step=1,
            value=st.session_state['bank_buy_pct'],
            key="bank_buy_pct_input"
        )
        changed = False
        if bank_buy_pct != st.session_state['bank_buy_pct']:
            st.session_state['bank_buy_pct'] = bank_buy_pct
            changed = True
        new_targets = {}
        new_divines = {}
        st.subheader("Edit Targets and Values")
        for item in ALL_ITEMS:
            cols = st.columns([2, 2])
            tgt = cols[0].number_input(
                f"{item} target",
                min_value=1,
                value=int(targets.get(item, 100)),
                step=1,
                key=f"target_{item}"
            )
            div = cols[1].number_input(
                f"Stack Value (Divines)",
                min_value=0.0,
                value=float(divines.get(item, 0)),
                step=0.1,
                format="%.2f",
                key=f"divine_{item}"
            )
            if tgt != targets[item] or div != divines[item]:
                changed = True
            new_targets[item] = tgt
            new_divines[item] = div
        if st.button("Save Targets and Values") and changed:
            save_targets(new_targets, new_divines, st.session_state['bank_buy_pct'], ws_targets)
            append_admin_log("Edit Targets/Values", "Admin updated targets or values.", st.session_state['admin_user'])
            st.success("Targets, Divine values and Bank % saved! Refresh the page to see updates.")
            st.stop()
    else:
        for item in ALL_ITEMS:
            st.markdown(
                f"""
                <span style='font-weight:bold;'>{item}:</span>
                Target = {targets[item]}, Stack Value = {divines[item]:.2f} Divines<br>
                """,
                unsafe_allow_html=True
            )

# --- MULTI-ITEM DEPOSIT FORM (EDITORS ONLY) ---
if st.session_state['is_editor']:
    if 'deposit_submitted' not in st.session_state:
        st.session_state['deposit_submitted'] = False

    with st.form("multi_item_deposit", clear_on_submit=True):
        st.subheader("Add a Deposit (multiple items per user)")
        user = st.text_input("User")
        col1, col2 = st.columns(2)
        item_qtys = {}
        for i, item in enumerate(ALL_ITEMS):
            col = col1 if i % 2 == 0 else col2
            item_qtys[item] = col.number_input(f"{item}", min_value=0, step=1, key=f"add_{item}")
        submitted = st.form_submit_button("Add Deposit(s)")
        if submitted and user and not st.session_state['deposit_submitted']:
            # --------- RACE-SAFE DUPLICATE DETECTION & DEPOSIT ADDITION ---------
            df_latest = load_data()
            new_rows = []
            for item, qty in item_qtys.items():
                if qty > 0:
                    is_duplicate = not df_latest[
                        (df_latest["User"].str.lower() == user.strip().lower()) &
                        (df_latest["Item"] == item) &
                        (df_latest["Quantity"] == int(qty))
                    ].empty
                    if is_duplicate:
                        append_pending_dupe(user.strip(), item, int(qty))
                    else:
                        new_rows.append({"User": user.strip(), "Item": item, "Quantity": int(qty)})
            if new_rows:
                # Before save, check AGAIN for race-safety
                df_final = load_data()
                actually_added = []
                for row in new_rows:
                    already_in = not df_final[
                        (df_final["User"].str.lower() == row["User"].lower()) &
                        (df_final["Item"] == row["Item"]) &
                        (df_final["Quantity"] == row["Quantity"])
                    ].empty
                    if not already_in:
                        df_final = pd.concat([df_final, pd.DataFrame([row])], ignore_index=True)
                        actually_added.append(f"{row['Quantity']}x {row['Item']}")
                        append_admin_log("Deposit", f"{row['User']}: {row['Quantity']}x {row['Item']}", st.session_state['admin_user'])
                if actually_added:
                    save_data(df_final)
                    st.session_state['deposit_submitted'] = True
                    st.success("Deposits added: " + ", ".join(actually_added))
                    st.rerun()
                else:
                    st.info("All selected deposits were already present. No duplicates added.")
            elif any(item_qtys[item] > 0 for item in item_qtys):
                st.warning("Duplicate offer detected! Please confirm it in the admin panel below.")
            else:
                st.warning("Please enter at least one item with quantity > 0.")

    if st.session_state.get('deposit_submitted', False) and not submitted:
        st.session_state['deposit_submitted'] = False

st.markdown("---")

# ---- DUPLICATE OFFERS ADMIN PANEL ----
if st.session_state['is_editor']:
    st.header("Pending Duplicate Offers (confirm or decline)")
    pending_dupes, ws_pending = load_pending_dupes()
    if not pending_dupes.empty and ws_pending is not None:
        for idx, row in pending_dupes.iterrows():
            c = st.columns([2, 2, 2, 1, 1])
            c[0].write(row['User'])
            c[1].write(row['Item'])
            c[2].write(row['Quantity'])
            confirm_key = f"confirm_dupe_{idx}"
            decline_key = f"decline_dupe_{idx}"
            if c[3].button("Confirm", key=confirm_key):
                # ------ RACE-SAFE: Check before confirming ------
                df_latest = load_data()
                already_in = not df_latest[
                    (df_latest["User"].str.lower() == row["User"].strip().lower()) &
                    (df_latest["Item"] == row["Item"]) &
                    (df_latest["Quantity"] == int(row["Quantity"]))
                ].empty
                if already_in:
                    st.info(f"Already exists: {row['User']} - {row['Item']} ({row['Quantity']})")
                else:
                    new_row = {"User": row["User"], "Item": row["Item"], "Quantity": row["Quantity"]}
                    df_latest = pd.concat([df_latest, pd.DataFrame([new_row])], ignore_index=True)
                    save_data(df_latest)
                    append_admin_log("Confirm Duplicate", f"{row['User']} - {row['Item']} ({row['Quantity']})", st.session_state['admin_user'])
                    st.success(f"Duplicate offer confirmed and added for {row['User']} - {row['Item']} ({row['Quantity']})")
                remove_pending_dupe(ws_pending, idx)
                st.rerun()
            if c[4].button("Decline", key=decline_key):
                remove_pending_dupe(ws_pending, idx)
                append_admin_log("Decline Duplicate", f"{row['User']} - {row['Item']} ({row['Quantity']})", st.session_state['admin_user'])
                st.info(f"Duplicate offer declined for {row['User']} - {row['Item']} ({row['Quantity']})")
                st.rerun()
    else:
        st.info("No pending duplicate offers.")

st.markdown("---")

# ---- DEPOSITS OVERVIEW ----
st.header("Deposits Overview")

bank_buy_pct = st.session_state.get('bank_buy_pct', DEFAULT_BANK_BUY_PCT)

for cat, items in ORIGINAL_ITEM_CATEGORIES.items():
    color = CATEGORY_COLORS.get(cat, "#FFD700")
    st.markdown(f"""
    <div style='margin-top: 38px;'></div>
    <h2 style="color:{color}; font-weight:bold; margin-bottom: 14px;">{cat}</h2>
    """, unsafe_allow_html=True)
    item_totals = []
    for item in items:
        total = df[(df["Item"] == item)]["Quantity"].sum()
        item_totals.append((item, total))
    item_totals.sort(key=lambda x: x[1], reverse=True)
    for item, total in item_totals:
        item_color = get_item_color(item)
        item_df = df[df["Item"] == item]
        target = targets[item]
        divine_val = divines[item]
        divine_total = (total / target * divine_val) if target > 0 else 0
        instant_sell_price = (divine_val / target) * bank_buy_pct / 100 if target > 0 else 0

        extra_info = ""
        if divine_val > 0 and target > 0:
            extra_info = (f"<span style='margin-left:22px; color:#AAA;'>"
                          f"[Stack = {divine_val:.2f} Divines → Current Value ≈ {divine_total:.2f} Divines | "
                          f"Instant Sell: <span style='color:#fa0;'>{instant_sell_price:.3f} Divines</span> <span style='font-size:85%; color:#888;'>(per item)</span>]</span>")
        elif divine_val > 0:
            extra_info = (f"<span style='margin-left:22px; color:#AAA;'>"
                          f"[Stack = {divine_val:.2f} Divines → Current Value ≈ {divine_total:.2f} Divines]</span>")

        st.markdown(
            f"""
            <div style='
                display:flex; 
                align-items:center; 
                border: 2px solid #222; 
                border-radius: 10px; 
                margin: 8px 0 16px 0; 
                padding: 10px 18px;
                background: #181818;
            '>
                <span style='font-weight:bold; color:{item_color}; font-size:1.18em; letter-spacing:0.5px;'>
                    [{item}]
                </span>
                <span style='margin-left:22px; font-size:1.12em; color:#FFF;'>
                    <b>Deposited:</b> {total} / {target}
                </span>
                {extra_info}
            </div>
            """,
            unsafe_allow_html=True
        )

        # GREEN BAR IF FULL, ELSE NORMAL
        if total >= target:
            st.success(f"✅ {total}/{target} – Target reached!")
            st.markdown("""
            <div style='height:22px; width:100%; background:#22c55e; border-radius:7px; display:flex; align-items:center;'>
                <span style='margin-left:10px; color:white; font-weight:bold;'>FULL</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.progress(min(total / target, 1.0), text=f"{total}/{target}")

        # ---- Per-user breakdown & payout ----
        with st.expander("Per-user breakdown & payout", expanded=False):
            user_summary = (
                item_df.groupby("User")["Quantity"]
                .sum()
                .sort_values(ascending=False)
                .reset_index()
            )
            payouts = []
            fees = []
            for idx, row in user_summary.iterrows():
                qty = row["Quantity"]
                raw_payout = (qty / target) * divine_val if target else 0
                fee = math.floor((raw_payout * 0.10) * 10) / 10
                payout_after_fee = raw_payout - (raw_payout * 0.10)
                payout_final = math.floor(payout_after_fee * 10) / 10
                payouts.append(payout_final)
                fees.append(fee)
            user_summary["Fee (10%)"] = fees
            user_summary["Payout (Divines, after fee)"] = payouts
            st.dataframe(
                user_summary.style.format({"Fee (10%)": "{:.1f}", "Payout (Divines, after fee)": "{:.1f}"}),
                use_container_width=True
            )

st.markdown("---")

# ---- DELETE BUTTONS PER ROW (EDITORS ONLY), GROUPED BY ITEM IN EXPANDERS ----
if st.session_state['is_editor']:
    st.header("Delete Deposits (permanently)")
    if len(df):
        for cat, items in ORIGINAL_ITEM_CATEGORIES.items():
            color = CATEGORY_COLORS.get(cat, "#FFD700")
            st.markdown(f'<h3 style="color:{color}; font-weight:bold;">{cat}</h3>', unsafe_allow_html=True)
            cols = st.columns(len(items))
            for idx, item in enumerate(items):
                item_rows = df[df["Item"] == item].reset_index()
                with cols[idx]:
                    with st.expander(f"{item} ({len(item_rows)} deposits)", expanded=False):
                        if not item_rows.empty:
                            for i, row in item_rows.iterrows():
                                c = st.columns([2, 2, 2, 1])
                                c[0].write(row['User'])
                                c[1].write(row['Item'])
                                c[2].write(row['Quantity'])
                                delete_button = c[3].button("Delete", key=f"delete_{row['index']}_{item}")
                                if delete_button:
                                    df = df.drop(row['index']).reset_index(drop=True)
                                    save_data(df)
                                    append_admin_log("Delete", f"{row['User']} - {row['Item']} ({row['Quantity']})", st.session_state['admin_user'])
                                    st.success(f"Permanently deleted: {row['User']} - {row['Item']} ({row['Quantity']})")
                                    st.rerun()
                        else:
                            st.info("No deposits for this item.")
    else:
        st.info("No deposits yet!")

# ---- SHOW ADMIN LOGS ----
if st.session_state['is_editor']:
    st.markdown("---")
    st.header("Admin Logs (Last 20 actions)")
    logs = load_admin_logs(n=20)
    if logs.empty:
        st.info("No admin logs yet.")
    else:
        st.dataframe(logs, use_container_width=True, hide_index=True)