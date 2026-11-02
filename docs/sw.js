self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('push',e=>{
  let d={title:'Snipvora',body:'',url:'./'};
  try{d=Object.assign(d,e.data.json());}catch(x){}
  e.waitUntil(self.registration.showNotification(d.title,{body:d.body,data:{url:d.url},icon:'icon-192.png'}));
});
self.addEventListener('notificationclick',e=>{
  e.notification.close();
  e.waitUntil(clients.openWindow((e.notification.data&&e.notification.data.url)||'./'));
});
// v2: always load the dashboard page fresh (iOS Home Screen app kept showing an old copy)
self.addEventListener('fetch',e=>{if(e.request.mode==='navigate')e.respondWith(fetch(new Request(e.request.url,{cache:'reload'})).catch(()=>fetch(e.request)))});
// v3: keep the unposted Lady A clips saved on the phone so the Share button is instant (also fills when a push alert arrives, app closed)
const CC='clips-v1';
async function precache(){try{const cl=await (await fetch('clips.json',{cache:'no-store'})).json();const want=cl.filter(c=>/^Lady A/.test(c.campaign||'')).map(c=>new URL(c.video,self.registration.scope).href);
  const cache=await caches.open(CC);for(const k of await cache.keys()){if(!want.includes(k.url))await cache.delete(k)}
  for(const u of want){if(!(await cache.match(u))){const r=await fetch(u);if(r.ok)await cache.put(u,r)}}}catch(e){}}
self.addEventListener('activate',e=>e.waitUntil(precache()));
self.addEventListener('push',e=>e.waitUntil(precache()));
self.addEventListener('message',e=>{if(e.data==='precache')e.waitUntil(precache())});
