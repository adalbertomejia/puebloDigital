(()=>{'use strict';
const chartData=document.getElementById('balance-grafica');
if(chartData){
  const draw=()=>{
    if(!window.Chart){document.querySelectorAll(".balance-chart").forEach(n=>n.hidden=true);return;}
    const data=JSON.parse(chartData.textContent), series=['#163f70','#6256a5','#18733c','#8a5a00'];
    const origin=document.getElementById('balance-origen'),monthly=document.getElementById('balance-mensual');
    // Decimal totals are produced by the server; Number is used only for chart geometry.
    if(origin)new window.Chart(origin,{type:'doughnut',data:{labels:data.origenes.map(r=>r.nombre),datasets:[{data:data.origenes.map(r=>Number(r.monto)),backgroundColor:series}]},options:{animation:false,responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}}}});
    if(monthly)new window.Chart(monthly,{type:'bar',data:{labels:data.meses.map(r=>r.nombre),datasets:[{label:'Recibido conocido · MXN',data:data.meses.map(r=>Number(r.monto)),backgroundColor:series[0]}]},options:{animation:false,responsive:true,maintainAspectRatio:false,scales:{y:{beginAtZero:true}},plugins:{legend:{display:false}}}});
  };
  if(document.readyState==='complete')draw();else window.addEventListener('load',draw,{once:true});
}
const form=document.querySelector('[data-corte-esperado]');
if(form){
  const input=form.querySelector('[name=contado]'),status=form.querySelector('[data-corte-diferencia]');
  const cents=text=>{const t=String(text).trim().replace(',','.');if(!/^\d+(\.\d{1,2})?$/.test(t))return null;const [a,b='']=t.split('.');return BigInt(a)*100n+BigInt(b.padEnd(2,'0'));};
  const money=n=>{const neg=n<0n,v=neg?-n:n;return(neg?'-':'')+'$'+String(v/100n).replace(/\B(?=(\d{3})+(?!\d))/g,',')+'.'+String(v%100n).padStart(2,'0');};
  const update=()=>{const expected=cents(form.dataset.corteEsperado),count=cents(input.value);if(expected===null||count===null){status.textContent='Escribe el conteo con hasta dos decimales.';return;}const diff=count-expected;status.textContent='Diferencia: '+money(diff)+(diff<0n?' · Faltante':diff>0n?' · Sobrante':' · Cuadrado')+'. Vista previa; se vuelve a validar al enviar.';status.classList.toggle('balance-warning',diff!==0n);};
  input.addEventListener('input',update);update();
}
})();
