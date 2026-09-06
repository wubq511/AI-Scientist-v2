from __future__ import annotations

import json
from typing import Any


def render_blind_review_html(packet: dict[str, Any]) -> bytes:
    """Render a self-contained, offline qrels annotation page."""
    embedded = json.dumps(
        packet,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    embedded = (
        embedded.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    html = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>本地文献相关性盲评</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; color: #1f2937; background: #f3f4f6; }
    header { position: sticky; top: 0; z-index: 3; padding: 14px 20px; background: #111827; color: white; }
    header strong { margin-right: 16px; }
    main { max-width: 980px; margin: 24px auto; padding: 0 18px 80px; }
    .notice, .query { background: white; border-radius: 12px; box-shadow: 0 1px 4px #0002; }
    .notice { padding: 18px 20px; margin-bottom: 20px; line-height: 1.65; }
    .query { padding: 20px; margin: 20px 0; }
    .query h2 { margin: 0 0 8px; font-size: 18px; }
    .query-text { padding: 12px 14px; border-left: 4px solid #2563eb; background: #eff6ff; line-height: 1.55; }
    .paper { margin: 16px 0; border: 1px solid #d1d5db; border-radius: 10px; overflow: hidden; }
    .paper summary { cursor: pointer; padding: 13px 15px; background: #f9fafb; font-weight: 650; }
    .paper-body { padding: 15px; }
    .title { font-weight: 650; margin-bottom: 10px; }
    .segment { margin: 12px 0; padding: 12px; background: #f9fafb; border-radius: 8px; white-space: pre-wrap; line-height: 1.55; }
    fieldset { margin: 12px 0; border: 0; padding: 0; }
    label { margin-right: 14px; line-height: 2; }
    .segment-ratings { margin-left: 12px; padding-left: 12px; border-left: 3px solid #d1d5db; }
    .hidden { display: none; }
    .actions { position: fixed; right: 18px; bottom: 18px; display: flex; gap: 10px; }
    button { border: 0; border-radius: 9px; padding: 12px 16px; font-weight: 650; cursor: pointer; }
    #export { color: white; background: #2563eb; }
    #clear { color: #991b1b; background: #fee2e2; }
    #message { margin-top: 10px; font-weight: 650; }
    .error { color: #b91c1c; }
    .ok { color: #047857; }
    code { overflow-wrap: anywhere; }
  </style>
</head>
<body>
<header><strong>本地文献相关性盲评</strong><span id="progress">尚未开始</span></header>
<main>
  <section class="notice">
    <strong>你只需要做相关性判断。</strong><br>
    文献等级：0=无关，1=背景相关，2=能提供直接有用证据，3=核心证据。<br>
    当文献为 2 或 3 时，再给它的每个摘要片段标：0=无用，1=部分支持，2=直接支持问题。<br>
    如果所有片段都不到 2，请勾选“没有直接支持片段”。页面不会联网，进度只保存在当前浏览器。
    英文吃力时，可使用浏览器自带的“翻译成中文”；请同时保留原文用于核对术语。
    <div id="split-note"></div><div id="message"></div>
  </section>
  <div id="app"></div>
</main>
<div class="actions"><button id="clear">清空本页</button><button id="export">检查并导出 JSON</button></div>
<script id="packet" type="application/json">__PACKET__</script>
<script>
const packet = JSON.parse(document.getElementById('packet').textContent);
const storageKey = `local-ranking-qrels:${packet.input_sha256}:${packet.split}`;
let state = JSON.parse(localStorage.getItem(storageKey) || '{"paper":{},"segment":{},"issues":{}}');
const app = document.getElementById('app');
const message = document.getElementById('message');

function esc(value) {
  return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
function key(a, b) { return `${a}::${b}`; }
function persist() { localStorage.setItem(storageKey, JSON.stringify(state)); updateProgress(); }
function updateProgress() {
  const total = packet.paper_judgment_count;
  const done = Object.keys(state.paper).length;
  document.getElementById('progress').textContent = `文献判断 ${done}/${total}`;
}
function setMessage(text, ok=false) { message.textContent = text; message.className = ok ? 'ok' : 'error'; }

document.getElementById('split-note').textContent = packet.split === 'holdout'
  ? '这是 holdout 盲评。导出的文件请自行保管；finalists 冻结前不要交给运行排名的任务。'
  : '这是 development 盲评。完成并导出后可以交给当前任务校验。';

for (const query of packet.queries) {
  const section = document.createElement('section');
  section.className = 'query';
  section.innerHTML = `<h2>${esc(query.query_id)} · ${query.kind === 'broad' ? '广义问题' : '聚焦问题'}</h2>` +
    `<div class="query-text" lang="en">${esc(query.text)}</div>`;
  query.papers.forEach((paper, index) => {
    const paperKey = key(query.query_id, paper.paper_id);
    const details = document.createElement('details');
    details.className = 'paper';
    details.innerHTML = `<summary>文献 ${index + 1}：${esc(paper.title)}</summary>`;
    const body = document.createElement('div');
    body.className = 'paper-body';
    body.innerHTML = `<div class="title" lang="en">${esc(paper.title)}</div>` +
      `<fieldset><legend>文献相关性</legend>${[0,1,2,3].map(grade =>
        `<label><input type="radio" name="paper-${esc(paperKey)}" value="${grade}" ${state.paper[paperKey] === grade ? 'checked' : ''}> ${grade}</label>`
      ).join('')}</fieldset>`;
    const segments = document.createElement('div');
    segments.className = `segment-ratings ${state.paper[paperKey] >= 2 ? '' : 'hidden'}`;
    paper.segments.forEach((segment, segmentIndex) => {
      const segmentKey = key(query.query_id, segment.segment_id);
      const block = document.createElement('div');
      block.innerHTML = `<div class="segment" lang="en"><strong>片段 ${segmentIndex + 1}</strong><br>${esc(segment.text)}</div>` +
        `<fieldset><legend>片段支持度</legend>${[0,1,2].map(grade =>
          `<label><input type="radio" name="segment-${esc(segmentKey)}" value="${grade}" ${state.segment[segmentKey] === grade ? 'checked' : ''}> ${grade}</label>`
        ).join('')}</fieldset>`;
      segments.appendChild(block);
    });
    segments.innerHTML += `<label><input type="checkbox" class="issue" ${state.issues[paperKey] ? 'checked' : ''}> 没有直接支持片段</label>`;
    body.appendChild(segments);
    details.appendChild(body);
    section.appendChild(details);

    body.addEventListener('change', event => {
      if (event.target.name === `paper-${paperKey}`) {
        state.paper[paperKey] = Number(event.target.value);
        segments.classList.toggle('hidden', state.paper[paperKey] < 2);
        if (state.paper[paperKey] < 2) {
          delete state.issues[paperKey];
          for (const segment of paper.segments) delete state.segment[key(query.query_id, segment.segment_id)];
          segments.querySelectorAll('input').forEach(input => { input.checked = false; });
        }
      } else if (event.target.classList.contains('issue')) {
        state.issues[paperKey] = event.target.checked;
      } else if (event.target.name && event.target.name.startsWith('segment-')) {
        state.segment[event.target.name.slice(8)] = Number(event.target.value);
      }
      persist();
    });
  });
  app.appendChild(section);
}

document.getElementById('clear').addEventListener('click', () => {
  if (!confirm('只清空当前 split 在这个浏览器里的未导出进度？')) return;
  localStorage.removeItem(storageKey); location.reload();
});

document.getElementById('export').addEventListener('click', () => {
  const paperJudgments = [], segmentJudgments = [], issues = [], errors = [];
  for (const query of packet.queries) for (const paper of query.papers) {
    const paperKey = key(query.query_id, paper.paper_id);
    const grade = state.paper[paperKey];
    if (![0,1,2,3].includes(grade)) { errors.push(`${query.query_id} / ${paper.title} 尚未标注文献等级`); continue; }
    paperJudgments.push({query_id: query.query_id, paper_id: paper.paper_id, grade});
    if (grade < 2) continue;
    let direct = false, complete = true;
    for (const segment of paper.segments) {
      const segmentKey = key(query.query_id, segment.segment_id);
      const segmentGrade = state.segment[segmentKey];
      if (![0,1,2].includes(segmentGrade)) { complete = false; continue; }
      direct ||= segmentGrade === 2;
      segmentJudgments.push({query_id: query.query_id, segment_id: segment.segment_id, grade: segmentGrade});
    }
    if (!complete) errors.push(`${query.query_id} / ${paper.title} 的片段没有全部标完`);
    const markedIssue = Boolean(state.issues[paperKey]);
    if (direct === markedIssue) errors.push(`${query.query_id} / ${paper.title} 必须“至少一个片段=2”和“没有直接支持片段”二选一`);
    if (markedIssue) issues.push({query_id: query.query_id, paper_id: paper.paper_id, code: 'no_supporting_segment'});
  }
  if (errors.length) { setMessage(`还不能导出：${errors[0]}（共 ${errors.length} 项）`); return; }
  const byQueryPaper = (a, b) => a.query_id.localeCompare(b.query_id) || a.paper_id.localeCompare(b.paper_id);
  const byQuerySegment = (a, b) => a.query_id.localeCompare(b.query_id) || a.segment_id.localeCompare(b.segment_id);
  const qrels = {schema_version:'local-ranking-qrels-v1', split:packet.split,
    paper_judgments:paperJudgments.sort(byQueryPaper),
    segment_judgments:segmentJudgments.sort(byQuerySegment),
    issues:issues.sort(byQueryPaper)};
  const blob = new Blob([JSON.stringify(qrels, null, 2) + '\n'], {type:'application/json'});
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob);
  link.download = `qrels-${packet.split}.json`; link.click(); URL.revokeObjectURL(link.href);
  setMessage('完整性检查通过，已导出。', true);
});
updateProgress();
</script>
</body>
</html>
""".replace("__PACKET__", embedded)
    return html.encode("utf-8")
