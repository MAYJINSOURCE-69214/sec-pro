'use strict';

const $ = id => document.getElementById(id);
const sourceLabels = { bundled: '随包经验', official: '维护者发布', team: '团队经验', personal: '我的经验' };
const views = {
  overview: ['总览', 'YOUR KNOWLEDGE, CONNECTED', '让每一次经验，都成为积累。', '汇集个人方法、团队经验与可复用技能，随时找到下一步的起点。'],
  library: ['经验与技能', 'A LIBRARY THAT GROWS WITH YOU', '找到方法，把经验用起来。', '浏览不同来源的经验与技能，阅读适用场景与具体操作。'],
  personal: ['我的经验', 'YOUR OWN WORKING KNOWLEDGE', '把自己的有效实践，留在这里。', '个人条目在本机私有保存，分享前由你逐条复核。'],
  models: ['分工设置', 'ONE COORDINATOR, MANY MODELS', '主模型派活，模型按能力搭配。', 'GPT、Kimi、千问与自定义角色共用并发名额，按任务与证据选择。'],
  updates: ['版本更新', 'KEEP THE TEAM IN SYNC', '团队更新，个人积累保留。', '配置维护者仓库，检查版本、空闲更新和回退。']
};
let state = null;
let view = 'overview';
let kind = 'all';
let currentItem = null;
let shareCheck = null;
let toastTimer;
let stateRequest = 0;

function node(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== undefined && value !== null) element.textContent = String(value);
  return element;
}

function items() { return Array.isArray(state?.experiences) ? state.experiences : []; }
function textValue(value) { return typeof value === 'string' ? value : ''; }
function dateLabel(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

async function api(path, body) {
  const options = { headers: { 'Content-Type': 'application/json', 'X-SEC-Pro': '1' }, cache: 'no-store' };
  if (body !== undefined) { options.method = 'POST'; options.body = JSON.stringify(body); }
  let response;
  try { response = await fetch(path, options); }
  catch (_) { throw new Error('无法连接本地服务，请确认 SEC Pro 服务仍在运行。'); }
  let result;
  try { result = await response.json(); }
  catch (_) { throw new Error('本地服务返回了无法读取的数据，请重试。'); }
  if (!response.ok) throw new Error(textValue(result.error) || `操作未完成（${response.status}），请重试。`);
  return result;
}

function showError(id, error) {
  $(id).textContent = error instanceof Error ? error.message : String(error);
  $(id).hidden = false;
}

function toast(message, error = false) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').classList.toggle('error', error);
  $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 6500);
}

async function busy(button, label, action) {
  if (button.disabled) return;
  const original = button.textContent;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  if (label) button.textContent = label;
  try { return await action(); }
  finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
    if (label) button.textContent = original;
  }
}

async function loadState(initial = false) {
  const request = ++stateRequest;
  if (initial) { $('loading').hidden = false; $('content').hidden = true; }
  try {
    const next = await api('/api/state');
    if (!Array.isArray(next.experiences)) throw new Error('经验库数据格式不完整，请重试。');
    if (request !== stateRequest) return false;
    state = next;
    $('global-error').hidden = true;
    $('content').hidden = false;
    render();
    return true;
  } catch (error) {
    if (request === stateRequest) {
      showError('global-error-text', error);
      $('global-error').hidden = false;
    }
    return false;
  } finally { if (request === stateRequest) $('loading').hidden = true; }
}

function navigate() {
  const requested = location.hash.slice(1);
  view = Object.hasOwn(views, requested) ? requested : 'overview';
  const [label, eyebrow, title, description] = views[view];
  $('page-label').textContent = label;
  $('page-eyebrow').textContent = eyebrow;
  $('page-title').textContent = title;
  $('page-description').textContent = description;
  document.querySelectorAll('[data-view]').forEach(link => {
    const active = link.dataset.view === view;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  $('overview-panel').hidden = view !== 'overview';
  $('library-panel').hidden = view === 'models' || view === 'updates';
  $('activity-panel').hidden = view !== 'overview';
  $('models-panel').hidden = view !== 'models';
  $('updates-panel').hidden = view !== 'updates';
  $('source-filter').disabled = view === 'personal';
  $('list-title').textContent = view === 'personal' ? '我的私有经验' : '探索经验库';
  $('list-description').textContent = view === 'personal' ? '保存的个人候选条目，仅在你确认后生成分享提案。' : '从已有积累中，找到适合当前任务的方法。';
  renderList();
}

function render() {
  const all = items();
  $('stat-total').textContent = all.length;
  $('stat-skills').textContent = all.filter(item => item.kind === 'skill').length;
  $('stat-personal').textContent = all.filter(item => item.source === 'personal').length;
  $('stat-team').textContent = all.filter(item => item.source === 'team').length;
  $('nav-count').textContent = all.length;
  $('sidebar-version').textContent = `SEC PRO / ${state.version || 'BETA'}`;
  $('footer-version').textContent = state.version || 'Beta';
  renderRuntime();
  renderList();
  renderActivity();
  renderModels();
  if (typeof renderIntegrations === 'function') renderIntegrations();
}

function renderRuntime() {
  const preview = state.preview === true;
  const repository = textValue(state.github?.repository).trim();
  $('runtime-badge').textContent = preview ? '本地演示预览' : '本地工作台';
  $('github-status').textContent = preview ? 'GitHub 未连接 · 演示模式' : (repository ? '仓库已配置 · 远程未验证' : 'GitHub 仓库未配置');
  $('github-status').title = !preview && repository ? repository : '';
  $('runtime-notice').textContent = preview
    ? '这是可交互的本地演示预览。同步读取演示目录，技能写入隔离预览目录；分享只生成本地待上传提案，未发送到 GitHub。'
    : '当前为本地工作台。同步会读取配置的远程目录，仓库配置不代表远程已验证；启用技能会写入真实用户技能目录。分享按钮只生成本地待上传提案，真实上传仅通过 CLI 单独确认。';
  $('sync-description').textContent = preview ? '读取本地演示经验与技能' : '读取维护者发布的经验与技能';
  $('release-description').textContent = preview
    ? '维护者发布、团队目录和个人经验采用独立来源标记。当前为隔离演示模式，未验证远程仓库发布或创建 PR。'
    : '维护者发布、团队目录和个人经验采用独立来源标记。此页面只生成本地待上传提案；真实上传及创建 PR 仅通过 CLI 单独确认，远程能力尚未验证。';
}

function addMeta(container, item) {
  container.append(node('span', `source-tag ${item.source === 'personal' || item.source === 'team' ? item.source : ''}`, sourceLabels[item.source] || '其他来源'));
  container.append(node('span', 'tag', item.kind === 'skill' ? '技能' : '经验'));
  if (item.status === 'candidate') container.append(node('span', 'tag candidate', '候选'));
  else if (item.status === 'active') container.append(node('span', 'tag', '有效'));
  if (item.version) container.append(node('span', 'meta-text', `v${String(item.version).replace(/^v/, '')}`));
}

function renderList() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const source = view === 'personal' ? 'personal' : $('source-filter').value;
  const filtered = items().filter(item => {
    const haystack = [item.title, item.summary, item.body, ...(Array.isArray(item.tags) ? item.tags : [])].join(' ').toLocaleLowerCase();
    return (kind === 'all' || item.kind === kind) && (source === 'all' || item.source === source) && (!query || haystack.includes(query));
  });
  $('result-count').textContent = `${filtered.length} 条内容`;
  $('experience-list').replaceChildren();
  $('empty-state').hidden = filtered.length > 0;
  for (const item of filtered) {
    const card = node('article', 'experience-card');
    const symbol = node('span', `item-symbol ${item.kind === 'skill' ? 'skill' : ''}`, item.kind === 'skill' ? '⌘' : '▤');
    symbol.setAttribute('aria-hidden', 'true');
    const content = node('div', 'item-content');
    const title = node('button', 'item-title-button', item.title || '未命名条目');
    title.type = 'button';
    title.addEventListener('click', () => openDetail(item));
    const summary = textValue(item.summary) || textValue(item.body).replace(/\s+/g, ' ').slice(0, 160);
    const meta = node('div', 'meta-row');
    addMeta(meta, item);
    (Array.isArray(item.tags) ? item.tags : []).slice(0, 3).forEach(tag => meta.append(node('span', 'tag', tag)));
    content.append(title, node('p', 'item-summary', summary), meta);
    card.append(symbol, content, node('span', 'item-date', dateLabel(item.updated_at)));
    $('experience-list').append(card);
  }
}

function renderActivity() {
  $('activity-list').replaceChildren();
  const activity = Array.isArray(state.activity) ? state.activity.slice(0, 5) : [];
  if (!activity.length) { $('activity-list').append(node('p', 'subtle-empty', '还没有本地操作记录。记录一条经验，或试试同步目录。')); return; }
  for (const event of activity) {
    const row = node('div', 'activity-row');
    row.append(node('span', 'activity-dot'), node('span', 'activity-message', event.message || event.action || '本地操作'));
    const time = node('time', '', dateLabel(event.time));
    if (event.time && !Number.isNaN(new Date(event.time).getTime())) time.dateTime = new Date(event.time).toISOString();
    row.append(time);
    $('activity-list').append(row);
  }
}

function renderModels() {
  $('model-grid').replaceChildren();
  const registry = state.workers?.config;
  for (const [key, role] of Object.entries(registry?.roles || {})) {
    const card = node('div', 'model-card');
    const matching = Object.entries(registry.models).filter(([,m])=>m.capabilities.includes(role.capability));
    card.append(node('span', 'eyebrow', `ROLE / ${key}`), node('h3', '', role.title), node('p', '', role.instructions));
    for (const [modelKey,m] of matching) {
      const provider = registry.providers[m.provider];
      card.append(node('div','model-name',m.model || `${m.provider} · 等待填写公司模型`), node('span','tag',`${provider.enabled?'已配置':'未启用'} · ${m.effort} · ${registry.evidence.filter(e=>e.model_key===modelKey).length} 条评测记录`));
    }
    const compare = node('button','button secondary','查看选型依据');
    compare.addEventListener('click', async()=> { try {const result=await api('/api/workers/candidates',{role:key});$('worker-evidence').textContent=JSON.stringify(result,null,2);} catch(error){toast(error.message,true);} });
    card.append(compare);
    $('model-grid').append(card);
  }
  $('parallel-info').textContent = `GPT与第三方合计最多 ${registry?.max_parallel ?? '未配置'} 个工人 · 同一文件不重复派活 · 超时不自动重试`;
}

function openDetail(item) {
  currentItem = item;
  $('detail-title').textContent = item.title || '未命名条目';
  $('detail-summary').textContent = item.summary || '';
  $('detail-body').textContent = item.body || '此条目暂无正文。';
  $('detail-meta').replaceChildren();
  addMeta($('detail-meta'), item);
  if (item.updated_at) $('detail-meta').append(node('span', 'meta-text', `更新于 ${dateLabel(item.updated_at)}`));
  $('detail-tags').replaceChildren();
  (Array.isArray(item.tags) ? item.tags : []).forEach(tag => $('detail-tags').append(node('span', 'tag', tag)));
  $('detail-error').hidden = true;
  $('detail-scope').hidden = item.kind !== 'skill';
  $('detail-action').hidden = item.kind !== 'skill' && item.source !== 'personal';
  $('detail-action').textContent = item.kind === 'skill' ? (state.preview === true ? '确认启用到隔离预览目录' : '确认写入真实用户技能目录') : '检查分享内容';
  $('detail-scope').textContent = state.preview === true
    ? '启用后会将此技能写入隔离的预览 Codex 技能目录，仅作用于本地预览；技能正文是 Markdown 指令。请先阅读并确认内容。'
    : '确认启用后会将此技能写入真实用户 Codex 技能目录，新会话刷新后可使用。技能正文是 Markdown 指令，请先阅读并确认内容。';
  $('detail-dialog').showModal();
}

async function sync(channel) {
  const button = channel === 'official' ? $('sync-official') : $('sync-team');
  await busy(button, null, async () => {
    try {
      const result = await api(`/api/sync/${channel}`, {});
      toast(`${result.message || '目录同步完成。'} 新增 ${result.added ?? 0}，更新 ${result.updated ?? 0}，未变更 ${result.unchanged ?? 0}。`);
      await loadState();
    } catch (error) { toast(error.message, true); }
  });
}

function clearShareReview() {
  shareCheck = null;
  $('share-preview').hidden = true;
  $('share-error').hidden = true;
  $('share-success').hidden = true;
  $('share-confirm').checked = false;
  $('prepare-share').disabled = true;
}

function openShare(id) {
  clearShareReview();
  const personal = items().filter(item => item.source === 'personal');
  $('share-select').replaceChildren();
  for (const item of personal) {
    const option = node('option', '', item.title || '未命名条目');
    option.value = item.id;
    $('share-select').append(option);
  }
  if (id && personal.some(item => item.id === id)) $('share-select').value = id;
  $('share-empty').hidden = personal.length > 0;
  $('share-select').disabled = personal.length === 0;
  $('review-share').disabled = personal.length === 0;
  $('share-dialog').showModal();
}

function renderShareCheck(result) {
  shareCheck = result;
  $('share-preview-title').textContent = result.title || '';
  $('share-preview-summary').textContent = result.summary || '';
  $('share-preview-summary').hidden = !result.summary;
  $('share-preview-tags').replaceChildren();
  (Array.isArray(result.tags) ? result.tags : []).forEach(tag => $('share-preview-tags').append(node('span', 'tag', tag)));
  $('share-preview-body').textContent = result.body || '';
  $('share-warnings').replaceChildren();
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  if (warnings.length) {
    $('share-warnings').append(node('p', '', '检测到需要你处理或复核的内容：'));
    for (const warning of warnings) $('share-warnings').append(node('p', '', `• ${typeof warning === 'string' ? warning : JSON.stringify(warning)}`));
  } else $('share-warnings').append(node('p', '', '未检测到明显的敏感信息。这不代表内容没有隐私风险，请继续人工复核。'));
  if (result.message) $('share-warnings').append(node('p', '', result.message));
  $('share-preview').hidden = false;
  $('share-confirm').checked = false;
  $('share-confirm').disabled = !result.can_prepare;
  $('prepare-share').disabled = true;
}

$('sync-official').addEventListener('click', () => sync('official'));
$('sync-team').addEventListener('click', () => sync('team'));
$('retry').addEventListener('click', () => busy($('retry'), '正在加载…', () => loadState(!state)));
$('search').addEventListener('input', renderList);
$('source-filter').addEventListener('change', renderList);
document.querySelectorAll('[data-kind]').forEach(button => button.addEventListener('click', () => {
  kind = button.dataset.kind;
  document.querySelectorAll('[data-kind]').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
  renderList();
}));
$('clear-filters').addEventListener('click', () => {
  $('search').value = '';
  $('source-filter').value = 'all';
  kind = 'all';
  document.querySelectorAll('[data-kind]').forEach(tab => tab.setAttribute('aria-pressed', String(tab.dataset.kind === 'all')));
  renderList();
});
$('add-experience').addEventListener('click', () => {
  $('create-form').reset();
  $('create-error').hidden = true;
  $('create-dialog').showModal();
  $('experience-title').focus();
});
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
$('create-form').addEventListener('submit', async event => {
  event.preventDefault();
  const title = $('experience-title').value.trim();
  const body = $('experience-body').value.trim();
  if (!title || !body) { showError('create-error', '请填写标题和正文，内容不能只有空格。'); return; }
  $('create-error').hidden = true;
  await busy($('save-experience'), '正在保存…', async () => {
    try {
      await api('/api/experiences', { title, body, kind: $('experience-kind').value, tags: [...new Set($('experience-tags').value.split(/[,，、\n]/).map(tag => tag.trim()).filter(Boolean))] });
      $('create-dialog').close();
      $('search').value = '';
      kind = 'all';
      document.querySelectorAll('[data-kind]').forEach(tab => tab.setAttribute('aria-pressed', String(tab.dataset.kind === 'all')));
      location.hash = 'personal';
      toast('已私有保存为个人候选条目。');
      await loadState();
    } catch (error) { showError('create-error', error); }
  });
});
$('open-share').addEventListener('click', () => openShare());
$('share-select').addEventListener('change', clearShareReview);
$('review-share').addEventListener('click', async () => {
  clearShareReview();
  await busy($('review-share'), '正在检查…', async () => {
    const id = $('share-select').value;
    $('share-select').disabled = true;
    try { renderShareCheck(await api('/api/share/preview', { id })); }
    catch (error) { showError('share-error', error); }
    finally { $('share-select').disabled = false; }
  });
});
$('share-confirm').addEventListener('change', () => { $('prepare-share').disabled = !shareCheck?.can_prepare || !$('share-confirm').checked; });
$('prepare-share').addEventListener('click', async () => {
  if (!shareCheck?.can_prepare || !$('share-confirm').checked) return;
  $('share-error').hidden = true;
  let prepared = false;
  await busy($('prepare-share'), '正在生成…', async () => {
    $('share-select').disabled = true;
    $('review-share').disabled = true;
    $('share-confirm').disabled = true;
    try {
      const result = await api('/api/share/prepare', { id: shareCheck.id, confirm: true });
      $('share-success').textContent = `${result.message || '已生成本地待上传提案。'}${result.proposal_id ? ` 提案编号：${result.proposal_id}。` : ''} 未发送到 GitHub。`;
      $('share-success').hidden = false;
      shareCheck = null;
      prepared = true;
      await loadState();
    } catch (error) { showError('share-error', error); }
    finally {
      $('share-select').disabled = false;
      $('review-share').disabled = false;
      $('share-confirm').disabled = prepared;
    }
  });
  $('prepare-share').disabled = prepared || !shareCheck?.can_prepare || !$('share-confirm').checked;
});
$('detail-action').addEventListener('click', async () => {
  if (!currentItem) return;
  if (currentItem.kind !== 'skill') {
    $('detail-dialog').close();
    openShare(currentItem.id);
    return;
  }
  $('detail-error').hidden = true;
  await busy($('detail-action'), '正在启用…', async () => {
    try {
      const result = await api('/api/activate', { id: currentItem.id, confirm: true });
      $('detail-dialog').close();
      toast(result.message || (state.preview === true ? '技能已写入隔离预览目录。' : '技能已写入真实用户技能目录，新会话刷新后可使用。'));
      await loadState();
    } catch (error) { showError('detail-error', error); }
  });
});
window.addEventListener('hashchange', navigate);
navigate();
loadState(true);
