const assert = require('node:assert/strict');
const {setup} = require('./web_markdown_runtime.cjs');
const cases = {
  'READY-WINDOWS': w => {
    w.renderDiagnosticReadiness({client_evidence_supported:true});
    assert.equal(w.document.querySelector('#windows-snapshot-guide').hidden,false);
    assert.match(w.document.querySelector('#windows-snapshot-guide').textContent,/PowerShell/);
  },
  'READY-UNSUPPORTED': w => {
    w.renderDiagnosticReadiness({client_evidence_supported:true});
    w.renderDiagnosticReadiness({client_evidence_supported:false});
    assert.equal(w.document.querySelector('#windows-snapshot-guide').hidden,true);
    assert.match(w.document.querySelector('#collector-support-note').textContent,/尚无对应采集器/);
    assert.doesNotMatch(w.document.querySelector('#collector-support-note').textContent,/PowerShell|ps1/);
  },
  'READY-UNKNOWN-RESET': w => {
    w.renderDiagnosticReadiness({client_evidence_supported:true});
    w.renderDiagnosticReadiness(null);
    assert.equal(w.document.querySelector('#windows-snapshot-guide').hidden,true);
    assert.match(w.document.querySelector('#collector-support-note').textContent,/先确认设备系统/);
  },
};
(async()=>{for(const name of process.argv[2]?[process.argv[2]]:Object.keys(cases)){
  const dom=await setup();try{cases[name](dom.window);console.log(`${name} passed`);}finally{dom.window.close();}
}})().catch(error=>{console.error(error);process.exitCode=1;});
