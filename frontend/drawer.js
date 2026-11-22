const $=id=>document.getElementById(id);
const panel=$('tools-drawer'),shell=$('tools-shell'),trigger=$('tools-toggle'),backdrop=$('tools-backdrop');
const desktop=window.matchMedia?.('(min-width: 900px) and (hover: hover) and (pointer: fine)');
const reduced=()=>window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches??false;
const drawerState={open:false,pinned:false};
let openTimer=null,closeTimer=null,hideTimer=null,lastFocus=null,hovering=false;
const backgrounds=[...document.querySelectorAll('[data-app-background]')];
let savedBackgrounds=[];
const hoverMode=()=>desktop?.matches??false;
function clearTimers(){clearTimeout(openTimer);clearTimeout(closeTimer);clearTimeout(hideTimer);}
function lockBackground(lock){
  if(lock&&!savedBackgrounds.length){savedBackgrounds=backgrounds.map(node=>[node,node.inert]);for(const [node] of savedBackgrounds)node.inert=true;document.body.classList.add('tools-modal');}
  if(!lock&&savedBackgrounds.length){for(const [node,inert] of savedBackgrounds)node.inert=inert;savedBackgrounds=[];document.body.classList.remove('tools-modal');}
}
function setMode(){
  const modal=drawerState.open&&!hoverMode();
  backdrop.hidden=!modal;
  document.documentElement.dataset.toolsMode=hoverMode()?'desktop':'touch';
  $('tools-pin').hidden=!hoverMode();
  if(drawerState.open){shell.setAttribute('role','dialog');shell.setAttribute('aria-labelledby','tools-title');shell.setAttribute('aria-modal',String(modal));}
  lockBackground(modal);
}
function pin(value){drawerState.pinned=value;$('tools-pin').setAttribute('aria-pressed',String(value));$('tools-pin').textContent=value?'Odepnij panel':'Przypnij panel';}
const sections=[...panel.querySelectorAll('details[data-tool-section]')];
let order=sections.filter(section=>section.open);
function sectionChanged(section){
  order=order.filter(item=>item!==section&&item.open);
  if(section.open){order.push(section);while(order.length>2)order.shift().open=false;document.dispatchEvent(new CustomEvent('tools:section',{detail:section.id}));}
}
sections.forEach(section=>section.addEventListener('toggle',()=>sectionChanged(section)));
function openTools(section='tool-help',{focus=true,pinned=focus}={}){
  clearTimers();
  if(!drawerState.open){lastFocus=document.activeElement;panel.hidden=false;panel.inert=false;panel.removeAttribute('inert');panel.removeAttribute('aria-hidden');drawerState.open=true;trigger.setAttribute('aria-expanded','true');document.body.classList.add('tools-open');}
  if(pinned)pin(true);
  if(section){const target=$(section);if(target&&sections.includes(target)){target.open=true;sectionChanged(target);}}
  setMode();requestAnimationFrame(()=>{if(drawerState.open)panel.classList.add('is-open');});
  if(focus||!hoverMode())$('tools-close').focus();
}
function closeTools({restoreFocus=true}={}){
  clearTimers();if(!drawerState.open)return;
  const focused=panel.contains(document.activeElement);
  drawerState.open=false;pin(false);panel.classList.remove('is-open');panel.inert=true;panel.setAttribute('inert','');panel.setAttribute('aria-hidden','true');
  trigger.setAttribute('aria-expanded','false');document.body.classList.remove('tools-open');shell.removeAttribute('role');shell.removeAttribute('aria-modal');shell.removeAttribute('aria-labelledby');lockBackground(false);backdrop.hidden=true;
  if(restoreFocus&&(focused||!hoverMode())){const target=lastFocus?.isConnected&&!panel.contains(lastFocus)?lastFocus:trigger;target.focus();}
  hideTimer=setTimeout(()=>{if(!drawerState.open)panel.hidden=true;},reduced()?0:200);
  document.dispatchEvent(new CustomEvent('tools:closed'));
}
function enter(event){
  if(!hoverMode()||event.pointerType==='touch')return;
  hovering=true;clearTimeout(closeTimer);clearTimeout(openTimer);
  if(!drawerState.open)openTimer=setTimeout(()=>openTools(null,{focus:false,pinned:false}),120);
}
function leave(event){
  if(!hoverMode()||event.pointerType==='touch')return;
  if(panel.contains(event.relatedTarget)||trigger.contains(event.relatedTarget))return;
  hovering=false;clearTimeout(openTimer);
  if(!drawerState.pinned&&!panel.contains(document.activeElement))closeTimer=setTimeout(()=>closeTools({restoreFocus:false}),350);
}
for(const node of [trigger,panel]){node.addEventListener('pointerenter',enter);node.addEventListener('pointerleave',leave);}
trigger.addEventListener('click',()=>drawerState.open?closeTools():openTools('tool-help'));
$('tools-close').addEventListener('click',()=>closeTools());backdrop.addEventListener('click',()=>closeTools());
$('tools-pin').addEventListener('click',()=>{pin(!drawerState.pinned);if(!drawerState.pinned&&!hovering&&!panel.contains(document.activeElement))leave({pointerType:'mouse',relatedTarget:null});});
panel.addEventListener('focusin',()=>clearTimeout(closeTimer));
panel.addEventListener('focusout',()=>Promise.resolve().then(()=>{if(!hovering&&hoverMode()&&!drawerState.pinned&&!panel.contains(document.activeElement))closeTimer=setTimeout(()=>closeTools({restoreFocus:false}),350);}));
function focusable(){
  return [...shell.querySelectorAll('button,a[href],input,select,textarea,summary,[tabindex]')].filter(node=>{
    if(node.disabled||node.tabIndex<0||node.closest('[hidden],[inert]'))return false;
    for(let parent=node.parentElement;parent&&parent!==shell;parent=parent.parentElement){
      if(parent.tagName==='DETAILS'&&!parent.open){const summary=parent.querySelector('summary');if(node!==summary&&!summary?.contains(node))return false;}
    }
    return true;
  });
}
document.addEventListener('keydown',event=>{
  if(!drawerState.open||$('aed-dialog').open)return;
  if(event.key==='Escape'){event.preventDefault();closeTools();return;}
  if(event.key==='Tab'&&!hoverMode()){
    const list=focusable(),first=list[0],last=list.at(-1);if(!first)return;
    if(event.shiftKey&&(document.activeElement===first||!shell.contains(document.activeElement))){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&(document.activeElement===last||!shell.contains(document.activeElement))){event.preventDefault();first.focus();}
  }
});
function modeChanged(){clearTimers();setMode();if(drawerState.open&&!hoverMode())$('tools-close').focus();}
if(desktop?.addEventListener)desktop.addEventListener('change',modeChanged);else desktop?.addListener?.(modeChanged);
setMode();
export {openTools,closeTools,drawerState};
