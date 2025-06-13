from flask import Flask, request, jsonify
from twilio.rest import Client
from bs4 import BeautifulSoup
import requests
import threading
import time
import json
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

app = Flask(__name__)

# Config Twilio desde variables de entorno
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM_WHATSAPP = "whatsapp:+14155238886"
MENSAJE_ALERTA = "¡Hay turnos! Entrá ya a la web con el siguiente link https://www.natividad.org.ar/turnos_enfermos.php"

USUARIOS_FILE = "usuarios.json"

def cargar_usuarios():
    if os.path.exists(USUARIOS_FILE):
        with open(USUARIOS_FILE, "r") as f:
            return json.load(f)
    return []

def guardar_usuarios(usuarios):
    with open(USUARIOS_FILE, "w") as f:
        json.dump(usuarios, f, indent=2)

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    numero = data.get("numero")
    if not numero:
        return jsonify({"error": "Falta el número"}), 400

    usuarios = cargar_usuarios()
    if numero not in usuarios:
        usuarios.append(numero)
        guardar_usuarios(usuarios)

    return jsonify({"ok": True, "registrado": numero}), 200

def hay_turnos_disponibles():
    try:
        url = "https://www.natividad.org.ar/turnos_enfermos.php"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        texto = soup.get_text().lower()
        if "en este momento la parroquia no cuenta con cupos para enfermos" in texto:
            return False
        return (
            "turnos enfermos menores de 17 años" in texto or
            "turnos enfermos mayores de 18 años" in texto
        )
    except Exception as e:
        print(f"Error en monitoreo: {e}")
        return False

def iniciar_monitor():
    client = Client(ACCOUNT_SID, AUTH_TOKEN)
    ya_aviso = False
    while True:
        if hay_turnos_disponibles():
            if not ya_aviso:
                usuarios = cargar_usuarios()
                for numero in usuarios:
                    try:
                        client.messages.create(
                            body=MENSAJE_ALERTA,
                            from_=FROM_WHATSAPP,
                            to=f"whatsapp:{numero}"
                        )
                        print(f"Mensaje enviado a {numero}")
                    except Exception as e:
                        print(f"Error enviando a {numero}: {e}")
                ya_aviso = True
        else:
            ya_aviso = False
        time.sleep(300)

threading.Thread(target=iniciar_monitor, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

@app.route("/test", methods=["GET"])
def test_mensaje():
    client = Client(ACCOUNT_SID, AUTH_TOKEN)
    numero = "+5493413164065"  # tu número real
    try:
        client.messages.create(
            body=MENSAJE_ALERTA,
            from_=FROM_WHATSAPP,
            to=f"whatsapp:{numero}"
        )
        return jsonify({"status": "mensaje enviado con éxito"})
    except Exception as e:
        return jsonify({"error": str(e)})
