const form = document.querySelector('#config-form');
const feedback = document.querySelector('#feedback');
const preview = document.querySelector('#config-preview');
let sessionToken = null;
function value(name) { return form.elements[name]?.value || ''; }
function number(name) { const n = Number(value(name)); return Number.isFinite(n) ? n : undefined; }
function json(name, fallback) { try { return JSON.parse(value(name) || JSON.stringify(fallback)); } catch { throw new Error(`${name} must be valid JSON`); } }
function config() {
  const type = value('question.type');
  const question = {id: value('question.id'), type, text: value('question.text'), weight: number('question.weight')};
  if (type === 'choice') question.options = json('question.values', {});
  if (type === 'score') question.levels = json('question.values', []);
  return {schema_version: 1, project: {name: 'local-eval'}, jev: {base_url: value('jev.base_url'), model: value('jev.model'), timeout: number('jev.timeout'), retry: number('jev.retry')}, evaluation: {engine: 'system_one', scope: value('evaluation.scope'), threshold: number('evaluation.threshold'), strict_mode: form.elements['evaluation.strict_mode'].checked, include_reason: form.elements['evaluation.include_reason'].checked, evaluation_params: value('evaluation.evaluation_params').split(',').map(x => x.trim()).filter(Boolean), questions: [question]}, dataset: {path: value('dataset.path'), max_cases: number('dataset.max_cases')}, target: {url: value('target.url'), headers: json('target.headers', {}), body_template: value('target.body_template'), output_path: value('target.output_path'), timeout: number('target.timeout')}, component: value('evaluation.scope') === 'component' ? {trace_path: value('component.trace_path'), node_ids: value('component.node_ids').split(',').map(x => x.trim()).filter(Boolean), questions: json('component.questions', [])} : null};
}
function payload() { const result = config(); const key = value('jev.api_key'); if (key) result.credentials = {jev_api_key: key}; return result; }
async function api(path, options = {}) { const headers = {'Content-Type': 'application/json'}; if (options.method && options.method !== 'GET' && sessionToken) headers['X-Session-Token'] = sessionToken; const response = await fetch(path, {...options, headers}); const data = await response.json(); if (!response.ok) throw new Error(Object.values(data.errors || {}).join('; ') || data.error || 'Request failed'); return data; }
form.addEventListener('submit', async event => { event.preventDefault(); try { await api('/api/config', {method: 'PUT', body: JSON.stringify(payload())}); feedback.textContent = 'Configuration saved and validated.'; } catch (error) { feedback.textContent = error.message; } });
document.querySelector('#preview').addEventListener('click', () => { try { preview.hidden = false; preview.textContent = JSON.stringify(config(), null, 2); } catch (error) { feedback.textContent = error.message; } });
document.querySelector('#start').addEventListener('click', async () => { try { const run = await api('/api/runs', {method: 'POST', body: JSON.stringify(payload())}); feedback.textContent = `Run ${run.run_id} is ${run.status}.`; } catch (error) { feedback.textContent = error.message; } });
fetch('/health').then(response => response.json()).then(data => { sessionToken = data.session_token; }).catch(() => {});
