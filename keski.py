import streamlit as st
import pandas as pd
import re
from io import StringIO

def extract_year(date_str):
    """
    Etsii merkkijonosta ensimmäisen nelinumeroisen luvun (vuosiluvun).
    Käsittelee 'ABT 1850', '12 JAN 1850' jne.
    """
    if not date_str:
        return None
    match = re.search(r'\d{4}', str(date_str))
    if match:
        return int(match.group(0))
    return None

def parse_gedcom_to_df(file_content):
    """
    Yksinkertainen GEDCOM-jäsennin, joka kerää vain tarvittavat tiedot:
    ID, Syntymävuosi, Kuolinvuosi.
    """
    individuals = []
    current_indi = None
    
    # Pilkotaan rivit
    lines = file_content.splitlines()
    
    # Liput tilan seurantaan
    last_tag = None 
    
    for line in lines:
        line = line.strip()
        parts = line.split(' ', 2)
        level = parts[0]
        
        if len(parts) > 1:
            tag = parts[1]
        else:
            continue
            
        payload = parts[2] if len(parts) > 2 else ""

        # Tunnistetaan uusi henkilö (0 @ID@ INDI)
        if level == '0' and payload == 'INDI':
            if current_indi:
                individuals.append(current_indi)
            current_indi = {'id': tag, 'birth_year': None, 'death_year': None}
            last_tag = None
            continue
        
        # Jos ollaan henkilön tiedoissa
        if current_indi is not None:
            # Tallennetaan mikä tagi oli edellinen, jotta tiedetään mihin DATE viittaa
            if level == '1':
                if tag in ['BIRT', 'DEAT']:
                    last_tag = tag
                else:
                    last_tag = None
            
            # Luetaan päivämäärä, jos se liittyy syntymään tai kuolemaan
            if level == '2' and tag == 'DATE' and last_tag:
                year = extract_year(payload)
                if last_tag == 'BIRT':
                    current_indi['birth_year'] = year
                elif last_tag == 'DEAT':
                    current_indi['death_year'] = year

    # Lisätään viimeinen henkilö luupin jälkeen
    if current_indi:
        individuals.append(current_indi)
        
    return pd.DataFrame(individuals)

# --- Streamlit Sovellus ---

st.set_page_config(page_title="Sukututkimus: Keski-ikä", layout="wide")

st.title("📊 Sukututkimustilastot: Keski-ikä aikajanalla")
st.markdown("""
Tämä työkalu lukee **GEDCOM**-tiedoston ja laskee henkilöiden keskimääräisen eliniän 
perustuen heidän syntymävuosikymmeneensä välillä **1800–1899**.
""")

uploaded_file = st.file_uploader("Lataa GEDCOM-tiedosto (.ged)", type=['ged'])

if uploaded_file is not None:
    try:
        # Luetaan tiedosto. Huom: GEDCOMit ovat usein UTF-8, ANSEL tai ISO-8859-1.
        # Kokeillaan utf-8 ja korvataan virheet, jotta koodi ei kaadu erikoismerkkeihin.
        stringio = StringIO(uploaded_file.getvalue().decode("utf-8", errors='replace'))
        content = stringio.read()
        
        with st.spinner('Luetaan ja jäsennetään sukupuuta...'):
            df = parse_gedcom_to_df(content)

        # Lasketaan ikä (Life Span)
        # Suodatetaan pois ne, joilta puuttuu joko syntymä- tai kuolinaika
        df = df.dropna(subset=['birth_year', 'death_year'])
        
        # Lasketaan ikä
        df['age'] = df['death_year'] - df['birth_year']
        
        # Poistetaan virheelliset iät (negatiiviset tai mahdottoman suuret)
        df = df[(df['age'] >= 0) & (df['age'] < 120)]

        # --- Suodatus ja Ryhmittely ---
        
        # Rajataan tarkastelu syntymävuosiin 1800 - 1899
        start_year = 1800
        end_year = 1899
        mask = (df['birth_year'] >= start_year) & (df['birth_year'] <= end_year)
        filtered_df = df.loc[mask].copy()

        if filtered_df.empty:
            st.warning("Tiedostosta ei löytynyt henkilöitä, joilla on sekä syntymä- että kuolinvuosi välillä 1800-1899.")
        else:
            # Luodaan vuosikymmen-sarake (Binning)
            # Esim. 1845 -> 1840
            filtered_df['decade'] = (filtered_df['birth_year'] // 10) * 10

            # Lasketaan keskiarvot vuosikymmenittäin
            stats = filtered_df.groupby('decade')['age'].agg(['mean', 'count']).reset_index()
            stats.columns = ['Vuosikymmen', 'Keski-ikä', 'Henkilömäärä']
            
            # Varmistetaan että kaikki vuosikymmenet 1800-1890 näkyvät, vaikka dataa puuttuisi
            all_decades = pd.DataFrame({'Vuosikymmen': range(start_year, end_year + 1, 10)})
            stats = pd.merge(all_decades, stats, on='Vuosikymmen', how='left').fillna(0)
            
            # Pyöristetään keski-ikä yhteen desimaaliin
            stats['Keski-ikä'] = stats['Keski-ikä'].round(1)
            stats['Vuosikymmen'] = stats['Vuosikymmen'].astype(str) + "-luku"

            # --- Visualisointi ---
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.subheader("Keski-ikä syntymävuosikymmenittäin")
                # Käytetään Streamlitin bar_chartia
                st.bar_chart(stats.set_index('Vuosikymmen')['Keski-ikä'])
                st.caption("Kuvaaja näyttää kyseisellä vuosikymmenellä syntyneiden keskimääräisen eliniän.")

            with col2:
                st.subheader("Tiedot taulukkona")
                st.dataframe(stats.style.format({'Keski-ikä': '{:.1f} v', 'Henkilömäärä': '{:.0f} kpl'}))

            # --- Lisätiedot datasta ---
            st.info(f"""
            **Analyysi:**
            - Yhteensä analysoituja henkilöitä aikavälillä: **{int(stats['Henkilömäärä'].sum())}**
            - Datan kattavuus: Tiedostosta löytyi {len(df)} henkilöä, joilla oli kelvolliset syntymä- ja kuolintiedot kokonaisuudessaan.
            """)

    except Exception as e:
        st.error(f"Virhe tiedoston käsittelyssä: {e}")
        st.info("Varmista, että tiedosto on validi GEDCOM-tiedosto.")
