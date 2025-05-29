from flask import Flask, jsonify, request
import plugin_framework as pf
import trust_engine as te

app = Flask(__name__)

@app.route('/')
def index():
    return """<html><body><h3>Plugin Dashboard</h3>
<table id='tbl'></table>
<pre id='logs' style='height:200px;overflow:auto'></pre>
<script>
async function load(){
  const r=await fetch('/api/plugins');
  const data=await r.json();
  let html='<tr><th>Plugin</th><th>Status</th><th>Actions</th></tr>';
  for(const p of data){
    const b=p.enabled?`<button onclick="toggle('${p.id}',true)">Disable</button>`:`<button onclick="toggle('${p.id}',false)">Enable</button>`;
    html+=`<tr><td>${p.id}</td><td>${p.enabled?'enabled':'disabled'}</td><td>${b}<button onclick="testPlugin('${p.id}')">Test</button></td></tr>`;
  }
  document.getElementById('tbl').innerHTML=html;
}
async function toggle(id,en){
  await fetch('/api/'+(en?'disable':'enable'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plugin:id})});
  await load();
  await loadLogs();
}
async function testPlugin(id){
  await fetch('/api/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({plugin:id})});
  await loadLogs();
}
async function loadLogs(){
  const r=await fetch('/api/logs');
  const data=await r.json();
  document.getElementById('logs').textContent=JSON.stringify(data,null,2);
}
setInterval(loadLogs,2000);
load();loadLogs();
</script></body></html>"""

@app.route('/api/plugins', methods=['GET', 'POST'])
def plugins_api():
    info=pf.list_plugins()
    status=pf.plugin_status()
    return jsonify([{"id":n,"doc":info[n],"enabled":status.get(n,True)} for n in info])

@app.route('/api/enable', methods=['POST'])
def enable_api():
    name=(request.get_json() or {}).get('plugin')
    pf.enable_plugin(name, user='dashboard')
    return jsonify({'status':'enabled'})

@app.route('/api/disable', methods=['POST'])
def disable_api():
    name=(request.get_json() or {}).get('plugin')
    pf.disable_plugin(name, user='dashboard')
    return jsonify({'status':'disabled'})

@app.route('/api/test', methods=['POST'])
def test_api():
    name=(request.get_json() or {}).get('plugin')
    res=pf.test_plugin(name)
    return jsonify(res)

@app.route('/api/logs', methods=['GET', 'POST'])
def logs_api():
    return jsonify(te.list_events(limit=20))

if __name__=='__main__':
    app.run(port=5001)
