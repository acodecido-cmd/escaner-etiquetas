#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, csv, io
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rutas (
            id             SERIAL PRIMARY KEY,
            fecha          TEXT NOT NULL,
            ruta_num       INTEGER NOT NULL,
            nombre         TEXT NOT NULL,
            hora_inicio    TEXT,
            hora_fin       TEXT,
            inicio_ts      BIGINT,
            duplicados     INTEGER DEFAULT 0,
            total_escaneos INTEGER DEFAULT 0,
            codigos        TEXT DEFAULT '[]'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dias_cerrados (
            fecha      TEXT PRIMARY KEY,
            cerrado_at TEXT NOT NULL,
            resumen    TEXT
        )
    """)
    conn.commit(); cur.close(); conn.close()

init_db()

def ruta_to_dict(r):
    d = dict(r)
    d["codigos"] = json.loads(d["codigos"] or "[]")
    d["paquetes_unicos"] = len(d["codigos"])
    d["_inicio_ts"] = d.pop("inicio_ts", None)
    return d

def generar_csv_dia(fecha, rutas):
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow([f"REPORTE DEL DÍA — {fecha}"])
    writer.writerow([])

    total_paq  = sum(r["paquetes_unicos"] for r in rutas)
    total_dups = sum(r["duplicados"] for r in rutas)
    total_esc  = sum(r["total_escaneos"] for r in rutas)

    writer.writerow(["RESUMEN GENERAL"])
    writer.writerow(["Fecha", fecha])
    writer.writerow(["Total choferes", len(rutas)])
    writer.writerow(["Total paquetes únicos", total_paq])
    writer.writerow(["Total duplicados detectados", total_dups])
    writer.writerow(["Total escaneos realizados", total_esc])
    writer.writerow([])

    writer.writerow(["DETALLE POR CHOFER"])
    writer.writerow(["Chofer", "Ruta #", "Hora inicio", "Hora fin", "Paquetes únicos", "Duplicados", "Total escaneos"])
    for r in rutas:
        writer.writerow([r["nombre"], r["ruta_num"], r.get("hora_inicio",""), r.get("hora_fin",""), r["paquetes_unicos"], r["duplicados"], r["total_escaneos"]])

    return output.getvalue()

def generar_csv_semanal(desde_str, hasta_str):
    desde_date = datetime.strptime(desde_str, "%d-%m-%Y").date()
    hasta_date = datetime.strptime(hasta_str, "%d-%m-%Y").date()
    fechas = []
    current = desde_date
    while current <= hasta_date:
        fechas.append(current.strftime("%d-%m-%Y"))
        current += timedelta(days=1)

    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM rutas WHERE fecha = ANY(%s) ORDER BY fecha, ruta_num", (fechas,))
    rutas = [ruta_to_dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()

    resumen_choferes = {}
    dias_con_datos   = sorted(set(r["fecha"] for r in rutas))

    for r in rutas:
        n = r["nombre"]; f = r["fecha"]
        if n not in resumen_choferes:
            resumen_choferes[n] = {"dias":{}, "total_paq":0, "total_dups":0, "total_esc":0}
        if f not in resumen_choferes[n]["dias"]:
            resumen_choferes[n]["dias"][f] = {"paq":0,"dups":0,"esc":0}
        resumen_choferes[n]["dias"][f]["paq"] += r["paquetes_unicos"]
        resumen_choferes[n]["dias"][f]["dups"] += r["duplicados"]
        resumen_choferes[n]["dias"][f]["esc"]  += r["total_escaneos"]
        resumen_choferes[n]["total_paq"]  += r["paquetes_unicos"]
        resumen_choferes[n]["total_dups"] += r["duplicados"]
        resumen_choferes[n]["total_esc"]  += r["total_escaneos"]

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow([f"REPORTE SEMANAL — {desde_str} al {hasta_str}"])
    writer.writerow([])

    if not dias_con_datos:
        writer.writerow(["Sin datos para el rango seleccionado."])
    else:
        total_paq  = sum(v["total_paq"]  for v in resumen_choferes.values())
        total_dups = sum(v["total_dups"] for v in resumen_choferes.values())
        writer.writerow(["RESUMEN GENERAL"])
        writer.writerow(["Días con actividad", len(dias_con_datos)])
        writer.writerow(["Total choferes distintos", len(resumen_choferes)])
        writer.writerow(["Total paquetes únicos", total_paq])
        writer.writerow(["Total duplicados", total_dups])
        writer.writerow([])
        writer.writerow(["PAQUETES POR CHOFER POR DÍA"])
        writer.writerow(["Chofer"] + dias_con_datos + ["TOTAL"])
        for nombre, info in sorted(resumen_choferes.items()):
            writer.writerow([nombre]+[info["dias"].get(f,{}).get("paq",0) for f in dias_con_datos]+[info["total_paq"]])
        writer.writerow(["TOTAL"]+[sum(v["dias"].get(f,{}).get("paq",0) for v in resumen_choferes.values()) for f in dias_con_datos]+[total_paq])
        writer.writerow([])
        writer.writerow(["DUPLICADOS POR CHOFER"])
        writer.writerow(["Chofer","Total duplicados","Total paquetes","% duplicados"])
        for nombre, info in sorted(resumen_choferes.items()):
            pct = round(info["total_dups"]/info["total_esc"]*100,1) if info["total_esc"]>0 else 0
            writer.writerow([nombre, info["total_dups"], info["total_paq"], f"{pct}%"])
        writer.writerow([])
        writer.writerow(["DETALLE DIARIO"])
        for f in dias_con_datos:
            writer.writerow([f"Fecha: {f}"])
            writer.writerow(["Chofer","Ruta #","Hora inicio","Hora fin","Paquetes únicos","Duplicados","Total escaneos"])
            for r in rutas:
                if r["fecha"]==f:
                    writer.writerow([r["nombre"],r["ruta_num"],r.get("hora_inicio",""),r.get("hora_fin",""),r["paquetes_unicos"],r["duplicados"],r["total_escaneos"]])
            writer.writerow([])

    return output.getvalue()

# ── RUTAS API ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    with open("escaner.html", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")

@app.route("/dias", methods=["GET"])
def listar_dias():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT DISTINCT fecha FROM rutas ORDER BY fecha DESC")
    dias = [r["fecha"] for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({"dias": dias})

@app.route("/dia", methods=["GET"])
def leer_dia():
    fecha = request.args.get("fecha", date.today().strftime("%d-%m-%Y"))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM rutas WHERE fecha=%s ORDER BY ruta_num", (fecha,))
    rutas = [ruta_to_dict(r) for r in cur.fetchall()]
    # Verificar si el día está cerrado
    cur.execute("SELECT cerrado_at FROM dias_cerrados WHERE fecha=%s", (fecha,))
    cerrado = cur.fetchone()
    cur.close(); conn.close()
    return jsonify({"fecha": fecha, "choferes": rutas, "cerrado": cerrado is not None, "cerrado_at": cerrado["cerrado_at"] if cerrado else None})

@app.route("/ruta", methods=["POST"])
def guardar_ruta():
    data = request.get_json()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO rutas (fecha, ruta_num, nombre, hora_inicio, hora_fin, inicio_ts, duplicados, total_escaneos, codigos)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        data.get("fecha", date.today().strftime("%d-%m-%Y")),
        data["ruta_num"], data["nombre"],
        data.get("hora_inicio",""), data.get("hora_fin",""),
        data.get("_inicio_ts"), data.get("duplicados",0),
        data.get("total_escaneos",0), json.dumps(data.get("codigos",[]))
    ))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/ruta", methods=["PUT"])
def actualizar_ruta():
    payload = request.get_json()
    fecha    = payload.get("fecha", date.today().strftime("%d-%m-%Y"))
    ruta_num = payload["ruta_num"]
    ruta     = payload["ruta"]
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        UPDATE rutas SET nombre=%s, hora_inicio=%s, hora_fin=%s, inicio_ts=%s,
        duplicados=%s, total_escaneos=%s, codigos=%s
        WHERE fecha=%s AND ruta_num=%s
    """, (
        ruta["nombre"], ruta.get("hora_inicio",""), ruta.get("hora_fin",""),
        ruta.get("_inicio_ts"), ruta.get("duplicados",0),
        ruta.get("total_escaneos",0), json.dumps(ruta.get("codigos",[])),
        fecha, ruta_num
    ))
    conn.commit(); cur.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/paquete", methods=["DELETE"])
def eliminar_paquete():
    data     = request.get_json()
    fecha    = data.get("fecha", date.today().strftime("%d-%m-%Y"))
    ruta_num = data["ruta_num"]
    codigo   = data["codigo"]
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT codigos, total_escaneos FROM rutas WHERE fecha=%s AND ruta_num=%s", (fecha, ruta_num))
    row = cur.fetchone()
    if row:
        codigos = json.loads(row["codigos"] or "[]")
        if codigo in codigos:
            codigos.remove(codigo)
        cur.execute("UPDATE rutas SET codigos=%s, total_escaneos=%s WHERE fecha=%s AND ruta_num=%s",
            (json.dumps(codigos), max(0, row["total_escaneos"]-1), fecha, ruta_num))
        conn.commit()
    cur.close(); conn.close()
    return jsonify({"ok": True})

@app.route("/cerrar-dia", methods=["POST"])
def cerrar_dia():
    data  = request.get_json()
    fecha = data.get("fecha", date.today().strftime("%d-%m-%Y"))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM rutas WHERE fecha=%s ORDER BY ruta_num", (fecha,))
    rutas = [ruta_to_dict(r) for r in cur.fetchall()]
    if not rutas:
        cur.close(); conn.close()
        return jsonify({"error": "No hay rutas para cerrar"}), 400

    # Guardar día como cerrado
    cerrado_at = datetime.now().strftime("%d-%m-%Y %H:%M")
    resumen = json.dumps({
        "choferes": len(rutas),
        "paquetes": sum(r["paquetes_unicos"] for r in rutas),
        "duplicados": sum(r["duplicados"] for r in rutas)
    })
    cur.execute("""
        INSERT INTO dias_cerrados (fecha, cerrado_at, resumen)
        VALUES (%s, %s, %s)
        ON CONFLICT (fecha) DO UPDATE SET cerrado_at=%s, resumen=%s
    """, (fecha, cerrado_at, resumen, cerrado_at, resumen))
    conn.commit(); cur.close(); conn.close()

    return jsonify({"ok": True, "cerrado_at": cerrado_at, "rutas": rutas})

@app.route("/reporte-dia", methods=["GET"])
def reporte_dia():
    fecha = request.args.get("fecha", date.today().strftime("%d-%m-%Y"))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM rutas WHERE fecha=%s ORDER BY ruta_num", (fecha,))
    rutas = [ruta_to_dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    if not rutas:
        return jsonify({"error": "Sin datos"}), 404
    csv_content = generar_csv_dia(fecha, rutas)
    nombre = f"reporte_{fecha}.csv"
    return Response(
        csv_content.encode("utf-8"),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'}
    )

@app.route("/reporte", methods=["GET"])
def reporte_semanal():
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")
    if not desde_str or not hasta_str:
        return jsonify({"error": "Falta desde o hasta"}), 400
    csv_content = generar_csv_semanal(desde_str, hasta_str)
    nombre = f"reporte_{desde_str}_al_{hasta_str}.csv"
    return Response(
        csv_content.encode("utf-8"),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'}
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port)
