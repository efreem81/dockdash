function csrfHeaders() { const token=document.querySelector('meta[name="csrf-token"]')?.content; return {'Content-Type':'application/json','X-CSRFToken':token}; }
function endpointId(){ return document.getElementById('projectEndpoint').value; }
function changeProjectEndpoint(id){ location.href=`/projects?endpoint_id=${id}`; }
async function discoverProjects(){
  const response=await fetch(`/api/projects/discover?endpoint_id=${endpointId()}`,{method:'POST',headers:csrfHeaders()}); const data=await response.json();
  if(data.success) location.reload(); else alert(data.error);
}
async function saveProject(id){
  const card=document.querySelector(`.project-card[data-id="${id}"]`);
  const payload={endpoint_id:endpointId(),required_mounts:card.querySelector('.required-mounts').value.split(',').map(v=>v.trim()).filter(Boolean),healthcheck_url:card.querySelector('.health-url').value,healthcheck_statuses:card.querySelector('.health-statuses').value.split(',').map(v=>v.trim()).filter(Boolean).map(Number)};
  const response=await fetch(`/api/projects/${id}`,{method:'PUT',headers:csrfHeaders(),body:JSON.stringify(payload)}); const data=await response.json(); if(!data.success) alert(data.error);
}
async function projectAction(id,action){
  const prompts={stop:'Stop this Compose project?',restart:'Restart this Compose project?',pull:'Pull project images without redeploying?',up:'Deploy the current Compose definition?',update:'Pull the current image tags, force-redeploy running services, verify health, and refresh vulnerability evidence?'};
  if(prompts[action] && !confirm(prompts[action])) return;
  const response=await fetch(`/api/projects/${id}/action`,{method:'POST',headers:csrfHeaders(),body:JSON.stringify({action,endpoint_id:endpointId()})}); const data=await response.json();
  if(!data.success){alert(data.error);return;} pollJob(data.job.id,id);
}
async function pollJob(jobId,projectId){
  const out=document.querySelector(`.project-card[data-id="${projectId}"] .job-output`); out.style.display='block'; out.textContent=`Job #${jobId} queued…`;
  const timer=setInterval(async()=>{const r=await fetch(`/api/jobs/${jobId}?endpoint_id=${encodeURIComponent(endpointId())}`);const d=await r.json();const job=d.job;out.textContent=`${job.stage||job.status}: ${job.error||job.output||''}`;if(['succeeded','failed'].includes(job.status)){clearInterval(timer);setTimeout(()=>location.reload(),1500);}},1500);
}
function showDeployModal(){document.getElementById('deployModal').style.display='flex';}
function closeDeployModal(e){if(e&&e.target.id!=='deployModal')return;document.getElementById('deployModal').style.display='none';}
function toggleDeploySource(){const git=document.getElementById('deploySource').value==='git';document.getElementById('gitFields').style.display=git?'block':'none';document.getElementById('managedFields').style.display=git?'none':'block';}
async function createDeployment(){
  const source=document.getElementById('deploySource').value; const payload={endpoint_id:endpointId(),name:document.getElementById('deployName').value};
  if(source==='git'){payload.repo_url=document.getElementById('repoUrl').value;payload.repo_ref=document.getElementById('repoRef').value;payload.compose_path=document.getElementById('composePath').value;}else{payload.compose_content=document.getElementById('composeContent').value;}
  const response=await fetch(`/api/projects/${source}`,{method:'POST',headers:csrfHeaders(),body:JSON.stringify(payload)});const data=await response.json();if(data.success)location.reload();else alert(data.error);
}
async function refreshGit(id){
  if(!confirm('Fast-forward this project from its configured Git reference?')) return;
  const response=await fetch(`/api/projects/${id}/git-update`,{method:'POST',headers:csrfHeaders(),body:JSON.stringify({endpoint_id:endpointId()})}); const data=await response.json();
  if(data.success) location.reload(); else alert(data.error);
}
async function showProjectDetails(id){const r=await fetch(`/api/projects/${id}?endpoint_id=${encodeURIComponent(endpointId())}`);const d=await r.json();document.getElementById('historyOutput').textContent=JSON.stringify(d,null,2);document.getElementById('historyModal').style.display='flex';}
function closeHistory(e){if(e&&e.target.id!=='historyModal')return;document.getElementById('historyModal').style.display='none';}
document.addEventListener('DOMContentLoaded',()=>{const focused=document.querySelector('.project-card-focused');if(focused)focused.scrollIntoView({behavior:'smooth',block:'center'});});
