"""Exercise popup site activation with Chrome API boundary doubles."""
import subprocess
import pytest


@pytest.mark.parametrize("granted", [True, False])
def test_popup_persists_only_the_opted_in_site(granted):
    script = r'''
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const elements = Object.fromEntries(['siteHost','statusDot','statusText','actionBtn','actionBtnText','infoText'].map(id => [id, {}]));
const requests = [], registered = [], injected = [];
let init;
const context = {console, URL, Set, window:{close(){}}, setTimeout(){},
 document:{getElementById:id=>elements[id], addEventListener:(event, fn)=>{init=fn;}},
 chrome:{
  tabs:{query:async()=>[{id:7,url:'https://member.example/settings'}],sendMessage:async()=>{throw Error('not injected');}},
  permissions:{request:async value=>{requests.push(value); return GRANTED;}},
  scripting:{getRegisteredContentScripts:async()=>[],registerContentScripts:async value=>registered.push(...value), executeScript:async value=>injected.push(value)},
  storage:{local:{get:async()=>({}),set:async()=>{}}},runtime:{sendMessage:async()=>({ok:true})}
 }};
vm.runInNewContext(fs.readFileSync('extension/popup/popup.js','utf8'), context);
(async()=>{
 await init(); await elements.actionBtn.onclick();
 assert.equal(requests.length,1,'Activation must request this site from the user gesture');
 assert.equal(requests[0].origins[0],'https://member.example/*');
 if (GRANTED) {
   assert.equal(registered.length,1);
   assert.equal(registered[0].matches[0],'https://member.example/*');
   assert.equal(registered[0].persistAcrossSessions,true);
   assert.equal(Array.from(registered[0].js).join(','),'navigation.js,content.js');
   assert.equal(injected.length,1);
   assert.equal(Array.from(injected[0].files).join(','),'navigation.js,content.js');
 } else {
   assert.equal(registered.length,0); assert.equal(injected.length,0);
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace("GRANTED", "true" if granted else "false")
    result = subprocess.run(["node", "-"], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
