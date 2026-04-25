#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, csv, io, sqlite3
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_PATH   = os.environ.get("DB_PATH", "datos.db")
TZ_CHILE  = ZoneInfo("America/Santiago")

def ahora_chile():
    return datetime.now(TZ_CHILE)

def fecha_str_chile():
    d = ahora_chile().date()
    return f"{d.day:02d}-{d.month:02d}-{d.year}"

# ── DB ─────────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rutas (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha          TEXT NOT NULL,
            ruta_num       INTEGER NOT NULL,
            nombre         TEXT NOT NULL,
            hora_inicio    TEXT,
            hora_fin       TEXT,
            inicio_ts      INTEGER,
            duplicados     INTEGER DEFAULT 0,
            total_escaneos INTEGER DEFAULT 0,
            codigos        TEXT DEFAULT '[]'
        )
    """)
    conn.commit()
    conn.close()

init_db()

def ruta_to_dict(r):
    d = dict(r)
    d["codigos"]        = json.loads(d["codigos"] or "[]")
    d["paquetes_unicos"] = len(d["codigos"])
    d["_inicio_ts"]     = d.pop("inicio_ts", None)
    return d

# ── HTML ────────────────────────────────────────────────────────────────────────
HTML_PATH   = os.path.join(os.path.dirname(__file__), "escaner.html")
ESCANER_HTML = open(HTML_PATH, encoding="utf-8").read() if os.path.exists(HTML_PATH) else "<h1>escaner.html no encontrado</h1>"

@app.route("/")
def index():
    return Response(ESCANER_HTML, mimetype="text/html")

@app.route("/health")
def health():
    return jsonify({"ok": True, "hora_chile": ahora_chile().strftime("%H:%M:%S"), "fecha": fecha_str_chile()})

# ── API ─────────────────────────────────────────────────────────────────────────
@app.route("/dias", methods=["GET"])
def listar_dias():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT fecha FROM rutas ORDER BY fecha DESC").fetchall()
    conn.close()
    return jsonify({"dias": [r["fecha"] for r in rows]})

@app.route("/dia", methods=["GET"])
def leer_dia():
    fecha = request.args.get("fecha", fecha_str_chile())
    conn  = get_db()
    rows  = conn.execute("SELECT * FROM rutas WHERE fecha=? ORDER BY ruta_num", (fecha,)).fetchall()
    conn.close()
    return jsonify({"fecha": fecha, "choferes": [ruta_to_dict(r) for r in rows]})

@app.route("/ruta", methods=["POST"])
def guardar_ruta():
    data = request.get_json()
    conn = get_db()
    conn.execute("""
        INSERT INTO rutas (fecha, ruta_num, nombre, hora_inicio, hora_fin, inicio_ts, duplicados, total_escaneos, codigos)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        data.get("fecha", fecha_str_chile()),
        data["ruta_num"], data["nombre"],
        data.get("hora_inicio", ""), data.get("hora_fin", ""),
        data.get("_inicio_ts"), data.get("duplicados", 0),
        data.get("total_escaneos", 0),
        json.dumps(data.get("codigos", []))
    ))
    conn.commit(); conn.close()
    return jsonify({"ok": True})

@app.route("/ruta", methods=["PUT"])
def actualizar_ruta():
    payload  = request.get_json()
    fecha    = payload.get("fecha", fecha_str_chile())
    ruta_num = payload["ruta_num"]
    ruta     = payload["ruta"]
    conn = get_db()
    conn.execute("""
        UPDATE rutas SET nombre=?, hora_inicio=?, hora_fin=?, inicio_ts=?,
        duplicados=?, total_escaneos=?, codigos=?
        WHERE fecha=? AND ruta_num=?
    """, (
        ruta["nombre"], ruta.get("hora_inicio",""), ruta.get("hora_fin",""),
        ruta.get("_inicio_ts"), ruta.get("duplicados", 0),
        ruta.get("total_escaneos", 0), json.dumps(ruta.get("codigos", [])),
        fecha, ruta_num
    ))
    conn.commit(); conn.close()
    return jsonify({"ok": True})

@app.route("/paquete", methods=["DELETE"])
def eliminar_paquete():
    data     = request.get_json()
    fecha    = data.get("fecha", fecha_str_chile())
    ruta_num = data["ruta_num"]
    codigo   = data["codigo"]
    conn = get_db()
    row  = conn.execute("SELECT codigos, total_escaneos FROM rutas WHERE fecha=? AND ruta_num=?", (fecha, ruta_num)).fetchone()
    if row:
        codigos = json.loads(row["codigos"] or "[]")
        if codigo in codigos:
            codigos.remove(codigo)
        conn.execute("""
            UPDATE rutas SET codigos=?, total_escaneos=? WHERE fecha=? AND ruta_num=?
        """, (json.dumps(codigos), max(0, row["total_escaneos"] - 1), fecha, ruta_num))
        conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/reporte", methods=["GET"])
def reporte_semanal():
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")
    if not desde_str or not hasta_str:
        return jsonify({"error": "Falta desde o hasta"}), 400

    desde_date = datetime.strptime(desde_str, "%d-%m-%Y").date()
    hasta_date = datetime.strptime(hasta_str, "%d-%m-%Y").date()

    fechas = []
    current = desde_date
    while current <= hasta_date:
        fechas.append(current.strftime("%d-%m-%Y"))
        current += timedelta(days=1)

    conn = get_db()
    ph   = ",".join("?" * len(fechas))
    rows = conn.execute(f"SELECT * FROM rutas WHERE fecha IN ({ph}) ORDER BY fecha, ruta_num", fechas).fetchall()
    conn.close()

    rutas            = [ruta_to_dict(r) for r in rows]
    resumen_choferes = {}
    dias_con_datos   = sorted(set(r["fecha"] for r in rutas))

    for r in rutas:
        n = r["nombre"]; f = r["fecha"]
        if n not in resumen_choferes:
            resumen_choferes[n] = {"dias": {}, "total_paq": 0, "total_dups": 0, "total_esc": 0}
        if f not in resumen_choferes[n]["dias"]:
            resumen_choferes[n]["dias"][f] = {"paq": 0, "dups": 0, "esc": 0}
        resumen_choferes[n]["dias"][f]["paq"]  += r["paquetes_unicos"]
        resumen_choferes[n]["dias"][f]["dups"] += r["duplicados"]
        resumen_choferes[n]["dias"][f]["esc"]  += r["total_escaneos"]
        resumen_choferes[n]["total_paq"]  += r["paquetes_unicos"]
        resumen_choferes[n]["total_dups"] += r["duplicados"]
        resumen_choferes[n]["total_esc"]  += r["total_escaneos"]

    output = io.StringIO()
    output.write('\ufeff')
    w = csv.writer(output, delimiter=';')

    w.writerow([f"REPORTE SEMANAL — {desde_str} al {hasta_str}"])
    w.writerow([])

    if not dias_con_datos:
        w.writerow(["Sin datos para el rango seleccionado."])
    else:
        total_paq  = sum(v["total_paq"]  for v in resumen_choferes.values())
        total_dups = sum(v["total_dups"] for v in resumen_choferes.values())
        w.writerow(["RESUMEN GENERAL"])
        w.writerow(["Días con actividad",       len(dias_con_datos)])
        w.writerow(["Total choferes distintos", len(resumen_choferes)])
        w.writerow(["Total paquetes únicos",    total_paq])
        w.writerow(["Total duplicados",         total_dups])
        w.writerow([])
        w.writerow(["PAQUETES POR CHOFER POR DÍA"])
        w.writerow(["Chofer"] + dias_con_datos + ["TOTAL"])
        for nombre, info in sorted(resumen_choferes.items()):
            w.writerow([nombre] + [info["dias"].get(f,{}).get("paq",0) for f in dias_con_datos] + [info["total_paq"]])
        w.writerow(["TOTAL"] + [sum(v["dias"].get(f,{}).get("paq",0) for v in resumen_choferes.values()) for f in dias_con_datos] + [total_paq])
        w.writerow([])
        w.writerow(["DUPLICADOS POR CHOFER"])
        w.writerow(["Chofer","Total duplicados","Total paquetes","% duplicados"])
        for nombre, info in sorted(resumen_choferes.items()):
            pct = round(info["total_dups"]/info["total_esc"]*100,1) if info["total_esc"]>0 else 0
            w.writerow([nombre, info["total_dups"], info["total_paq"], f"{pct}%"])
        w.writerow([])
        w.writerow(["DETALLE DIARIO"])
        for f in dias_con_datos:
            w.writerow([f"Fecha: {f}"])
            w.writerow(["Chofer","Ruta #","Hora inicio","Hora fin","Paquetes únicos","Duplicados","Total escaneos"])
            for r in rutas:
                if r["fecha"] == f:
                    w.writerow([r["nombre"],r["ruta_num"],r.get("hora_inicio",""),r.get("hora_fin",""),r["paquetes_unicos"],r["duplicados"],r["total_escaneos"]])
            w.writerow([])

    nombre_archivo = f"reporte_{desde_str}_al_{hasta_str}.csv"
    return Response(
        output.getvalue().encode("utf-8"),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'}
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port)
