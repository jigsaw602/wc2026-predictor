import streamlit as st
import pandas as pd
import json
import os
import requests
from datetime import datetime

# Set up page configuration
st.set_page_config(page_title="FIFA WC 2026 Predictor", page_icon="⚽", layout="centered")

# --- HYBRID DATABASE CONFIGURATION (Local file vs Cloud Secrets Engine) ---
DB_FILE = "db.json"

def fetch_database():
    # CLOUD DEPLOYMENT CONTEXT: Direct fallback to Streamlit Cloud Secrets Manager
    if "database_state" in st.secrets:
        try:
            data = json.loads(st.secrets["database_state"]["payload"])
            if "users" not in data: data["users"] = {}
            if "predictions" not in data: data["predictions"] = []
            return data
        except Exception:
            pass

    # LOCAL DEV CONTEXT: Fallback to your local Mac db.json file
    if not os.path.exists(DB_FILE):
        initial_structure = {"users": {}, "predictions": []}
        with open(DB_FILE, "w") as f:
            json.dump(initial_structure, f, indent=4)
        return initial_structure
    
    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            if "users" not in data: data["users"] = {}
            if "predictions" not in data: data["predictions"] = []
            return data
    except Exception:
        return {"users": {}, "predictions": []}

def db_get(key, default_value):
    # Check if a session memory override exists to handle instant UI refreshes online
    if f"cloud_{key}" in st.session_state:
        return st.session_state[f"cloud_{key}"]
    
    db = fetch_database()
    return db.get(key, default_value)

def db_set(key, value):
    # Maintain state inside session cache for instant local context tracking
    st.session_state[f"cloud_{key}"] = value
    
    # 1. Update Local File Build if running on your Mac
    db = fetch_database()
    db[key] = value
    try:
        with open(DB_FILE, "w") as f:
            json.dump(db, f, indent=4)
    except Exception:
        pass
        
    # 2. If running online, print out the backup JSON string for easy admin copy-pasting
    if "database_state" in st.secrets:
        st.info("💡 **Live Database Update Generated!** Copy the text block from the Admin Panel below into your Streamlit Secrets setting to keep records saved permanently.")
    return True

# --- STATIC FILE LOADER (Local Files vs Live GitHub Raw Streams) ---
def load_static_data(filename):
    if os.path.exists(filename):
        return pd.read_csv(filename, keep_default_na=False, na_values=[''])
    
    # ONLINE DEPLOYMENT ENGINE: Fetches directly from your raw GitHub repo stream
    # Ensure you replace 'your-username' and 'your-repo' with your actual GitHub parameters!
    GITHUB_RAW_ROOT = "https://raw.githubusercontent.com/jigsaw602/wc2026-predictor/main/"
    try:
        return pd.read_csv(f"{GITHUB_RAW_ROOT}{filename}", keep_default_na=False, na_values=[''])
    except Exception:
        st.error(f"❌ Could not locate or read raw static file asset stream: '{filename}'")
        st.stop()

# Load Static Assets
df_config = load_static_data("config.csv")
active_matchday = str(df_config.iloc[0]["Active_Matchday"]).strip()
deadline_str = str(df_config.iloc[0]["Deadline"]).strip()
deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S")

df_matches = load_static_data("matches.csv")

# Initialize Session State tracking parameters
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

# Scoring Logic Processing Engine
def calculate_points(pred_a, pred_b, actual_a, actual_b):
    if pd.isna(actual_a) or pd.isna(actual_b) or str(actual_a).strip() == "" or str(actual_b).strip() == "":
        return 0
    try:
        act_a, act_b = int(float(actual_a)), int(float(actual_b))
        p_a, p_b = int(pred_a), int(pred_b)
    except (ValueError, TypeError):
        return 0
    if p_a == act_a and p_b == act_b: return 3
    if p_a > p_b and act_a > act_b: return 1
    if p_a < p_b and act_a < act_b: return 1
    if p_a == p_b and act_a == act_b: return 1
    return 0

# App UI Header Title
st.title("⚽ FIFA World Cup 2026 Predictor")

# Navigation Setup
tabs = st.tabs(["📋 Submit Predictions", "🏆 Leaderboard"])
tab1, tab2 = tabs[0], tabs[1]

# -------------------------------------------------------------------
# TAB 1: AUTHENTICATION & SCORE SUBMISSIONS
# -------------------------------------------------------------------
with tab1:
    if st.session_state.logged_in_user is None:
        st.header("Account Authorization")
        auth_mode = st.radio("Choose Action", ["Login", "Sign Up"], horizontal=True)
        
        user_input = st.text_input("Username").strip().lower()
        pass_input = st.text_input("Password", type="password").strip()
        
        if st.button("Submit Auth"):
            users_db = db_get("users", {})
            
            if auth_mode == "Sign Up":
                if not user_input or not pass_input:
                    st.error("Fields cannot be empty!")
                elif user_input in users_db:
                    st.error("Username already taken!")
                else:
                    users_db[user_input] = pass_input
                    if db_set("users", users_db):
                        st.success("🎉 Account successfully registered! Toggle the choice above to 'Login' to enter your dashboard.")
            else:
                if user_input in users_db and str(users_db[user_input]) == pass_input:
                    st.session_state.logged_in_user = user_input
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("❌ Invalid Username or Password.")
    else:
        st.subheader(f"Welcome back, {st.session_state.logged_in_user.capitalize()}! 👋")
        if st.button("Log Out"):
            st.session_state.logged_in_user = None
            st.rerun()
            
        st.write("---")
        st.info(f"**Current Open Phase:** {active_matchday} \n\n⏳ **Submission Deadline:** {deadline_str}")
        
        is_locked = datetime.now() > deadline_dt
        if is_locked:
            st.warning("⚠️ Submissions for this round are locked! The deadline has passed.")
            
        round_matches = df_matches[df_matches["Matchday"].astype(str) == active_matchday]
        
        if round_matches.empty:
            st.info(f"No match fixtures currently scheduled for {active_matchday}.")
        else:
            all_predictions = db_get("predictions", [])
                
            user_existing_preds = {str(p["Match ID"]): p for p in all_predictions if isinstance(p, dict) and p.get("User") == st.session_state.logged_in_user}
            
            with st.form("prediction_form"):
                user_preds = {}
                for _, match in round_matches.iterrows():
                    m_id = str(match['Match ID'])
                    st.write(f"**Match {m_id}: {match['Team A']} vs {match['Team B']}**")
                    
                    default_a = int(user_existing_preds[m_id]["Pred A"]) if m_id in user_existing_preds else 0
                    default_b = int(user_existing_preds[m_id]["Pred B"]) if m_id in user_existing_preds else 0
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        pred_a = st.number_input(f"{match['Team A']} Score", min_value=0, max_value=20, step=1, value=default_a, key=f"pred_a_{m_id}", disabled=is_locked)
                    with col2:
                        pred_b = st.number_input(f"{match['Team B']} Score", min_value=0, max_value=20, step=1, value=default_b, key=f"pred_b_{m_id}", disabled=is_locked)
                    user_preds[int(m_id)] = (pred_a, pred_b)
                
                if st.form_submit_button("Save Predictions", disabled=is_locked):
                    match_ids_to_clear = round_matches["Match ID"].tolist()
                    cleaned_predictions = [p for p in all_predictions if isinstance(p, dict) and not (p.get("User") == st.session_state.logged_in_user and p.get("Match ID") in match_ids_to_clear)]
                    
                    for match_id, scores in user_preds.items():
                        cleaned_predictions.append({
                            "User": st.session_state.logged_in_user,
                            "Match ID": match_id,
                            "Pred A": scores[0],
                            "Pred B": scores[1]
                        })
                    
                    if db_set("predictions", cleaned_predictions):
                        st.success(f"⚽ Your predictions for {active_matchday} have been locked in successfully!")
                        st.rerun()

# -------------------------------------------------------------------
# TAB 2: LIVE LEADERBOARD MATRIX CALCULATIONS & ADMIN RAW EXPORT
# -------------------------------------------------------------------
with tab2:
    st.header("Tournament Leaderboard")
    predictions_list = db_get("predictions", [])
    
    if not isinstance(predictions_list, list) or len(predictions_list) == 0:
        st.info("No predictions submitted yet.")
    else:
        df_preds = pd.DataFrame(predictions_list)
        if not df_preds.empty and "Match ID" in df_preds.columns:
            df_merged = pd.merge(df_preds, df_matches, on="Match ID")
            
            df_merged['Points'] = df_merged.apply(
                lambda r: calculate_points(r['Pred A'], r['Pred B'], r['Actual A'], r['Actual B']), axis=1
            )
            
            leaderboard = df_merged.groupby("User")["Points"].sum().reset_index()
            leaderboard = leaderboard.sort_values(by="Points", ascending=False).reset_index(drop=True)
            st.dataframe(leaderboard, use_container_width=True)
        else:
            st.info("No predictions submitted yet.")

    # --- IMMUTABLE BACKUP DATA EXPORT AREA ---
    if "database_state" in st.secrets or st.session_state.logged_in_user is not None:
        st.write("---")
        with st.expander("⚙️ Admin Database Backup Panel"):
            st.write("If users register or save predictions, copy this unified text payload block into your Streamlit Advanced Settings panel to save them permanently:")
            
            current_full_db = {"users": db_get("users", {}), "predictions": db_get("predictions", [])}
            minified_json_string = json.dumps(current_full_db)
            
            st.code(f'[database_state]\npayload = \'{minified_json_string}\'')