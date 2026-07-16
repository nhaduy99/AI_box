#!/usr/bin/env python3
"""Web UI for manual 100% motor runs and the integrated AI Box sequence."""

from __future__ import annotations

import argparse
import atexit
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

from sequence_runner import MOTOR_NAMES, MotorHatController


ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
motor_controller: MotorHatController | None = None
job_lock = threading.Lock()
job: dict = {"active": False, "kind": "", "message": "Ready", "started_at": None}
cancel_event = threading.Event()
sequence_process: subprocess.Popen[str] | None = None


HTML = r"""
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Box Sequence Control</title><style>
:root{--bg:#f2f5f4;--card:#fff;--ink:#17211e;--muted:#62706b;--line:#d7dfdc;--green:#087f5b;--red:#c92a2a;--blue:#1864ab}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px Arial,sans-serif}
header{background:#fff;border-bottom:1px solid var(--line);padding:18px 24px;display:flex;justify-content:space-between;align-items:center;gap:16px}
h1,h2{margin:0}h1{font-size:22px}h2{font-size:18px}.sub,.status{color:var(--muted);margin-top:6px}
main{max-width:1050px;margin:auto;padding:24px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px}
.head{display:flex;justify-content:space-between;margin-bottom:16px}.tag{color:var(--muted)}label{display:block;color:var(--muted);font-weight:bold;font-size:13px;margin:12px 0 6px}
input,select,button{min-height:42px;border:1px solid var(--line);border-radius:7px;background:#fff;padding:8px 11px;font:inherit}input,select{width:100%}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}button{cursor:pointer;font-weight:bold}.run{width:100%;margin-top:14px;background:var(--green);border-color:var(--green);color:#fff}
.stop{background:var(--red);border-color:var(--red);color:#fff}.sequence{margin-top:18px}.times{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.sequence button{background:var(--blue);border-color:var(--blue);color:#fff;width:100%;margin-top:16px}
button:disabled{opacity:.5;cursor:not-allowed}.active{color:var(--blue);font-weight:bold}.error{color:var(--red);font-weight:bold}pre{white-space:pre-wrap;background:#f7f9f8;padding:12px;border-radius:7px;max-height:180px;overflow:auto}
@media(max-width:700px){header{align-items:flex-start;flex-direction:column}.grid,.times{grid-template-columns:1fr}main{padding:14px}}
</style></head><body><header><div><h1>AI Box Control</h1><div class="sub">All motors run at fixed 100% speed</div></div><button class="stop" onclick="stopAll()">STOP ALL</button></header>
<main><div id="system" class="status">Connecting…</div><section class="grid" id="motors"></section>
<section class="card sequence"><h2>Automated sequence</h2><div class="sub">Set each pump's forward time. The remaining color moves, measurements, and final 10-second reverse step follow the previous sequence.</div>
<div class="times"><div><label>Pump 1 time (seconds)</label><input id="p1" type="number" min="0" step="0.1" value="8"></div><div><label>Pump 2 time (seconds)</label><input id="p2" type="number" min="0" step="0.1" value="8"></div><div><label>Pump 3 time (seconds)</label><input id="p3" type="number" min="0" step="0.1" value="8"></div></div>
<button id="sequence-button" onclick="runSequence()">Run Previous Sequence</button><pre id="log">No sequence output yet.</pre></section></main>
<script>
const names={1:'Pump 1',2:'Pump 2',3:'Pump 3',4:'Linear actuator'};
async function api(path,options={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...options});const p=await r.json();if(!r.ok)throw Error(p.error||'Request failed');return p}
function cards(){document.getElementById('motors').innerHTML=Object.entries(names).map(([c,n])=>`<section class="card"><div class="head"><h2>${n}</h2><span class="tag">M${c}</span></div><div class="row"><div><label>Direction</label><select id="dir-${c}"><option value="forward">Forward</option><option value="reverse">Reverse</option></select></div><div><label>Run time (seconds)</label><input id="time-${c}" type="number" min="0.1" step="0.1" value="5"></div></div><button class="run motor-run" onclick="runMotor(${c})">Run at 100%</button></section>`).join('')}
function setBusy(active){document.querySelectorAll('.motor-run').forEach(x=>x.disabled=active);document.getElementById('sequence-button').disabled=active}
async function refresh(){try{const p=await api('/api/status');const e=document.getElementById('system');e.className=p.job.active?'status active':'status';e.textContent=(p.dry_run?'DRY RUN — ':'Hardware connected — ')+p.job.message;setBusy(p.job.active);if(p.job.output)document.getElementById('log').textContent=p.job.output}catch(e){document.getElementById('system').className='status error';document.getElementById('system').textContent=e.message}}
async function runMotor(c){try{await api(`/api/motors/${c}/run`,{method:'POST',body:JSON.stringify({direction:document.getElementById(`dir-${c}`).value,seconds:Number(document.getElementById(`time-${c}`).value)})});refresh()}catch(e){alert(e.message)}}
async function runSequence(){try{await api('/api/sequence/run',{method:'POST',body:JSON.stringify({pump_1_seconds:Number(document.getElementById('p1').value),pump_2_seconds:Number(document.getElementById('p2').value),pump_3_seconds:Number(document.getElementById('p3').value)})});refresh()}catch(e){alert(e.message)}}
async function stopAll(){try{await api('/api/stop-all',{method:'POST'});refresh()}catch(e){alert(e.message)}}
cards();refresh();setInterval(refresh,1000);
</script></body></html>
"""


def require_number(data: dict, name: str, minimum: float = 0.0) -> float:
    try:
        value = float(data[name])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"{name} must be a number") from None
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def set_job(**values) -> None:
    with job_lock:
        job.update(values)


def manual_worker(channel: int, direction: str, seconds: float) -> None:
    assert motor_controller is not None
    try:
        motor_controller.set_motor(channel, 100, direction)
        cancel_event.wait(seconds)
        message = "Stopped by user" if cancel_event.is_set() else f"{MOTOR_NAMES[channel]} finished"
    except Exception as exc:
        message = f"Manual run failed: {exc}"
    finally:
        motor_controller.stop_motor(channel)
        set_job(active=False, message=message)


def sequence_worker(command: list[str]) -> None:
    global sequence_process
    try:
        sequence_process = subprocess.Popen(
            command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True,
        )
        output, _ = sequence_process.communicate()
        code = sequence_process.returncode
        message = "Sequence completed" if code == 0 else f"Sequence stopped (exit {code})"
        set_job(active=False, message=message, output=output.strip())
    except Exception as exc:
        set_job(active=False, message=f"Sequence failed: {exc}", output=str(exc))
    finally:
        sequence_process = None


@app.get("/")
def index():
    return render_template_string(HTML)


@app.get("/api/status")
def status():
    assert motor_controller is not None
    with job_lock:
        current_job = dict(job)
    return jsonify({**motor_controller.status(), "job": current_job})


@app.post("/api/motors/<int:channel>/run")
def run_motor(channel: int):
    if channel not in MOTOR_NAMES:
        return jsonify(error="Unknown motor"), 404
    data = request.get_json(silent=True) or {}
    direction = data.get("direction")
    if direction not in {"forward", "reverse"}:
        return jsonify(error="direction must be forward or reverse"), 400
    try:
        seconds = require_number(data, "seconds", 0.1)
        with job_lock:
            if job["active"]:
                raise ValueError("Another motor or sequence job is already running")
            job.update(active=True, kind="manual", message=f"Running {MOTOR_NAMES[channel]} {direction} for {seconds:g}s", started_at=time.time())
        cancel_event.clear()
        threading.Thread(target=manual_worker, args=(channel, direction, seconds), daemon=True).start()
        return jsonify(ok=True)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/sequence/run")
def run_automated_sequence():
    data = request.get_json(silent=True) or {}
    try:
        times = [require_number(data, f"pump_{n}_seconds") for n in (1, 2, 3)]
        with job_lock:
            if job["active"]:
                raise ValueError("Another motor or sequence job is already running")
            job.update(active=True, kind="sequence", message="Automated sequence running", started_at=time.time(), output="")
        command = [
            sys.executable,
            str(ROOT / "sequence_runner.py"),
            "--pump-pwm", "100",
            "--actuator-pwm", "100",
            "--reverse-pump-order",
        ]
        for number, seconds in enumerate(times, 1):
            command += [f"--pump-{number}-seconds", str(seconds)]
        if motor_controller and motor_controller.dry_run:
            command.append("--dry-run-motors")
        threading.Thread(target=sequence_worker, args=(command,), daemon=True).start()
        return jsonify(ok=True)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@app.post("/api/stop-all")
def stop_all():
    cancel_event.set()
    process = sequence_process
    if process is not None and process.poll() is None:
        process.terminate()
    if motor_controller is not None:
        motor_controller.stop_all()
    set_job(active=False, message="All motors stopped")
    return jsonify(ok=True)


def main() -> None:
    global motor_controller
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    motor_controller = MotorHatController(dry_run=args.dry_run)
    atexit.register(motor_controller.stop_all)
    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
