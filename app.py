import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import datetime
import plotly.express as px

st.set_page_config(page_title="Pensionskalkylator", page_icon="💰", layout="wide")
st.title("Din Pensions-Dashboard 💰")

conn = st.connection("gsheets", type=GSheetsConnection)
sheet_url = "https://docs.google.com/spreadsheets/d/1WI1KfXWkygOVdL8XxWiHprzNyCax0cIowxzthBta_3I/edit?gid=0#gid=0"

# Läs enbart in inställningarna högst upp i arket (Vi ignorerar numera allt under rad 15)
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

# Läs in startvärden från inställningarna
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

# --- SIDOMENY ---
st.sidebar.header("⚙️ Dina val")
pensionsalder = st.sidebar.slider("Ditt standardmål för pension?", min_value=55, max_value=75, value=65)

st.sidebar.markdown("---")
st.sidebar.subheader("Skatt & Uttag")
skatte_läge = st.sidebar.radio("Visa värden som:", ["Brutto (Före skatt)", "Netto (I plånboken)"])

st.sidebar.markdown("---")
st.sidebar.subheader("Inflation & Köpkraft")
simulera_inflation = st.sidebar.checkbox("Visa i dagens penningvärde", value=False)
inflations_takt = 0.0
if simulera_inflation:
    inflations_takt = st.sidebar.slider("Årlig inflation (%)", min_value=0.0, max_value=5.0, value=2.0, step=0.1)

pott_lista = ['ISK Värde', 'Bolagets Kassa Värde', 'Aktiekonto Värde', 'Allmän Pension Värde', 'Tjänstepension Värde', 'Pensionsförsäkring Värde', 'IPS Värde', 'KPA Traditionell Värde', 'Futur Pension Värde']
pott_namn_ren = ['ISK', 'Bolagets Kassa', 'Aktiekonto', 'Allmän Pension', 'Tjänstepension', 'Pensionsförsäkring', 'IPS', 'KPA Traditionell', 'Futur Pension']

# --- BYGG UPP FRAMTIDSPROGNOSEN FÖR DASHBOARD (TIDIGARE EXCEL-RADER) ---
aldrar_t1 = list(range(aktuell_alder, 91))
t1_isk, t1_tjp, t1_aktie, t1_ips, t1_pf = [s_isk_start], [s_tjp_start], [s_aktie_start], [s_ips_start], [s_pf_start]
t1_allm, t1_kpa, t1_futur = [allman_start], [kpa_start], [futur_start]
t1_bolag = [bolagets_kassa_start]

avk_faktor_t1 = 1 + (forvantad_avkastning_procent / 100)

for i in range(1, len(aldrar_t1)):
    age = aldrar_t1[i]
    ins_isk = arlig_isk_ins if age <= pensionsalder else 0
    ins_tjp = arlig_tjp_ins if age <= pensionsalder else 0
    
    t1_isk.append((t1_isk[-1] + ins_isk) * avk_faktor_t1)
    t1_tjp.append((t1_tjp[-1] + ins_tjp) * avk_faktor_t1)
    t1_aktie.append(t1_aktie[-1] * avk_faktor_t1)
    t1_ips.append(t1_ips[-1] * avk_faktor_t1)
    t1_pf.append(t1_pf[-1] * avk_faktor_t1)
    t1_allm.append(t1_allm[-1] * avk_faktor_t1)
    t1_kpa.append(t1_kpa[-1] * avk_faktor_t1)
    t1_futur.append(t1_futur[-1] * avk_faktor_t1)
    t1_bolag.append(t1_bolag[-1] * avk_faktor_t1)

df = pd.DataFrame({
    'Ålder': aldrar_t1,
    'ISK Värde': t1_isk, 'Tjänstepension Värde': t1_tjp, 'Aktiekonto Värde': t1_aktie,
    'IPS Värde': t1_ips, 'Pensionsförsäkring Värde': t1_pf, 'Allmän Pension Värde': t1_allm,
    'KPA Traditionell Värde': t1_kpa, 'Futur Pension Värde': t1_futur, 'Bolagets Kassa Värde': t1_bolag
})

# --- SKATTE- & INFLATIONSLOGIK HUVUDTABELL ---
def justera_data(row):
    ny_rad = row.copy()
    if skatte_läge == "Netto (I plånboken)":
        inkomstskatt = 0.22 if ny_rad['Ålder'] >= 68 else 0.32
        for konto in ['Tjänstepension Värde', 'IPS Värde', 'Pensionsförsäkring Värde', 'Allmän Pension Värde', 'KPA Traditionell Värde', 'Futur Pension Värde']:
            if konto in ny_rad: ny_rad[konto] *= (1 - inkomstskatt)
        if 'Aktiekonto Värde' in ny_rad: ny_rad['Aktiekonto Värde'] *= 0.70
        if 'Bolagets Kassa Värde' in ny_rad: ny_rad['Bolagets Kassa Värde'] *= 0.80 
            
    if simulera_inflation:
        ar_framat = max(0, ny_rad['Ålder'] - aktuell_alder)
        diskonteringsfaktor = (1 + (inflations_takt / 100)) ** ar_framat
        for konto in pott_lista:
            if konto in ny_rad: ny_rad[konto] = ny_rad[konto] / diskonteringsfaktor

    ny_rad['Totalt Värde'] = sum([ny_rad[k] for k in pott_lista if k in ny_rad])
    return ny_rad

chart_df = df.apply(justera_data, axis=1)
pension_rad = chart_df[chart_df['Ålder'] == pensionsalder]
totalt_vid_pension = pension_rad['Totalt Värde'].values[0] if not pension_rad.empty else 0

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
            if skatte_läge == "Netto (I plånboken)":
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
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "🔮 Uttag & Scenarier", "💼 Företagaren", "📚 Skatt & Strategi", "⚙️ Loggbok & Uppdatering"])

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

    skatte_text = "Netto" if skatte_läge == "Netto (I plånboken)" else "Brutto"
    inflations_text = f" (Köpkraft)" if simulera_inflation else ""
    
    st.subheader(f"Din ekonomi vid {pensionsalder} års ålder | {skatte_text}{inflations_text}")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Prognos Totalt Värde", snygga_siffror(totalt_vid_pension))
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
        fig_hist = px.bar(clean_historik, x='År', y='Totalt', labels={'Totalt': f"Totalt Värde ({skatte_text})"})
        st.plotly_chart(fig_hist, use_container_width=True)

with tab2:
    st.subheader(f"🔮 Uttag & Scenarier: Avancerad Skattesmart Uttagsmotor ({skatte_text}{inflations_text})")
    
    col_top1, col_top2 = st.columns(2)
    with col_top1: 
        start_alder = st.slider("Global startålder för brygga (ISK/Bolag)", min_value=aktuell_alder, max_value=75, value=60)
    with col_top2:
        with st.expander("⚙️ Justera sparande (Före & Under nedtrappning)"):
            st.markdown("**1. Fram till startåldern**")
            sim_ny_isk_ins = st.number_input("Sparande till ISK (kr/år)", value=int(arlig_isk_ins), step=10000)
            sim_ny_tjp_ins = st.number_input("Avsättning till TJP (kr/år)", value=int(arlig_tjp_ins), step=10000)
            st.markdown("---")
            st.markdown("**2. Under nedtrappningen**")
            sim_isk_ins_under = st.number_input("Nytt sparande till ISK under nedtrappning (kr/år)", value=0, step=1000)
            sim_tjp_ins_under = st.number_input("Ny avsättning till TJP under nedtrappning (kr/år)", value=0, step=1000)
        
        with st.expander("🎯 Individuella Startåldrar & Utbetalningstider (Skatteregler)"):
            c_i1, c_i2 = st.columns(2)
            with c_i1:
                start_alder_allman = st.slider("Allmän Pension (Startålder)", 60, 75, 68)
                utb_tid_allman = st.slider("Allmän Pension (Utb.tid år)", 5, 40, 20)
                
                start_alder_tjp = st.slider("Tjänstepension (Startålder)", 55, 75, 68)
                utb_tid_tjp = st.slider("Tjänstepension (Utb.tid år)", 5, 30, 10)
                
                start_alder_kpa = st.slider("KPA Traditionell (Startålder)", 55, 75, 68)
                utb_tid_kpa = st.slider("KPA (Utb.tid år)", 5, 30, 10)
            with c_i2:
                start_alder_futur = st.slider("Futur Pension (Startålder)", 55, 75, 68)
                utb_tid_futur = st.slider("Futur (Utb.tid år)", 5, 30, 10)
                
                start_alder_ips = st.slider("IPS (Startålder)", 55, 75, 68)
                utb_tid_ips = st.slider("IPS (Utb.tid år)", 5, 30, 10)
                
                start_alder_pf = st.slider("Pensionsförsäkring (Startålder)", 55, 75, 68)
                utb_tid_pf = st.slider("PF (Utb.tid år)", 5, 30, 10)

    col_u1, col_u2 = st.columns([1, 1.5])
    with col_u1:
        onskat_netto_manad = st.number_input("Önskad utbetalning första året (Netto kr/mån)", min_value=10000, max_value=150000, value=40000, step=1000)
        sim_avkastning = st.slider("Förväntad avkastning under pension (%)", min_value=0.0, max_value=12.0, value=5.0, step=0.5)
        sim_uttags_inflation = st.slider("Årlig inflation (Ökar ditt uttag varje år) (%)", min_value=0.0, max_value=5.0, value=2.0, step=0.1)
        
    pre_isk, pre_tjp, pre_aktie, pre_ips, pre_pf = s_isk_start, s_tjp_start, s_aktie_start, s_ips_start, s_pf_start
    pre_allm, pre_kpa, pre_futur = allman_start, kpa_start, futur_start
    pre_bolag = bolagets_kassa_start
    avk_faktor = 1 + (sim_avkastning / 100)
    
    for age in range(aktuell_alder, start_alder):
        pre_isk += sim_ny_isk_ins; pre_tjp += sim_ny_tjp_ins
        pre_isk *= avk_faktor; pre_tjp *= avk_faktor; pre_aktie *= avk_faktor; pre_ips *= avk_faktor; pre_pf *= avk_faktor; pre_allm *= avk_faktor; pre_kpa *= avk_faktor; pre_futur *= avk_faktor; pre_bolag *= avk_faktor
        
    total_brutto_start = sum([pre_isk, pre_tjp, pre_aktie, pre_ips, pre_pf, pre_allm, pre_kpa, pre_futur, pre_bolag])
    skatt_snitt = 0.32 if start_alder < 68 else 0.22
    total_netto_start = pre_isk + (pre_bolag * 0.80) + (pre_aktie * 0.70) + ((pre_tjp + pre_ips + pre_pf + pre_allm + pre_kpa + pre_futur) * (1 - skatt_snitt))
    beraknad_uttagsgrad_netto = ((onskat_netto_manad * 12) / total_netto_start) * 100 if total_netto_start > 0 else 0

    with col_u2:
        st.markdown("<p style='font-size:16px; margin-bottom: -10px;'>Ditt uttag per månad (Startåret):</p>", unsafe_allow_html=True)
        st.markdown(f"<h1 style='font-size: 48px; color: #4CAF50;'>{int(onskat_netto_manad):,} kr / mån</h1>".replace(',', ' '), unsafe_allow_html=True)
        st.markdown(f"<p style='color: gray;'>Motsvarar ett uttag på ca {beraknad_uttagsgrad_netto:.1f}% av ditt nettokapital första året. Därefter ökar uttaget med {sim_uttags_inflation}% per år för att matcha inflationen.</p>", unsafe_allow_html=True)

    s_isk, s_tjp, s_aktie, s_ips, s_pf = s_isk_start, s_tjp_start, s_aktie_start, s_ips_start, s_pf_start
    s_allm, s_kpa, s_futur, s_bolag = allman_start, kpa_start, futur_start, bolagets_kassa_start
    
    aldrar, n_isk, n_bolag, n_tjp, n_aktie, n_ips, n_pf, n_allm, n_kpa, n_futur = [], [], [], [], [], [], [], [], [], []
    ut_isk, ut_bolag, ut_aktie, ut_tjp, ut_ips, ut_pf, ut_allm, ut_kpa, ut_futur = [], [], [], [], [], [], [], [], []
    
    STATLIG_SKATT_GRANS_BRUTTO = 612000
    
    for age in range(aktuell_alder, 91):
        aldrar.append(age)
        
        n_isk.append(max(0, s_isk)); n_bolag.append(max(0, s_bolag)); n_tjp.append(max(0, s_tjp)); n_aktie.append(max(0, s_aktie)); n_ips.append(max(0, s_ips)); n_pf.append(max(0, s_pf)); n_allm.append(max(0, s_allm)); n_kpa.append(max(0, s_kpa)); n_futur.append(max(0, s_futur))
        
        if age < start_alder:
            s_isk += sim_ny_isk_ins; s_tjp += sim_ny_tjp_ins
            arets_uttag = {"ISK": 0, "Bolagets Kassa": 0, "Aktiekonto": 0, "Allmän Pension": 0, "Tjänstepension": 0, "KPA": 0, "Futur": 0, "IPS": 0, "PF": 0}
        else:
            s_isk += sim_isk_ins_under; s_tjp += sim_tjp_ins_under
            kvar_netto_att_fa_ut = (onskat_netto_manad * 12) * ((1 + (sim_uttags_inflation / 100)) ** (age - start_alder))
            ink_skatt_nu = 0.22 if age >= 68 else 0.32
            
            arets_uttag = {"ISK": 0, "Bolagets Kassa": 0, "Aktiekonto": 0, "Allmän Pension": 0, "Tjänstepension": 0, "KPA": 0, "Futur": 0, "IPS": 0, "PF": 0}
            
            pension_pots_config = [
                ("Allmän Pension", s_allm, start_alder_allman, utb_tid_allman),
                ("Tjänstepension", s_tjp, start_alder_tjp, utb_tid_tjp),
                ("KPA", s_kpa, start_alder_kpa, utb_tid_kpa),
                ("Futur", s_futur, start_alder_futur, utb_tid_futur),
                ("IPS", s_ips, start_alder_ips, utb_tid_ips),
                ("PF", s_pf, start_alder_pf, utb_tid_pf)
            ]
            
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
                flex_konton = [("ISK", s_isk, 0.0), ("Bolagets Kassa", s_bolag, 0.20), ("Aktiekonto", s_aktie, 0.30)]
                for namn, saldo_brutto, skatt in flex_konton:
                    if kvar_netto_att_fa_ut > 0 and saldo_brutto > 0:
                        max_netto = saldo_brutto * (1 - skatt)
                        if max_netto <= kvar_netto_att_fa_ut:
                            uttag_brutto = saldo_brutto
                            uttag_netto = max_netto
                        else:
                            uttag_netto = kvar_netto_att_fa_ut
                            uttag_brutto = kvar_netto_att_fa_ut / (1 - skatt)
                            
                        arets_uttag[namn] = uttag_brutto
                        kvar_netto_att_fa_ut -= uttag_netto
                        
                        if namn == "ISK": s_isk -= uttag_brutto
                        elif namn == "Bolagets Kassa": s_bolag -= uttag_brutto
                        elif namn == "Aktiekonto": s_aktie -= uttag_brutto
                        
            elif kvar_netto_att_fa_ut < 0:
                s_isk += abs(kvar_netto_att_fa_ut)
                arets_uttag["ISK"] = -abs(kvar_netto_att_fa_ut)

        ut_isk.append(arets_uttag["ISK"]); ut_bolag.append(arets_uttag.get("Bolagets Kassa", 0)); ut_aktie.append(arets_uttag["Aktiekonto"]); ut_tjp.append(arets_uttag["Tjänstepension"]); ut_ips.append(arets_uttag["IPS"]); ut_pf.append(arets_uttag["PF"]); ut_allm.append(arets_uttag["Allmän Pension"]); ut_kpa.append(arets_uttag["KPA"]); ut_futur.append(arets_uttag["Futur"])
        s_isk *= avk_faktor; s_bolag *= avk_faktor; s_tjp *= avk_faktor; s_aktie *= avk_faktor; s_ips *= avk_faktor; s_pf *= avk_faktor; s_allm *= avk_faktor; s_kpa *= avk_faktor; s_futur *= avk_faktor

    sim_df_area = pd.DataFrame({"Ålder": aldrar, "Bolagets Kassa": n_bolag, "Aktiekonto": n_aktie, "ISK": n_isk, "Pensionsförsäkring": n_pf, "IPS": n_ips, "Futur Pension": n_futur, "KPA Traditionell": n_kpa, "Tjänstepension": n_tjp, "Allmän Pension": n_allm}).set_index("Ålder")
    sim_uttag_df = pd.DataFrame({"Ålder": aldrar, "Bolagets Kassa": ut_bolag, "Aktiekonto": ut_aktie, "ISK": ut_isk, "Pensionsförsäkring": ut_pf, "IPS": ut_ips, "Futur Pension": ut_futur, "KPA Traditionell": ut_kpa, "Tjänstepension": ut_tjp, "Allmän Pension": ut_allm}).set_index("Ålder")

    st.markdown("---")
    st.subheader(f"📊 Saldoutveckling från {start_alder} år (Visas som {skatte_text}{inflations_text})")
    fig_sim = rita_stapeldiagram_med_total(sim_df_area, 'Ålder', pott_namn_ren)
    st.plotly_chart(fig_sim, use_container_width=True)
    
    st.subheader(f"💸 Årliga uttag (Bruttobelopp som tas från konton)")
    fig_uttag_sim = rita_stapeldiagram_med_total(sim_uttag_df, 'Ålder', pott_namn_ren)
    st.plotly_chart(fig_uttag_sim, use_container_width=True)

    st.markdown("### Detaljerad Uttagsplan (Tabell)")
    sim_uttag_df_filtered = sim_uttag_df[sim_uttag_df.index >= start_alder].copy().round(0).astype(int)
    skattesats_pension_lista_sim, netto_lista_sim, ingaende_saldo_lista = [], [], []
    
    for age, row in sim_uttag_df_filtered.iterrows():
        ink_skatt = 0.32 if age < 68 else 0.22
        pens_uttag = max(0, row['Pensionsförsäkring']) + max(0, row['IPS']) + max(0, row['Futur Pension']) + max(0, row['KPA Traditionell']) + max(0, row['Tjänstepension']) + max(0, row['Allmän Pension'])
        aktie_uttag, isk_uttag, bolag_uttag = row['Aktiekonto'], row['ISK'], max(0, row['Bolagets Kassa'])
        netto = (pens_uttag * (1 - ink_skatt)) + (aktie_uttag * 0.70) + (bolag_uttag * 0.80) + isk_uttag
        netto_lista_sim.append(int(netto))
        skattesats_pension_lista_sim.append(f"{int(ink_skatt*100)} %" if pens_uttag > 0 else "- (Skattefritt/Kapital)")

        belastade_konton = []
        for pott in pott_namn_ren:
            if row[pott] > 0: belastade_konton.append(f"{pott}: {int(sim_df_area.loc[age, pott]):,} kr".replace(',', ' '))
            elif row[pott] < 0: belastade_konton.append(f"{pott} (Återinvesterat): +{int(abs(row[pott])):,} kr".replace(',', ' '))
                
        ingaende_saldo_lista.append(" | ".join(belastade_konton) if belastade_konton else "Inga uttag")

    sim_uttag_df_filtered['Skattesats (Pensioner)'] = skattesats_pension_lista_sim
    sim_uttag_df_filtered['Totalt Uttag (Brutto)'] = sim_uttag_df_filtered[pott_namn_ren].sum(axis=1)
    sim_uttag_df_filtered['I plånboken (Netto)'] = netto_lista_sim
    sim_uttag_df_filtered['Ingående Saldo (Före uttag)'] = ingaende_saldo_lista
    
    cols = ['Aktiekonto', 'Bolagets Kassa', 'ISK', 'Pensionsförsäkring', 'IPS', 'Futur Pension', 'KPA Traditionell', 'Tjänstepension', 'Allmän Pension', 'Skattesats (Pensioner)', 'Totalt Uttag (Brutto)', 'I plånboken (Netto)', 'Ingående Saldo (Före uttag)']
    st.dataframe(sim_uttag_df_filtered[cols].astype(object), use_container_width=True)

with tab3:
    st.subheader("⚖️ Företagaren: Aktiebolaget")
    st.markdown("### 🏢 Din bolagsstatus just nu")
    col_stat1, col_stat2 = st.columns(2)
    with col_stat1: st.metric("Sparade vinstmedel i Bolaget", f"{int(bolagets_kassa_start):,} kr".replace(',', ' '))
    with col_stat2: st.metric("Sparat K10-utrymme", f"{int(bolagets_k10_start):,} kr".replace(',', ' '))
        
    st.markdown("---")
    st.markdown("### Simulera årets oskattade vinst: Utdelning vs. Tjänstepension")
    col_f1, col_f2 = st.columns(2)
    with col_f1: vinst_att_fordela = st.slider("Årets oskattade vinst att fördela (kr)", 50000, 2000000, 100000, 10000)
    with col_f2: k10_utrymme = st.number_input("Använd detta K10-utrymme för simuleringen (kr)", value=int(bolagets_k10_start), step=10000)
    
    col_sim1, col_sim2 = st.columns(2)
    with col_sim1:
        st.markdown("#### Alt 1: Aktieutdelning")
        bolagsskatt = vinst_att_fordela * 0.206
        vinst_efter_bolagsskatt = vinst_att_fordela - bolagsskatt
        if vinst_efter_bolagsskatt <= k10_utrymme:
            st.success("✅ Vinsten ryms inom K10! (Kapitalskatt 20%)")
            utdelningsskatt = vinst_efter_bolagsskatt * 0.20
        else:
            st.warning("⚠️ Vinsten överstiger K10. Överskottet beskattas som lön (ca 50%).")
            utdelningsskatt = (k10_utrymme * 0.20) + ((vinst_efter_bolagsskatt - k10_utrymme) * 0.50)
            
        netto_utdelning = vinst_efter_bolagsskatt - utdelningsskatt
        st.write(f"- Bolagsskatt (20,6%): **-{int(bolagsskatt):,} kr**".replace(',', ' '))
        st.write(f"- Privat skatt: **-{int(utdelningsskatt):,} kr**".replace(',', ' '))
        st.metric("In på ISK (Netto)", f"{int(netto_utdelning):,} kr".replace(',', ' '))
        
    with col_sim2:
        st.markdown("#### Alt 2: Tjänstepension")
        tjp_avsattning = vinst_att_fordela / 1.2426
        sls_skatt = vinst_att_fordela - tjp_avsattning
        inkomstskatt_procent = 0.22 if start_alder >= 68 else 0.32
        framtida_inkomstskatt = tjp_avsattning * inkomstskatt_procent
        netto_tjp = tjp_avsattning - framtida_inkomstskatt
        st.write(f"- Särskild löneskatt (24,26% i bolaget): **-{int(sls_skatt):,} kr**".replace(',', ' '))
        st.write(f"- Framtida inkomstskatt ({int(inkomstskatt_procent*100)}%): **-{int(framtida_inkomstskatt):,} kr**".replace(',', ' '))
        st.metric("I plånboken framöver (Netto)", f"{int(netto_tjp):,} kr".replace(',', ' '))

with tab4:
    st.subheader("📚 Pensionsskolan: Så beskattas dina 9 potter")
    skatte_data = {
        "Pott / Konto": ["Bolagets Kassa (AB)", "ISK", "Aktiekonto", "Allmän Pension", "Tjänstepension", "KPA", "Futur", "IPS", "Pensionsförsäkring"],
        "Beskattning (Före 68)": ["20% Utdelningsskatt (Inom K10)", "Skatt på schablon (0%)", "30% kapitalskatt på vinst", "Inkomstskatt (ca 32%)", "Inkomstskatt (ca 32%)", "Inkomstskatt (ca 32%)", "Inkomstskatt (ca 32%)", "Inkomstskatt (ca 32%)", "Inkomstskatt (ca 32%)"],
        "Beskattning (Efter 68)": ["20% Utdelningsskatt", "Samma (Fortsatt låg skatt)", "Samma (30% på vinst)", "Sänkt Inkomstskatt (ca 22%)", "Sänkt Inkomstskatt (ca 22%)", "Sänkt Inkomstskatt (ca 22%)", "Sänkt Inkomstskatt (ca 22%)", "Sänkt Inkomstskatt (ca 22%)", "Sänkt Inkomstskatt (ca 22%)"],
        "Strategi": ["Använd som skattelyx (20%)", "Töm före 68 (Bryggan)", "Använd före 68", "Spara till 68", "Spara till 68", "Spara till 68", "Spara till 68", "Spara till 68", "Spara till 68"]
    }
    st.table(pd.DataFrame(skatte_data))

with tab5:
    st.subheader("⚙️ Loggbok & Uppdatering")
    st.markdown("### 💸 1. Löpande transaktioner under året")
    
    aktuell_alder_logg = st.number_input("Din ålder i år:", min_value=50, max_value=100, value=aktuell_alder)
    alder_68 = aktuell_alder_logg >= 68
    
    if not alder_68: st.info("🤖 **AI-Assistentens rekommendation:** Du är under 68 år. Finansiera livet via utdelning från **Bolagets Kassa** (20 % skatt inom K10) eller sälj av från **ISK/Aktiekontot**.")
    else: st.info("🤖 **AI-Assistentens rekommendation:** Du har nått 68 år (Full skatterabatt). Prioritera uttag från **tjänstepensioner och allmän pension** för att tömma dessa medan det är billigt.")
        
    with st.form("batch_uttag_form"):
        inmatning_typ = st.radio("Beloppen nedan avser:", ["Netto (Det jag fick in på banken)", "Brutto (Hela beloppet före skatt)"])
        
        c1, c2, c3, c4 = st.columns(4)
        batch_inputs = {}
        with c1:
            batch_inputs["Allmän Pension"] = st.number_input("Allmän Pension", min_value=0, value=0, step=1000)
            batch_inputs["Tjänstepension"] = st.number_input("Tjänstepension", min_value=0, value=0, step=1000)
            batch_inputs["Bolagets Kassa"] = st.number_input("Utdelning (Bolagets Kassa)", min_value=0, value=0, step=1000)
        with c2:
            batch_inputs["KPA"] = st.number_input("KPA Traditionell", min_value=0, value=0, step=1000)
            batch_inputs["Futur Pension"] = st.number_input("Futur Pension", min_value=0, value=0, step=1000)
        with c3:
            batch_inputs["ISK"] = st.number_input("ISK (Stöduttag)", min_value=0, value=0, step=1000)
            batch_inputs["Aktiekonto"] = st.number_input("Aktiekonto", min_value=0, value=0, step=1000)
        with c4:
            batch_inputs["IPS"] = st.number_input("IPS", min_value=0, value=0, step=1000)
            batch_inputs["Pensionsförsäkring"] = st.number_input("Pensionsförsäkring", min_value=0, value=0, step=1000)
            
        if st.form_submit_button("Logga Månadens Uttag (Optimerad Batch)"):
            if sum(batch_inputs.values()) == 0:
                st.warning("Du måste ange ett belopp större än 0 för minst ett konto.")
            else:
                try:
                    # NAMNGIVNA OMRÅDEN! Ingen mer B7/E6-koordinat.
                    cell_map = {"ISK": "ISK_Saldo", "Tjänstepension": "TJP_Saldo", "Aktiekonto": "Aktiekonto_Saldo", "IPS": "IPS_Saldo", "Pensionsförsäkring": "PF_Saldo", "Allmän Pension": "Allman_Pension", "KPA Traditionell": "KPA_Traditionell", "Futur Pension": "Futur_Pension", "Bolagets Kassa": "Bolagets_Kassa"}
                    batch_map = {"Allmän Pension": "Allmän Pension", "Tjänstepension": "Tjänstepension", "KPA": "KPA Traditionell", "Futur Pension": "Futur Pension", "ISK": "ISK", "Aktiekonto": "Aktiekonto", "IPS": "IPS", "Pensionsförsäkring": "Pensionsförsäkring", "Bolagets Kassa": "Bolagets Kassa"}
                    
                    # Hämta nuvarande saldon snabbt från våra inlästa variabler, inga onödiga API-anrop!
                    current_saldos = {"ISK": s_isk_start, "Tjänstepension": s_tjp_start, "Aktiekonto": s_aktie_start, "IPS": s_ips_start, "Pensionsförsäkring": s_pf_start, "Allmän Pension": allman_start, "KPA Traditionell": kpa_start, "Futur Pension": futur_start, "Bolagets Kassa": bolagets_kassa_start}
                    
                    creds_dict = dict(st.secrets["connections"]["gsheets"])
                    gc = gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets']))
                    sh = gc.open_by_url(sheet_url)
                    worksheet = sh.sheet1
                    logg_sheet = sh.worksheet("Händelselogg")

                    updates = []
                    log_rows = []
                    total_netto = 0
                    total_brutto = 0
                    
                    for ui_namn, belopp in batch_inputs.items():
                        if belopp > 0:
                            riktigt_namn = batch_map[ui_namn]
                            skattesats = 0.0
                            if riktigt_namn == "ISK": skattesats = 0.0
                            elif riktigt_namn == "Bolagets Kassa": skattesats = 0.20
                            elif riktigt_namn == "Aktiekonto": skattesats = 0.30
                            else: skattesats = 0.22 if alder_68 else 0.32
                            
                            if "Netto" in inmatning_typ:
                                netto = belopp
                                brutto = netto / (1 - skattesats)
                            else:
                                brutto = belopp
                                netto = brutto * (1 - skattesats)
                                
                            total_netto += netto
                            total_brutto += brutto
                            
                            target_cell_name = cell_map[riktigt_namn]
                            curr = current_saldos[riktigt_namn]
                            ny_siffra = max(0, curr - brutto)
                            
                            updates.append({'range': target_cell_name, 'values': [[ny_siffra]]})
                            log_rows.append([datetime.datetime.now().strftime("%Y-%m-%d"), f"Månadsuttag ({riktigt_namn}) - Netto in: {int(netto)} kr", -brutto])
                    
                    if updates:
                        worksheet.batch_update(updates)
                        logg_sheet.append_rows(log_rows)
                    
                    st.success(f"✅ Månadslönen loggad via säkra namnanrop! Du fick totalt **{int(total_netto):,} kr** i plånboken. Systemet drog totalt **{int(total_brutto):,} kr** (brutto) från kalkylarket.".replace(',', ' '))
                    st.cache_data.clear()
                except Exception as e: st.error(f"Fel vid uppdatering: {e}")

    col_log2, col_log3 = st.columns(2)
    with col_log2:
        st.markdown("#### 🚗 Oväntat uttag (ISK)")
        with st.form("isk_uttag_form"):
            uttag_belopp_isk = st.number_input("Belopp (kr)", min_value=1, value=50000, step=1000, key="isk_uttag")
            uttag_beskrivning_isk = st.text_input("Vad gick pengarna till?")
            if st.form_submit_button("Logga Oväntat Uttag") and uttag_beskrivning_isk:
                try:
                    creds_dict = dict(st.secrets["connections"]["gsheets"])
                    sh = gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])).open_by_url(sheet_url)
                    ny_siffra = s_isk_start - uttag_belopp_isk
                    sh.sheet1.update(range_name="ISK_Saldo", values=[[ny_siffra]])
                    sh.worksheet("Händelselogg").append_row([datetime.datetime.now().strftime("%Y-%m-%d"), f"Oväntat uttag ISK ({uttag_beskrivning_isk})", -uttag_belopp_isk])
                    st.success("✅ Klart! Pengarna dragna från ISK."); st.cache_data.clear()
                except Exception as e: st.error(e)

    with col_log3:
        st.markdown("#### 💰 Insättning (ISK)")
        with st.form("insattning_form"):
            ins_belopp = st.number_input("Belopp (kr)", min_value=1, value=10000, step=1000, key="isk_ins")
            ins_beskrivning = st.text_input("Varifrån kommer pengarna?")
            if st.form_submit_button("Logga Insättning") and ins_beskrivning:
                try:
                    creds_dict = dict(st.secrets["connections"]["gsheets"])
                    sh = gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])).open_by_url(sheet_url)
                    ny_siffra = s_isk_start + ins_belopp
                    sh.sheet1.update(range_name="ISK_Saldo", values=[[ny_siffra]])
                    sh.worksheet("Händelselogg").append_row([datetime.datetime.now().strftime("%Y-%m-%d"), f"Insättning ISK ({ins_beskrivning})", ins_belopp])
                    st.success("✅ Klart! Pengarna insatta på ISK."); st.cache_data.clear()
                except Exception as e: st.error(e)

    st.markdown("---")
    st.markdown("### 📅 2. Den årliga storstädningen")
    with st.expander("Öppna formulär för årlig uppdatering av saldon & uppföljning"):
        with st.form("update_form"):
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                new_isk = st.number_input("ISK Värde (kr)", value=int(s_isk_start), step=1000)
                new_aktie = st.number_input("Aktiekonto Värde (kr)", value=int(s_aktie_start), step=1000)
                new_allman = st.number_input("Allmän Pension (kr)", value=int(allman_start), step=1000)
            with col_s2:
                new_bolagskassa = st.number_input("Företagets Kassa (kr)", value=int(bolagets_kassa_start), step=1000)
                new_k10 = st.number_input("Sparat K10-utrymme (kr)", value=int(bolagets_k10_start), step=1000)
                new_tjp = st.number_input("Tjänstepension Värde (kr)", value=int(s_tjp_start), step=1000)
            with col_s3:
                new_ips = st.number_input("IPS Värde (kr)", value=int(s_ips_start), step=1000)
                new_pens = st.number_input("Pensionsförsäkring (kr)", value=int(s_pf_start), step=1000)
                new_kpa = st.number_input("KPA Traditionell (kr)", value=int(kpa_start), step=1000)
                new_futur = st.number_input("Futur Pension (kr)", value=int(futur_start), step=1000)
                
            st.markdown("#### Planerat sparande kommande 12 månader")
            new_privatspar_ar = st.number_input("Privat sparande (kr/år)", value=36000, step=1000)
            new_utdelning = st.number_input("Aktieutdelning in på ISK (kr/år)", value=150000, step=10000)
            new_tjp_ins = st.number_input("Bolagets avsättning TJP (kr/år)", value=int(arlig_tjp_ins), step=10000)
                
            if st.form_submit_button("Spara allt till Kalkylark (Optimerad Batch)"):
                try:
                    gammal_totalsumma = s_isk_start + s_tjp_start + s_aktie_start + s_ips_start + s_pf_start + allman_start + kpa_start + futur_start + bolagets_kassa_start
                    ny_totalsumma = new_isk + new_tjp + new_aktie + new_ips + new_pens + new_allman + new_kpa + new_futur + new_bolagskassa
                    summa_isk_insattning = new_privatspar_ar + new_utdelning
                    
                    creds_dict = dict(st.secrets["connections"]["gsheets"])
                    gc = gspread.authorize(Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets']))
                    sh = gc.open_by_url(sheet_url)
                    worksheet = sh.sheet1
                    
                    # Använder uteslutande Namngivna Områden
                    batch_updates = [
                        {'range': 'ISK_Saldo', 'values': [[new_isk]]},
                        {'range': 'TJP_Saldo', 'values': [[new_tjp]]},
                        {'range': 'Aktiekonto_Saldo', 'values': [[new_aktie]]},
                        {'range': 'IPS_Saldo', 'values': [[new_ips]]},
                        {'range': 'PF_Saldo', 'values': [[new_pens]]},
                        {'range': 'ISK_Insattning', 'values': [[summa_isk_insattning]]},
                        {'range': 'TJP_Avsattning', 'values': [[new_tjp_ins]]},
                        {'range': 'Total_Saldo', 'values': [[ny_totalsumma]]},
                        {'range': 'Allman_Pension', 'values': [[new_allman]]},
                        {'range': 'KPA_Traditionell', 'values': [[new_kpa]]},
                        {'range': 'Futur_Pension', 'values': [[new_futur]]},
                        {'range': 'Bolagets_Kassa', 'values': [[new_bolagskassa]]},
                        {'range': 'Sparat_K10', 'values': [[new_k10]]}
                    ]
                    worksheet.batch_update(batch_updates)
                    
                    try:
                        historik_sheet = sh.worksheet("Historik")
                        historik_sheet.append_row([
                            datetime.datetime.now().year, 
                            new_isk, new_tjp, new_aktie, new_ips, new_pens, 
                            ny_totalsumma, new_allman, new_kpa, new_futur, new_bolagskassa
                        ])
                    except: pass
                        
                    st.cache_data.clear()
                    
                    utveckling_kr = ny_totalsumma - gammal_totalsumma
                    utveckling_procent = (utveckling_kr / gammal_totalsumma) * 100 if gammal_totalsumma > 0 else 0
                    
                    if utveckling_procent >= forvantad_avkastning_procent:
                        st.balloons()
                        st.success(f"🎉 **Fantastiskt jobbat!** Din portfölj har vuxit med {int(utveckling_kr):,} kr (+{utveckling_procent:.1f}%) sedan förra mätningen. Ränta-på-ränta-maskinen går på högvarv och du slår din egen plan. All data är sparad säkert!")
                    elif utveckling_procent > 0:
                        st.success(f"📈 **Bra jobbat!** Portföljen växer stabilt. Du är upp {int(utveckling_kr):,} kr (+{utveckling_procent:.1f}%). Fortsätt mata maskinen enligt plan. All data är loggad!")
                    else:
                        st.info(f"⚖️ **Allt enligt plan, trots skakig marknad.** Portföljen har backat med {int(abs(utveckling_kr)):,} kr ({utveckling_procent:.1f}%), men minns att du sparar långsiktigt. Sitt still i båten! Datan är sparad.")
                        
                except Exception as e: st.error(f"Fel: {e}")