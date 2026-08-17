import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
import json
import google.generativeai as genai
from PIL import Image
import urllib.parse 
import os
import difflib

# ==========================================
# KONFIGURATION AV APP & AI
# ==========================================
st.set_page_config(page_title="Sixtens Studieplattform", page_icon="🚀", layout="wide")

st.markdown("<style>[data-testid='stAudio'] { display: none; }</style>", unsafe_allow_html=True)

try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error("Kunde inte hitta Gemini API-nyckeln i Secrets. Har du lagt in den där?")
    st.stop()

model = genai.GenerativeModel(
    'gemini-flash-latest',
    system_instruction="Du är en pedagogisk och peppande studiecoach. Du MÅSTE uteslutande svara på 100% korrekt svenska. Du får under INGA omständigheter använda engelska låneord, engelsk stavning eller svengelska (skriv t.ex. 'Bra jobbat' och ALDRIG 'Snyggt job'). Håll alltid svaren korta, peppande och i ren brödtext utan listor."
)

# Sessionsvariabler
if 'ljud_spelat_for_quiz' not in st.session_state:
    st.session_state.ljud_spelat_for_quiz = None
if 'slutprov_fragor' not in st.session_state:
    st.session_state.slutprov_fragor = None
if 'slutprov_amne' not in st.session_state:
    st.session_state.slutprov_amne = None

# --- CALLBACK-FUNKTIONER FÖR KNAPPARNA ---
def replay_quiz():
    for key in list(st.session_state.keys()):
        if key.startswith("quiz_radio_"):
            del st.session_state[key]

def reset_quiz():
    if 'quiz_selector' in st.session_state:
        st.session_state.quiz_selector = None
    if 'ljud_spelat_for_quiz' in st.session_state:
        st.session_state.ljud_spelat_for_quiz = None
    replay_quiz()
# -----------------------------------------

st.title("Sixtens Studieplattform 🚀")

tab_planering, tab_spela_quiz, tab_repetition, tab_admin_planering, tab_skapa_quiz = st.tabs([
    "📅 Planering & Framsteg", 
    "🎮 Spela Quiz", 
    "🎓 Repetition & Slutprov",
    "📝 Hantera Planering (Föräldrar)", 
    "🛠️ Skapa Quiz (Föräldrar)"
])

# ==========================================
# DATABAS-UPPKOPPLING MED SMART CACHE (MINNE) FÖR ATT UNDVIKA BUGGAR
# ==========================================
@st.cache_resource(show_spinner=False)
def get_gsheet_connection():
    try:
        google_json_str = st.secrets["GOOGLE_JSON"]
        creds_dict = json.loads(google_json_str)
        gc = gspread.service_account_from_dict(creds_dict)
        return gc.open_by_key("1LPmKB3fAXxySRf0ZCa3GFc8FCYppSAcXLhlgJis9D3o")
    except Exception as e:
        st.error(f"Kunde inte ansluta till Google Sheets. Fel: {e}")
        st.stop()

sh = get_gsheet_connection()

@st.cache_data(ttl=60, show_spinner=False)
def fetch_sheet_data(sheet_name):
    try:
        ws = sh.worksheet(sheet_name)
        return pd.DataFrame(ws.get_all_records())
    except:
        return pd.DataFrame()

def clear_sheet_cache():
    fetch_sheet_data.clear()

# --- LÄS IN ALL DATA VIA CACHE ---
df_uppgifter_raw = fetch_sheet_data("Data")
if not df_uppgifter_raw.empty:
    df_uppgifter = df_uppgifter_raw.copy()
    df_uppgifter['_RowNumber'] = range(2, len(df_uppgifter) + 2)
    df_uppgifter = df_uppgifter.dropna(how="all").fillna("")
else:
    df_uppgifter = pd.DataFrame()

df_milstolpar = fetch_sheet_data("Milstolpar").dropna(how="all").fillna("")

# --- NY KRONOLOGISK SORTERING AV MILSTOLPAR ---
if not df_milstolpar.empty and 'Startdatum' in df_milstolpar.columns:
    # Omvandla till äkta datum-objekt
    df_milstolpar['Startdatum_obj'] = pd.to_datetime(df_milstolpar['Startdatum'], errors='coerce')
    # Sortera kronologiskt, så att närmast kommande (tidigaste datumet) hamnar högst upp
    df_milstolpar = df_milstolpar.sort_values(by='Startdatum_obj', ascending=True).reset_index(drop=True)
# ----------------------------------------------

df_highscores = fetch_sheet_data("Highscores")
df_quiz_all = fetch_sheet_data("Quiz").dropna(how="all").fillna("")

# --- GLOBALA XP & STREAK BERÄKNINGAR ---
total_xp = 0
streak_dagar = 0

if not df_highscores.empty:
    if 'Antal_Rätt' in df_highscores.columns:
        df_hs_temp = df_highscores.copy()
        df_hs_temp['Antal_Rätt'] = pd.to_numeric(df_hs_temp['Antal_Rätt'], errors='coerce').fillna(0)
        total_xp = int(df_hs_temp['Antal_Rätt'].sum() * 10)
        
    if 'Datum' in df_highscores.columns:
        df_hs_temp['DateOnly'] = pd.to_datetime(df_highscores['Datum']).dt.date
        unika_dagar = sorted(df_hs_temp['DateOnly'].unique(), reverse=True)
        
        dagens_datum = datetime.now().date()
        koll_datum = dagens_datum
        
        if unika_dagar and unika_dagar[0] == dagens_datum:
            streak_dagar = 1
            start_idx = 1
            koll_datum = dagens_datum - timedelta(days=1)
        elif unika_dagar and unika_dagar[0] == dagens_datum - timedelta(days=1):
            streak_dagar = 1
            start_idx = 1
            koll_datum = dagens_datum - timedelta(days=2)
        else:
            start_idx = 0
            
        if streak_dagar > 0:
            for d in unika_dagar[start_idx:]:
                if d == koll_datum:
                    streak_dagar += 1
                    koll_datum -= timedelta(days=1)
                else:
                    break

# ==========================================
# FLIK 1: PLANERING & FRAMSTEG
# ==========================================
with tab_planering:
    idag_obj = datetime.now()
    idag_datum = idag_obj.date()
    
    col_titel, col_streak = st.columns([3, 1])
    with col_titel:
        st.subheader("Terminens Framsteg & Tidslinje 🔋")
    with col_streak:
        st.markdown(f"<div style='background: #FFF3E0; padding: 10px; border-radius: 8px; border: 1px solid #FFCC80; text-align: center; color: #E65100; font-weight: bold;'>🔥 Dagens Streak: {streak_dagar}</div>", unsafe_allow_html=True)
        
    termin_start = datetime(2026, 8, 17).date()
    termin_slut = datetime(2026, 12, 20).date()
    totala_dagar = (termin_slut - termin_start).days

    # --- HITTA NÄSTA MILSTOLPE ---
    nasta_milstolpe_namn = ""
    dagar_till_milstolpe = -1
    
    if not df_milstolpar.empty and 'Startdatum_obj' in df_milstolpar.columns:
        # Filtrera fram milstolpar från och med idag
        framtida = df_milstolpar[df_milstolpar['Startdatum_obj'].dt.date >= idag_datum].dropna(subset=['Startdatum_obj'])
        if not framtida.empty:
            nasta = framtida.iloc[0]
            nasta_milstolpe_namn = str(nasta.get('Händelse', '')).strip()
            dagar_till_milstolpe = (nasta['Startdatum_obj'].date() - idag_datum).days
    # -----------------------------

    # --- SMART MOTIVATOR-MEDDELANDE ---
    if idag_datum < termin_start:
        dagar_kvar_start = (termin_start - idag_datum).days
        pepp_msg = f"Terminen börjar om {dagar_kvar_start} dagar. Passa på att ladda batterierna! 🔋"
        if nasta_milstolpe_namn:
            pepp_msg += f"\n\nFörsta målet att se fram emot är **{nasta_milstolpe_namn}** (om {dagar_till_milstolpe} dagar)."
        st.info(pepp_msg)
        procent_idag = 0
        
    elif idag_datum > termin_slut:
        st.success("Höstterminen är avslutad! Snyggt jobbat. 🏆")
        procent_idag = 100
        
    else:
        dagar_idag = (idag_datum - termin_start).days
        procent_idag = max(0, min(100, (dagar_idag / totala_dagar) * 100))
        passerade_veckor = dagar_idag // 7
        passerade_dagar = dagar_idag % 7
        totala_veckor = totala_dagar // 7
        
        # Grundtext
        if dagar_idag == 0:
            pepp_msg = "🚀 **Nu kör vi!** Höstterminen är officiellt igång."
        else:
            pepp_msg = f"Bra kämpat! Du har klarat av **{passerade_veckor} veckor** och **{passerade_dagar} dagar** av höstterminen."
            
        # Dynamisk text för nästa belöning/milstolpe
        if nasta_milstolpe_namn:
            if dagar_till_milstolpe == 0:
                pepp_msg += f"\n\n🎉 **Målet är nått! Idag är det dags för {nasta_milstolpe_namn}.** Njut, det är du värd!"
            elif dagar_till_milstolpe == 1:
                pepp_msg += f"\n\n🎯 **Håll ut!** Imorgon är det dags för **{nasta_milstolpe_namn}**!"
            else:
                if dagar_idag == 0:
                     pepp_msg += f" Det är **{dagar_till_milstolpe} dagar** kvar till **{nasta_milstolpe_namn}**. Nu sätter vi fart!"
                else:
                     pepp_msg += f"\n\n🎯 **Siktet är inställt:** Endast **{dagar_till_milstolpe} dagar** kvar till nästa belöning: **{nasta_milstolpe_namn}**. Fortsätt så här, du är grym!"
                     
        st.info(pepp_msg)
    # ----------------------------------
        
    html_timeline = (
        f"<div style='position: relative; width: 100%; height: 160px; margin-top: 30px; margin-bottom: 20px; font-family: sans-serif;'>"
        f"<div style='position: absolute; top: 50%; left: 0; width: 100%; height: 10px; background-color: #e0e0e0; border-radius: 5px; transform: translateY(-50%);'></div>"
        f"<div style='position: absolute; top: 50%; left: 0; width: {procent_idag}%; height: 10px; background-color: #4CAF50; border-radius: 5px; transform: translateY(-50%); z-index: 1;'></div>"
        f"<div style='position: absolute; top: 50%; left: 0%; transform: translate(0%, -50%); z-index: 2; text-align: center;'>"
        f"<div style='width: 4px; height: 24px; background-color: #999; margin: 0 auto;'></div>"
        f"<div style='position: absolute; top: 30px; left: 50%; transform: translateX(-50%); font-size: 12px; color: #666; font-weight: bold;'>Start</div>"
        f"</div>"
        f"<div style='position: absolute; top: 50%; left: 100%; transform: translate(-100%, -50%); z-index: 2; text-align: center;'>"
        f"<div style='width: 4px; height: 24px; background-color: #999; margin: 0 auto;'></div>"
        f"<div style='position: absolute; top: 30px; left: 50%; transform: translateX(-50%); font-size: 12px; color: #666; font-weight: bold;'>Mål</div>"
        f"</div>"
        f"<div style='position: absolute; top: 50%; left: {procent_idag}%; transform: translate(-50%, -50%); z-index: 4; text-align: center;'>"
        f"<div style='width: 20px; height: 20px; background-color: #2E7D32; border: 3px solid white; border-radius: 50%; box-shadow: 0 0 5px rgba(0,0,0,0.4); margin: 0 auto;'></div>"
        f"<div style='position: absolute; top: -35px; left: 50%; transform: translateX(-50%); font-size: 12px; font-weight: bold; color: #2E7D32; background: white; padding: 2px 6px; border-radius: 4px; border: 1px solid #2E7D32;'>IDAG</div>"
        f"</div>"
    )

    if not df_milstolpar.empty:
        for index, row in df_milstolpar.iterrows():
            handelse = str(row.get('Händelse', '')).strip()
            datum_str = str(row.get('Startdatum', '')).strip()
            
            if handelse and datum_str:
                milestone_date = pd.to_datetime(datum_str, errors='coerce')
                if pd.notnull(milestone_date):
                    dagar_milestone = (milestone_date.date() - termin_start).days
                    procent_pos = max(0, min(100, (dagar_milestone / totala_dagar) * 100))
                    
                    if index % 2 == 0:
                        etikett_stil = "bottom: 25px;"
                    else:
                        etikett_stil = "top: 25px;"
                        
                    html_timeline += (
                        f"<div style='position: absolute; top: 50%; left: {procent_pos}%; transform: translate(-50%, -50%); z-index: 3; text-align: center;'>"
                        f"<div style='width: 14px; height: 14px; background-color: #FFC107; border: 2px solid white; border-radius: 50%; box-shadow: 0 0 3px rgba(0,0,0,0.3); margin: 0 auto;'></div>"
                        f"<div style='position: absolute; {etikett_stil} left: 50%; transform: translateX(-50%); font-size: 11px; color: #333; background: #fff; padding: 4px 8px; border-radius: 4px; border: 1px solid #ddd; white-space: nowrap; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
                        f"🚩 <b>{handelse}</b><br><span style='font-size:9px; color:#666;'>{datum_str}</span>"
                        f"</div></div>"
                    )
    
    html_timeline += "</div>"
    st.markdown(html_timeline, unsafe_allow_html=True)
        
    st.write("---")
    st.subheader("📍 Milstolpar & Belöningar")
    
    if not df_milstolpar.empty:
        for index, row in df_milstolpar.iterrows():
            handelse = str(row.get('Händelse', '')).strip()
            start = str(row.get('Startdatum', '')).strip()
            slut = str(row.get('Slutdatum', '')).strip()
            beloning = str(row.get('Belöning', '')).strip()
            if handelse:
                html_card = f"""
                <div style="background: linear-gradient(135deg, #fafafa 0%, #f0f0f0 100%); border: 1px solid #e0e0e0; border-left: 6px solid #4CAF50; border-radius: 8px; padding: 15px; margin-bottom: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                    <div>
                        <h4 style="margin: 0 0 5px 0; color: #333; font-family: sans-serif;">🏕️ {handelse}</h4>
                        <p style="margin: 0; font-size: 13px; color: #666;">🗓️ <b>Period:</b> {start} ➔ {slut}</p>
                    </div>
                    <div style="background: #E8F5E9; padding: 10px 15px; border-radius: 6px; border: 1px dashed #81C784; text-align: center; min-width: 150px;">
                        <p style="margin: 0 0 2px 0; font-size: 11px; color: #2E7D32; text-transform: uppercase; font-weight: bold;">🎁 Din Belöning</p>
                        <p style="margin: 0; font-size: 14px; color: #1B5E20; font-weight: bold;">{beloning}</p>
                    </div>
                </div>
                """
                st.markdown(html_card, unsafe_allow_html=True)
    else:
        st.info("Inga milstolpar inlagda just nu.")
    
    st.write("---")

    if not df_uppgifter.empty:
        df_uppgifter['Datum_obj'] = pd.to_datetime(df_uppgifter['Datum'], errors='coerce')
        df_uppgifter_sorterad = df_uppgifter.sort_values(by='Datum_obj')
        
        svenska_manader = ["", "Januari", "Februari", "Mars", "April", "Maj", "Juni", "Juli", "Augusti", "September", "Oktober", "November", "December"]
        aktuell_vecka_rubrik = None
        
        for index, row in df_uppgifter_sorterad.iterrows():
            datum_obj = row['Datum_obj']
            
            if pd.notnull(datum_obj):
                vecka_nr = datum_obj.isocalendar()[1]
                manad_namn = svenska_manader[datum_obj.month]
                start_pa_veckan = datum_obj - timedelta(days=datum_obj.weekday())
                slut_pa_veckan = start_pa_veckan + timedelta(days=6)
                datum_spann = f"{start_pa_veckan.day} {svenska_manader[start_pa_veckan.month][:3].lower()} - {slut_pa_veckan.day} {svenska_manader[slut_pa_veckan.month][:3].lower()}"
                
                ny_rubrik = f"📅 Vecka {vecka_nr} | {datum_spann} | {manad_namn}"
                
                if ny_rubrik != aktuell_vecka_rubrik:
                    st.subheader(ny_rubrik)
                    aktuell_vecka_rubrik = ny_rubrik
            
            with st.container():
                col1, col2 = st.columns([1, 8])
                is_done = str(row.get('Status', '')).strip().lower() == 'klar'
                
                with col1:
                    checked_main = st.checkbox("", value=is_done, key=f"check_main_{index}")
                
                with col2:
                    amne = str(row.get('Ämne', 'Okänt ämne')).strip()
                    uppgift = str(row.get('Uppgift', '')).strip()
                    datum_str = str(row.get('Datum', '')).strip()
                    
                    etapper_str = str(row.get('Etapper', '')).strip()
                    etapp_status_str = str(row.get('Etapp_Status', '')).strip()
                    etapp_datum_str = str(row.get('Etapp_Datum', '')).strip()
                    
                    etapp_lista = []
                    status_lista = []
                    datum_lista = []
                    delim = ','
                    
                    if etapper_str and "Etapp_Status" in df_uppgifter_sorterad.columns:
                        delim = '|' if '|' in etapper_str or '|' in etapp_status_str else ','
                        etapp_lista = [e.strip() for e in etapper_str.split(delim) if e.strip()]
                        status_lista = [s.strip().lower() == 'true' for s in etapp_status_str.split(delim)] if etapp_status_str else []
                        datum_lista = [d.strip() for d in etapp_datum_str.split(delim)] if etapp_datum_str else []
                        
                        while len(status_lista) < len(etapp_lista):
                            status_lista.append(False)
                        while len(datum_lista) < len(etapp_lista):
                            datum_lista.append("")

                    if checked_main:
                        st.markdown(f"~~**{amne}**: {uppgift} (Inlämning {datum_str})~~")
                    else:
                        st.markdown(f"**{amne}**: {uppgift} (Inlämning {datum_str})")
                        
                        senaste_datum = ""
                        for i, etapp_text in enumerate(etapp_lista):
                            if etapp_text:
                                gammalt_datum = datum_lista[i] if i < len(datum_lista) else ""
                                
                                if gammalt_datum:
                                    senaste_datum = gammalt_datum
                                    visa_text = f"🔹 {etapp_text} 📅 *(Planerad: {senaste_datum})*"
                                elif ',' in etapp_text:
                                    delar = etapp_text.rsplit(',', 1)
                                    uppgift_del = delar[0].strip()
                                    senaste_datum = delar[1].strip()
                                    visa_text = f"🔹 {uppgift_del} 📅 *(Planerad: {senaste_datum})*"
                                else:
                                    if senaste_datum:
                                        visa_text = f"🔹 {etapp_text} 📅 *(Planerad: {senaste_datum})*"
                                    else:
                                        visa_text = f"🔹 {etapp_text}"
                                    
                                etapp_checked = st.checkbox(visa_text, value=status_lista[i], key=f"etapp_{index}_{i}")
                                
                                # Om en etapp klickas i/ur
                                if etapp_checked != status_lista[i]:
                                    status_lista[i] = etapp_checked
                                    new_status_str = delim.join(["True" if s else "False" for s in status_lista])
                                    
                                    ws_data = sh.worksheet("Data")
                                    ws_data.update_cell(row['_RowNumber'], df_uppgifter_sorterad.columns.get_loc("Etapp_Status") + 1, new_status_str)
                                    
                                    # Känner av om alla etapper blev klara, eller om en etapp bockades ur
                                    if all(status_lista) and not is_done:
                                        ws_data.update_cell(row['_RowNumber'], df_uppgifter_sorterad.columns.get_loc("Status") + 1, "Klar")
                                    elif not all(status_lista) and is_done:
                                        ws_data.update_cell(row['_RowNumber'], df_uppgifter_sorterad.columns.get_loc("Status") + 1, "Ej klar")
                                        
                                    clear_sheet_cache()
                                    st.rerun()
                
                # Om huvuduppgiften klickas i/ur
                if checked_main != is_done:
                    ny_status = "Klar" if checked_main else "Ej klar"
                    ws_data = sh.worksheet("Data")
                    ws_data.update_cell(row['_RowNumber'], df_uppgifter_sorterad.columns.get_loc("Status") + 1, ny_status)
                    
                    if etapp_lista:
                        ny_etapp_status = delim.join(["True" if checked_main else "False"] * len(etapp_lista))
                        ws_data.update_cell(row['_RowNumber'], df_uppgifter_sorterad.columns.get_loc("Etapp_Status") + 1, ny_etapp_status)
                        
                    clear_sheet_cache()
                    st.rerun()
            st.write("---")

# ==========================================
# FLIK 2: SPELA QUIZ
# ==========================================
with tab_spela_quiz:
    st.header("🎮 Dags för Quiz!")
    
    try:
        if 'Årskurs' not in df_quiz_all.columns:
            df_quiz_all['Årskurs'] = ""
        if 'Kategori' not in df_quiz_all.columns:
            df_quiz_all['Kategori'] = ""
            
        df_quiz_all['Årskurs'] = df_quiz_all['Årskurs'].replace("", "Osorterat")
        df_quiz_all['Kategori'] = df_quiz_all['Kategori'].replace("", "Osorterat")
            
        nivaer = [
            (0, "Nybörjare 🥚"),
            (50, "Lärling 📖"),
            (150, "Klokuggla 🦉"),
            (300, "Bokslukare 📚"),
            (500, "Mästare 🏅"),
            (800, "Quiz-Ninja 🥷"),
            (1500, "Studie-Boss 👑")
        ]
        
        current_level = 1
        titel = "Nybörjare 🥚"
        prev_xp = 0
        next_xp = 50
        
        for i, (xp_krav, namn) in enumerate(nivaer):
            if total_xp >= xp_krav:
                current_level = i + 1
                titel = namn
                prev_xp = xp_krav
                if i + 1 < len(nivaer):
                    next_xp = nivaer[i+1][0]
                else:
                    next_xp = total_xp
                    
        if next_xp > prev_xp:
            progress = (total_xp - prev_xp) / (next_xp - prev_xp)
        else:
            progress = 1.0 
        
        st.markdown("### 🏆 Spelarprofil")
        col1, col2, col3 = st.columns([1, 1, 3])
        with col1:
            st.metric(label="Totalt XP", value=f"{total_xp} XP")
        with col2:
            st.metric(label="Dagens Streak", value=f"{streak_dagar} 🔥")
        with col3:
            st.write(f"**Level {current_level}: {titel}**")
            st.progress(progress)
            if next_xp > prev_xp:
                st.caption(f"{total_xp} / {next_xp} XP till Level {current_level + 1}")
            else:
                st.caption("Maxnivå nådd! Helt otroligt!")
        st.write("---")
        
        if df_quiz_all.empty:
            st.info("Frågebanken är tom. Gå till fliken 'Skapa Quiz' och ladda upp det första provet!")
        else:
            st.subheader("📚 Välj i arkivet")
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                val_arskurs = st.selectbox("1. Välj Årskurs", sorted(df_quiz_all['Årskurs'].unique()))
            
            df_filtered_arskurs = df_quiz_all[df_quiz_all['Årskurs'] == val_arskurs]
            
            with col_b:
                val_kategori = st.selectbox("2. Välj Ämne", sorted(df_filtered_arskurs['Kategori'].unique()))
                
            df_filtered_kategori = df_filtered_arskurs[df_filtered_arskurs['Kategori'] == val_kategori]
            
            with col_c:
                val_quiz = st.selectbox("3. Välj Quiz", df_filtered_kategori['Quiz_Namn'].unique(), index=None, placeholder="Välj ett prov...", key="quiz_selector")
            st.write("---")
            
            if st.session_state.quiz_selector is None:
                st.session_state.ljud_spelat_for_quiz = None
                st.success("👋 Välkommen in! Gör valen i rullgardinsmenyerna ovan för att starta ett test och börja samla XP.")
                safe_prompt = urllib.parse.quote("beautiful welcoming glowing library full of academic books, empty desk, highly detailed, no people, no faces")
                bild_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=800&height=300&nologo=true"
                st.image(bild_url, use_container_width=True)
            else:
                if st.session_state.ljud_spelat_for_quiz != st.session_state.quiz_selector:
                    if os.path.exists("start.mp3"):
                        st.audio("start.mp3", format="audio/mp3", autoplay=True)
                    st.session_state.ljud_spelat_for_quiz = st.session_state.quiz_selector

                quiz_namn_lower = val_kategori.lower() + " " + st.session_state.quiz_selector.lower()
                
                if "geografi" in quiz_namn_lower or "klimat" in quiz_namn_lower:
                    tema = "globe, world map, earth landscapes, topography, weather"
                elif "spanska" in quiz_namn_lower:
                    tema = "spanish flag, madrid streets, spanish dictionary, travel to spain"
                elif "historia" in quiz_namn_lower:
                    tema = "ancient history, historical artifacts, old parchment, museum"
                elif "svenska" in quiz_namn_lower or "engelska" in quiz_namn_lower:
                    tema = "stack of books, alphabet, reading glasses, library, dictionary"
                elif "matte" in quiz_namn_lower or "matematik" in quiz_namn_lower:
                    tema = "mathematical equations, geometry, calculator, blueprint"
                elif "biologi" in quiz_namn_lower or "no" in quiz_namn_lower:
                    tema = "nature, microscope, dna, biology, forest"
                else:
                    tema = "school desk, open textbooks, library, studying"

                eng_prompt = f"{tema}, beautiful academic educational photography, no people, no faces, high quality"
                safe_prompt = urllib.parse.quote(eng_prompt)
                bild_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=800&height=300&nologo=true"
                
                st.image(bild_url, use_container_width=True)
                
                df_valt_quiz = df_filtered_kategori[df_filtered_kategori['Quiz_Namn'] == st.session_state.quiz_selector].reset_index(drop=True)
                
                tidigare_rekord = 0
                if not df_highscores.empty:
                    df_hs_filter = df_highscores[df_highscores['Ämne'] == st.session_state.quiz_selector]
                    if not df_hs_filter.empty:
                        tidigare_rekord = pd.to_numeric(df_hs_filter['Antal_Rätt'], errors='coerce').fillna(0).max()
                
                st.write(f"**Du spelar:** {val_kategori} - {st.session_state.quiz_selector}")
                
                spellage = st.radio("Välj spelläge:", ["📝 Flervalsquiz (Samla XP)", "🃏 Vändkort (Övningsläge)"], horizontal=True)
                st.write("---")
                
                if spellage == "📝 Flervalsquiz (Samla XP)":
                    with st.form("quiz_form"):
                        user_answers = {}
                        for index, row in df_valt_quiz.iterrows():
                            st.markdown(f"**Fråga {index + 1}: {row['Fråga']}**")
                            
                            if 'Ledtråd' in df_valt_quiz.columns and str(row['Ledtråd']).strip():
                                with st.expander("💡 Behöver du en ledtråd?"):
                                    st.info(row['Ledtråd'])
                            
                            alt_str = str(row['Alternativ'])
                            if '|' in alt_str:
                                options = [opt.strip() for opt in alt_str.split('|')]
                            else:
                                options = [opt.strip() for opt in alt_str.split(',')]
                            
                            user_answers[index] = st.radio("Ditt svar:", options, key=f"quiz_radio_{index}")
                            st.write("---")
                        
                        submitted = st.form_submit_button("✅ Rätta mitt quiz!")
                        
                        if submitted:
                            correct_count = 0
                            fel_fragor = [] 
                            
                            st.header("Ditt Resultat:")
                            
                            for index, row in df_valt_quiz.iterrows():
                                correct_answer = str(row['Rätt_svar']).strip()
                                forklaring = str(row.get('Förklaring', '')).strip()
                                
                                if user_answers[index] == correct_answer:
                                    st.success(f"Fråga {index + 1}: Helt rätt! 🎉 ({correct_answer})")
                                    if forklaring:
                                        st.caption(f"ℹ️ Bra att veta: {forklaring}")
                                    correct_count += 1
                                else:
                                    st.error(f"Fråga {index + 1}: Tyvärr fel. Rätt svar var: {correct_answer}")
                                    fel_fragor.append(str(row['Fråga']))
                                    if forklaring:
                                        st.info(f"💡 **Varför?** {forklaring}")
                            
                            total_q = len(df_valt_quiz)
                            score_percent = int((correct_count / total_q) * 100)
                            
                            ny_xp = correct_count * 10
                            st.metric(label="Poäng", value=f"{correct_count} / {total_q} ({score_percent}%)", delta=f"+{ny_xp} XP!")
                            
                            dagens_datum = datetime.now().strftime("%Y-%m-%d %H:%M")
                            
                            ws_hs = sh.worksheet("Highscores")
                            ws_hs.append_row([dagens_datum, st.session_state.quiz_selector, correct_count, f"{score_percent}%"])
                            clear_sheet_cache()
                            
                            if correct_count > tidigare_rekord and tidigare_rekord > 0:
                                st.toast("🏆 NYTT PERSONBÄSTA!", icon="🎉")
                                st.balloons()
                                st.success(f"Grymt jobbat! Du slog ditt gamla rekord på {int(tidigare_rekord)} rätt!")
                            elif score_percent == 100:
                                st.balloons()
                                st.success("Fantastiskt! Alla rätt! 🏆")
                                if os.path.exists("success.mp3"):
                                    st.audio("success.mp3", format="audio/mp3", autoplay=True)
                            elif score_percent >= 50:
                                st.info("Snyggt jobbat! Du kan klara alla om du försöker igen.")
                            else:
                                st.warning("Bra kämpat! Läs på lite till och testa igen.")
                                
                            st.write("---")
                            with st.spinner("🤖 Coachen analyserar ditt resultat..."):
                                coach_prompt = f"Eleven fick precis {correct_count} av {total_q} rätt på sitt quiz i {val_kategori}. "
                                if fel_fragor:
                                    coach_prompt += f"Hen svarade fel på dessa områden: {', '.join(fel_fragor)}. Skriv ett kort, peppande meddelande till eleven (max 30 ord)."
                                else:
                                    coach_prompt += "Skriv ett väldigt kort och extremt peppande meddelande till eleven (max 20 ord) för att fira alla rätt!"

                                try:
                                    response = model.generate_content(coach_prompt, generation_config={"max_output_tokens": 200})
                                    coach_svar = response.text
                                    st.info(f"🦸‍♂️ **Coachen säger:** {coach_svar}")
                                except Exception as e:
                                    st.warning(f"Coachen kunde inte svara just nu (Timeout eller nätverksfel). Felkod: {e}")
                
                else:
                    st.info("💡 **Övningsläge!** Vändkorten ger inga XP, utan är till för att plugga in faktan innan du gör provet. Klicka på raderna för att vända korten.")
                    for index, row in df_valt_quiz.iterrows():
                        st.markdown(f"#### Fråga {index + 1}")
                        st.markdown(f"**{row['Fråga']}**")
                        
                        with st.expander("🔄 Klicka här för att vända kortet och se svaret"):
                            st.success(f"**Rätt svar:** {row['Rätt_svar']}")
                            if 'Förklaring' in df_valt_quiz.columns and str(row['Förklaring']).strip():
                                st.caption(f"ℹ️ **Varför?** {row['Förklaring']}")
                        st.write("---")

                if st.session_state.quiz_selector is not None:
                    st.write("---")
                    col_btn1, col_btn2 = st.columns(2)
                    
                    with col_btn1:
                        st.button("🔄 Spela om Quiz", on_click=replay_quiz)
                            
                    with col_btn2:
                        st.button("⬅️ Klar! Återgå till startsidan", on_click=reset_quiz)
                            
                    st.write("---")
                    st.subheader(f"🏆 Highscore-tavla för {st.session_state.quiz_selector}")
                    
                    if not df_highscores.empty:
                        df_hs_filter_uppdaterad = df_highscores[df_highscores['Ämne'] == st.session_state.quiz_selector]
                        if not df_hs_filter_uppdaterad.empty:
                            st.dataframe(df_hs_filter_uppdaterad.tail(5), use_container_width=True)
                        else:
                            st.write("Inga rekord för detta prov ännu!")
                    else:
                        st.write("Inga rekord sparade ännu!")

    except Exception as e:
        st.error(f"Ett fel uppstod vid laddning av quiz-modulen. Felmeddelande: {e}")

# ==========================================
# FLIK 3: REPETITION & SLUTPROV
# ==========================================
with tab_repetition:
    st.header("🎓 Repetition & Slutprov")
    st.markdown("Här samlas allt som har pluggats under terminen. Dags att knyta ihop säcken inför stora prov!")
    
    amnen_historik = []
    if not df_uppgifter.empty:
        amnen_historik.extend([str(a).strip() for a in df_uppgifter['Ämne'].unique() if str(a).strip()])
    if not df_quiz_all.empty:
        amnen_historik.extend([str(a).strip() for a in df_quiz_all['Kategori'].unique() if str(a).strip()])
        
    amnen_historik = sorted(list(set(amnen_historik)))
    
    if amnen_historik:
        valt_amne_rep = st.selectbox("Välj ämne för repetition:", amnen_historik, key="rep_amne")
        
        if valt_amne_rep:
            st.write("---")
            # --- 1. HISTORIK & LÄSLISTA ---
            st.subheader(f"📚 Din historik och läslista för {valt_amne_rep}")
            
            har_historik = False
            if not df_uppgifter.empty:
                df_rep_amne = df_uppgifter[df_uppgifter['Ämne'].str.strip().str.lower() == valt_amne_rep.lower()]
                for index, row in df_rep_amne.iterrows():
                    uppgift = str(row.get('Uppgift', '')).strip()
                    etapper_str = str(row.get('Etapper', '')).strip()
                    
                    if uppgift or etapper_str:
                        har_historik = True
                        st.markdown(f"**Kapitel / Uppgift:** {uppgift}")
                        
                        if etapper_str:
                            delim = '|' if '|' in etapper_str else ','
                            etapper = [e.strip() for e in etapper_str.split(delim) if e.strip()]
                            for e in etapper:
                                st.markdown(f"📖 {e}")
                        st.write("")
            
            if not har_historik:
                st.info("Hittade ingen detaljerad läshistorik för detta ämne just nu, men du kan fortfarande göra slutprovet nedan!")
            
            st.write("---")
            
            # --- 2. SLUTPROV ---
            st.subheader(f"🧠 Det Stora Slutprovet i {valt_amne_rep}")
            st.info("🦸‍♂️ **Coachen säger:** Dags att testa vad som fastnat! Läs igenom din sammanställda historik här ovanför. När du känner dig redo, klicka på knappen nedanför för att slumpa fram ett unikt slutprov från hela terminen. Du fixar detta!")
            
            if st.button(f"🚀 Generera Slutprov i {valt_amne_rep}"):
                for key in list(st.session_state.keys()):
                    if key.startswith("slutprov_radio_"):
                        del st.session_state[key]
                        
                try:
                    df_quiz_rep = df_quiz_all[df_quiz_all['Kategori'].str.strip().str.lower() == valt_amne_rep.lower()].copy()
                    
                    if df_quiz_rep.empty:
                        st.warning(f"Kunde inte hitta några frågor i frågebanken för ämnet {valt_amne_rep}.")
                    else:
                        def is_similar(a, b, threshold=0.75):
                            return difflib.SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio() > threshold
                            
                        unique_rows = []
                        for index, row in df_quiz_rep.iterrows():
                            q_text = row['Fråga']
                            a_text = row['Rätt_svar']
                            
                            is_dup = False
                            for u_row in unique_rows:
                                if is_similar(q_text, u_row['Fråga'], 0.75) or is_similar(a_text, u_row['Rätt_svar'], 0.75):
                                    is_dup = True
                                    break
                            
                            if not is_dup:
                                unique_rows.append(row)
                                
                        df_quiz_rep_clean = pd.DataFrame(unique_rows)
                        
                        antal_fragor = min(20, len(df_quiz_rep_clean))
                        st.session_state.slutprov_fragor = df_quiz_rep_clean.sample(n=antal_fragor).reset_index(drop=True)
                        st.session_state.slutprov_amne = valt_amne_rep
                        
                except Exception as e:
                    st.error(f"Ett fel uppstod vid generering av provet: {e}")
            
            if st.session_state.slutprov_fragor is not None and st.session_state.slutprov_amne == valt_amne_rep:
                st.write("---")
                st.success(f"Ditt unika slutprov är klart! Appen drog {len(st.session_state.slutprov_fragor)} unika frågor ur {valt_amne_rep}-arkivet.")
                
                df_slutprov = st.session_state.slutprov_fragor
                
                with st.form("slutprov_form"):
                    user_answers_sp = {}
                    for index, row in df_slutprov.iterrows():
                        st.markdown(f"**Fråga {index + 1}: {row['Fråga']}**")
                        
                        alt_str = str(row['Alternativ'])
                        if '|' in alt_str:
                            options = [opt.strip() for opt in alt_str.split('|')]
                        else:
                            options = [opt.strip() for opt in alt_str.split(',')]
                        
                        user_answers_sp[index] = st.radio("Ditt svar:", options, key=f"slutprov_radio_{index}")
                        st.write("---")
                    
                    submitted_sp = st.form_submit_button("✅ Lämna in Slutprovet!")
                    
                    if submitted_sp:
                        correct_count_sp = 0
                        fel_fragor_sp = [] 
                        
                        st.header("Ditt Resultat:")
                        
                        for index, row in df_slutprov.iterrows():
                            correct_answer = str(row['Rätt_svar']).strip()
                            forklaring = str(row.get('Förklaring', '')).strip()
                            
                            if user_answers_sp[index] == correct_answer:
                                st.success(f"Fråga {index + 1}: Helt rätt! 🎉 ({correct_answer})")
                                correct_count_sp += 1
                            else:
                                st.error(f"Fråga {index + 1}: Tyvärr fel. Rätt svar var: {correct_answer}")
                                fel_fragor_sp.append(str(row['Fråga']))
                                if forklaring:
                                    st.info(f"💡 **Varför?** {forklaring}")
                        
                        total_q_sp = len(df_slutprov)
                        score_percent_sp = int((correct_count_sp / total_q_sp) * 100)
                        
                        ny_xp_sp = correct_count_sp * 20 
                        st.metric(label="Poäng", value=f"{correct_count_sp} / {total_q_sp} ({score_percent_sp}%)", delta=f"+{ny_xp_sp} XP (Dubbel XP)!")
                        
                        dagens_datum = datetime.now().strftime("%Y-%m-%d %H:%M")
                        ws_hs = sh.worksheet("Highscores")
                        ws_hs.append_row([dagens_datum, f"Slutprov - {valt_amne_rep}", correct_count_sp, f"{score_percent_sp}%"])
                        clear_sheet_cache()
                        
                        if score_percent_sp == 100:
                            st.balloons()
                            st.success("Otroligt! Alla rätt på det stora slutprovet! 🏆")
                            if os.path.exists("success.mp3"):
                                st.audio("success.mp3", format="audio/mp3", autoplay=True)
                        elif score_percent_sp >= 50:
                            st.info("Snyggt jobbat! Gå igenom det du missade och försök igen för att nå 100%.")
                        else:
                            st.warning("Bra kämpat! Läs på lite mer i listan ovan och testa igen.")
                            
                        st.write("---")
                        with st.spinner("🤖 Coachen analyserar ditt resultat..."):
                            coach_prompt_sp = f"Eleven gjorde precis ett stort slutprov i {valt_amne_rep} och fick {correct_count_sp} av {total_q_sp} rätt. "
                            if fel_fragor_sp:
                                coach_prompt_sp += f"Hen svarade fel på dessa områden: {', '.join(fel_fragor_sp)}. Skriv ett kort, peppande meddelande (max 30 ord)."
                            else:
                                coach_prompt_sp += "Skriv ett extremt peppande meddelande (max 20 ord) för att fira att hen spikade hela slutprovet."
                            
                            try:
                                response_sp = model.generate_content(coach_prompt_sp, generation_config={"max_output_tokens": 200})
                                st.info(f"🦸‍♂️ **Coachen säger:** {response_sp.text}")
                            except Exception as e:
                                st.warning("Coachen vilar just nu.")

    else:
        st.info("Det finns inga registrerade ämnen i historiken ännu.")

# ==========================================
# FLIK 4: HANTERA PLANERING (FÖRÄLDRAR)
# ==========================================
with tab_admin_planering:
    st.header("📝 Hantera Läxor & Milstolpar")
    st.markdown("Här kan ni lägga till ny planering direkt i systemet, så slipper ni öppna Google Sheets.")
    
    col_admin1, col_admin2 = st.columns(2)
    
    with col_admin1:
        st.subheader("📚 Lägg till ny uppgift/läxa")
        with st.form("form_ny_uppgift"):
            ny_amne = st.text_input("Ämne (t.ex. Engelska)")
            ny_uppgift = st.text_input("Uppgift (t.ex. Glosor kap 3)")
            ny_datum = st.date_input("Inlämningsdatum")
            
            st.markdown("**(Frivilligt) Dela upp i mindre etapper:**")
            st.info("💡 **Så här skriver du:** Skriv en etapp per rad. Appen letar alltid efter det *sista* kommatecknet på raden för att klippa ut datumet och visa en snygg kalender-ikon 📅.\n\nDu kan alltså använda andra kommatecken i själva uppgiftstexten utan problem. Om en rad saknar datum, lånar den automatiskt datumet från raden ovanför.\n\n**Exempel:**  \nLäs s21 - s24, Gör uppgift s1 - s5, 16-18 aug  \nLäs s25 - s28, Gör uppgift s6 - s11, 19-24 aug  \nRepetera glosorna")
            
            ny_etapper_area = st.text_area("Etapper:", placeholder="Läs s21 - s24, Gör uppgift s1 - s5, 16-18 aug\nLäs s25 - s28, Gör uppgift s6 - s11, 19-24 aug\nRepetera glosorna")
            
            submit_uppgift = st.form_submit_button("Spara uppgift 💾")
            if submit_uppgift:
                if not ny_amne or not ny_uppgift:
                    st.warning("Ämne och Uppgift måste fyllas i!")
                else:
                    try:
                        etapp_rader = [r.strip().replace('|', '-') for r in ny_etapper_area.split('\n') if r.strip()]
                        num_etapper = len(etapp_rader)
                        
                        ny_etapp_status = "|".join(["False"] * num_etapper)
                        ny_etapper = "|".join(etapp_rader)
                        ny_etapp_datum = "|".join([""] * num_etapper)
                        
                        ws_data = sh.worksheet("Data")
                        headers = ws_data.row_values(1)
                        new_row = [""] * len(headers)
                        
                        if "Ämne" in headers: new_row[headers.index("Ämne")] = ny_amne
                        if "Uppgift" in headers: new_row[headers.index("Uppgift")] = ny_uppgift
                        if "Datum" in headers: new_row[headers.index("Datum")] = str(ny_datum)
                        if "Status" in headers: new_row[headers.index("Status")] = "Ej klar"
                        if "Etapper" in headers: new_row[headers.index("Etapper")] = ny_etapper
                        if "Etapp_Status" in headers: new_row[headers.index("Etapp_Status")] = ny_etapp_status
                        if "Etapp_Datum" in headers: new_row[headers.index("Etapp_Datum")] = ny_etapp_datum
                        
                        ws_data.append_row(new_row)
                        clear_sheet_cache()
                        st.success(f"✅ {ny_amne} tillagd!")
                        st.rerun() 
                    except Exception as e:
                        st.error(f"Ett fel uppstod: {e}")

        # --- REDIGERA BEFINTLIGA UPPGIFTER MED AUTO-ÅTERSTÄLLNING ---
        st.write("---")
        st.subheader("✏️ Redigera befintlig uppgift")
        
        if not df_uppgifter.empty:
            uppgift_options = []
            row_map = {}
            for idx, row in df_uppgifter.iterrows():
                status_mark = "✅ " if str(row.get('Status', '')).strip().lower() == 'klar' else "⏳ "
                display_text = f"{status_mark}{row['Ämne']}: {row['Uppgift']} ({row['Datum']})"
                uppgift_options.append(display_text)
                row_map[display_text] = row
                
            vald_uppgift_text = st.selectbox("Välj uppgift att redigera", ["Välj en uppgift..."] + uppgift_options, key="edit_task_selectbox")
            
            if vald_uppgift_text != "Välj en uppgift...":
                vald_row = row_map[vald_uppgift_text]
                
                with st.form("form_redigera_uppgift"):
                    red_amne = st.text_input("Ämne", value=str(vald_row.get('Ämne', '')))
                    red_uppgift = st.text_input("Uppgift", value=str(vald_row.get('Uppgift', '')))
                    
                    try:
                        parsed_date = datetime.strptime(str(vald_row.get('Datum', '')), "%Y-%m-%d").date()
                    except:
                        parsed_date = datetime.now().date()
                        
                    red_datum = st.date_input("Inlämningsdatum", value=parsed_date)
                    
                    st.markdown("**Etapper:**")
                    
                    gamla_etapper_str = str(vald_row.get('Etapper', '')).strip()
                    gamla_datum_str = str(vald_row.get('Etapp_Datum', '')).strip()
                    gamla_status_str = str(vald_row.get('Etapp_Status', '')).strip()
                    
                    delim = '|' if '|' in gamla_etapper_str or '|' in gamla_status_str else ','
                    gamla_etapper_lista = [e.strip() for e in gamla_etapper_str.split(delim)] if gamla_etapper_str else []
                    gamla_datum_lista = [d.strip() for d in gamla_datum_str.split(delim)] if gamla_datum_str else []
                    gamla_status_lista = [s.strip() for s in gamla_status_str.split(delim)] if gamla_status_str else []
                    
                    text_area_rader = []
                    for i, etapp in enumerate(gamla_etapper_lista):
                        if etapp:
                            d = gamla_datum_lista[i] if i < len(gamla_datum_lista) else ""
                            if d and d not in etapp:
                                text_area_rader.append(f"{etapp}, {d}")
                            else:
                                text_area_rader.append(etapp)
                                
                    red_etapper_area = st.text_area("Ändra eller lägg till etapper (en per rad):", value="\n".join(text_area_rader), height=150)
                    
                    submit_redigera = st.form_submit_button("Spara ändringar 💾")
                    
                    if submit_redigera:
                        if not red_amne or not red_uppgift:
                            st.warning("Ämne och Uppgift måste fyllas i!")
                        else:
                            try:
                                nya_etapp_rader = [r.strip().replace('|', '-') for r in red_etapper_area.split('\n') if r.strip()]
                                num_nya_etapper = len(nya_etapp_rader)
                                
                                ny_status_lista = []
                                for i in range(num_nya_etapper):
                                    if i < len(gamla_status_lista):
                                        ny_status_lista.append(gamla_status_lista[i])
                                    else:
                                        ny_status_lista.append("False")
                                
                                ny_etapper = "|".join(nya_etapp_rader)
                                ny_etapp_datum = "|".join([""] * num_nya_etapper)
                                ny_etapp_status = "|".join(ny_status_lista)
                                
                                r_idx = vald_row['_RowNumber']
                                ws_data = sh.worksheet("Data")
                                headers = ws_data.row_values(1)
                                
                                with st.spinner("Sparar ändringar..."):
                                    if "Ämne" in headers: ws_data.update_cell(r_idx, headers.index("Ämne") + 1, red_amne)
                                    if "Uppgift" in headers: ws_data.update_cell(r_idx, headers.index("Uppgift") + 1, red_uppgift)
                                    if "Datum" in headers: ws_data.update_cell(r_idx, headers.index("Datum") + 1, str(red_datum))
                                    if "Etapper" in headers: ws_data.update_cell(r_idx, headers.index("Etapper") + 1, ny_etapper)
                                    if "Etapp_Status" in headers: ws_data.update_cell(r_idx, headers.index("Etapp_Status") + 1, ny_etapp_status)
                                    if "Etapp_Datum" in headers: ws_data.update_cell(r_idx, headers.index("Etapp_Datum") + 1, ny_etapp_datum)
                                
                                clear_sheet_cache()
                                if "edit_task_selectbox" in st.session_state:
                                    del st.session_state["edit_task_selectbox"]
                                    
                                st.toast("✅ Ändringarna sparades och uppgiften har uppdaterats!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Ett fel uppstod vid sparande: {e}")

    with col_admin2:
        st.subheader("📍 Lägg till ny milstolpe")
        with st.form("form_ny_milstolpe"):
            ny_handelse = st.text_input("Händelse (t.ex. Höstlov)")
            ny_start = st.date_input("Startdatum")
            ny_slut = st.date_input("Slutdatum")
            ny_beloning = st.text_input("Belöning (t.ex. Spela 2h extra)")
            
            submit_milstolpe = st.form_submit_button("Spara milstolpe 🏆")
            if submit_milstolpe:
                if not ny_handelse:
                    st.warning("Händelse måste fyllas i!")
                else:
                    try:
                        ws_milstolpar = sh.worksheet("Milstolpar")
                        m_headers = ws_milstolpar.row_values(1)
                        m_row = [""] * len(m_headers)
                        
                        if "Händelse" in m_headers: m_row[m_headers.index("Händelse")] = ny_handelse
                        if "Startdatum" in m_headers: m_row[m_headers.index("Startdatum")] = str(ny_start)
                        if "Slutdatum" in m_headers: m_row[m_headers.index("Slutdatum")] = str(ny_slut)
                        if "Belöning" in m_headers: m_row[m_headers.index("Belöning")] = ny_beloning
                        
                        ws_milstolpar.append_row(m_row)
                        clear_sheet_cache()
                        st.success(f"✅ Milstolpe '{ny_handelse}' tillagd!")
                    except Exception as e:
                        st.error(f"Ett fel uppstod: {e}")

# ==========================================
# FLIK 5: SKAPA QUIZ (FÖRÄLDRAR)
# ==========================================
with tab_skapa_quiz:
    st.header("🛠️ Bygg upp frågebanken")
    st.markdown("Bilderna analyseras och sparas som ett nytt test i arkivet.")
    
    col1, col2 = st.columns(2)
    with col1:
        arskurs = st.selectbox("Årskurs", ["Åk 4", "Åk 5", "Åk 6", "Åk 7", "Åk 8", "Åk 9", "Gymnasiet"], index=3)
    with col2:
        kategori = st.text_input("Ämne / Kategori", placeholder="t.ex. Geografi, Spanska")
        
    quiz_namn = st.text_input("Namnge detta Quiz", placeholder="t.ex. Huvudstäder, Klimat Vecka 40")
    
    uppladdade_filer = st.file_uploader("Välj bilder (JPG/PNG)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    
    if st.button("Generera och spara i arkivet ✨"):
        if not quiz_namn or not kategori:
            st.warning("⚠️ Du måste fylla i kategori och namn på quizet!")
        elif not uppladdade_filer:
            st.warning("⚠️ Du måste ladda upp minst en bild!")
        else:
            with st.spinner("AI:n analyserar bilderna och bygger provet... (Tar ca 1-3 minuter)"):
                try:
                    ai_bilder = [Image.open(f) for f in uppladdade_filer]
                    
                    prompt = """
                    Du är en pedagogisk lärare. Läs texten i bilderna. 
                    Skapa max 10 stycken flervalsfrågor baserat på texten.
                    Varje fråga ska ha 4 svarsalternativ där endast ett är rätt.
                    Skapa en kort ledtråd till varje fråga.
                    Skapa även en kort förklaring till VARFÖR det rätta svaret är rätt, för att hjälpa eleven att förstå och minnas.
                    Du MÅSTE returnera svaret EXAKT i detta JSON-format. Använd ALDRIG kommatecken för att separera alternativen, använd BARA vertikalstreck (|) som i exemplet:
                    [
                      {
                        "Ämne": "Kort ämnesnamn",
                        "Fråga": "Själva frågan",
                        "Alternativ": "Alt 1 | Alt 2 | Alt 3 | Alt 4",
                        "Rätt_svar": "Alt 2",
                        "Ledtråd": "En hjälpsam liten knuff i rätt riktning.",
                        "Förklaring": "Fakta som förklarar varför svaret är det rätta."
                      }
                    ]
                    """
                    innehall = [prompt] + ai_bilder
                    response = model.generate_content(innehall)
                    
                    raw_text = response.text.replace("```json", "").replace("```", "").strip()
                    quiz_data = json.loads(raw_text)
                    
                    ws_quiz_target = sh.worksheet("Quiz")
                    for item in quiz_data:
                        ledtrad_text = item.get("Ledtråd", "")
                        forklaring_text = item.get("Förklaring", "")
                        ws_quiz_target.append_row([arskurs, kategori, quiz_namn, item["Ämne"], item["Fråga"], item["Alternativ"], item["Rätt_svar"], ledtrad_text, forklaring_text])
                    
                    clear_sheet_cache()
                    st.success(f"✅ Provet '{quiz_namn}' har skapats och arkiverats!")
                except Exception as e:
                    st.error(f"Ett fel uppstod: {e}. AI:n kanske inte kunde läsa texten tydligt. Prova igen!")