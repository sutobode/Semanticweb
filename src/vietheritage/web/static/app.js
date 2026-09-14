const app = document.getElementById('app');
const config = { canonical_base: 'http://localhost:3030/vietheritage', sparql_endpoint: 'http://localhost:3031/vietheritage/sparql', graph_store: 'http://localhost:3031/vietheritage/data' };
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeHref = (value) => /^(https?:\/\/|\/|#)/i.test(String(value || '')) ? String(value) : '#';
const api = (path) => fetch(path, { headers: { Accept: 'application/json' } }).then(async (response) => {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error?.message || `HTTP ${response.status}`);
  return data;
});

function setBusy(value) {
  app.setAttribute('aria-busy', value ? 'true' : 'false');
}
function focusHeading() {
  const heading = app.querySelector('h1');
  if (heading) {
    heading.setAttribute('tabindex', '-1');
    heading.focus({ preventScroll: true });
  }
}
function render(markup, { busy = false, focus = true } = {}) {
  setBusy(busy);
  app.innerHTML = markup;
  if (focus) requestAnimationFrame(focusHeading);
}
function loading(message = 'Đang tải dữ liệu RDF…') {
  render(`<section class="status" role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span><p>${esc(message)}</p></section>`, { busy: true, focus: false });
}
function errorView(error, retry) {
  render(`<section class="error" role="alert"><h1>Không thể tải dữ liệu</h1><p>${esc(error.message)}</p><p>Kiểm tra Fuseki và Explorer service đang chạy, sau đó thử lại.</p>${retry ? '<button id="retry" type="button">Thử lại</button>' : ''}</section>`, { focus: true });
  document.getElementById('retry')?.addEventListener('click', retry);
}
function valueOf(item) {
  return typeof item === 'string' ? item : item?.['@value'] ?? item?.['@id'] ?? '';
}
function shortUri(value) {
  const text = String(value || '');
  return text.split(/[\/#]/).pop() || text;
}
function uriLink(value, relation = '') {
  const href = safeHref(value);
  const rel = `${relation ? `${esc(relation)} ` : ''}noopener`;
  return `<a href="${esc(href)}" target="_blank" rel="${rel}" title="${esc(value)}">${esc(shortUri(value))}</a>`;
}
function badges(values, ontology = false) {
  return (values || []).map((value) => {
    const raw = valueOf(value);
    return ontology && /^https?:\/\//i.test(raw)
      ? `<a class="badge" href="${esc(safeHref(raw))}" target="_blank" rel="noopener" title="${esc(raw)}">${esc(shortUri(raw))}</a>`
      : `<span class="badge">${esc(shortUri(raw))}</span>`;
  }).join('') || '<span class="muted">Không có</span>';
}
function literalList(values, empty = 'Chưa có dữ liệu.') {
  return (values || []).map((item) => `<li>${esc(valueOf(item))}${item?.['@language'] ? ` <span class="language">@${esc(item['@language'])}</span>` : ''}</li>`).join('') || `<li class="muted">${empty}</li>`;
}
function setEndpointLinks() {
  const link = document.getElementById('sparql-link');
  if (link) link.href = safeHref(config.sparql_endpoint);
}
function searchState() {
  try { return JSON.parse(sessionStorage.getItem('vh-search-state') || '{}'); } catch (_) { return {}; }
}
function saveSearchState(data) {
  try { sessionStorage.setItem('vh-search-state', JSON.stringify(data)); } catch (_) { /* private browsing may disable storage */ }
}

async function loadConfig() {
  try {
    const data = await api('/api/config');
    Object.assign(config, data);
  } catch (_) {
    // The documented local defaults keep navigation useful if config is unavailable.
  }
  setEndpointLinks();
}

async function home() {
  loading();
  try {
    const [stats] = await Promise.all([api('/api/stats'), loadConfig()]);
    render(`<section class="hero" aria-labelledby="home-title"><p class="eyebrow">Linked Open Data Explorer</p><h1 id="home-title">Khám phá Di sản Văn hóa Việt Nam</h1><p>Trải nghiệm cùng một RDF graph qua tìm kiếm, provenance, Turtle, JSON-LD và competency questions — không cần viết SPARQL.</p><div class="actions"><a class="button" href="#/search">Bắt đầu tìm kiếm</a><a class="button secondary" href="#/queries">Xem competency questions</a></div></section><section class="grid" aria-label="Thống kê dataset"><div class="card"><div class="metric">${esc(stats.total_entities)}</div><div>Entities trong RDF graph</div></div><div class="card"><div class="metric">${esc(stats.verified_external_links)}</div><div>Verified external links</div></div><div class="card"><div class="metric">${esc(stats.classes?.length || 0)}</div><div>Ontology types có dữ liệu</div></div><div class="card"><div class="metric">${esc(stats.categories?.length || 0)}</div><div>Registry categories</div></div></section><section class="card semantic-access" aria-labelledby="access-title"><h2 id="access-title">Semantic Web access</h2><p>Dataset: <code>${esc(stats['@id'])}</code></p><p><a href="/docs">API documentation</a> · <a id="home-sparql" href="${esc(safeHref(config.sparql_endpoint))}" target="_blank" rel="noopener">Public SPARQL endpoint</a> · <a href="${esc(safeHref(stats['@id']))}" target="_blank" rel="noopener">Dataset URI</a></p></section>`, { focus: true });
    document.getElementById('home-sparql').href = safeHref(config.sparql_endpoint);
  } catch (error) { errorView(error, home); }
}

function searchFormMarkup(state) {
  return `<section aria-labelledby="search-title"><h1 id="search-title">Tìm kiếm di sản</h1><p id="search-help">Tìm theo nhãn tiếng Việt, địa điểm, loại entity, category hoặc năm. Kết quả được truy vấn từ RDF graph.</p><form id="search-form" aria-describedby="search-help"><div class="field"><label for="search-q">Từ khóa</label><input id="search-q" name="q" placeholder="Ví dụ: Huế, Hội An" value="${esc(state.q || '')}"></div><div class="field"><label for="search-type">Loại entity</label><select id="search-type" name="entity_type"><option value="">Tất cả</option>${['HeritageSite','IntangibleHeritage','NationalTreasure','Museum','HistoricalPerson'].map((type) => `<option value="${type}"${state.entity_type === type ? ' selected' : ''}>${type}</option>`).join('')}</select></div><div class="field"><label for="search-category">Registry category</label><input id="search-category" name="registry_category" placeholder="world_heritage" value="${esc(state.registry_category || '')}"></div><div class="field"><label for="search-location">Địa điểm</label><input id="search-location" name="location" placeholder="Hà Nội" value="${esc(state.location || '')}"></div><div class="field"><label for="search-year">Năm</label><input id="search-year" name="year" inputmode="numeric" pattern="[0-9]{1,4}" placeholder="1999" value="${esc(state.year || '')}"></div><button type="submit">Tìm kiếm</button></form><div id="results" class="results" aria-live="polite" aria-atomic="false"></div></section>`;
}

async function search() {
  render(searchFormMarkup(searchState()), { focus: true });
  const form = document.getElementById('search-form');
  const results = document.getElementById('results');
  const run = async (page = 1) => {
    const state = Object.fromEntries(new FormData(form).entries());
    saveSearchState(state);
    const params = new URLSearchParams(state);
    params.set('page', page);
    params.set('page_size', '25');
    results.setAttribute('aria-busy', 'true');
    results.innerHTML = '<p class="status" role="status">Đang truy vấn RDF graph…</p>';
    try {
      const data = await api(`/api/search?${params}`);
      const items = data.items || [];
      results.innerHTML = `<div class="result-summary" role="status"><strong>${esc(data.total)}</strong> kết quả · trang ${esc(data.page)}</div>${items.length ? `<div class="result-list">${items.map((item) => `<article class="card"><h2><a href="#/entity/${encodeURIComponent(shortUri(item['@id']))}">${esc(valueOf(item.label) || item['@id'])}</a></h2><p>${badges(item['@type'], true)} ${badges(item.category)}</p><p>${esc(item.location || '')} ${esc(item.year || '')}</p><p class="uri">${uriLink(item['@id'], 'canonical')}</p></article>`).join('')}</div>` : '<p class="empty" role="status">Không có kết quả. Hãy thử từ khóa ngắn hơn hoặc bỏ bớt bộ lọc.</p>'}${data.page > 1 || data.has_next ? `<nav class="pagination" aria-label="Phân trang">${data.page > 1 ? '<button id="previous" type="button">← Trang trước</button>' : ''}${data.has_next ? '<button id="next" type="button">Trang sau →</button>' : ''}</nav>` : ''}`;
      document.getElementById('previous')?.addEventListener('click', () => run(data.page - 1));
      document.getElementById('next')?.addEventListener('click', () => run(data.page + 1));
    } catch (error) {
      results.innerHTML = `<div class="error" role="alert"><p>${esc(error.message)}</p><button id="retry-search" type="button">Thử lại</button></div>`;
      document.getElementById('retry-search')?.addEventListener('click', () => run(page));
    } finally { results.setAttribute('aria-busy', 'false'); }
  };
  form.addEventListener('submit', (event) => { event.preventDefault(); run(1); });
  run(1);
}

function tripleList(triples, empty) {
  return triples?.length ? `<ul class="triple-list">${triples.map((triple) => `<li><span class="predicate">${uriLink(triple.predicate)}</span> <span class="object">${/^https?:\/\//i.test(triple.object) ? uriLink(triple.object) : esc(triple.object)}</span> <span class="graph">graph: ${esc(shortUri(triple.graph))}</span></li>`).join('')}</ul>` : `<p class="muted">${empty}</p>`;
}
function entityMarkup(data, entityId) {
  const canonical = data['@id'] || `${config.canonical_base}/resource/${entityId}`;
  const turtle = `${canonical}?format=turtle`;
  const jsonld = `${canonical}?format=jsonld`;
  return `<article aria-labelledby="entity-title"><p><a href="#/search">← Quay lại tìm kiếm</a></p><p class="eyebrow">Semantic resource</p><h1 id="entity-title">${esc(valueOf(data.label?.[0]) || entityId)}</h1><p class="uri"><a href="${esc(safeHref(canonical))}" rel="canonical">${esc(canonical)}</a> <button class="inline-button" id="copy-uri" type="button">Sao chép URI</button><span id="copy-status" class="sr-only" role="status"></span></p><div class="actions" aria-label="Linked Data representations"><a class="button" href="${esc(safeHref(canonical))}" target="_blank" rel="noopener">HTML resource</a><a class="button secondary" href="${esc(safeHref(turtle))}" type="text/turtle" target="_blank" rel="noopener">Turtle</a><a class="button secondary" href="${esc(safeHref(jsonld))}" type="application/ld+json" target="_blank" rel="noopener">JSON-LD</a><a class="button secondary" href="${esc(safeHref(config.sparql_endpoint))}" target="_blank" rel="noopener">SPARQL</a></div><section class="card" aria-labelledby="identity-title"><h2 id="identity-title">Identity and ontology</h2><dl class="facts"><dt>RDF types</dt><dd>${badges(data['@type'], true)}</dd><dt>Categories</dt><dd>${badges(data.categories)}</dd><dt>Source status</dt><dd>${esc(data.source_status || 'unknown')}</dd></dl><h3>Mô tả</h3><ul>${literalList(data.description)}</ul><h3>Aliases</h3><ul>${literalList(data.aliases, 'Không có alias.')}</ul></section><section class="card" aria-labelledby="provenance-title"><h2 id="provenance-title">Provenance and external identity</h2><h3>Source / derivation</h3><ul>${(data.sources || []).map((source) => `<li>${uriLink(source, 'dcterms:source prov:wasDerivedFrom')}</li>`).join('') || '<li class="muted">Chưa có source.</li>'}</ul><h3>Verified external identity</h3><ul>${(data.external_links || []).map((link) => `<li>${uriLink(link['@id'], 'owl:sameAs')} <span class="badge">verified</span></li>`).join('') || '<li class="muted">Không có verified external link.</li>'}</ul></section><section class="card" aria-labelledby="semantics-title"><h2 id="semantics-title">Graph semantics</h2><p>Asserted: <strong>${data.asserted_triples?.length || 0}</strong> · Novel inferred: <strong>${data.inferred_triples?.length || 0}</strong> · Closure: <strong>${data.closure_triples?.length || 0}</strong></p><details><summary>Asserted từ dữ liệu nguồn</summary>${tripleList(data.asserted_triples, 'Không có asserted triple.')}</details><details><summary>Inferred bởi reasoning (novel)</summary>${tripleList(data.inferred_triples, 'Không có novel inferred triple.')}</details><details><summary>Closure graph</summary>${tripleList(data.closure_triples, 'Không có closure triple.')}</details></section></article>`;
}
async function entity(entityId) {
  loading();
  try {
    const data = await api(`/api/entities/${encodeURIComponent(entityId)}`);
    render(entityMarkup(data, entityId), { focus: true });
    document.getElementById('copy-uri')?.addEventListener('click', async () => {
      const status = document.getElementById('copy-status');
      try { await navigator.clipboard.writeText(data['@id']); status.textContent = 'Đã sao chép canonical URI.'; } catch (_) { status.textContent = 'Không thể tự động sao chép; hãy chọn URI trên màn hình.'; }
    });
  } catch (error) { errorView(error, () => entity(entityId)); }
}

async function queries() {
  loading();
  try {
    const data = await api('/api/queries');
    render(`<section aria-labelledby="queries-title"><h1 id="queries-title">Competency Questions</h1><p>Các query SPARQL read-only đã được allowlist. Mỗi query có hash để truy nguyên contract.</p><div class="result-list">${data.items.map((query) => `<article class="card"><h2>${esc(query.id)} — ${esc(query.title)}</h2><p>${esc(query.description)}</p><p class="hash">SHA-256: <code>${esc(query.sha256)}</code></p><button type="button" data-query="${esc(query.id)}">Chạy query</button><div id="output-${esc(query.id)}" class="query-output" aria-live="polite"></div></article>`).join('')}</div></section>`, { focus: true });
    document.querySelectorAll('[data-query]').forEach((button) => button.addEventListener('click', async () => {
      const id = button.dataset.query;
      const output = document.getElementById(`output-${id}`);
      button.disabled = true;
      output.setAttribute('aria-busy', 'true');
      output.innerHTML = '<p role="status">Đang chạy SPARQL…</p>';
      try { const result = await api(`/api/queries/${encodeURIComponent(id)}/run`); output.innerHTML = `<p role="status">Query ${esc(result.id)} hoàn tất.</p><pre tabindex="0">${esc(JSON.stringify(result.results, null, 2))}</pre>`; }
      catch (error) { output.innerHTML = `<div class="error" role="alert"><p>${esc(error.message)}</p><button type="button" class="retry-query">Thử lại</button></div>`; output.querySelector('.retry-query')?.addEventListener('click', () => button.click()); }
      finally { button.disabled = false; output.setAttribute('aria-busy', 'false'); }
    }));
  } catch (error) { errorView(error, queries); }
}

function route() {
  const hash = location.hash.slice(1) || '/';
  if (hash === '/') return home();
  if (hash === '/search') return search();
  if (hash === '/queries') return queries();
  if (hash.startsWith('/entity/')) return entity(decodeURIComponent(hash.slice('/entity/'.length)));
  return home();
}
window.addEventListener('hashchange', route);
loadConfig().finally(route);
