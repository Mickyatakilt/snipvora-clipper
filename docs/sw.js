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
