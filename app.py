from flask import Flask, request, jsonify, Response
from twilio.rest import Client
from bs4 import BeautifulSoup
import requests
import threading
import time
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM_WHATSAPP = "whatsapp:+14155238886"
MENSAJE_ALERTA = "¡Hay turnos! Entrá ya a la web con el siguiente link https://www.natividad.org.ar/turnos_enfermos.php"
CLAVE_LISTADO = "eva2025"

USUARIOS_FILE = "usuarios.json"
HISTORIAL_FILE = "historial.json"

estado_sistema = {
    "pausado": False,
    "modo_simulacion": False,
    "ultimo_aviso": None,
    "estado": "inicial"
}

def cargar_usuarios():
    if os.path.exists(USUARIOS_FILE):
        with open(USUARIOS_FILE, "r") as f:
            return json.load(f)
    return []

def guardar_usuarios(usuarios):
    with open(USUARIOS_FILE, "w") as f:
        json.dump(usuarios, f, indent=2)

def guardar_historial(numero):
    registro = {
        "numero": numero,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    historial = []
    if os.path.exists(HISTORIAL_FILE):
        with open(HISTORIAL_FILE, "r") as f:
            historial = json.load(f)
    historial.append(registro)
    with open(HISTORIAL_FILE, "w") as f:
        json.dump(historial, f, indent=2)

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

@app.route("/listado", methods=["GET"])
def listado_usuarios():
    if request.args.get("clave") != CLAVE_LISTADO:
        return jsonify({"error": "No autorizado"}), 403
    return jsonify({"usuarios": cargar_usuarios()})

@app.route("/historial", methods=["GET"])
def ver_historial():
    if request.args.get("clave") != CLAVE_LISTADO:
        return jsonify({"error": "No autorizado"}), 403
    if os.path.exists(HISTORIAL_FILE):
        with open(HISTORIAL_FILE, "r") as f:
            return Response(f.read(), mimetype="application/json")
    return jsonify({"historial": []})

@app.route("/status", methods=["GET"])
def status():
    if request.args.get("clave") != CLAVE_LISTADO:
        return jsonify({"error": "No autorizado"}), 403
    return jsonify({
        "estado": estado_sistema["estado"],
        "registrados": len(cargar_usuarios()),
        "ultimo_aviso": estado_sistema["ultimo_aviso"],
        "pausado": estado_sistema["pausado"],
        "modo_simulacion": estado_sistema["modo_simulacion"]
    })

@app.route("/exportar_csv", methods=["GET"])
def exportar_csv():
    if request.args.get("clave") != CLAVE_LISTADO:
        return jsonify({"error": "No autorizado"}), 403
    usuarios = cargar_usuarios()
    csv = "Numero\n" + "\n".join(usuarios)
    return Response(csv, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=usuarios.csv"})

@app.route("/pausar", methods=["GET"])
def pausar_envios():
    if request.args.get("clave") != CLAVE_LISTADO:
        return jsonify({"error": "No autorizado"}), 403
    estado_sistema["pausado"] = request.args.get("on") == "true"
    return jsonify({"pausado": estado_sistema["pausado"]})

@app.route("/modo_simulacion", methods=["GET"])
def modo_simulacion():
    if request.args.get("clave") != CLAVE_LISTADO:
        return jsonify({"error": "No autorizado"}), 403
    estado_sistema["modo_simulacion"] = request.args.get("on") == "true"
    return jsonify({"modo_simulacion": estado_sistema["modo_simulacion"]})

def hay_turnos_disponibles():
    if estado_sistema["modo_simulacion"]:
        return True
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
        if estado_sistema["pausado"]:
            estado_sistema["estado"] = "pausado"
            time.sleep(5)
            continue

        hay_turno = hay_turnos_disponibles()
        estado_sistema["estado"] = "enviando" if hay_turno else "esperando"

        if hay_turno:
            if not ya_aviso:
                usuarios = cargar_usuarios()
                for numero in usuarios:
                    try:
                        client.messages.create(
                            body=MENSAJE_ALERTA,
                            from_=FROM_WHATSAPP,
                            to=f"whatsapp:{numero}"
                        )
                        guardar_historial(numero)
                        print(f"Mensaje enviado a {numero}")
                    except Exception as e:
                        print(f"Error enviando a {numero}: {e}")
                estado_sistema["ultimo_aviso"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ya_aviso = True
        else:
            ya_aviso = False

        time.sleep(300)

threading.Thread(target=iniciar_monitor, daemon=True).start()

@app.route("/test", methods=["GET"])
def test_mensaje():
    client = Client(ACCOUNT_SID, AUTH_TOKEN)
    numero = "+5493413164065"
    try:
        client.messages.create(
            body=MENSAJE_ALERTA,
            from_=FROM_WHATSAPP,
            to=f"whatsapp:{numero}"
        )
        guardar_historial(numero)
        return jsonify({"status": "mensaje enviado con éxito"})
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
