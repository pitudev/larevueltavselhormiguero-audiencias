import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
from github import Github


def parse_date(date_str):
    """Convierte el string de fecha a formato ISO (YYYY-MM-DD)."""
    try:
        parts = date_str.strip().split()
        date_obj = datetime.strptime(parts[1], "%d/%m/%Y")
        return date_obj.strftime("%Y-%m-%d")
    except Exception as e:
        print("Error parseando la fecha:", e)
        return None


def parse_number(num_str):
    """Convierte un número con separadores de miles a entero."""
    try:
        return int(num_str.replace(".", "").strip())
    except Exception as e:
        print("Error parseando el número:", e)
        return 0


def parse_share(share_str):
    """Convierte un porcentaje a float."""
    try:
        return float(share_str.replace("%", "").strip())
    except Exception as e:
        print("Error parseando el share:", e)
        return 0.0


def scrape_daily_data(url):
    """Extrae los datos de audiencia desde la URL dada."""
    # Usar headers genéricos para evitar bloqueos
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error al acceder a la URL: {response.status_code}")
        return None

    soup = BeautifulSoup(response.content, "html.parser")
    rank_body = soup.find("div", class_="md-tv-rank__body")
    if not rank_body:
        print("No se encontró el ranking en la página")
        return None

    h1 = rank_body.find("h1")
    if not h1:
        print("No se encontró la fecha en la página")
        return None
    date_iso = parse_date(h1.get_text())

    daily_record = {"date": date_iso, "laRevuelta": {"viewers": 0, "share": 0},
                    "elHormiguero": {"viewers": 0, "share": 0}}
    tbody = rank_body.find("tbody")
    if not tbody:
        return None

    for row in tbody.find_all("tr"):
        if "bar" in row.get("class", []):
            continue

        th = row.find("th")
        if not th:
            continue
        program_name = th.get_text().strip()

        program_name_lower = program_name.lower()

        if "el hormiguero" in program_name_lower:
            viewers = parse_number(row.find("td", class_="total").get_text())
            share = parse_share(row.find("td", class_="share").get_text())
            daily_record["elHormiguero"] = {"viewers": viewers, "share": share}
        elif "la revuelta" in program_name_lower:
            viewers = parse_number(row.find("td", class_="total").get_text())
            share = parse_share(row.find("td", class_="share").get_text())
            daily_record["laRevuelta"] = {"viewers": viewers, "share": share}

    return daily_record


def generate_dates(start_date):
    """Genera una lista de fechas de lunes a jueves desde start_date hasta hoy."""
    dates = []
    current_date = start_date
    while current_date <= datetime.today():
        if current_date.weekday() in [0, 1, 2, 3]:  # Lunes a Jueves
            dates.append(current_date.strftime("%Y/%m/%d"))
        current_date += timedelta(days=1)
    return dates


def get_github_data(github_token, repo_name, file_path):
    """Obtiene el archivo JSON actual de GitHub."""
    g = Github(github_token)
    repo = g.get_repo(repo_name)
    try:
        file_content = repo.get_contents(file_path)
        content = file_content.decoded_content.decode('utf-8')
        return json.loads(content), file_content.sha
    except Exception as e:
        print(f"No se encontró el archivo en GitHub o hubo un error: {e}")
        return {"dailyData": [], "weeklyData": [], "monthlyData": []}, None


def update_github_data(github_token, repo_name, file_path, new_data, sha=None):
    """Actualiza el archivo JSON en GitHub."""
    g = Github(github_token)
    repo = g.get_repo(repo_name)

    json_content = json.dumps(new_data, indent=4, ensure_ascii=False)
    commit_message = f"Actualización de datos - {datetime.now().strftime('%Y-%m-%d')}"

    try:
        if sha:
            # Actualizar archivo existente
            repo.update_file(file_path, commit_message, json_content, sha)
            print(f"✅ Archivo {file_path} actualizado en GitHub")
        else:
            # Crear nuevo archivo
            repo.create_file(file_path, commit_message, json_content)
            print(f"✅ Archivo {file_path} creado en GitHub")
        return True
    except Exception as e:
        print(f"❌ Error al actualizar GitHub: {e}")
        return False


def main():
    # Obtener datos sensibles de las variables de entorno
    github_token = os.environ.get("GITHUB_TOKEN")
    repo_name = os.environ.get("REPO_NAME")
    file_path = os.environ.get("FILE_PATH", "tv_ratings.json")
    base_url = os.environ.get("DATA_SOURCE_URL")

    if not all([github_token, repo_name, base_url]):
        print("Error: Faltan variables de entorno requeridas")
        return

    # Establecer la fecha de inicio a través de variable de entorno o usar un valor predeterminado
    start_date_str = os.environ.get("START_DATE", "2024-09-09")
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")

    # Obtener datos actuales de GitHub
    current_data, sha = get_github_data(github_token, repo_name, file_path)

    # Obtener fechas existentes para evitar duplicados
    existing_dates = [item["date"] for item in current_data.get("dailyData", [])]

    # Generar fechas para escanear
    dates = generate_dates(start_date)

    new_records_count = 0
    for date in dates:
        url = f"{base_url}{date}/"
        daily_data = scrape_daily_data(url)

        if daily_data and daily_data["date"] not in existing_dates:
            if "dailyData" not in current_data:
                current_data["dailyData"] = []

            current_data["dailyData"].append(daily_data)
            existing_dates.append(daily_data["date"])
            new_records_count += 1
            print(f"Añadido registro de {daily_data['date']}")

    # Ordenar por fecha (más reciente primero)
    if "dailyData" in current_data:
        current_data["dailyData"].sort(key=lambda x: x["date"], reverse=True)

    # Actualizar el timestamp
    current_data["lastUpdated"] = datetime.now().isoformat()

    print(f"Se encontraron {new_records_count} nuevos registros.")

    # Actualizar en GitHub solo si hay nuevos datos o el archivo no existe
    if new_records_count > 0 or sha is None:
        update_github_data(github_token, repo_name, file_path, current_data, sha)
    else:
        print("No hay nuevos datos para actualizar en GitHub.")


if __name__ == "__main__":
    main()