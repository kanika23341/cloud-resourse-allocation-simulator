const API = "http://127.0.0.1:8000";
const $ = (id) => document.getElementById(id);
const money = (n, digits=2) => "₹" + Number(n || 0).toLocaleString("en-IN", {minimumFractionDigits: digits, maximumFractionDigits: digits});
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function api(path, options={}) {
    const response = await fetch(API + path, {headers: {"Content-Type":"application/json", ...(options.headers||{})}, ...options});
    let data;
    try { data = await response.json(); } catch { data = {detail: "Server returned an unreadable response."}; }
    if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
    return data;
}

function feedback(id, message, type="success") {
    const el=$(id); if(!el) return;
    el.className="feedback "+type; el.textContent=message;
}

function clearFeedback(id) { 
    const el=$(id); 
    if(el){
        el.className="feedback hidden";el.textContent="";
    } 
}

function setActiveNav() {
  const file = location.pathname.split("/").pop() || "index.html";
  const map={
    "index.html":"dashboard",
    "ec2.html":"ec2",
    "storage.html":"storage",
    "load-balancer.html":"database",
    "availability-zones.html":"zones"
};
  document.querySelectorAll("[data-nav]").forEach(a=>a.classList.toggle("active",a.dataset.nav===map[file]));
}

async function loadHealth(){
  const el=$("apiStatus"); 
  if(!el) return;
  try{
    await api("/health");
    el.textContent="API connected";
    el.parentElement.style.borderColor="#c7d9cb";
}
  catch{
    el.textContent="API offline";
    el.parentElement.style.borderColor="#e2c2c2";
}
}

async function loadDashboard(){
    if(!$("serverGrid"))
        return;
    try{
        const [m,s]= await Promise.all([api("/metrics"),api("/servers")]);
        $("activeVms").textContent=m.active_vms;
        $("cpuUsage").textContent=m.cpu_utilization+"%";
        $("ramUsage").textContent=m.ram_utilization+"%";
        $("hourlyCost").textContent=money(m.hourly_cost);
        $("serverGrid").innerHTML=s.servers.map(server=>{
            const cpu= server.total_cpu?server.used_cpu/server.total_cpu*100:0;
            const ram= server.total_ram?server.used_ram/server.total_ram*100:0;
            return `<article class="server-card"><div class="server-top"><h3>${esc(server.name)}</h3><span class="pill">${server.vms.length} VM(s)</span></div>
            <div class="resource"><div class="resource-head"><span>CPU</span><span>${server.used_cpu}/${server.total_cpu} vCPU</span></div><div class="progress"><span style="width:${cpu}%"></span></div></div>
            <div class="resource"><div class="resource-head"><span>RAM</span><span>${server.used_ram}/${server.total_ram} GB</span></div><div class="progress"><span style="width:${ram}%"></span></div></div>
            <div class="resource-head muted"><span>Server rate</span><span>${money(server.cost_per_hour)}/hr</span></div>
            <div class="vm-list">${server.vms.length?server.vms.map(v=>`<div class="vm-chip"><span>${esc(v.name)} · ${v.cpu} CPU / ${v.ram} GB</span><span>${esc(v.algorithm)}</span></div>`).join(""):'<div class="muted small">No workloads allocated</div>'}</div></article>`;
        }).join("");
    }catch(e){$("serverGrid").innerHTML=`<div class="feedback error">Could not load compute pool: ${esc(e.message)}. Start the FastAPI backend.</div>`;}
}

function initDashboard(){
    $("vmForm")?.addEventListener("submit",async e=>{
        e.preventDefault();clearFeedback("allocationFeedback");
        const body={name:$("vmName").value.trim(),cpu:Number($("vmCpu").value),ram:Number($("vmRam").value),duration:Number($("vmDuration").value),algorithm:$("vmAlgorithm").value};
        try{
            const r=await api("/allocate",{method:"POST",body:JSON.stringify(body)});
            feedback("allocationFeedback",`${r.message}\nServer: ${r.allocation.server}\nAlgorithm: ${r.allocation.algorithm}\nEstimated cost: ${money(r.allocation.estimated_cost)}`,"success");
            $("allocationResult").className="record-result";
            $("allocationResult").innerHTML=`<strong>${esc(r.vm.name)}</strong><p class="muted small">Placed on ${esc(r.allocation.server)} using ${esc(r.allocation.algorithm.replace("_"," "))}.</p><p>CPU: ${r.vm.cpu} · RAM: ${r.vm.ram} GB · Duration: ${r.vm.duration} hours</p><h2>${money(r.allocation.estimated_cost)}</h2><span class="status"><span class="dot"></span>Allocated</span>`;
            await loadDashboard();
        }
        catch(err){
            feedback("allocationFeedback",err.message,"error");
        }
    });
    $("resetCompute")?.addEventListener("click",async()=>{
        if(!confirm("Reset VM allocations and restore compute capacity? Storage and database records will remain.")) return;
        try{
            const r= await api("/reset",{method:"POST",body:"{}"});
            feedback("resetFeedback",r.message);
            await loadDashboard();
        }
        catch(e){
            feedback("resetFeedback",e.message,"error");
        }
    });
    $("refreshBtn")?.addEventListener("click",loadDashboard);
}

async function loadInstances(){
    if(!$("instanceGrid")) return;
    try{
        const data=await api("/ec2/instances");
        $("instanceGrid").innerHTML=data.instances.map(i=>`<article class="service-card"><span class="service-icon">▦</span><span class="pill">${esc(i.family)}</span><h3>${esc(i.name)}</h3><p>${esc(i.use_case)}</p><div class="resource-head"><span>vCPU</span><strong>${i.vcpu}</strong></div><div class="resource-head"><span>RAM</span><strong>${i.ram_gb} GB</strong></div><div class="resource-head"><span>Sample rate</span><strong>${money(i.price_per_hour,4)}/hr</strong></div></article>`).join("");
    }
    catch(e){
        $("instanceGrid").innerHTML= `<div class="feedback error">${esc(e.message)}. Start the backend first.</div>`;
    }
}

function initEc2(){ 
    $("reloadInstances")?.addEventListener("click",loadInstances); 
}

async function loadTiers(){
    if(!$("storageType"))return;
    try{const d=await api("/cloud/storage/types");
        $("storageType").innerHTML=d.tiers.map(t=>`<option value="${esc(t.key)}">${esc(t.label)} — ${money(t.cost_per_gb_month,3)}/GB-mo</option>`).join("");
        $("tierGrid").className="grid";
        $("tierGrid").innerHTML=d.tiers.map(t=>`<div class="panel"><h3>${esc(t.label)}</h3><div class="value" style="font-size:1.15rem;font-weight:800">${money(t.cost_per_gb_month,3)}<span class="muted small">/GB-mo</span></div><div class="muted small">${t.latency_ms} ms simulated latency</div><p class="muted small">${esc(t.description)}</p></div>`).join("");
    }catch(e){feedback("storageFeedback",e.message,"error");}
}

async function loadStorage(){
    if(!$("storageRows"))return;
    try{const d=await api("/cloud/storage");
        $("storageTotal").textContent=`${d.objects.length} object(s) · estimated total ${money(d.total_monthly_cost,4)}/month`;
        $("storageRows").innerHTML=d.objects.map(o=>`<tr><td>${esc(o.name)}</td><td>${esc(o.storage_type.replace("_"," "))}</td><td>${Number(o.size_gb).toLocaleString()} GB</td><td>${o.latency_ms} ms</td><td>${money(o.monthly_cost,4)}</td><td><button class="btn danger" data-delete-storage="${o.id}">Delete</button></td></tr>`).join("");
        $("storageEmpty").classList.toggle("hidden",d.objects.length!==0);
        $("storageRows").querySelectorAll("[data-delete-storage]").forEach(btn=>btn.addEventListener("click",async()=>{
            if(!confirm("Delete this storage object?"))return;
            try{
                await api(`/cloud/storage/${btn.dataset.deleteStorage}`,{method:"DELETE"});
                await loadStorage();
            }
            catch(e){
                feedback("storageFeedback",e.message,"error");
            }
        }));
    }catch(e){feedback("storageFeedback",e.message,"error");}
}

function initStorage(){
    $("storageForm")?.addEventListener("submit",async e=>{
        e.preventDefault();clearFeedback("storageFeedback");
        try{
            const d= await api("/cloud/storage",{
                method:"POST",
                body:JSON.stringify({name:$("storageName").value.trim(),
                    storage_type:$("storageType").value,
                    size_gb:Number($("storageSize").value),
                    data:$("storageData").value
                })});
            feedback("storageFeedback",`Created "${d.object.name}" · ${money(d.object.monthly_cost,4)}/month · ${d.object.latency_ms} ms simulated latency.`);
            e.target.reset();$("storageSize").value="10";await loadStorage();
        }
        catch(err){
            feedback("storageFeedback",err.message,"error");
        }
    });
    $("refreshStorage")?.addEventListener("click",loadStorage);
}

async function loadDbStatus(){
    if(!$("routingStatus"))return;
    try{
        const [s,l]=await Promise.all([api("/cloud/database"),api("/cloud/load-balancer")]);
        $("replicaCount").value=s.config.read_replicas;$("shardCount").value=s.config.shards;$("zoneCount").value=s.config.zones;$("backupMode").value=s.config.backup_mode;$("cacheEnabled").checked=!!s.config.cache_enabled;
        $("routingStatus").className="";
        $("routingStatus").innerHTML=`<div class="grid two">
        <div class="metric"><div class="label">Primary records</div><div class="value">${s.primary_records}</div></div>
        <div class="metric"><div class="label">Replica copies</div><div class="value">${s.replica_record_copies}</div></div>
        <div class="metric"><div class="label">Replication pending</div><div class="value">${s.pending_replications}</div></div>
        <div class="metric"><div class="label">Completed backups</div><div class="value">${s.completed_backups}</div></div></div>
        <div class="record-result"><p><strong>Write target:</strong> ${esc(l.write_target)}</p><p><strong>Read targets:</strong> ${esc(l.read_targets.join(", "))}</p><p><strong>Routing:</strong> ${esc(l.routing_policy)}</p><p><strong>Cache hits:</strong> ${s.cache_hits}</p></div>`;
    }
    catch(e){
        $("routingStatus").innerHTML=`<div class="feedback error">${esc(e.message)}. Start the backend.</div>`;
    }
}

async function loadReplicas(){
    if(!$("replicaGrid"))
        return;
    try{
        const d=await api("/cloud/database/replicas");
        $("replicaGrid").innerHTML=(d.replicas.length?d.replicas.map(r=>`<article class="panel"><div class="status"><span class="dot"></span>Replica configured</div><h3 style="margin-top:14px">${esc(r.name)}</h3><div class="metric" style="padding:12px 0;border:0;background:transparent"><div class="label">Record copies</div><div class="value">${r.record_copies}</div></div><div class="resource-head"><span>Highest version</span><strong>${r.max_version}</strong></div></article>`).join(""):'<div class="empty">No read replicas configured. Reads route to the primary.</div>')+`<article class="panel"><h3>Replication queue</h3><div class="metric" style="padding:12px 0;border:0;background:transparent"><div class="label">Pending jobs</div><div class="value">${d.pending}</div></div><div class="resource-head"><span>Completed jobs</span><strong>${d.completed}</strong></div><p class="muted small">The background worker applies queued updates automatically.</p></article>`;
    }
    catch(e){
        $("replicaGrid").innerHTML=`<div class="feedback error">${esc(e.message)}</div>`;
    }
}

async function loadBackups(){
    if(!$("backupRows"))return;
    try{
        const d=await api("/cloud/database/backups");
        $("backupRows").innerHTML=d.backups.map(b=>`<tr><td>${esc(b.key)}</td><td>${b.version}</td><td>${esc(b.mode)}</td><td><span class="pill">${esc(b.status)}</span></td><td>${esc(b.created_at)}</td></tr>`).join("");
        $("backupEmpty").classList.toggle("hidden",d.backups.length!==0);
    }
    catch(e){
        feedback("configFeedback",e.message,"error");
    }
}

function initDatabase(){
    $("configForm")?.addEventListener("submit",async e=>{
        e.preventDefault();
        const body={
            read_replicas:Number($("replicaCount").value),
            shards:Number($("shardCount").value),
            zones:Number($("zoneCount").value),
            backup_mode:$("backupMode").value,
            cache_enabled:$("cacheEnabled").checked
        };
        try{
            const r= await api("/cloud/database/configure",{method:"POST",body:JSON.stringify(body)});
            feedback("configFeedback",r.message);
            await refreshDatabase();
        }
        catch(err){
            feedback("configFeedback",err.message,"error");
        }
    });
    $("writeForm")?.addEventListener("submit",async e=>{
        e.preventDefault();
        let value;
        try{
            value=JSON.parse($("recordValue").value);
        }
        catch{
            feedback("writeFeedback","Value must be valid JSON.","error");
            return;
        }
        try{
            const r= await api("/cloud/database/write",{
                method:"POST",
                body:JSON.stringify({key:$("recordKey").value.trim(),value})
            });
            feedback("writeFeedback",`Write committed to primary shard ${r.shard_id}.\nBackup: ${r.backup_status}\nReplica updates queued: ${r.replicas_queued}.\n${r.message}`,"success");
            $("readKey").value=$("recordKey").value.trim();await refreshDatabase();
        }
        catch(err){
            feedback("writeFeedback",err.message,"error");
        }
    });
    $("readForm")?.addEventListener("submit",async e=>{
        e.preventDefault();
        clearFeedback("readFeedback");
        $("readResult").classList.add("hidden");
        try{
            const key=$("readKey").value.trim();
            const r=await api("/cloud/database/read/"+encodeURIComponent(key));
            feedback("readFeedback",`Source: ${r.source}\nVersion: ${r.version}\nCache hit: ${r.cache_hit}\nConsistency: ${r.consistency}`,"success");
            $("readOutput").textContent=JSON.stringify(r.value,null,2);$("readResult").classList.remove("hidden");
        }
        catch(err){
            feedback("readFeedback",err.message,"error");
        }
    });
    $("refreshDb")?.addEventListener("click",refreshDatabase);
    $("refreshReplicas")?.addEventListener("click",refreshDatabase);
    $("refreshBackups")?.addEventListener("click",refreshDatabase);
}

async function refreshDatabase(){
    await loadDbStatus();
    await loadReplicas();
    await loadBackups();
}

async function loadZones(){
    if(!$("zoneGrid"))
        return;
    try{
        const d=await api("/cloud/zones");
        $("zoneMetrics").innerHTML=`<article class="metric"><div class="label">Zones</div><div class="value">${d.zones.length}</div></article><article class="metric"><div class="label">Shards</div><div class="value">${d.shards}</div></article><article class="metric"><div class="label">Cache</div><div class="value">${d.cache_enabled?"ON":"OFF"}</div></article><article class="metric"><div class="label">Placement</div><div class="value" style="font-size:1.1rem">Round-robin</div></article>`;
        $("zoneGrid").innerHTML=d.zones.map(z=>`<article class="panel zone-card"><div class="server-top"><h3>${esc(z.name.toUpperCase())}</h3><span class="status"><span class="dot"></span>${esc(z.status)}</span></div><p class="muted small">Simulated availability zone</p><div class="section-head" style="margin:20px 0 10px"><h2 style="font-size:1rem">Shard placement</h2></div><div>${z.shards.length?z.shards.map(s=>`<span class="pill" style="display:inline-block;margin:0 5px 7px 0">${esc(s)}</span>`).join(""):'<span class="muted small">No shards assigned</span>'}</div></article>`).join("");
    }
    catch(e){
        $("zoneGrid").innerHTML=`<div class="feedback error">${esc(e.message)}. Start the backend.</div>`;
    }
}

function initZones(){ 
    $("refreshZones")?.addEventListener("click",loadZones); 
}

document.addEventListener("DOMContentLoaded",()=>{
    setActiveNav();loadHealth();initDashboard();initEc2();initStorage();initDatabase();initZones();
    loadDashboard();loadInstances();loadTiers();loadStorage();refreshDatabase();loadZones();
});
