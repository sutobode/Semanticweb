const app = document.getElementById('app');
const config = { canonical_base: 'http://localhost:3030/vietheritage', sparql_endpoint: 'http://localhost:3031/vietheritage/sparql', graph_store: 'http://localhost:3031/vietheritage/data' };
const entityTypeLabels = {
  HeritageSite: 'Di tích / địa điểm di sản', HeritageComplex: 'Quần thể di sản', IntangibleHeritage: 'Di sản văn hóa phi vật thể',
  NationalTreasure: 'Bảo vật quốc gia', DocumentaryHeritage: 'Di sản tư liệu', CulturalObject: 'Hiện vật / đối tượng văn hóa',
  Museum: 'Bảo tàng', HistoricalPerson: 'Nhân vật lịch sử', HistoricalEvent: 'Sự kiện lịch sử', HistoricalPeriod: 'Giai đoạn lịch sử',
  AdministrativeArea: 'Đơn vị hành chính', Organization: 'Tổ chức', Artisan: 'Nghệ nhân', ArchitecturalStyle: 'Phong cách kiến trúc'
};
const entityTypeGroups = [
  ['Di sản và địa điểm', ['HeritageSite', 'HeritageComplex', 'IntangibleHeritage', 'NationalTreasure', 'DocumentaryHeritage', 'CulturalObject', 'Museum']],
  ['Con người và bối cảnh', ['HistoricalPerson', 'HistoricalEvent', 'HistoricalPeriod', 'AdministrativeArea', 'Organization', 'Artisan']],
  ['Thuộc tính mô tả', ['ArchitecturalStyle']]
];
const semanticTypeLabels = {
  UNESCOHeritageSite: 'Di sản UNESCO', HistoricalSite: 'Di tích lịch sử', ReligiousSite: 'Di tích tôn giáo / tín ngưỡng',
  ArchaeologicalSite: 'Di tích khảo cổ', ArchitecturalSite: 'Di tích kiến trúc',
  HeritageSiteWithHistoricalBuilder: 'Di tích có người xây dựng lịch sử'
};
const relationLabels = {
  associatedWithPerson: 'Có liên quan đến nhân vật lịch sử', builtBy: 'Được xây dựng bởi nhân vật lịch sử',
  associatedWithEvent: 'Có liên quan đến sự kiện lịch sử', belongsToPeriod: 'Thuộc giai đoạn lịch sử',
  partOf: 'Thuộc quần thể di sản', sameAs: 'Có liên kết ngoài đã xác minh'
};
const categoryLabels = {
  world_heritage: 'Di sản thế giới', national_special_monuments: 'Di tích quốc gia đặc biệt', national_monuments: 'Di tích quốc gia',
  intangible_representative: 'Di sản phi vật thể đại diện của nhân loại', intangible_urgent: 'Di sản phi vật thể cần bảo vệ khẩn cấp',
  national_intangible: 'Di sản văn hóa phi vật thể quốc gia', artisans: 'Nghệ nhân', national_treasures: 'Bảo vật quốc gia',
  artifacts_antiquities: 'Di vật, cổ vật', national_artisans: 'Nghệ nhân Nhân dân', meritorious_artisans: 'Nghệ nhân Ưu tú',
  national_museums: 'Bảo tàng quốc gia', ministry_museums: 'Bảo tàng thuộc bộ, ngành và tổ chức trung ương',
  central_organization_museums: 'Bảo tàng thuộc đơn vị trực thuộc trung ương', provincial_museums: 'Bảo tàng cấp tỉnh',
  private_museums: 'Bảo tàng ngoài công lập', documentary_heritage: 'Di sản tư liệu'
};
const hiddenTypeNames = new Set(['Resource', 'Thing', 'NamedIndividual']);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeHref = (value) => /^(https?:\/\/|\/|#)/i.test(String(value || '')) ? String(value) : '#';
const api = (path, options = {}) => fetch(path, { ...options, headers: { Accept: 'application/json', ...(options.headers || {}) } }).then(async (response) => {
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
    heading.classList.add('route-heading');
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
function entityTypeBadges(values) {
  const visible = (values || []).map(valueOf).filter((raw) => {
    const name = shortUri(raw);
    return raw && !hiddenTypeNames.has(name) && !/^b\d+$/i.test(name) && !raw.startsWith('_:');
  });
  return visible.map((raw) => {
    const name = shortUri(raw);
    const label = entityTypeLabels[name] || semanticTypeLabels[name] || name;
    return /^https?:\/\//i.test(raw)
      ? `<a class="badge" href="${esc(safeHref(raw))}" target="_blank" rel="noopener" title="${esc(raw)}">${esc(label)}</a>`
      : `<span class="badge" title="${esc(raw)}">${esc(label)}</span>`;
  }).join('');
}
function categoryLabel(value) {
  const name = shortUri(valueOf(value));
  return categoryLabels[name] || name;
}
function categoryBadges(values) {
  return (values || []).map((value) => `<span class="badge" title="${esc(valueOf(value))}">${esc(categoryLabel(value))}</span>`).join('');
}
function literalList(values, empty = 'Chưa có dữ liệu.') {
  return (values || []).map((item) => `<li>${esc(valueOf(item))}${item?.['@language'] ? ` <span class="language">@${esc(item['@language'])}</span>` : ''}</li>`).join('') || `<li class="muted">${empty}</li>`;
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
}

async function home() {
  loading();
  try {
    const [stats] = await Promise.all([api('/api/stats'), loadConfig()]);
    render(`<section class="hero" aria-labelledby="home-title"><p class="eyebrow">Linked Open Data Explorer</p><h1 id="home-title">Khám phá Di sản Văn hóa Việt Nam</h1><p>Trải nghiệm cùng một RDF graph qua tìm kiếm, provenance, Turtle, JSON-LD và competency questions — không cần viết SPARQL.</p><div class="actions"><a class="button" href="#/search">Bắt đầu tìm kiếm</a><a class="button secondary" href="#/queries">Xem competency questions</a></div></section><section class="grid" aria-label="Thống kê dataset"><div class="card"><div class="metric">${esc(stats.total_entities)}</div><div>Entities trong verified registry snapshot</div></div><div class="card"><div class="metric">${esc(stats.verified_external_links)}</div><div>Verified identity statements</div></div><div class="card"><div class="metric">${esc(stats.classes?.length || 0)}</div><div>Ontology types có dữ liệu</div></div><div class="card"><div class="metric">${esc(stats.categories?.length || 0)}</div><div>Registry categories</div></div></section><section class="card semantic-access" aria-labelledby="access-title"><h2 id="access-title">Semantic Web access</h2><p>Dataset: <code>${esc(stats['@id'])}</code></p><p><a href="/docs">API documentation</a> · <a id="home-sparql" href="${esc(safeHref(config.sparql_endpoint))}" target="_blank" rel="noopener">Public SPARQL endpoint</a> · <a href="${esc(safeHref(stats['@id']))}" target="_blank" rel="noopener">Dataset URI</a></p></section>`, { focus: true });
    document.getElementById('home-sparql').href = safeHref(config.sparql_endpoint);
  } catch (error) { errorView(error, home); }
}

function searchFormMarkup(state, stats) {
  const availableClasses = Array.isArray(stats.classes) ? new Set(stats.classes.map((item) => shortUri(item['@id'])).filter(Boolean)) : null;
  const typeOptions = entityTypeGroups.map(([group, types]) => {
    const options = types.filter((type) => !availableClasses || availableClasses.has(type)).map((type) => `<option value="${type}"${state.entity_type === type ? ' selected' : ''}>${esc(entityTypeLabels[type])}</option>`).join('');
    return options ? `<optgroup label="${esc(group)}">${options}</optgroup>` : '';
  }).join('');
  const semanticOptions = Object.entries(semanticTypeLabels).filter(([type]) => !availableClasses || availableClasses.has(type)).map(([type, label]) => `<option value="${type}"${state.semantic_type === type ? ' selected' : ''}>${esc(label)}</option>`).join('');
  const availableRelations = Array.isArray(stats.relations) ? new Set(stats.relations.map((item) => shortUri(item['@id'])).filter(Boolean)) : null;
  const relationOptions = Object.entries(relationLabels).filter(([relation]) => !availableRelations || availableRelations.has(relation)).map(([relation, label]) => `<option value="${relation}"${state.relation === relation ? ' selected' : ''}>${esc(label)}</option>`).join('');
  const categoryValues = [...new Set((stats.categories || []).map((item) => shortUri(item['@id'] || item)).filter(Boolean))];
  if (state.registry_category && !categoryValues.includes(state.registry_category)) categoryValues.push(state.registry_category);
  const categoryOptions = categoryValues.map((value) => `<option value="${esc(value)}"${state.registry_category === value ? ' selected' : ''}>${esc(categoryLabel(value))}</option>`).join('');
  return `<section aria-labelledby="search-title"><h1 id="search-title">Tìm kiếm di sản</h1><p id="search-help">Kết hợp từ khóa với loại thực thể, phân loại ngữ nghĩa và các quan hệ trong knowledge graph.</p><form id="search-form" aria-describedby="search-help"><div class="field"><label for="search-q">Từ khóa</label><input id="search-q" name="q" placeholder="Ví dụ: Huế, Hội An" value="${esc(state.q || '')}"></div><div class="field"><label for="search-type">Loại thực thể</label><select id="search-type" name="entity_type"><option value="">Tất cả loại thực thể</option>${typeOptions}</select></div><div class="field"><label for="search-semantic-type">Phân loại ngữ nghĩa</label><select id="search-semantic-type" name="semantic_type"><option value="">Tất cả phân loại</option>${semanticOptions}</select></div><div class="field"><label for="search-location">Địa điểm</label><input id="search-location" name="location" placeholder="Hà Nội" value="${esc(state.location || '')}"></div><div class="field"><label for="search-category">Danh mục trong nguồn đăng ký</label><select id="search-category" name="registry_category"><option value="">Tất cả danh mục</option>${categoryOptions}</select></div><div class="field"><label for="search-relation">Quan hệ</label><select id="search-relation" name="relation"><option value="">Tất cả quan hệ</option>${relationOptions}</select></div><div class="field"><label for="search-year">Năm</label><input id="search-year" name="year" inputmode="numeric" pattern="[0-9]{1,4}" placeholder="1999" value="${esc(state.year || '')}"></div><button type="submit">Tìm kiếm</button></form><div id="results" class="results" aria-live="polite" aria-atomic="false"></div></section>`;
}
function defaultSparqlQuery() {
  return `PREFIX vh: <${config.canonical_base}/ontology/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?site ?label
WHERE {
  ?site a vh:HeritageSite ;
        rdfs:label ?label .
  FILTER(LANG(?label) = "vi")
}
LIMIT 20`;
}

async function search() {
  loading('Đang chuẩn bị bộ lọc tìm kiếm…');
  let stats = { categories: [], classes: null, relations: null };
  try { stats = await api('/api/stats'); } catch (_) { /* Search remains usable without filter metadata. */ }
  render(searchFormMarkup(searchState(), stats), { focus: true });
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
      results.innerHTML = `<div class="result-summary" role="status"><strong>${esc(data.total)}</strong> kết quả · trang ${esc(data.page)}</div>${items.length ? `<div class="result-list">${items.map((item) => { const types = entityTypeBadges(item['@type']); const itemCategories = categoryBadges(item.category); const reasons = (item.match_reasons || []).map((reason) => { let label = ''; if (reason.filter === 'keyword') label = 'Khớp từ khóa'; else if (reason.filter === 'entity_type') label = `Loại thực thể: ${entityTypeLabels[reason.value] || reason.value}`; else if (reason.filter === 'semantic_type') label = `Phân loại: ${semanticTypeLabels[reason.value] || reason.value}`; else if (reason.filter === 'relation') label = relationLabels[reason.value] || reason.value; else if (reason.filter === 'registry_category') label = `Danh mục: ${categoryLabel(reason.value)}`; else if (reason.filter === 'location') label = `Địa điểm: ${reason.value}`; else if (reason.filter === 'year') label = `Năm: ${reason.value}`; return label ? `<li>${esc(label)}${reason.inferred ? ' <span class="inferred-badge">Suy luận</span>' : ''}</li>` : ''; }).join(''); return `<article class="card"><h2><a href="#/entity/${encodeURIComponent(shortUri(item['@id']))}">${esc(valueOf(item.label) || item['@id'])}</a></h2>${types ? `<p class="result-taxonomy"><span class="taxonomy-label">Loại:</span> ${types}</p>` : ''}${itemCategories ? `<p class="result-taxonomy"><span class="taxonomy-label">Danh mục:</span> ${itemCategories}</p>` : ''}<p>${esc(item.location || '')} ${esc(item.year || '')}</p>${reasons ? `<section class="match-reasons" aria-label="Vì sao kết quả khớp"><h3>Vì sao khớp</h3><ul>${reasons}</ul></section>` : ''}<p class="uri">${uriLink(item['@id'], 'canonical')}</p></article>`; }).join('')}</div>` : '<p class="empty" role="status">Không có kết quả. Hãy thử từ khóa ngắn hơn hoặc bỏ bớt bộ lọc.</p>'}${data.page > 1 || data.has_next ? `<nav class="pagination" aria-label="Phân trang">${data.page > 1 ? '<button id="previous" type="button">← Trang trước</button>' : ''}${data.has_next ? '<button id="next" type="button">Trang sau →</button>' : ''}</nav>` : ''}`;
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
    render(`<section aria-labelledby="queries-title"><h1 id="queries-title">Câu hỏi năng lực</h1><p>Mười competency questions minh họa cách graph trả lời các câu hỏi về di sản bằng truy vấn SPARQL read-only đã được cho phép.</p><div class="result-list">${data.items.map((query) => `<article class="card query-card"><p class="query-id">${esc(query.id)}</p><h2>${esc(query.display_title)}</h2><p class="query-question">${esc(query.question)}</p><p class="semantic-note">${esc(query.semantic_note)}</p><div class="query-actions"><button type="button" data-query="${esc(query.id)}">Chạy truy vấn</button><button type="button" class="secondary-control" data-sparql-toggle="${esc(query.id)}" aria-expanded="false" aria-controls="sparql-${esc(query.id)}">Xem SPARQL</button></div><div id="sparql-${esc(query.id)}" class="sparql-panel" hidden><pre tabindex="0"><code>${esc(query.sparql)}</code></pre></div><details class="technical-details"><summary>Chi tiết kỹ thuật</summary><p>Truy vấn read-only trong allowlist.</p><p class="hash">SHA-256: <code>${esc(query.sha256)}</code></p></details><div id="output-${esc(query.id)}" class="query-output" aria-live="polite"></div></article>`).join('')}</div></section>`, { focus: true });
    document.querySelectorAll('[data-sparql-toggle]').forEach((button) => button.addEventListener('click', () => {
      const panel = document.getElementById(`sparql-${button.dataset.sparqlToggle}`);
      const expanded = button.getAttribute('aria-expanded') === 'true';
      button.setAttribute('aria-expanded', String(!expanded));
      button.textContent = expanded ? 'Xem SPARQL' : 'Ẩn SPARQL';
      panel.hidden = expanded;
    }));
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

function sparqlValue(binding) {
  if (!binding) return '<span class="muted">—</span>';
  const value = binding.value || '';
  if (binding.type === 'uri') {
    const resourcePrefix = `${config.canonical_base}/resource/`;
    if (value.startsWith(resourcePrefix)) {
      const entityId = value.slice(resourcePrefix.length);
      if (/^[a-z0-9][a-z0-9-]*$/.test(entityId)) return `<a href="#/entity/${encodeURIComponent(entityId)}" title="${esc(value)}">${esc(shortUri(value))}</a>`;
    }
    return `<a href="${esc(safeHref(value))}" target="_blank" rel="noopener" title="${esc(value)}">${esc(shortUri(value))}</a>`;
  }
  if (binding.type === 'bnode') return `<span title="Blank node">_:${esc(value)}</span>`;
  const detail = binding['xml:lang'] ? `@${binding['xml:lang']}` : binding.datatype ? shortUri(binding.datatype) : '';
  return `${esc(value)}${detail ? ` <span class="term-meta">${esc(detail)}</span>` : ''}`;
}

function sparqlResultMarkup(data) {
  const timing = `<span>${esc(data.elapsed_ms)} ms</span>`;
  if (data.query_form === 'ASK') {
    return `<div class="result-summary"><strong>Kết quả: ${data.results?.boolean === true ? 'true' : 'false'}</strong> · ${timing}</div>`;
  }
  if (data.query_form === 'CONSTRUCT' || data.query_form === 'DESCRIBE') {
    return `<div class="result-summary">Kết quả RDF · ${timing}</div><pre tabindex="0"><code>${esc(data.rdf || '')}</code></pre>`;
  }
  const variables = data.results?.head?.vars || [];
  const rows = data.results?.results?.bindings || [];
  const table = rows.length
    ? `<div class="table-scroll" tabindex="0"><table><thead><tr>${variables.map((name) => `<th scope="col">?${esc(name)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${variables.map((name) => `<td>${sparqlValue(row[name])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`
    : '<p class="empty">Truy vấn không trả về dòng kết quả nào.</p>';
  return `<div class="result-summary"><strong>${esc(rows.length)}</strong> kết quả · ${timing}</div>${table}`;
}

function sparql() {
  const example = defaultSparqlQuery();
  render(`<section aria-labelledby="sparql-title"><h1 id="sparql-title">SPARQL Query</h1><p id="sparql-help">Thực hiện truy vấn SPARQL chỉ đọc trên knowledge graph VietHeritageLOD.</p><form id="sparql-form" class="sparql-form" aria-describedby="sparql-help"><label for="sparql-editor">Truy vấn</label><textarea id="sparql-editor" name="query" spellcheck="false">${esc(example)}</textarea><div class="query-actions"><button id="run-sparql" type="submit">Chạy truy vấn</button><button id="reset-sparql" class="secondary-control" type="button">Khôi phục ví dụ</button></div></form><div id="sparql-output" class="query-output" aria-live="polite"></div></section>`, { focus: true });
  const form = document.getElementById('sparql-form');
  const editor = document.getElementById('sparql-editor');
  const runButton = document.getElementById('run-sparql');
  const output = document.getElementById('sparql-output');
  document.getElementById('reset-sparql').addEventListener('click', () => { editor.value = defaultSparqlQuery(); editor.focus(); });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (runButton.disabled) return;
    runButton.disabled = true;
    output.setAttribute('aria-busy', 'true');
    output.innerHTML = '<p class="status" role="status">Đang chạy truy vấn SPARQL…</p>';
    try {
      const data = await api('/api/sparql', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: editor.value }) });
      output.innerHTML = sparqlResultMarkup(data);
    } catch (error) {
      output.innerHTML = `<div class="error" role="alert"><p>${esc(error.message)}</p></div>`;
    } finally {
      runButton.disabled = false;
      output.setAttribute('aria-busy', 'false');
    }
  });
}

function updateNavigation(hash) {
  const route = hash === '/' ? '#/' : `#${hash.split('?')[0]}`;
  document.querySelectorAll('nav a[href^="#/"]').forEach((link) => {
    const active = link.getAttribute('href') === route;
    link.classList.toggle('nav-link-active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

function route() {
  const hash = location.hash.slice(1) || '/';
  updateNavigation(hash);
  if (hash === '/') return home();
  if (hash === '/search') return search();
  if (hash === '/queries') return queries();
  if (hash === '/sparql') return sparql();
  if (hash.startsWith('/entity/')) return entity(decodeURIComponent(hash.slice('/entity/'.length)));
  return home();
}
window.addEventListener('hashchange', route);
loadConfig().finally(route);
