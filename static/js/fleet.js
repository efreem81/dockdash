function csrfHeaders() { const token = document.querySelector('meta[name="csrf-token"]')?.content; return {'Content-Type':'application/json', 'X-CSRFToken':token}; }
function showEndpointForm(){ document.getElementById('endpointModal').style.display='flex'; }
function closeEndpointForm(e){ if(e && e.target.id!=='endpointModal') return; document.getElementById('endpointModal').style.display='none'; }
async function testEndpoint(id){
  const card=document.querySelector(`.endpoint-card[data-id="${id}"]`); const out=card.querySelector('.endpoint-result'); out.textContent='Testing…';
  const response=await fetch(`/api/endpoints/${id}/test`,{method:'POST',headers:csrfHeaders()}); const data=await response.json();
  out.textContent=data.success ? `${data.system.name} · Docker ${data.system.docker_version} · ${data.system.containers_running} running` : data.error;
}
async function selectEndpoint(id){ await fetch(`/api/endpoints/${id}/select`,{method:'POST',headers:csrfHeaders()}); location.href=`/dashboard?endpoint_id=${id}`; }
async function createEndpoint(){
  const payload={name:document.getElementById('endpointName').value,url:document.getElementById('endpointUrl').value,public_ip:document.getElementById('endpointPublicIp').value,kind:'agent'};
  const response=await fetch('/api/endpoints',{method:'POST',headers:csrfHeaders(),body:JSON.stringify(payload)}); const data=await response.json();
  if(data.success) location.reload(); else alert(data.error);
}
