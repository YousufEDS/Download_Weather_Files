import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
import pandas as pd
import io



@st.cache_data(show_spinner=False)
@st.cache_data(show_spinner=False)
def fetch_City_files(url):
    resp = requests.get(url, verify=False)
    soup = BeautifulSoup(resp.text, 'html.parser')
    City_files = {}
    all_files = []
    # Find all zip links
    for link in soup.find_all('a', href=re.compile(r'\.zip$')):
        href = link.get('href')
        file = link.text.strip()
        # Extract City folder (before "/")   
        parts = href.split('/')
        if len(parts) < 2:
            continue
        City = parts[0].strip()
        entry = {
            'City': City,
            'href': href,
            'file': file,
            'full_url': url + href
        }
        if City not in City_files:
            City_files[City] = []
        City_files[City].append(entry)
        all_files.append(entry)
    return City_files, all_files

def normalize_name(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower())

def match_city_file(city, all_files, City=None):
    # Only match files like IND_XX_CityName.XXXXX_TMYx.zip (not with extra suffixes)
    city_norm = normalize_name(city)
    City_norm = normalize_name(City) if City else None
    pattern = re.compile(r'^IND_([A-Z]{2})_([^.]+)\.[0-9]+_TMYx\.zip$', re.IGNORECASE)
    candidates = []
    for entry in all_files:
        m = pattern.match(entry['file'])
        if m:
            file_City = m.group(1)
            file_city = m.group(2)
            file_city_norm = normalize_name(file_city)
            entry_City_norm = normalize_name(entry['City'])
            # Match city, and if City is provided, prefer City match
            if file_city_norm == city_norm:
                if City_norm:
                    if City_norm in entry_City_norm or City_norm == file_City.lower():
                        return entry['full_url'], entry['file']
                    else:
                        candidates.append((entry['full_url'], entry['file']))
                else:
                    candidates.append((entry['full_url'], entry['file']))
    # If no perfect City match, return first city match
    if candidates:
        return candidates[0]
    return '', ''

def main():
    st.title("Weather Files Selector")
    st.write("Select one weather .zip file for each City. You can download your selection as an Excel file.")

    # Load country-region mapping
    mapping_path = "20250904_country_region_mapping.csv"
    try:
        mapping_df = pd.read_csv(mapping_path)
        # Normalize country names in mapping
        mapping_df['Country'] = mapping_df['Country'].astype(str).str.strip().str.upper()
        country_to_url = {row['Country']: row['Region_URL'] for _, row in mapping_df.iterrows()}
    except Exception as e:
        st.error(f"Failed to load country-region mapping: {e}")
        return

    uploaded = st.file_uploader("Upload Excel file", type=["xlsx"], key="excel_upload")
    if not uploaded:
        st.info("Please upload an Excel file to begin.")
        return

    df = pd.read_excel(uploaded)
    # Find the city and country columns (case-insensitive, ignore whitespace)
    city_col = None
    country_col = None
    for col in df.columns:
        if col.strip().lower() == "city":
            city_col = col
        if col.strip().lower() == "country":
            country_col = col
    if not city_col or not country_col:
        st.error("Excel must have 'City' and 'Country' columns.")
        return

    excel_cities = [str(s).strip() for s in df[city_col] if pd.notna(s)]
    excel_countries = [str(s).strip().upper() for s in df[country_col] if pd.notna(s)]
    city_country_pairs = list(zip(excel_cities, excel_countries))
    unique_countries = sorted(set(excel_countries))

    # Map each country to its region URL
    country_url_map = {}
    for country in unique_countries:
        url = country_to_url.get(country)
        if url:
            country_url_map[country] = url
        else:
            st.warning(f"No region URL found for country: '{country}'. Please check the mapping CSV and Excel country names.")

    # For each country, fetch its weather files
    all_country_files = {}
    for country, url in country_url_map.items():
        st.markdown(f"**Fetching for {country} from:** [{url}]({url})")
        City_files, all_files = fetch_City_files(url)
        all_country_files[country] = all_files

    # For each city-country pair, use the correct all_files for matching
    def city_in_filename(city, filename):
        city_norm = re.sub(r'[^a-z0-9]', '', city.lower())
        filename_norm = re.sub(r'[^a-z0-9]', '', filename.lower())
        return city_norm in filename_norm and filename.lower().endswith('tmyx.zip')

    selected_files = {}
    mapped_cities = set()
    cities_with_options = set()
    for city, country in city_country_pairs:
        all_files = all_country_files.get(country)
        if not all_files:
            continue
        matches = [f for f in all_files if city_in_filename(city, f['file'])]
        if matches:
            cities_with_options.add((city, country))
            # Prefer file that contains .Intl.AP
            intl_matches = [f for f in matches if '.intl.ap' in f['file'].lower()]
            file_options = {f["file"]: f for f in matches}
            file_names = list(file_options.keys())
            if intl_matches:
                selected_files[(city, country)] = intl_matches[0]
                mapped_cities.add((city, country))
            elif len(file_names) == 1:
                selected_files[(city, country)] = file_options[file_names[0]]
                mapped_cities.add((city, country))
    # Only show unmapped cities with options for manual selection
    unmapped_cities = [(city, country) for city, country in city_country_pairs if (city, country) not in mapped_cities and (city, country) in cities_with_options]
    manual_selected = {}
    import re as _re
    def safe_key(city, country):
        return _re.sub(r'[^a-zA-Z0-9_]', '_', f"{city}_{country}")
    for city, country in unmapped_cities:
        all_files = all_country_files.get(country)
        matches = [f for f in all_files if city_in_filename(city, f['file'])]
        st.subheader(f"{city} ({country})")
        file_options = {f["file"]: f for f in matches}
        file_names = list(file_options.keys())
        widget_key = safe_key(city, country)
        selected = st.radio(f"Select a .zip file for {city}, {country}", file_names, key=widget_key)
        manual_selected[(city, country)] = file_options[selected]
    # Merge manual selections into selected_files
    selected_files.update(manual_selected)

    # Prepare summary and table before showing table
    result_rows = []
    for city, country in city_country_pairs:
        fileinfo = selected_files.get((city, country))
        if fileinfo:
            result_rows.append({
                "City": city,
                "Country": country,
                "Weather File-zip": fileinfo["file"],
                "Weather File Url": fileinfo["full_url"],
                "Status": "Found"
            })
        else:
            result_rows.append({
                "City": city,
                "Country": country,
                "Weather File-zip": "",
                "Weather File Url": "",
                "Status": "Not found"
            })
    result_df = pd.DataFrame(result_rows)
    found_count = (result_df['Status'] == 'Found').sum()
    not_found_count = (result_df['Status'] == 'Not found').sum()
    st.info(f"Mapped: {found_count} | Not mapped: {not_found_count}")
    if not result_df.empty:
        st.header("Step 3: Your Selection Table")
        st.dataframe(result_df)

        # Download all mapped zip files to a directory
        import os
        import shutil
        import requests as reqs
        if st.button("Download All Mapped Files to Server Directory"):
            import datetime
            base_dir = "downloaded_zips"
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            download_dir = os.path.join(base_dir, f"download_{timestamp}")
            os.makedirs(download_dir, exist_ok=True)
            for row in result_rows:
                if row["Status"] == "Found":
                    url = row["Weather File Url"]
                    filename = os.path.join(download_dir, row["Weather File-zip"])
                    try:
                        r = reqs.get(url, stream=True, timeout=60)
                        with open(filename, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                    except Exception as e:
                        st.error(f"Failed to download {row['Weather File-zip']}: {e}")
            st.success(f"All mapped zip files downloaded to ./{download_dir}/")

        # Download button for Excel
        towrite = io.BytesIO()
        result_df.to_excel(towrite, index=False)
        towrite.seek(0)
        st.download_button("Download Selection as Excel", towrite, file_name=f"selected_weather_files.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")



if __name__ == "__main__":
    main()
