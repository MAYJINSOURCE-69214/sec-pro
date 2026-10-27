'use strict';
const configPanel=node('div','panel release-panel');
configPanel.append(node('h2','','模型可以换，选择依据不能省。'),node('p','','当前主模型负责判断，角色与供应商均可自定义。第三方返回产物后，由 Codex 审核、应用修改并测试；不会直接执行模型给出的命令。'));
const editWorkers=node('button','button primary','配置公司 API / 自定义角色');
editWorkers.addEventListener('click',()=>{$('worker-config').value=JSON.stringify(state.workers.config,null,2);$('worker-error').hidden=true;$('worker-dialog').showModal();});
configPanel.append(editWorkers);
const evidenceView=node('pre','body-content','点击角色卡片查看候选模型、费用配置与有出处的跑分。缺少资料时只允许小规模试评，不猜测哪家更强。');evidenceView.id='worker-evidence';configPanel.append(evidenceView);
const jobsView=node('pre','body-content');jobsView.id='worker-jobs';configPanel.append(node('h3','','共用工单记录'),jobsView);
$('models-panel').append(configPanel);

function renderIntegrations(){
  const u=state.updates;
  $('update-version').textContent=`已安装：${u.installed} · 当前页面服务：${u.running}`;
  if(document.activeElement!==$('update-repository')) $('update-repository').value=u.policy.repository;
  $('update-channel').value=u.policy.channel;
  $('update-trusted').checked=u.policy.trusted;
  $('update-auto').checked=u.policy.auto_apply;
  $('update-message').textContent=u.last_check.message || '尚未检查远程版本。当前包没有发布到 GitHub。';
  $('worker-jobs').textContent=state.workers.jobs.length?JSON.stringify(state.workers.jobs,null,2):'尚无已登记工单。配置存在不代表已调用模型。';
}
$('save-workers').addEventListener('click',async()=>{
  await busy($('save-workers'),'保存中…',async()=>{
    try {const result=await api('/api/workers/config',JSON.parse($('worker-config').value));$('worker-dialog').close();toast(result.message);await loadState();}
    catch(error){showError('worker-error',error);}
  });
});
$('add-worker-profile').addEventListener('click',()=>{
  try{
    const c=JSON.parse($('worker-config').value), id=$('new-worker-id').value.trim(), title=$('new-worker-title').value.trim(), model=$('new-worker-model').value.trim();
    if(!/^[a-z][a-z0-9-]{1,63}$/.test(id)||!title||!model) throw new Error('请填写英文小写工人编号、角色名称和实际模型 ID。');
    if(c.models[id]||c.roles[id]||c.providers[id]) throw new Error('这个编号已存在，请换一个，或在高级配置中修改原条目。');
    const kind=$('new-worker-kind').value, capability=$('new-worker-capability').value;
    c.providers[id]=kind==='codex'?{kind,enabled:true}:{kind,enabled:true,base_url:$('new-worker-url').value.trim(),key_env:$('new-worker-env').value.trim()};
    c.models[id]={provider:id,model,effort:'medium',capabilities:[capability],max_output_tokens:4096,parameters:{},price:null};
    c.roles[id]={title,capability,instructions:$('new-worker-instructions').value.trim()||'只完成限定工单，返回可审核产物和未验证部分。'};
    $('worker-config').value=JSON.stringify(c,null,2);$('worker-error').hidden=true;toast('已加入草稿。点击保存本机配置才生效；尚未调用 API。');
  }catch(error){showError('worker-error',error);}
});
$('update-form').addEventListener('submit',async event=>{
  event.preventDefault();
  try {const result=await api('/api/updates/config',{repository:$('update-repository').value.trim(),channel:$('update-channel').value,trusted:$('update-trusted').checked,auto_apply:$('update-auto').checked,interval_hours:24});toast(result.message);await loadState();}
  catch(error){toast(error.message,true);}
});
for(const [button,action] of [['check-update','check'],['apply-update','apply'],['rollback-update','rollback']]){
  $(button).addEventListener('click',async()=>{
    if(action!=='check'&&!$('confirm-update').checked){toast('请先勾选确认安装或回退。',true);return;}
    await busy($(button),'处理中…',async()=>{
      try{const result=await api('/api/updates/'+action,{confirm:$('confirm-update').checked});await loadState();$('update-message').textContent=result.message;toast(result.message);}
      catch(error){$('update-message').textContent=error.message;toast(error.message,true);}
    });
  });
}
if(state) renderIntegrations();
