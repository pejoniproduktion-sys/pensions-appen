import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime
import plotly.express as px

st.set_page_config(page_title="Pensionskalkylator", page_icon="💰", layout="wide")

# --- HÄMTA DATA FRÅN GSHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)
sheet_url = "https://docs.google.com/spreadsheets/d/1WI1KfXWkygOVdL8XxWiHprzNyCax0cIowxzthBta_3I/edit?gid=0#gid=0"

df_settings = conn.read(spreadsheet=sheet_url, ttl=600, nrows=14, header=None)

def get_setting_val(row_index, col_index=1):
    try:
        if row_index < len(df_settings) and col_index < len(df_settings.columns):
            val = str(df_settings.iloc[row_index, col_index]).replace(' ', '').replace(',', '.')
            if val.lower() != 'nan' and val != '':
                return float(val)
        return 0.0
    except:
        return 0.0

aktuell_alder = int(get_setting_val(1)) if get_setting_val(1) > 0 else 50
forvantad_avkastning_procent = get_setting_val(4) * 100 if get_setting_val(4) < 1 else get_setting_val(4)

allman_start = get_setting_val(1, 4) if get_setting_val(1, 4) > 0 else 2361985
kpa_start = get_setting_val(2, 4) if get_setting_val(2, 4) > 0 else 36210
futur_start = get_setting_val(3, 4) if get_setting_val(3, 4) > 0 else 9454
bolagets_kassa_start = get_setting_val(5, 4) 
bolagets_k10_start = get_setting_val(6, 4) 

s_isk_start = get_setting_val(6)
s_tjp_start = get_setting_val(8)
s_aktie_start = get_setting_val(10)
s_ips_start = get_setting_val(11)
s_pf_start = get_setting_val(12)

arlig_isk_ins = get_setting_val(7)
arlig_tjp_ins = get_setting_val(9)

# --- GLOBALA INSTÄLLNINGAR (TOPPEN AV APPEN) ---
st.title("Din Pensions-Dashboard 💰")
st.markdown("##### Välj hur du vill visa värden i hela kalkylatorn:")

col_glob1, col_glob2 = st.columns(2)
with col_glob1:
    skatte_läge = st.radio("Skattevy:", ["Netto (I plånboken efter skatt)", "Brutto (Före skatt)"], horizontal=True)
with col_glob2:
    simulera_inflation = st.checkbox("Räkna om till dagens penningvärde (Köpkraft)", value=False)
    if simulera_inflation:
        inflations_takt = st.slider("Årlig inflation (%)", min_value=0.0, max_value=5.0, value=2.0, step=0.1)
    else:
        inflations_takt = 0.0

st.markdown("---")

pott_lista = ['ISK Värde', 'Bolagets Kassa Värde', 'Aktiekonto Värde', 'Allmän Pension Värde', 'Tjänstepension Värde', 'Pensionsförsäkring Värde', 'IPS Värde', 'KPA Traditionell Värde', 'Futur Pension Värde']
pott_namn_ren = ['ISK', 'Bolagets Kassa', 'Aktiekonto', 'Allmän Pension', 'Tjänstepension', 'Pensionsförsäkring', 'IPS', 'KPA Traditionell', 'Futur Pension']

# --- BYGG UPP GRUNDPROGNOSEN FÖR DASHBOARD (FLIK 1) ---
aldrar_t1 = list(range(aktuell_alder, 91))
t1_isk, t1_tjp, t1_aktie, t1_ips, t1_pf = [s_isk_start], [s_tjp_start], [s_aktie_start], [s_ips_start], [s_pf_start]
t1_allm, t1_kpa, t1_futur = [allman_start], [kpa_start], [futur_start]
t1_bolag = [bolagets_kassa_start]

avk_faktor_t1 = 1 + (forvantad_avkastning_procent / 100)
avk_faktor_bolag = 1.02  # Fast tillväxt på kassa
avk_faktor_allman = 1.03 # Fast tillväxt inkomstbasbelopp

for i in range(1, len(aldrar_t1)):
    age = aldrar_t1[i]
    ins_isk = arlig_isk_ins if age <= 65 else 0
    ins_tjp = arlig_tjp_ins if age <= 65 else 0
    
    t1_isk.append((t1_isk[-1] + ins_isk) * avk_faktor_t1)
    t1_tjp.append((t1_tjp[-1] + ins_tjp) * avk_faktor_t1)
    t1_aktie.append(t1_aktie[-1] * avk_faktor_t1)
    t1_ips.append(t1_ips[-1] * avk_faktor_t1)
    t1_pf.append(t1_pf[-1] * avk_faktor_t1)
    t1_kpa.append(t1_kpa[-1] * avk_faktor_t1)
    t1_futur.append(t1_futur[-1] * avk_faktor_t1)
    t1_allm.append(t1_allm[-1] * avk_faktor_allman)
    t1_bolag.append(t1_bolag[-1] * avk_faktor_bolag)

df = pd.DataFrame({
    'Ålder': aldrar_t1, 'ISK Värde': t1_isk, 'Tjänstepension Värde': t1_tjp, 'Aktiekonto Värde': t1_aktie,
    'IPS Värde': t1_ips, 'Pensionsförsäkring Värde': t1_pf, 'Allmän Pension Värde': t1_allm,
    'KPA Traditionell Värde': t1_kpa, 'Futur Pension Värde': t1_futur, 'Bolagets Kassa Värde': t1_bolag
})

def justera_data(row):
    ny_rad = row.copy()
    if "Netto" in skatte_läge:
        inkomstskatt = 0.22 if ny_rad['Ålder'] >= 68 else 0.32
        for konto in ['Tjänstepension Värde', 'IPS Värde', 'Pensionsförsäkring Värde', 'Allmän Pension Värde', 'KPA Traditionell Värde', 'Futur Pension Värde']:
            if konto in ny_rad: ny_rad[konto] *= (1 - inkomstskatt)
        ny_rad['Aktiekonto Värde'] *= 0.70
        ny_rad['Bolagets Kassa Värde'] *= 0.80 
            
    if simulera_inflation:
        ar_framat = max(0, ny_rad['Ålder'] - aktuell_alder)
        diskonteringsfaktor = (1 + (inflations_takt / 100)) ** ar_framat
        for konto in pott_lista:
            ny_rad[konto] = ny_rad[konto] / diskonteringsfaktor

    ny_rad['Totalt Värde'] = sum([ny_rad[k] for k in pott_lista])
    return ny_rad

chart_df = df.apply(justera_data, axis=1)

def snygga_siffror(val):
    try: return f"{int(val):,} kr".replace(',', ' ')
    except: return "0 kr"

def rita_stapeldiagram_med_total(df_data, x_col, y_cols, y_titel="Belopp (kr)", ar_offset=aktuell_alder):
    temp_df = df_data.copy()
    if x_col not in temp_df.columns:
        temp_df = temp_df.reset_index()
        
    if "ISK" in temp_df.columns and "ISK Värde" not in temp_df.columns:
        for age, row in temp_df.iterrows():
            riktig_alder = row[x_col]
            if "Netto" in skatte_läge:
                ink_skatt = 0.22 if riktig_alder >= 68 else 0.32
                for p in ['Allmän Pension', 'Tjänstepension', 'KPA Traditionell', 'Futur Pension', 'IPS', 'Pensionsförsäkring']:
                    if p in temp_df.columns: temp_df.at[age, p] *= (1 - ink_skatt)
                if 'Aktiekonto' in temp_df.columns: temp_df.at[age, 'Aktiekonto'] *= 0.70
                if 'Bolagets Kassa' in temp_df.columns: temp_df.at[age, 'Bolagets Kassa'] *= 0.80
            
            if simulera_inflation:
                ar_framat = max(0, riktig_alder - ar_offset)
                disk = (1 + (inflations_takt / 100)) ** ar_framat
                for p in y_cols:
                    if p in temp_df.columns: temp_df.at[age, p] /= disk
    
    temp_df['Totalt'] = temp_df[y_cols].sum(axis=1)
    fig = px.bar(temp_df, x=x_col, y=y_cols, labels={'value': y_titel, 'variable': 'Konto / Pott', x_col: 'Ålder'})
    fig.add_scatter(x=temp_df[x_col], y=temp_df['Totalt'], mode='lines', name='Totalt Värde', line=dict(color='gray', width=2, dash='dot'))
    fig.update_traces(hovertemplate="%{y:,.0f} kr")
    fig.update_layout(hovermode="x unified", xaxis_title="Ålder", yaxis_title=y_titel, legend_title="Potter", hoverlabel=dict(bgcolor="rgba(255,255,255,0.98)", font_size=13), margin=dict(t=50))
    return fig

# --- FLIKAR ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 1. Översikt (Dashboard)", "🔮 2. Uttag & Scenarier", "💼 3. Företagaren", "📚 4. Skattefakta", "⚙️ 5. Uppdatera data"])

with tab1:
    historik_finns = False
    try:
        df_historik = conn.read(spreadsheet=sheet_url, worksheet="Historik", ttl=0)
        df_historik.columns = df_historik.columns.astype(str).str.strip()
        if not df_historik.empty and 'År' in df_historik.columns:
            df_historik['År'] = pd.to_numeric(df_historik['År'], errors='coerce').fillna(0).astype(int)
            df_historik['Totalt'] = pd.to_numeric(df_historik['Totalt'], errors='coerce')
            clean_historik = df_historik.groupby('År').last().reset_index().sort_values('År')
            
            if not clean_historik.empty:
                historik_finns = True
                nuvarande_totalt = clean_historik['Totalt'].iloc[-1]
                diff_1y = 0; pct_1y = 0.0; visar_1y = False
                if len(clean_historik) > 1:
                    prev_total = clean_historik['Totalt'].iloc[-2]
                    diff_1y = nuvarande_totalt - prev_total
                    pct_1y = (diff_1y / prev_total) * 100 if prev_total > 0 else 0
                    visar_1y = True
                    
                start_val_series = clean_historik.loc[clean_historik['År'] == 2026, 'Totalt']
                if not start_val_series.empty: start_totalt = start_val_series.values[0]
                else: start_totalt = clean_historik['Totalt'].iloc[0]
                    
                diff_start = 0; pct_start = 0.0; visar_start = False
                if len(clean_historik) > 0:
                    diff_start = nuvarande_totalt - start_totalt
                    pct_start = (diff_start / start_totalt) * 100 if start_totalt > 0 else 0
                    visar_start = True
                
                st.subheader("📈 Din Verkliga Portföljutveckling")
                col_h1, col_h2, col_h3 = st.columns(3)
                with col_h1: st.metric("💰 Bokfört Värde", f"{int(nuvarande_totalt):,} kr".replace(',', ' '))
                with col_h2:
                    if visar_1y: st.metric("📅 Utveckling sedan förra mätningen", f"{int(diff_1y):,} kr".replace(',', ' '), f"{pct_1y:.1f} %")
                    else: st.metric("📅 Utveckling sedan förra mätningen", "-", "Väntar på nästa mätpunkt")
                with col_h3:
                    if visar_start: st.metric("🚀 Utveckling sedan start (2026)", f"{int(diff_start):,} kr".replace(',', ' '), f"{pct_start:.1f} %")
                    else: st.metric("🚀 Utveckling sedan start (2026)", "-", "Kräver minst 1 mätpunkt")
                st.markdown("---")
    except: pass

    st.subheader("🔎 Välj ålder för att se prognos")
    visnings_alder = st.slider("Dra för att se dina värden vid en specifik ålder:", min_value=aktuell_alder, max_value=85, value=max(aktuell_alder, 65))
    
    pension_rad = chart_df[chart_df['Ålder'] == visnings_alder]
    totalt_vid_val = pension_rad['Totalt Värde'].values[0] if not pension_rad.empty else 0
    
    skatte_text = "Netto" if "Netto" in skatte_läge else "Brutto"
    inflations_text = f" (Köpkraft)" if simulera_inflation else ""
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric(f"Prognos Totalt Värde | {skatte_text}{inflations_text}", snygga_siffror(totalt_vid_val))
    with col2: st.metric("ISK", snygga_siffror(pension_rad['ISK Värde'].values[0] if not pension_rad.empty else 0))
    with col3: st.metric("Bolagets Kassa", snygga_siffror(pension_rad['Bolagets Kassa Värde'].values[0] if not pension_rad.empty else 0))
    with col4: st.metric("Tjänstepension", snygga_siffror(pension_rad['Tjänstepension Värde'].values[0] if not pension_rad.empty else 0))
    
    st.write("") 
    
    col5, col6, col7, col8 = st.columns(4)
    with col5: st.metric("Allmän Pension", snygga_siffror(pension_rad['Allmän Pension Värde'].values[0] if not pension_rad.empty else 0))
    with col6: st.metric("Aktiekonto", snygga_siffror(pension_rad['Aktiekonto Värde'].values[0] if not pension_rad.empty else 0))
    with col7: st.metric("KPA & Futur", snygga_siffror((pension_rad['KPA Traditionell Värde'].values[0] if not pension_rad.empty else 0) + (pension_rad['Futur Pension Värde'].values[0] if not pension_rad.empty else 0)))
    with col8: st.metric("IPS & PF", snygga_siffror((pension_rad['IPS Värde'].values[0] if not pension_rad.empty else 0) + (pension_rad['Pensionsförsäkring Värde'].values[0] if not pension_rad.empty else 0)))

    st.markdown("---")
    prognos_fig = rita_stapeldiagram_med_total(chart_df, 'Ålder', pott_lista)
    st.plotly_chart(prognos_fig, use_container_width=True)
    
    if historik_finns:
        st.markdown("---")
        st.subheader("📚 Historisk Tillväxt (Graf)")
        clean_historik['År'] = clean_historik['År'].astype(str) 
        fig_hist = px.bar(clean_historik, x='År', y='Totalt', labels={'Totalt': f"Totalt Värde"})
        st.plotly_chart(fig_hist, use_container_width=True)

with tab2:
    st.subheader(f"🔮 Uttag & Scenarier: Avancerad Skattesmart Uttagsmotor")
    st.info("Här styr ditt önskade **Nettouttag** precis allt. Systemet räknar automatiskt ut hur mycket brutto som krävs från olika konton för att nå dit varje år.")
    
    col_top1, col_top2 = st.columns([1, 1])
    with col_top1:
        start_alder = st.slider("Global startålder för uttag (Brygga ISK/Bolag)", min_value=aktuell_alder, max_value=75, value=60)
        onskat_netto_manad = st.number_input("Önskat netto-uttag (I plånboken) första året (kr/mån)", min_value=10000, max_value=150000, value=40000, step=1000)
        
    with col_top2:
        with st.expander("⚙️ Avancerade inställningar (Pensionsåldrar & Sparande)"):
            c_i1, c_i2 = st.columns(2)
            with c_i1:
                sim_ny_isk_ins = st.number_input("Sparande ISK (kr/år)", value=int(arlig_isk_ins), step=10000)
                sim_ny_tjp_ins = st.number_input("Avsättning TJP (kr/år)", value=int(arlig_tjp_ins), step=10000)
                start_alder_allman = st.slider("Start Allmän Pension", 60, 75, 68)
                utb_tid_allman = st.slider("Utb.tid Allmän (år)", 5, 40, 20)
                start_alder_kpa = st.slider("Start KPA", 55, 75, 68)
                utb_tid_kpa = st.slider("Utb.tid KPA (år)", 5, 30, 10)
            with c_i2:
                sim_isk_ins_under = st.number_input("Nytt sparande till ISK under nedtrappning (kr/år)", value=0, step=1000)
                sim_tjp_ins_under = st.number_input("Ny avsättning till TJP under nedtrappning (kr/år)", value=0, step=1000)
                start_alder_tjp = st.slider("Start Tjänstepension", 55, 75, 68)
                utb_tid_tjp = st.slider("Utb.tid TJP (år)", 5, 30, 10)
                start_alder_futur = st.slider("Start Futur", 55, 75, 68)
                utb_tid_futur = st.slider("Utb.tid Futur (år)", 5, 30, 10)
                start_alder_ips = st.slider("Start IPS", 55, 75, 68)
                utb_tid_ips = st.slider("Utb.tid IPS (år)", 5, 30, 10)
                start_alder_pf = st.slider("Start PF", 55, 75, 68)
                utb_tid_pf = st.slider("Utb.tid PF (år)", 5, 30, 10)

    st.markdown("---")
    anvand_7_procent = st.checkbox("Aktivera 7-procentsmetoden (Lågbeskattad lön från bolaget från 68 år)", value=True)
    
    # --- UTTAGSMOTORN KÖR --
    s_isk, s_tjp, s_aktie, s_ips, s_pf = s_isk_start, s_tjp_start, s_aktie_start, s_ips_start, s_pf_start
    s_allm, s_kpa, s_futur, s_bolag = allman_start, kpa_start, futur_start, bolagets_kassa_start
    s_k10 = bolagets_k10_start
    
    aldrar, n_isk, n_bolag, n_tjp, n_aktie, n_ips, n_pf, n_allm, n_kpa, n_futur = [], [], [], [], [], [], [], [], [], []
    ut_isk, ut_bolag, ut_aktie, ut_tjp, ut_ips, ut_pf, ut_allm, ut_kpa, ut_futur = [], [], [], [], [], [], [], [], []
    
    STATLIG_SKATT_GRANS_BRUTTO = 612000
    avk_faktor = 1 + (forvantad_avkastning_procent / 100)
    
    for age in range(aktuell_alder, 91):
        aldrar.append(age)
        
        n_isk.append(max(0, s_isk)); n_bolag.append(max(0, s_bolag)); n_tjp.append(max(0, s_tjp)); n_aktie.append(max(0, s_aktie)); n_ips.append(max(0, s_ips)); n_pf.append(max(0, s_pf)); n_allm.append(max(0, s_allm)); n_kpa.append(max(0, s_kpa)); n_futur.append(max(0, s_futur))
        
        s_k10 += 204325
        
        if age < start_alder:
            s_isk += sim_ny_isk_ins; s_tjp += sim_ny_tjp_ins
            arets_uttag = {"ISK": 0, "Bolagets Kassa": 0, "Aktiekonto": 0, "Allmän Pension": 0, "Tjänstepension": 0, "KPA": 0, "Futur": 0, "IPS": 0, "PF": 0}
        else:
            s_isk += sim_isk_ins_under; s_tjp += sim_tjp_ins_under
            kvar_netto_att_fa_ut = (onskat_netto_manad * 12) * ((1 + (inflations_takt / 100)) ** (age - start_alder))
            ink_skatt_nu = 0.22 if age >= 68 else 0.32
            
            arets_uttag = {"ISK": 0, "Bolagets Kassa": 0, "Aktiekonto": 0, "Allmän Pension": 0, "Tjänstepension": 0, "KPA": 0, "Futur": 0, "IPS": 0, "PF": 0}
            
            pension_pots_config = [("Allmän Pension", s_allm, start_alder_allman, utb_tid_allman), ("Tjänstepension", s_tjp, start_alder_tjp, utb_tid_tjp), ("KPA", s_kpa, start_alder_kpa, utb_tid_kpa), ("Futur", s_futur, start_alder_futur, utb_tid_futur), ("IPS", s_ips, start_alder_ips, utb_tid_ips), ("PF", s_pf, start_alder_pf, utb_tid_pf)]
            lopande_brutto_pension = 0
            for namn, saldo, s_alder, utb_tid in pension_pots_config:
                if age >= s_alder and saldo > 0:
                    ar_i_uttag = age - s_alder
                    if ar_i_uttag < utb_tid:
                        resterande_ar = utb_tid - ar_i_uttag
                        onipat_brutto = saldo / resterande_ar
                        
                        if lopande_brutto_pension + onipat_brutto > STATLIG_SKATT_GRANS_BRUTTO:
                            onipat_brutto = max(0, STATLIG_SKATT_GRANS_BRUTTO - lopande_brutto_pension)
                            
                        if onipat_brutto > 0:
                            arets_uttag[namn] = onipat_brutto
                            lopande_brutto_pension += onipat_brutto
                            kvar_netto_att_fa_ut -= onipat_brutto * (1 - ink_skatt_nu)
                            
                            if namn == "Allmän Pension": s_allm -= onipat_brutto
                            elif namn == "Tjänstepension": s_tjp -= onipat_brutto
                            elif namn == "KPA": s_kpa -= onipat_brutto
                            elif namn == "Futur": s_futur -= onipat_brutto
                            elif namn == "IPS": s_ips -= onipat_brutto
                            elif namn == "PF": s_pf -= onipat_brutto

            if kvar_netto_att_fa_ut > 0:
                if age >= 68 and anvand_7_procent:
                    max_7_procent_brutto = 150000
                    bolag_7_procent = min(s_bolag, max_7_procent_brutto)
                    s_bolag_rest = s_bolag - bolag_7_procent
                    bolag_k10 = min(s_bolag_rest, s_k10)
                    bolag_lon = max(0, s_bolag_rest - s_k10)
                    flex_konton = [("ISK", s_isk, 0.0), ("Bolagets Kassa 7-procent", bolag_7_procent, 0.10), ("Bolagets Kassa K10", bolag_k10, 0.20), ("Aktiekonto", s_aktie, 0.30), ("Bolagets Kassa Lön", bolag_lon, 0.50)]
                else:
                    bolag_k10 = min(s_bolag, s_k10)
                    bolag_lon = max(0, s_bolag - s_k10)
                    flex_konton = [("ISK", s_isk, 0.0), ("Bolagets Kassa K10", bolag_k10, 0.20), ("Aktiekonto", s_aktie, 0.30), ("Bolagets Kassa Lön", bolag_lon, 0.50)]
                
                for flex_namn, saldo_brutto, skatt in flex_konton:
                    if kvar_netto_att_fa_ut > 0 and saldo_brutto > 0:
                        max_netto = saldo_brutto * (1 - skatt)
                        if max_netto <= kvar_netto_att_fa_ut:
                            uttag_brutto = saldo_brutto; uttag_netto = max_netto
                        else:
                            uttag_netto = kvar_netto_att_fa_ut; uttag_brutto = kvar_netto_att_fa_ut / (1 - skatt)
                            
                        kvar_netto_att_fa_ut -= uttag_netto
                        
                        if flex_namn == "ISK": s_isk -= uttag_brutto; arets_uttag["ISK"] += uttag_brutto
                        elif flex_namn in ["Bolagets Kassa K10", "Bolagets Kassa 7-procent"]:
                            s_bolag -= uttag_brutto
                            if flex_namn == "Bolagets Kassa K10": s_k10 -= uttag_brutto
                            arets_uttag["Bolagets Kassa"] += uttag_brutto
                        elif flex_namn == "Bolagets Kassa Lön": s_bolag -= uttag_brutto; arets_uttag["Bolagets Kassa"] += uttag_brutto
                        elif flex_namn == "Aktiekonto": s_aktie -= uttag_brutto; arets_uttag["Aktiekonto"] += uttag_brutto
                        
            elif kvar_netto_att_fa_ut < 0:
                s_isk += abs(kvar_netto_att_fa_ut)
                arets_uttag["ISK"] -= abs(kvar_netto_att_fa_ut)

        ut_isk.append(arets_uttag["ISK"]); ut_bolag.append(arets_uttag.get("Bolagets Kassa", 0)); ut_aktie.append(arets_uttag["Aktiekonto"]); ut_tjp.append(arets_uttag["Tjänstepension"]); ut_ips.append(arets_uttag["IPS"]); ut_pf.append(arets_uttag["PF"]); ut_allm.append(arets_uttag["Allmän Pension"]); ut_kpa.append(arets_uttag["KPA"]); ut_futur.append(arets_uttag["Futur"])
        
        s_isk *= avk_faktor; s_aktie *= avk_faktor; s_tjp *= avk_faktor; s_ips *= avk_faktor; s_pf *= avk_faktor; s_kpa *= avk_faktor; s_futur *= avk_faktor
        s_allm *= avk_faktor_allman
        s_bolag *= avk_faktor_bolag

    sim_df_area = pd.DataFrame({"Ålder": aldrar, "Bolagets Kassa": n_bolag, "Aktiekonto": n_aktie, "ISK": n_isk, "Pensionsförsäkring": n_pf, "IPS": n_ips, "Futur Pension": n_futur, "KPA Traditionell": n_kpa, "Tjänstepension": n_tjp, "Allmän Pension": n_allm}).set_index("Ålder")
    sim_uttag_df = pd.DataFrame({"Ålder": aldrar, "Bolagets Kassa": ut_bolag, "Aktiekonto": ut_aktie, "ISK": ut_isk, "Pensionsförsäkring": ut_pf, "IPS": ut_ips, "Futur Pension": ut_futur, "KPA Traditionell": ut_kpa, "Tjänstepension": ut_tjp, "Allmän Pension": ut_allm}).set_index("Ålder")

    st.subheader(f"📊 1. Saldoutveckling från {start_alder} år (Visar Bruttokapital)")
    fig_sim = rita_stapeldiagram_med_total(sim_df_area, 'Ålder', pott_namn_ren)
    st.plotly_chart(fig_sim, use_container_width=True)
    
    # --- NY GRAF: SKATT VS NETTO ---
    st.markdown("---")
    st.subheader(f"💰 2. Din Inkomst & Skatt över tid (När och hur mycket beskattas du?)")
    st.info("Här ser du brutto, netto och skatt sammanflätat. Den gröna stapeln är pengarna som landar på bankkontot (ditt valda mål). Den röda stapeln är skatten som systemet måste betala in från dina konton för att nettot ska stämma. **Hela stapelns höjd = Ditt faktiska Bruttouttag.**")
    
    sim_uttag_df_filtered = sim_uttag_df[sim_uttag_df.index >= start_alder].copy().round(0).astype(int)
    skattesats_pension_lista_sim, netto_lista_sim, skatt_kr_lista, ingaende_saldo_lista, total_brutto_lista = [], [], [], [], []
    
    for age, row in sim_uttag_df_filtered.iterrows():
        ink_skatt = 0.32 if age < 68 else 0.22
        pens_uttag = max(0, row['Pensionsförsäkring']) + max(0, row['IPS']) + max(0, row['Futur Pension']) + max(0, row['KPA Traditionell']) + max(0, row['Tjänstepension']) + max(0, row['Allmän Pension'])
        aktie_uttag, isk_uttag, bolag_uttag = row['Aktiekonto'], row['ISK'], max(0, row['Bolagets Kassa'])
        
        brutto = pens_uttag + aktie_uttag + bolag_uttag + isk_uttag
        netto = (pens_uttag * (1 - ink_skatt)) + (aktie_uttag * 0.70) + (bolag_uttag * 0.80) + isk_uttag
        skatt_kr = brutto - netto
        
        total_brutto_lista.append(int(brutto))
        netto_lista_sim.append(int(netto))
        skatt_kr_lista.append(int(skatt_kr))
        skattesats_pension_lista_sim.append(f"{int(ink_skatt*100)} %" if pens_uttag > 0 else "-")

        belastade_konton = []
        for pott in pott_namn_ren:
            if row[pott] > 0: belastade_konton.append(f"{pott}: {int(sim_df_area.loc[age, pott]):,} kr".replace(',', ' '))
        ingaende_saldo_lista.append(" | ".join(belastade_konton) if belastade_konton else "Inga uttag")

    sim_uttag_df_filtered['Totalt Uttag (Brutto)'] = total_brutto_lista
    sim_uttag_df_filtered['Inbetald Skatt (kr)'] = skatt_kr_lista
    sim_uttag_df_filtered['I plånboken (Netto)'] = netto_lista_sim
    sim_uttag_df_filtered['Skattesats (Pensioner)'] = skattesats_pension_lista_sim
    sim_uttag_df_filtered['Ingående Saldo (Före uttag)'] = ingaende_saldo_lista
    
    # Bygg grafen
    df_skatt_graf = pd.DataFrame({
        'Ålder': sim_uttag_df_filtered.index,
        'I plånboken (Netto)': netto_lista_sim,
        'Inbetald Skatt': skatt_kr_lista
    })
    
    fig_skatt = px.bar(df_skatt_graf, x='Ålder', y=['I plånboken (Netto)', 'Inbetald Skatt'], 
                       title="Ditt Bruttouttag uppdelat i Netto och Skatt",
                       labels={'value': 'Belopp (kr)', 'variable': 'Kategori'},
                       color_discrete_map={'I plånboken (Netto)': '#4CAF50', 'Inbetald Skatt': '#F44336'})
    fig_skatt.update_layout(barmode='stack', hovermode="x unified", legend_title="")
    st.plotly_chart(fig_skatt, use_container_width=True)

    with st.expander("Tabell: Detaljerad Uttagsplan (Med exakt skatt i kronor)"):
        cols = ['Totalt Uttag (Brutto)', 'Inbetald Skatt (kr)', 'I plånboken (Netto)', 'Skattesats (Pensioner)', 'ISK', 'Bolagets Kassa', 'Aktiekonto', 'Allmän Pension', 'Tjänstepension', 'KPA Traditionell', 'Futur Pension', 'IPS', 'Pensionsförsäkring', 'Ingående Saldo (Före uttag)']
        st.dataframe(sim_uttag_df_filtered[cols].astype(object), use_container_width=True)

    # --- UPPGRADERAD: SJÄLVKÖRANDE HELIKOPTERVY ---
    st.markdown("---")
    st.subheader("🎢 3. Helikoptervyn: Stresstest av hela kapitalet")
    st.info("I denna vy drar vi bort kalkylatorns komplexa lager. Vi slår ihop hela din portfölj till en enda klumpsumma. **Istället för att du ska gissa ett bruttouttag, hämtar simuleringen nu automatiskt det totala bruttouttag som krävs första året för att nå ditt nettomål.**")
    
    col_sim_1, col_sim_2 = st.columns(2)
    with col_sim_1:
        start_alder_sim = st.slider("Välj startålder för Helikoptersimulering", min_value=60, max_value=75, value=max(60, start_alder))
        
        simulerat_startkapital = sim_df_area.loc[start_alder_sim].sum() if start_alder_sim in sim_df_area.index else 0
        st.metric("Ditt Totala Startkapital (Alla potter ihopslagna)", f"{int(simulerat_startkapital):,} kr".replace(',', ' '))
        
    with col_sim_2:
        dash_avkastning = st.slider("Långsiktig förväntad avkastning på portföljen (%)", min_value=0.0, max_value=12.0, value=forvantad_avkastning_procent, step=0.5, key="dash_avk")
        anvand_faktisk_avk = st.checkbox("📍 Använd avvikande/faktisk avkastning just i år", value=False)
        if anvand_faktisk_avk:
            faktisk_avk_ar_1 = st.number_input("Faktisk avkastning i år (%)", min_value=-50.0, max_value=100.0, value=10.0, step=0.5)
        else:
            faktisk_avk_ar_1 = dash_avkastning

        dash_inflation = st.slider("Årlig inflation (ökning av uttag) (%)", min_value=0.0, max_value=5.0, value=inflations_takt if simulera_inflation else 0.0, step=0.5, key="dash_inf")

    # Hämta det RIKTIGA bruttouttaget från uttagsmotorn för detta startår
    start_idx = start_alder_sim - start_alder
    if start_idx >= 0 and start_idx < len(sim_uttag_df_filtered):
        forsta_aret_uttag = sim_uttag_df_filtered.iloc[start_idx]['Totalt Uttag (Brutto)']
        forsta_aret_netto = sim_uttag_df_filtered.iloc[start_idx]['I plånboken (Netto)']
        forsta_aret_skatt = sim_uttag_df_filtered.iloc[start_idx]['Inbetald Skatt (kr)']
    else:
        forsta_aret_uttag = onskat_netto_manad * 12 * 1.3 # Fallback om slidern hamnar utanför
        forsta_aret_netto = onskat_netto_manad * 12
        forsta_aret_skatt = forsta_aret_uttag - forsta_aret_netto

    # Röntgen-rutan
    forsta_aret_avkastning = simulerat_startkapital * (faktisk_avk_ar_1 / 100)
    netto_forsta_aret = forsta_aret_avkastning - forsta_aret_uttag
    
    with st.expander(f"🧐 Så fungerar ditt startår vid {start_alder_sim} års ålder (Klicka för insyn)", expanded=True):
        st.write(f"För att få ut ditt mål på **{int(forsta_aret_netto):,} kr netto**, drar systemet **{int(forsta_aret_uttag):,} kr brutto** från dina konton (inkl. **{int(forsta_aret_skatt):,} kr** i skatt).".replace(',', ' '))
        st.write("Ditt kapital slåss nu mot detta bruttouttag:")
        st.markdown(f"**+ Årets avkastning ({faktisk_avk_ar_1} %):** {int(forsta_aret_avkastning):,} kr".replace(',', ' '))
        st.markdown(f"**- Hela årets bruttouttag:** - {int(forsta_aret_uttag):,} kr".replace(',', ' '))
        st.markdown("---")
        
        if netto_forsta_aret > 0:
            st.success(f"⚖️ **Resultat:** Avkastningen vinner. Kapitalet växer med **{int(netto_forsta_aret):,} kr** under året och grafen pekar uppåt.".replace(',', ' '))
        else:
            st.warning(f"⚖️ **Resultat:** Uttagen vinner. Kapitalet krymper med **{int(abs(netto_forsta_aret)):,} kr** detta år och grafen pekar nedåt.".replace(',', ' '))

    # Simuleringsloop
    sim_ar, sim_kapital = [], []
    nuvarande_kap = simulerat_startkapital
    nuvarande_arsuttag = forsta_aret_uttag
    
    for i, ar in enumerate(range(start_alder_sim, 96)):
        sim_ar.append(ar)
        sim_kapital.append(max(0, nuvarande_kap))
        arets_avk_procent = faktisk_avk_ar_1 if (anvand_faktisk_avk and i == 0) else dash_avkastning
        nuvarande_kap = (nuvarande_kap - nuvarande_arsuttag) * (1 + (arets_avk_procent / 100))
        nuvarande_arsuttag *= (1 + (dash_inflation / 100))
        
    sim_data = pd.DataFrame({"Ålder": sim_ar, "Kapital (kr)": sim_kapital})
    fig_line = px.area(sim_data, x="Ålder", y="Kapital (kr)", title=f"Total kapitalutveckling från {start_alder_sim} år")
    fig_line.update_traces(fillcolor='rgba(76, 175, 80, 0.2)', line_color='rgba(76, 175, 80, 1)')
    fig_line.update_layout(hovermode="x unified", xaxis_title="Ålder", yaxis_title="Totalt Portföljvärde (kr)", yaxis_tickformat=",.0f")
    st.plotly_chart(fig_line, use_container_width=True)
    
    ar_kvar = len([k for k in sim_kapital if k > 0])
    st.caption(f"💡 Med din inställda avkastning och ditt riktiga skatteberäknade uttag, räcker pengarna till minst {start_alder_sim + ar_kvar - 1} års ålder.")

with tab3:
    st.subheader("⚖️ Företagaren: Aktiebolaget")
    col_stat1, col_stat2 = st.columns(2)
    with col_stat1: st.metric("Fritt Eget Kapital (Sparade Vinstmedel)", f"{int(bolagets_kassa_start):,} kr".replace(',', ' '))
    with col_stat2: st.metric("Sparat K10-utrymme", f"{int(bolagets_k10_start):,} kr".replace(',', ' '))
        
    st.markdown("---")
    st.markdown("### 🧮 Kalkylator 68+: K10-Utdelning vs Lön (7%-metoden)")
    st.info("När du fyllt 68 år (riktåldern) sänks arbetsgivaravgiften till 10,21 % och du får maximerat jobbskatteavdrag. Här jämför vi om det är bäst att ta ut **redan skattade vinstmedel** som aktieutdelning eller som lön.")
    
    utrymme_att_ta_ut = st.slider("Belopp i bolaget att ta ut (kr)", 50000, 500000, 150000, 10000)
    din_snittskatt_lon = st.slider("Din förväntade inkomstskatt på denna lön (%)", 5.0, 20.0, 10.0, 0.5)
    
    col_k1, col_k2 = st.columns(2)
    with col_k1:
        st.markdown("#### Alt 1: K10-Utdelning (20 %)")
        privat_skatt_k10 = utrymme_att_ta_ut * 0.20
        netto_k10 = utrymme_att_ta_ut - privat_skatt_k10
        st.write(f"- Skatt (20 %): **-{int(privat_skatt_k10):,} kr**".replace(',', ' '))
        st.metric("Netto i plånboken", f"{int(netto_k10):,} kr".replace(',', ' '))
        
    with col_k2:
        st.markdown("#### Alt 2: Lön (7%-metoden)")
        bruttolon_68 = utrymme_att_ta_ut / 1.1021
        arb_avgift_68 = utrymme_att_ta_ut - bruttolon_68
        privat_skatt_lon = bruttolon_68 * (din_snittskatt_lon / 100)
        netto_lon = bruttolon_68 - privat_skatt_lon
        pgi_vinst = bruttolon_68 * 0.185
        
        st.write(f"- Ålderspensionsavgift (10,21 %): **-{int(arb_avgift_68):,} kr**".replace(',', ' '))
        st.write(f"- Inkomstskatt ({din_snittskatt_lon} %): **-{int(privat_skatt_lon):,} kr**".replace(',', ' '))
        st.metric("Netto i plånboken", f"{int(netto_lon):,} kr".replace(',', ' '))
        st.caption(f"💡 **Bonus:** Lönen ger dig även ca **+{int(pgi_vinst):,} kr** insatt på din allmänna pension!")
        
    if netto_lon + pgi_vinst > netto_k10:
        st.success(f"✅ **Slutsats:** Lön är mer lönsamt! Du får in mer värde totalt när man räknar in den extra pensionsinsättningen från staten.")
    elif netto_lon > netto_k10:
        st.success("✅ **Slutsats:** Lön ger mer direkt i handen, plus att du får extra pension! Ett självklart val.")
    else:
        st.warning("⚖️ **Slutsats:** K10 ger marginellt mer kontanter i handen just nu. Men lönen bygger din pension.")

with tab4:
    st.subheader("📚 Pensionsskolan: Så beskattas dina potter")
    skatte_data = {
        "Pott / Konto": ["Bolagets Kassa (AB)", "ISK", "Aktiekonto", "Allmän Pension", "Tjänstepension", "KPA", "Futur", "IPS", "Pensionsförsäkring"],
        "Beskattning (Före 68)": ["20% Utdelningsskatt (Inom K10)", "Skatt på schablon (0%)", "30% kapitalskatt på vinst", "Inkomstskatt (ca 32%)", "Inkomstskatt (ca 32%)", "Inkomstskatt (ca 32%)", "Inkomstskatt (ca 32%)", "Inkomstskatt (ca 32%)", "Inkomstskatt (ca 32%)"],
        "Beskattning (Efter 68)": ["20% Utdelningsskatt ELLER ~10% som Lön (7%-metoden)", "Samma", "Samma (30% på vinst)", "Sänkt Inkomstskatt (ca 22%)", "Sänkt Inkomstskatt (ca 22%)", "Sänkt Inkomstskatt (ca 22%)", "Sänkt Inkomstskatt (ca 22%)", "Sänkt Inkomstskatt (ca 22%)", "Sänkt Inkomstskatt (ca 22%)"]
    }
    st.table(pd.DataFrame(skatte_data))

with tab5:
    st.subheader("⚙️ Loggbok & Uppdatering mot Kalkylarket")
    
    st.markdown("### 💸 1. Löpande uttag under året")
    with st.form("batch_uttag_form"):
        inmatning_typ = st.radio("Beloppen nedan avser:", ["Netto (Det jag fick in på banken)", "Brutto (Hela beloppet före skatt)"])
        alder_68_val = st.checkbox("Jag är 68 år eller äldre (ger lägre inkomstskatt i loggningen)")
        
        c1, c2, c3, c4 = st.columns(4)
        batch_inputs = {}
        with c1:
            batch_inputs["Allmän Pension"] = st.number_input("Allmän Pension", min_value=0, value=0, step=1000)
            batch_inputs["Tjänstepension"] = st.number_input("Tjänstepension", min_value=0, value=0, step=1000)
            batch_inputs["Bolagets Kassa"] = st.number_input("Utdelning/Lön (Kassa)", min_value=0, value=0, step=1000)
        with c2:
            batch_inputs["KPA"] = st.number_input("KPA Traditionell", min_value=0, value=0, step=1000)
            batch_inputs["Futur Pension"] = st.number_input("Futur Pension", min_value=0, value=0, step=1000)
        with c3:
            batch_inputs["ISK"] = st.number_input("ISK (Stöduttag)", min_value=0, value=0, step=1000)
            batch_inputs["Aktiekonto"] = st.number_input("Aktiekonto", min_value=0, value=0, step=1000)
        with c4:
            batch_inputs["IPS"] = st.number_input("IPS", min_value=0, value=0, step=1000)
            batch_inputs["Pensionsförsäkring"] = st.number_input("Pensionsförsäkring", min_value=0, value=0, step=1000)
            
        if st.form_submit_button("Logga Månadens Uttag"):
            if sum(batch_inputs.values()) == 0:
                st.warning("Ange minst ett belopp.")
            else:
                try:
                    cell_map = {"ISK": "ISK_Saldo", "Tjänstepension": "TJP_Saldo", "Aktiekonto": "Aktiekonto_Saldo", "IPS": "IPS_Saldo", "Pensionsförsäkring": "PF_Saldo", "Allmän Pension": "Allman_Pension", "KPA Traditionell": "KPA_Traditionell", "Futur Pension": "Futur_Pension", "Bolagets Kassa": "Bolagets_Kassa"}
                    batch_map = {"Allmän Pension": "Allmän Pension", "Tjänstepension": "Tjänstepension", "KPA": "KPA Traditionell", "Futur Pension": "Futur Pension", "ISK": "ISK", "Aktiekonto": "Aktiekonto", "IPS": "IPS", "Pensionsförsäkring": "Pensionsförsäkring", "Bolagets Kassa": "Bolagets Kassa"}
                    current_saldos = {"ISK": s_isk_start, "Tjänstepension": s_tjp_start, "Aktiekonto": s_aktie_start, "IPS": s_ips_start, "Pensionsförsäkring": s_pf_start, "Allmän Pension": allman_start, "KPA Traditionell": kpa_start, "Futur Pension": futur_start, "Bolagets Kassa": bolagets_kassa_start}
                    
                    creds_dict = dict(st.secrets["connections"]["gsheets"])
                    gc = gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets']))
                    sh = gc.open_by_url(sheet_url)
                    worksheet = sh.sheet1
                    logg_sheet = sh.worksheet("Händelselogg")

                    updates, log_rows, total_netto, total_brutto = [], [], 0, 0
                    
                    for ui_namn, belopp in batch_inputs.items():
                        if belopp > 0:
                            riktigt_namn = batch_map[ui_namn]
                            if riktigt_namn == "ISK": skattesats = 0.0
                            elif riktigt_namn == "Bolagets Kassa": skattesats = 0.20
                            elif riktigt_namn == "Aktiekonto": skattesats = 0.30
                            else: skattesats = 0.22 if alder_68_val else 0.32
                            
                            if "Netto" in inmatning_typ:
                                netto = belopp; brutto = netto / (1 - skattesats)
                            else:
                                brutto = belopp; netto = brutto * (1 - skattesats)
                                
                            total_netto += netto; total_brutto += brutto
                            ny_siffra = max(0, current_saldos[riktigt_namn] - brutto)
                            updates.append({'range': cell_map[riktigt_namn], 'values': [[ny_siffra]]})
                            log_rows.append([datetime.datetime.now().strftime("%Y-%m-%d"), f"Månadsuttag ({riktigt_namn})", -brutto])
                    
                    if updates:
                        worksheet.batch_update(updates)
                        logg_sheet.append_rows(log_rows)
                    st.success(f"✅ Klart! Totalt uttag loggat: {int(total_brutto):,} kr brutto.".replace(',', ' '))
                    st.cache_data.clear()
                except Exception as e: st.error(f"Fel: {e}")

    st.markdown("---")
    st.markdown("### 📅 2. Den årliga storstädningen (Saldouppdatering)")
    with st.expander("Öppna formulär för att spara nya aktuella saldon till databasen"):
        with st.form("update_form"):
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                new_isk = st.number_input("ISK Värde", value=int(s_isk_start), step=1000)
                new_aktie = st.number_input("Aktiekonto", value=int(s_aktie_start), step=1000)
                new_allman = st.number_input("Allmän Pension", value=int(allman_start), step=1000)
            with col_s2:
                new_bolagskassa = st.number_input("Bolagets Kassa (Fritt Eget)", value=int(bolagets_kassa_start), step=1000)
                new_k10 = st.number_input("Sparat K10-utrymme", value=int(bolagets_k10_start), step=1000)
                new_tjp = st.number_input("Tjänstepension", value=int(s_tjp_start), step=1000)
            with col_s3:
                new_ips = st.number_input("IPS Värde", value=int(s_ips_start), step=1000)
                new_pens = st.number_input("Pensionsförsäkring", value=int(s_pf_start), step=1000)
                new_kpa = st.number_input("KPA Traditionell", value=int(kpa_start), step=1000)
                new_futur = st.number_input("Futur Pension", value=int(futur_start), step=1000)
                
            new_privatspar_ar = st.number_input("Privat sparande (kr/år)", value=36000, step=1000)
            new_tjp_ins = st.number_input("Bolagets avsättning TJP (kr/år)", value=int(arlig_tjp_ins), step=10000)
                
            if st.form_submit_button("Spara till Kalkylark"):
                try:
                    ny_totalsumma = new_isk + new_tjp + new_aktie + new_ips + new_pens + new_allman + new_kpa + new_futur + new_bolagskassa
                    creds_dict = dict(st.secrets["connections"]["gsheets"])
                    gc = gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets']))
                    sh = gc.open_by_url(sheet_url)
                    
                    batch_updates = [
                        {'range': 'ISK_Saldo', 'values': [[new_isk]]},
                        {'range': 'TJP_Saldo', 'values': [[new_tjp]]},
                        {'range': 'Aktiekonto_Saldo', 'values': [[new_aktie]]},
                        {'range': 'IPS_Saldo', 'values': [[new_ips]]},
                        {'range': 'PF_Saldo', 'values': [[new_pens]]},
                        {'range': 'ISK_Insattning', 'values': [[new_privatspar_ar]]},
                        {'range': 'TJP_Avsattning', 'values': [[new_tjp_ins]]},
                        {'range': 'Total_Saldo', 'values': [[ny_totalsumma]]},
                        {'range': 'Allman_Pension', 'values': [[new_allman]]},
                        {'range': 'KPA_Traditionell', 'values': [[new_kpa]]},
                        {'range': 'Futur_Pension', 'values': [[new_futur]]},
                        {'range': 'Bolagets_Kassa', 'values': [[new_bolagskassa]]},
                        {'range': 'Sparat_K10', 'values': [[new_k10]]}
                    ]
                    sh.sheet1.batch_update(batch_updates)
                    
                    try:
                        sh.worksheet("Historik").append_row([
                            datetime.datetime.now().year, new_isk, new_tjp, new_aktie, new_ips, new_pens, 
                            ny_totalsumma, new_allman, new_kpa, new_futur, new_bolagskassa
                        ])
                    except: pass
                        
                    st.cache_data.clear()
                    st.success("✅ Ny mätpunkt sparad och historiken är uppdaterad!")
                except Exception as e: st.error(f"Fel vid uppdatering: {e}")